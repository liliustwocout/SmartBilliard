"""Propose table cloth quadrilaterals and surrounding zones from a real frame.

Uses colour and contour geometry, not a learned table detector. Proposals never
save calibration or change sessions. Covered/occluded tables can be missed.
"""
from __future__ import annotations

import base64
from typing import Any

import cv2
import numpy as np

from services.vision.auto_roi_config import AutoRoiConfig
from services.vision.calibration import CalibrationConfig, TableZone


def _cloth_contours(mask: np.ndarray, config: AutoRoiConfig) -> list[np.ndarray]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cleaned: list[np.ndarray] = []
    for contour in contours:
        if not config.min_area_ratio <= cv2.contourArea(contour) / mask.size <= config.max_area_ratio:
            continue
        corners = cv2.boxPoints(cv2.minAreaRect(contour))
        edges = np.roll(corners, -1, axis=0) - corners
        lengths = np.linalg.norm(edges, axis=1)
        vector = edges[int(np.argmax(lengths))]
        length = max(3, int(max(lengths) * config.long_edge_opening_fraction))
        vector = vector / np.linalg.norm(vector) * (length / 2)
        extent = np.ceil(np.abs(vector)).astype(int) + 1
        kernel = np.zeros((2 * extent[1] + 1, 2 * extent[0] + 1), dtype=np.uint8)
        cv2.line(kernel, tuple(np.round(extent - vector).astype(int)),
                 tuple(np.round(extent + vector).astype(int)), 1, 1)
        component = np.zeros_like(mask)
        cv2.drawContours(component, [contour], -1, 255, -1)
        # Opening along the cloth's long edge removes narrow attached shirts/sleeves.
        opened = cv2.morphologyEx(cv2.bitwise_and(mask, component), cv2.MORPH_OPEN, kernel)
        parts, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cleaned.extend(parts)
    return cleaned


