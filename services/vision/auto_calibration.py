"""Automatic Table ROI Detection & Unsaved Proposal Engine.

Combines YOLOv8-seg table felt inference (when ONNX weights exist) with local
OpenCV cloth/contour geometry (`AutoRoiConfig`), plus symmetric standing-zone
estimation and clockwise 4-corner ordering. Proposals never auto-save calibration.
"""
from __future__ import annotations

import base64
import math
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np

from services.vision.auto_roi_config import AutoRoiConfig
from services.vision.calibration import (
    CalibrationConfig,
    Point,
    Polygon,
    TableZone,
    is_self_intersecting,
    point_in_polygon,
    polygon_area,
    polygons_overlap,
)


def _order_points_clockwise(pts: np.ndarray) -> list[Point]:
    """Order 4 (x, y) points in clockwise order starting from top-left."""
    pts = np.asarray(pts, dtype=np.float32)
    if len(pts) != 4:
        return [(round(float(p[0]), 4), round(float(p[1]), 4)) for p in pts]

    cx = float(np.mean(pts[:, 0]))
    cy = float(np.mean(pts[:, 1]))
    angles = np.arctan2(pts[:, 1] - cy, pts[:, 0] - cx)
    sort_idx = np.argsort(angles)
    pts_sorted = pts[sort_idx]

    # Find the vertex closest to top-left (min sum x + y)
    sums = pts_sorted[:, 0] + pts_sorted[:, 1]
    tl_idx = int(np.argmin(sums))
    ordered = np.roll(pts_sorted, -tl_idx, axis=0)

    return [(round(float(p[0]), 4), round(float(p[1]), 4)) for p in ordered]


def generate_standing_polygon(
    play_polygon: Polygon,
    other_standing: Sequence[Polygon] = (),
    scale: float = 1.30,
) -> Polygon:
    """Generate an expanded standing polygon around play_polygon avoiding overlaps.

    Applies perspective-aware expansion (bottom edges near camera expand slightly more
    than top edges far from camera) and checks candidate scale buffers.
    """
    if len(play_polygon) < 3:
        return list(play_polygon)

    cx = sum(p[0] for p in play_polygon) / len(play_polygon)
    cy = sum(p[1] for p in play_polygon) / len(play_polygon)

    candidate_scales = [scale, 1.25, 1.20, 1.15, 1.10, 1.05]
    for s in candidate_scales:
        scaled: list[Point] = []
        for px, py in play_polygon:
            # Perspective compensation: points lower in the frame (larger y) expand slightly more
            persp_factor = 1.0 + (py - cy) * 0.15
            dx = (px - cx) * s * max(0.9, min(1.2, persp_factor))
            dy = (py - cy) * s * max(0.9, min(1.2, persp_factor))
            scaled.append(
                (
                    max(0.005, min(0.995, round(cx + dx, 4))),
                    max(0.005, min(0.995, round(cy + dy, 4))),
                )
            )

        # Check if overlapping with any existing standing polygon
        if not any(polygons_overlap(scaled, other) for other in other_standing):
            return scaled

    # Fallback to minimal expansion
    return [
        (
            max(0.005, min(0.995, round(cx + (px - cx) * 1.05, 4))),
            max(0.005, min(0.995, round(cy + (py - cy) * 1.05, 4))),
        )
        for px, py in play_polygon
    ]


