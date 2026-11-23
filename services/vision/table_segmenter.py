"""YOLOv8-seg Table Felt Instance Segmenter via OpenCV DNN.

Provides On-Demand (Lazy-Loaded) Deep Learning segmentation for billiard table
play areas, with automatic fallback to Classical Computer Vision when model
weights are not present.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

from services.vision.auto_calibration import (
    _order_points_clockwise,
    auto_detect_table_zones as classical_detect_table_zones,
    generate_standing_polygon,
)
from services.vision.calibration import Point, Polygon, TableZone, is_self_intersecting, polygon_area

logger = logging.getLogger("smartbilliard.vision.table_segmenter")

DEFAULT_TABLE_SEG_MODEL = Path("models/yolov8n-table-seg.onnx")


def _signed_polygon_area_xy(pts: np.ndarray) -> float:
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _fit_quad_edge_collapse(contour: np.ndarray) -> np.ndarray:
    """Reduce a mask contour's convex hull to a minimum-area enclosing quadrilateral.

    Iteratively collapses the shortest/lowest-cost edge by extending its two adjacent
    edges outward to their intersection, reconstructing sharp corners on thin perspective
    tables where Douglas-Peucker approxPolyDP cuts off acute corners.
    """
    hull = cv2.convexHull(contour).reshape(-1, 2).astype(np.float64)
    if len(hull) < 4:
        return cv2.boxPoints(cv2.minAreaRect(contour)).astype(np.float32)
    if _signed_polygon_area_xy(hull) < 0:
        hull = hull[::-1].copy()

    # Light cleanup only for ~1px micro-collinear edges before outward edge collapse
    peri = cv2.arcLength(hull.astype(np.float32), True)
    hull = cv2.approxPolyDP(hull.astype(np.float32), 0.002 * peri, True).reshape(-1, 2).astype(np.float64)
    if len(hull) < 4:
        return cv2.boxPoints(cv2.minAreaRect(contour)).astype(np.float32)
    if len(hull) == 4:
        return hull.astype(np.float32)
    if _signed_polygon_area_xy(hull) < 0:
        hull = hull[::-1].copy()

    pts = list(hull)
    while len(pts) > 4:
        n = len(pts)
        best_idx = -1
        best_added_area = float("inf")
        best_inter: np.ndarray | None = None

        for i in range(n):
            p_prev = pts[(i - 1) % n]
            p_a = pts[i]
            p_b = pts[(i + 1) % n]
            p_next = pts[(i + 2) % n]

            d1 = p_a - p_prev
            d2 = p_b - p_next
            cross = float(d1[0] * (-d2[1]) - d1[1] * (-d2[0]))
            if abs(cross) < 1e-8:
                continue
            rhs = p_b - p_a
            t = float((rhs[0] * (-d2[1]) - rhs[1] * (-d2[0])) / cross)
            u = float((d1[0] * rhs[1] - d1[1] * rhs[0]) / cross)
            # Adjacent edges must meet outward past p_a and p_b rather than behind the edge
            if t < -1e-6 or u < -1e-6:
                continue
            inter = p_a + t * d1
            tri_area = 0.5 * abs(
                float((inter[0] - p_a[0]) * (p_b[1] - p_a[1]) - (inter[1] - p_a[1]) * (p_b[0] - p_a[0]))
            )
            if tri_area < best_added_area:
                best_added_area = tri_area
                best_idx = i
                best_inter = inter

        if best_idx == -1 or best_inter is None:
            drop_i = min(
                range(n),
                key=lambda i: abs(
                    float(
                        (pts[i][0] - pts[(i - 1) % n][0]) * (pts[(i + 1) % n][1] - pts[(i - 1) % n][1])
                        - (pts[i][1] - pts[(i - 1) % n][1]) * (pts[(i + 1) % n][0] - pts[(i - 1) % n][0])
                    )
                ),
            )
            pts.pop(drop_i)
        else:
            idx_b = (best_idx + 1) % n
            pts[best_idx] = best_inter
            pts.pop(idx_b)

    return np.array(pts, dtype=np.float32)


def _refine_quad_fitline(contour: np.ndarray, init_quad: np.ndarray) -> np.ndarray:
    """Refine the 4 sides of init_quad via robust Huber line fitting on middle edge points."""
    pts_cnt = contour.reshape(-1, 2).astype(np.float64)
    q = init_quad.astype(np.float64)
    side_pts: list[list[np.ndarray]] = [[] for _ in range(4)]

    for p in pts_cnt:
        best_s = -1
        best_d = float("inf")
        best_proj = 0.0
        for s in range(4):
            a, b = q[s], q[(s + 1) % 4]
            ab = b - a
            len2 = float(ab[0] * ab[0] + ab[1] * ab[1])
            if len2 < 1e-6:
                continue
            proj = float(((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / len2)
            proj_c = max(0.0, min(1.0, proj))
            closest = a + proj_c * ab
            d = math.hypot(float(p[0] - closest[0]), float(p[1] - closest[1]))
            if d < best_d:
                best_d = d
                best_s = s
                best_proj = proj
        # Ignore rounded corner regions (keep interior 12%..88% of each edge)
        if best_s >= 0 and 0.12 <= best_proj <= 0.88:
            side_pts[best_s].append(p)

    lines: list[tuple[float, float, float, float]] = []
    for s in range(4):
        a, b = q[s], q[(s + 1) % 4]
        if len(side_pts[s]) >= 4:
            arr = np.array(side_pts[s], dtype=np.float32)
            vx, vy, x0, y0 = cv2.fitLine(arr, cv2.DIST_HUBER, 0, 0.01, 0.01).flatten()
            lines.append((float(x0), float(y0), float(vx), float(vy)))
        else:
            ab = b - a
            seg_len = max(1e-6, math.hypot(float(ab[0]), float(ab[1])))
            lines.append((float(a[0]), float(a[1]), float(ab[0] / seg_len), float(ab[1] / seg_len)))

    refined: list[list[float]] = []
    for s in range(4):
        x1, y1, dx1, dy1 = lines[(s - 1) % 4]
        x2, y2, dx2, dy2 = lines[s]
        det = dx1 * (-dy2) - dy1 * (-dx2)
        if abs(det) < 1e-6:
            return init_quad
        t = ((x2 - x1) * (-dy2) - (y2 - y1) * (-dx2)) / det
        ix, iy = x1 + t * dx1, y1 + t * dy1
        edge_len = math.hypot(float(q[(s + 1) % 4][0] - q[s][0]), float(q[(s + 1) % 4][1] - q[s][1]))
        if math.hypot(ix - float(q[s][0]), iy - float(q[s][1])) > 0.25 * edge_len + 25.0:
            return init_quad
        refined.append([ix, iy])

    return np.array(refined, dtype=np.float32)


def fit_quad_from_contour(contour: np.ndarray) -> np.ndarray:
    """Fit a sharp 4-corner perspective quadrilateral to a binary table segmentation contour."""
    init_quad = _fit_quad_edge_collapse(contour)
    return _refine_quad_fitline(contour, init_quad)


class YoloTableSegmenter:
    """On-Demand YOLOv8-seg instance segmentation for billiard table detection."""

    def __init__(
        self,
        model_path: Path | str = DEFAULT_TABLE_SEG_MODEL,
        prefer_gpu: bool = False,
    ) -> None:
        self.model_path = Path(model_path)
        self.prefer_gpu = prefer_gpu

    @property
    def is_available(self) -> bool:
        """Check if trained ONNX weights exist on disk."""
        return self.model_path.is_file()

    def segment_tables(
        self,
        frame: np.ndarray,
        max_tables: int = 8,
        conf_threshold: float = 0.35,
        nms_threshold: float = 0.45,
        allow_fallback: bool = True,
    ) -> list[TableZone]:
        """Detect tables using YOLOv8-seg ONNX network with on-demand loading.

        Loads model, performs one-shot inference, extracts 4-corner perspective polygons,
        and releases network resources immediately to conserve memory.
        """
        if not self.is_available:
            logger.info("YOLOv8-seg weights not found at %s.", self.model_path)
            return classical_detect_table_zones(frame, max_tables=max_tables) if allow_fallback else []

        if frame is None or frame.size == 0:
            return []

        orig_h, orig_w = frame.shape[:2]

        try:
            # 1. Load network on-demand
            net = cv2.dnn.readNetFromONNX(str(self.model_path))
            net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

            # 2. Pre-process frame (Letterbox resize to 640x640)
            input_size = 640
            scale = min(input_size / orig_w, input_size / orig_h)
            nw, nh = int(orig_w * scale), int(orig_h * scale)
            pad_w = (input_size - nw) // 2
            pad_h = (input_size - nh) // 2

            resized = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
            canvas = np.full((input_size, input_size, 3), 114, dtype=np.uint8)
            canvas[pad_h:pad_h + nh, pad_w:pad_w + nw] = resized

            blob = cv2.dnn.blobFromImage(canvas, 1.0 / 255.0, (input_size, input_size), swapRB=True, crop=False)
            net.setInput(blob)

            # 3. Forward pass
            out_names = net.getUnconnectedOutLayersNames()
            outputs = net.forward(out_names)

            # Separate output0 (detections) and output1 (prototype masks)
            if len(outputs) >= 2:
                if len(outputs[0].shape) == 4:
                    proto = outputs[0]
                    preds = outputs[1]
                else:
                    preds = outputs[0]
                    proto = outputs[1]
            else:
                preds = outputs[0]
                proto = None

            # 4. Decode detections
            # preds shape: (1, 4 + num_classes + 32, 8400) -> transpose to (8400, C)
            preds = np.squeeze(preds, axis=0)
            if preds.shape[0] < preds.shape[1]:
                preds = preds.T

            boxes_xywh: list[list[int]] = []
            confidences: list[float] = []
            mask_coeffs: list[np.ndarray] = []

            num_mask_channels = 32
            # Class score is at index 4 (for single-class table_felt)
            for row in preds:
                conf = float(row[4])
                if conf < conf_threshold:
                    continue

                cx, cy, w, h = float(row[0]), float(row[1]), float(row[2]), float(row[3])
                # Unletterbox coordinates to original frame pixels
                x1 = (cx - w / 2.0 - pad_w) / scale
                y1 = (cy - h / 2.0 - pad_h) / scale
                box_w = w / scale
                box_h = h / scale

                x1_clamped = max(0, min(orig_w - 1, int(x1)))
                y1_clamped = max(0, min(orig_h - 1, int(y1)))
                bw_clamped = max(1, min(orig_w - x1_clamped, int(box_w)))
                bh_clamped = max(1, min(orig_h - y1_clamped, int(box_h)))

                boxes_xywh.append([x1_clamped, y1_clamped, bw_clamped, bh_clamped])
                confidences.append(conf)
                if row.shape[0] >= 5 + num_mask_channels:
                    mask_coeffs.append(row[5:5 + num_mask_channels])
                else:
                    mask_coeffs.append(np.array([]))

            if not boxes_xywh:
                return classical_detect_table_zones(frame, max_tables=max_tables) if allow_fallback else []

            indices = cv2.dnn.NMSBoxes(boxes_xywh, confidences, conf_threshold, nms_threshold)
            if len(indices) == 0:
                return classical_detect_table_zones(frame, max_tables=max_tables) if allow_fallback else []

            detected_polygons: list[tuple[float, float, Polygon]] = []

            # 5. Extract 4-corner polygons from masks or bounding boxes
            for idx in indices:
                i = int(idx)
                bx, by, bw, bh = boxes_xywh[i]
                coeffs = mask_coeffs[i]

                corner_pts: np.ndarray | None = None

                if proto is not None and coeffs.size == num_mask_channels:
                    # Matrix multiply coeffs with proto masks (160x160)
                    proto_c = proto[0]  # shape (32, 160, 160)
                    proto_flat = proto_c.reshape(num_mask_channels, -1)
                    raw_mask = coeffs @ proto_flat
                    sigmoid_mask = 1.0 / (1.0 + np.exp(-raw_mask))
                    mask_160 = sigmoid_mask.reshape(160, 160)

                    # Unletterbox mask via pixel-center resizing (matching Ultralytics align_corners=False)
                    mask_input = cv2.resize(
                        mask_160.astype(np.float32),
                        (input_size, input_size),
                        interpolation=cv2.INTER_LINEAR,
                    )
                    cropped_mask = mask_input[pad_h:pad_h + nh, pad_w:pad_w + nw]
                    full_mask = cv2.resize(cropped_mask, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)

                    # Restrict mask inside slightly padded bounding box so tight boxes don't clip corners
                    box_pad = 4
                    x0 = max(0, bx - box_pad)
                    y0 = max(0, by - box_pad)
                    x1 = min(orig_w, bx + bw + box_pad)
                    y1 = min(orig_h, by + bh + box_pad)
                    binary_mask = np.zeros((orig_h, orig_w), dtype=np.uint8)
                    binary_mask[y0:y1, x0:x1] = (full_mask[y0:y1, x0:x1] > 0.5).astype(np.uint8) * 255

                    contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
                    if contours:
                        largest_cnt = max(contours, key=cv2.contourArea)
                        if cv2.contourArea(largest_cnt) > (orig_w * orig_h * 0.002):
                            corner_pts = fit_quad_from_contour(largest_cnt)

                if corner_pts is None:
                    # Fallback to oriented bounding box
                    corner_pts = np.array([
                        [bx, by],
                        [bx + bw, by],
                        [bx + bw, by + bh],
                        [bx, by + bh],
                    ], dtype=np.float32)

                # Normalize to [0, 1]
                norm_pts = np.zeros_like(corner_pts, dtype=np.float32)
                norm_pts[:, 0] = np.clip(corner_pts[:, 0] / float(orig_w), 0.001, 0.999)
                norm_pts[:, 1] = np.clip(corner_pts[:, 1] / float(orig_h), 0.001, 0.999)

                ordered = _order_points_clockwise(norm_pts)
                if polygon_area(ordered) < 0.001 or is_self_intersecting(ordered):
                    continue
                cx = sum(p[0] for p in ordered) / 4.0
                cy = sum(p[1] for p in ordered) / 4.0
                detected_polygons.append((cy, cx, ordered))

            if not detected_polygons:
                return classical_detect_table_zones(frame, max_tables=max_tables) if allow_fallback else []

            # Sort in reading order (top-to-bottom, left-to-right)
            detected_polygons.sort(key=lambda item: (round(item[0], 1), item[1]))
            detected_polygons = detected_polygons[:max_tables]

            table_zones: list[TableZone] = []
            standing_list: list[Polygon] = []

            for _, _, play_poly in detected_polygons:
                standing_poly = generate_standing_polygon(play_poly, standing_list)
                try:
                    zone = TableZone(
                        table_id=len(table_zones) + 1,
                        enabled=True,
                        play_polygon=play_poly,
                        standing_polygon=standing_poly,
                    )
                except ValueError as err:
                    logger.warning("Skipping invalid YOLOv8-seg table polygon: %s", err)
                    continue
                standing_list.append(standing_poly)
                table_zones.append(zone)

            if not table_zones:
                return classical_detect_table_zones(frame, max_tables=max_tables) if allow_fallback else []

            logger.info("YOLOv8-seg successfully detected %d tables on-demand.", len(table_zones))
            return table_zones

        except Exception as err:
            logger.error("Error during YOLOv8-seg table detection: %s.", err)
            return classical_detect_table_zones(frame, max_tables=max_tables) if allow_fallback else []


def auto_detect_with_best_method(
    frame: np.ndarray,
    max_tables: int = 8,
    model_path: Path | str = DEFAULT_TABLE_SEG_MODEL,
) -> tuple[list[TableZone], str]:
    """Detect billiard table zones using YOLOv8-seg if available, otherwise Classical CV.

    Returns:
        tuple of (detected_tables, method_used)
    """
    segmenter = YoloTableSegmenter(model_path=model_path)
    if segmenter.is_available:
        zones = segmenter.segment_tables(frame, max_tables=max_tables, allow_fallback=False)
        if zones:
            return zones, "YOLOv8-seg (Deep Learning)"

    zones = classical_detect_table_zones(frame, max_tables=max_tables)
    if segmenter.is_available:
        return zones, "Classical Computer Vision (OpenCV — fallback từ YOLOv8-seg)"
    return zones, "Classical Computer Vision (OpenCV)"