def find_table_surfaces(frame: np.ndarray, config: AutoRoiConfig) -> list[np.ndarray]:
    """Return convex four-point surfaces in normalized image coordinates."""
    if frame.ndim != 3 or frame.shape[2] != 3 or frame.size == 0:
        raise ValueError("Cần khung hình BGR hợp lệ để nhận diện bàn.")
    height, width = frame.shape[:2]
    scale = min(1.0, config.analysis_width / width)
    small = cv2.resize(frame, (max(1, round(width * scale)), max(1, round(height * scale))))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (config.hue_min, config.saturation_min, config.value_min),
                       (config.hue_max, 255, 255))
    kernel = np.ones((config.morphology_size, config.morphology_size), dtype=np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours = _cloth_contours(mask, config)
    surfaces: list[np.ndarray] = []
    image_area = mask.shape[0] * mask.shape[1]
    for contour in contours:
        area_ratio = cv2.contourArea(contour) / image_area
        if not config.min_area_ratio <= area_ratio <= config.max_area_ratio:
            continue
        hull = cv2.convexHull(contour)
        perimeter = cv2.arcLength(hull, True)
        quad = None
        for factor in (1.0, 1.5, 2.0):
            points = cv2.approxPolyDP(hull, config.polygon_epsilon * factor * perimeter, True).reshape(-1, 2)
            if len(points) == 4:
                quad = points
                break
            if len(points) < 4:
                break
        if quad is None or not cv2.isContourConvex(quad):
            continue
        vectors = np.roll(quad, -1, axis=0) - quad
        edges = np.linalg.norm(vectors, axis=1)
        direction = vectors[int(np.argmax(edges))]
        angle = abs(float(np.degrees(np.arctan2(direction[1], direction[0]))))
        if min(angle, 180 - angle) > config.max_long_edge_angle_degrees:
            continue
        side_a, side_b = edges[0] + edges[2], edges[1] + edges[3]
        aspect = max(side_a, side_b) / max(1.0, min(side_a, side_b))
        if not config.min_aspect_ratio <= aspect <= config.max_aspect_ratio:
            continue
        quad_mask = np.zeros_like(mask)
        cv2.fillConvexPoly(quad_mask, quad, 255)
        coverage = cv2.countNonZero(cv2.bitwise_and(mask, quad_mask)) / max(1, cv2.countNonZero(quad_mask))
        if coverage < config.min_cloth_coverage:
            continue
        points = quad.astype(np.float32) / np.array([mask.shape[1], mask.shape[0]], dtype=np.float32)
        # Keep adjacent corners in contour order, starting at the top-left corner.
        points = np.roll(points, -int(np.argmin(points.sum(axis=1))), axis=0)
        surfaces.append(points)
    # New IDs start at the closest visible table; existing IDs are matched by overlap.
    return sorted(surfaces, key=lambda points: (-float(points[:, 1].mean()), float(points[:, 0].mean())))


def estimate_standing_polygon(surface: np.ndarray, margin: float) -> list[list[float]]:
    """Expand in the table's projected plane and clip to the image boundary.

    This is an editable estimate: the cloth plane does not calibrate the floor.
    """
    edges = np.linalg.norm(np.roll(surface, -1, axis=0) - surface, axis=1)
    width, height = (2.0, 1.0) if edges[0] + edges[2] >= edges[1] + edges[3] else (1.0, 2.0)
    plane = np.array([[0, 0], [width, 0], [width, height], [0, height]], dtype=np.float32)
    transform = cv2.getPerspectiveTransform(plane, surface.astype(np.float32))
    expanded = np.array([[-margin, -margin], [width + margin, -margin],
                         [width + margin, height + margin], [-margin, height + margin]], dtype=np.float32)
    homogeneous = np.column_stack((expanded, np.ones(4))) @ transform.T
    divisors = homogeneous[:, 2]
    if np.any(np.abs(divisors) < 1e-6) or not (np.all(divisors > 0) or np.all(divisors < 0)):
        # Avoid a projection through the horizon; use a bounded centroid expansion.
        projected = surface.mean(axis=0) + (surface - surface.mean(axis=0)) * (1 + margin)
    else:
        projected = homogeneous[:, :2] / divisors[:, None]
    boundary = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
    _, clipped = cv2.intersectConvexConvex(cv2.convexHull(projected.astype(np.float32)), boundary)
    if clipped is None:
        raise ValueError("Không thể ước lượng vùng đứng trong khung hình.")
    return np.clip(clipped.reshape(-1, 2), 0, 1).astype(float).tolist()


def _polygon_iou(first: np.ndarray, second: list[list[float]]) -> float:
    left = cv2.convexHull(first.astype(np.float32))
    right = cv2.convexHull(np.array(second, dtype=np.float32))
    intersection, _ = cv2.intersectConvexConvex(left, right)
    union = cv2.contourArea(left) + cv2.contourArea(right) - intersection
    return float(intersection / union) if union > 0 else 0.0


def propose_table_zones(frame: np.ndarray, current: CalibrationConfig, table_count: int,
                        config: AutoRoiConfig) -> dict[str, Any]:
    """Produce an unsaved proposal, preserving unmatched zones and existing IDs."""
    surfaces = find_table_surfaces(frame, config)
    pairs = sorted(((_polygon_iou(surface, table.play_polygon), index, table.table_id)
                    for index, surface in enumerate(surfaces) for table in current.tables
                    if table.table_id <= table_count), reverse=True)
    assigned: dict[int, int] = {}
    matched_ids: set[int] = set()
    for overlap, index, table_id in pairs:
        if overlap >= config.match_iou and index not in assigned and table_id not in matched_ids:
            assigned[index] = table_id
            matched_ids.add(table_id)
    existing = {table.table_id: table for table in current.tables}
    available = [table_id for table_id in range(1, table_count + 1) if table_id not in existing]
    for index in range(len(surfaces)):
        if index not in assigned and available:
            assigned[index] = available.pop(0)
    tables = dict(existing)
    updated_ids: list[int] = []
    warnings = ["Vùng đứng là ước lượng theo hình ảnh. Kiểm tra lại vị trí chân người và vùng chồng lấn trước khi lưu."]
    for index, table_id in assigned.items():
        surface = surfaces[index]
        try:
            tables[table_id] = TableZone(
                table_id=table_id,
                enabled=existing[table_id].enabled if table_id in existing else True,
                play_polygon=surface.astype(float).tolist(),
                standing_polygon=estimate_standing_polygon(surface, config.standing_margin),
            )
            updated_ids.append(table_id)
        except ValueError:
            warnings.append(f"Chưa tạo được vùng hợp lệ cho Bàn {table_id:02d}; giữ nguyên ROI cũ nếu có.")
    retained = sorted(set(existing) - set(updated_ids))
    if retained:
        warnings.append("Giữ nguyên ROI chưa nhận diện lại của bàn: " + ", ".join(f"{item:02d}" for item in retained) + ".")
    if len(assigned) < len(surfaces):
        warnings.append("Một số mặt bàn chưa được gán số. Kiểm tra số bàn và ROI hiện có.")
    proposal = current.model_copy(update={"tables": [tables[key] for key in sorted(tables)]})
    ok, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise ValueError("Không thể tạo ảnh kiểm tra ROI.")
    message = (f"Đã đề xuất ROI cho {len(updated_ids)} bàn. Kiểm tra, chỉnh nếu cần rồi bấm Lưu cấu hình ROI."
               if updated_ids else "Chưa tìm thấy mặt bàn xanh lá/xanh dương đủ rõ. Thử khung hình ít che khuất hơn hoặc vẽ ROI thủ công.")
    return {
        "config": proposal.model_dump(),
        "overlaps": [item.model_dump() for item in proposal.detect_overlaps()],
        "method": "opencv_cloth_contours_v1",
        "requires_review": True,
        "detected_count": len(surfaces),
        "updated_table_ids": sorted(updated_ids),
        "warnings": warnings,
        "message": message,
        "preview_data_url": "data:image/jpeg;base64," + base64.b64encode(jpeg.tobytes()).decode("ascii"),
    }