def auto_detect_table_zones(
    frame: np.ndarray,
    max_tables: int = 8,
    min_area_ratio: float = 0.006,
    max_area_ratio: float = 0.70,
) -> list[TableZone]:
    """Automatically detect billiard tables in a BGR frame and return calibrated TableZone objects.

    Supports green, blue, red, and modern grey felt cloths, with morphological highlight bridging
    and convex-hull quadrilateral fitting.

    Args:
        frame: Input BGR image.
        max_tables: Maximum number of tables to detect (default: 8).
        min_area_ratio: Minimum ratio of contour area over frame area (default: 0.6%).
        max_area_ratio: Maximum ratio of contour area over frame area (default: 70%).

    Returns:
        List of detected and ordered TableZone configurations.
    """
    if frame is None or frame.size == 0:
        return []

    h, w = frame.shape[:2]
    total_area = float(w * h)
    min_area = total_area * min_area_ratio
    max_area = total_area * max_area_ratio

    # 1. Convert to HSV
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # 2. Threshold for typical billiard felt cloth colors:
    # Green felt (traditional tournament/pool cloth)
    mask_green = cv2.inRange(hsv, np.array([28, 25, 20]), np.array([92, 255, 255]))
    # Blue felt (Simonis tournament blue cloth)
    mask_blue = cv2.inRange(hsv, np.array([88, 30, 20]), np.array([138, 255, 255]))
    # Red/Burgundy felt (Carom/snooker burgundy cloth)
    mask_red1 = cv2.inRange(hsv, np.array([0, 35, 25]), np.array([14, 255, 255]))
    mask_red2 = cv2.inRange(hsv, np.array([166, 35, 25]), np.array([180, 255, 255]))
    mask_red = cv2.bitwise_or(mask_red1, mask_red2)

    cloth_colored = cv2.bitwise_or(mask_green, cv2.bitwise_or(mask_blue, mask_red))

    # Morphological kernels for bridging holes (balls, cues, lamp specular highlights)
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 17))
    open_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))

    def _extract_candidates_from_mask(mask: np.ndarray) -> list[tuple[float, float, Polygon]]:
        closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel)
        cleaned = cv2.morphologyEx(closed, cv2.MORPH_OPEN, open_kernel)
        contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        found: list[tuple[float, float, Polygon]] = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area or area > max_area:
                continue

            # Compute Convex Hull to smooth out pocket indentations and cue stick occlusions
            hull = cv2.convexHull(cnt)
            peri = cv2.arcLength(hull, True)
            pts_px: np.ndarray | None = None

            # Try multiple precision levels to find cleanest 4-point quadrilateral
            for eps_factor in [0.035, 0.045, 0.025, 0.055, 0.015, 0.07]:
                approx = cv2.approxPolyDP(hull, eps_factor * peri, True)
                if len(approx) == 4 and cv2.isContourConvex(approx):
                    pts_px = approx.reshape(4, 2)
                    break

            if pts_px is None:
                # Fall back to oriented minimum area bounding box
                rect = cv2.minAreaRect(hull)
                pts_px = cv2.boxPoints(rect)

            # Aspect ratio check (length / width between 1.05 and 3.6)
            d1 = math.hypot(pts_px[0][0] - pts_px[1][0], pts_px[0][1] - pts_px[1][1])
            d2 = math.hypot(pts_px[1][0] - pts_px[2][0], pts_px[1][1] - pts_px[2][1])
            if min(d1, d2) < 5:
                continue
            ratio = max(d1, d2) / max(1.0, min(d1, d2))
            if ratio < 1.05 or ratio > 3.6:
                continue

            # Convert to normalized coordinates [0.0, 1.0]
            norm_pts = np.zeros_like(pts_px, dtype=np.float32)
            norm_pts[:, 0] = np.clip(pts_px[:, 0] / float(w), 0.001, 0.999)
            norm_pts[:, 1] = np.clip(pts_px[:, 1] / float(h), 0.001, 0.999)

            ordered_poly = _order_points_clockwise(norm_pts)
            poly_area_val = polygon_area(ordered_poly)
            if poly_area_val < 0.001 or is_self_intersecting(ordered_poly):
                continue

            cx = sum(p[0] for p in ordered_poly) / 4.0
            cy = sum(p[1] for p in ordered_poly) / 4.0
            found.append((cy, cx, ordered_poly))

        return found

    # First attempt: colored felt masks (green, blue, red)
    candidates = _extract_candidates_from_mask(cloth_colored)

    # Second attempt fallback: if no colored table found, check for modern grey / neutral cloth
    if not candidates:
        mask_grey = cv2.inRange(hsv, np.array([0, 0, 45]), np.array([180, 42, 225]))
        candidates = _extract_candidates_from_mask(mask_grey)

    # 5. Sort candidates in reading order: top-to-bottom, left-to-right (grid layout)
    candidates.sort(key=lambda item: (round(item[0], 1), item[1]))

    # Limit to max_tables
    candidates = candidates[:max_tables]

    # 6. Build TableZone objects with non-overlapping standing zones
    table_zones: list[TableZone] = []
    standing_list: list[Polygon] = []

    for idx, (_, _, play_poly) in enumerate(candidates, start=1):
        standing_poly = generate_standing_polygon(play_poly, standing_list)
        standing_list.append(standing_poly)

        table_zones.append(
            TableZone(
                table_id=idx,
                enabled=True,
                play_polygon=play_poly,
                standing_polygon=standing_poly,
            )
        )

    return table_zones


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


def propose_table_zones(
    frame: np.ndarray,
    current: CalibrationConfig,
    table_count: int,
    config: AutoRoiConfig,
    model_path: Path | str | None = None,
) -> dict[str, Any]:
    """Produce an unsaved proposal, preserving unmatched zones and existing IDs."""
    if frame is None or frame.ndim != 3 or frame.shape[2] != 3 or frame.size == 0:
        raise ValueError("Cần khung hình BGR hợp lệ để nhận diện bàn.")
    surfaces: list[np.ndarray] = []
    method = "opencv_cloth_contours_v1"
    if model_path is not None:
        from services.vision.table_segmenter import YoloTableSegmenter

        segmenter = YoloTableSegmenter(model_path=model_path)
        if segmenter.is_available:
            yolo_zones = segmenter.segment_tables(
                frame,
                max_tables=table_count,
                allow_fallback=False,
            )
            surfaces = [
                np.array(z.play_polygon, dtype=np.float32)
                for z in yolo_zones
                if len(z.play_polygon) == 4
            ]
            if surfaces:
                method = "YOLOv8-seg (Deep Learning)"
    if not surfaces:
        surfaces = find_table_surfaces(frame, config)
    pairs = sorted(
        (
            (_polygon_iou(surface, table.play_polygon), index, table.table_id)
            for index, surface in enumerate(surfaces)
            for table in current.tables
            if table.table_id <= table_count
        ),
        reverse=True,
    )
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
    if updated_ids:
        method_suffix = f" ({method})" if method == "YOLOv8-seg (Deep Learning)" else ""
        message = f"Đã đề xuất ROI cho {len(updated_ids)} bàn{method_suffix}. Kiểm tra, chỉnh nếu cần rồi bấm Lưu cấu hình ROI."
    else:
        message = "Chưa tìm thấy mặt bàn xanh lá/xanh dương đủ rõ. Thử khung hình ít che khuất hơn hoặc vẽ ROI thủ công."
    return {
        "config": proposal.model_dump(),
        "overlaps": [item.model_dump() for item in proposal.detect_overlaps()],
        "method": method,
        "requires_review": True,
        "detected_count": len(surfaces),
        "updated_table_ids": sorted(updated_ids),
        "warnings": warnings,
        "message": message,
        "preview_data_url": "data:image/jpeg;base64," + base64.b64encode(jpeg.tobytes()).decode("ascii"),
    }
