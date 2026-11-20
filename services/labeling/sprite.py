"""Render a labeling clip as one JPEG sprite sheet (grid of square tiles), faces blurred.

A sprite sheet plays in any browser from a local file, with no video codec needed.
"""
from __future__ import annotations

import math
from typing import Sequence

import cv2
import numpy as np

HEAD_KEYPOINTS = (0, 1, 2, 3, 4)  # COCO: nose, eyes, ears
_MIN_KP_CONF = 0.3


def head_box(bbox: tuple[float, float, float, float],
             keypoints: Sequence[tuple[float, float, float]] | None) -> tuple[float, float, float, float]:
    """Normalized head region from face keypoints; falls back to the top of the person box."""
    x1, y1, x2, y2 = bbox
    height = max(y2 - y1, 1e-6)
    if keypoints and len(keypoints) > max(HEAD_KEYPOINTS):
        pts = [(kp[0], kp[1]) for i, kp in enumerate(keypoints)
               if i in HEAD_KEYPOINTS and kp[2] >= _MIN_KP_CONF]
        if len(pts) >= 2:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            side = max(max(xs) - min(xs), max(ys) - min(ys), height * 0.12) * 1.8
            return (cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)
    return (x1, y1, x2, y1 + height * 0.22)


def blur_region(frame: np.ndarray, box: tuple[float, float, float, float]) -> None:
    """Heavily blur a normalized box in place."""
    h, w = frame.shape[:2]
    x1, y1 = max(0, int(box[0] * w)), max(0, int(box[1] * h))
    x2, y2 = min(w, int(math.ceil(box[2] * w))), min(h, int(math.ceil(box[3] * h)))
    if x2 - x1 < 2 or y2 - y1 < 2:
        return
    roi = frame[y1:y2, x1:x2]
    k = max(3, (min(roi.shape[:2]) // 2) | 1)
    frame[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (k, k), 0)
    frame[y1:y2, x1:x2] = cv2.GaussianBlur(frame[y1:y2, x1:x2], (k, k), 0)


def render_tile(frame: np.ndarray, target: tuple[float, float, float, float],
                head_boxes: Sequence[tuple[float, float, float, float]], tile: int = 224,
                context: float = 1.5) -> np.ndarray:
    """Crop a square around ``target`` (with context), blur every head, outline the target."""
    work = frame.copy()
    for box in head_boxes:
        blur_region(work, box)
    h, w = work.shape[:2]
    cx, cy = (target[0] + target[2]) / 2 * w, (target[1] + target[3]) / 2 * h
    side = max((target[2] - target[0]) * w, (target[3] - target[1]) * h) * context
    side = max(side, 32.0)
    x1, y1 = int(round(cx - side / 2)), int(round(cy - side / 2))
    size = int(round(side))
    canvas = np.full((size, size, 3), 40, dtype=np.uint8)
    sx1, sy1 = max(0, x1), max(0, y1)
    sx2, sy2 = min(w, x1 + size), min(h, y1 + size)
    if sx2 > sx1 and sy2 > sy1:
        canvas[sy1 - y1:sy2 - y1, sx1 - x1:sx2 - x1] = work[sy1:sy2, sx1:sx2]
    scale = tile / size
    out = cv2.resize(canvas, (tile, tile), interpolation=cv2.INTER_AREA)
    ox1, oy1 = int((target[0] * w - x1) * scale), int((target[1] * h - y1) * scale)
    ox2, oy2 = int((target[2] * w - x1) * scale), int((target[3] * h - y1) * scale)
    cv2.rectangle(out, (ox1, oy1), (ox2, oy2), (255, 200, 0), 2)
    return out


def build_sprite(tiles: Sequence[np.ndarray], cols: int = 6, quality: int = 72) -> tuple[bytes, int, int]:
    """Arrange tiles in a grid and return (jpeg_bytes, cols, rows)."""
    if not tiles:
        raise ValueError("no tiles")
    tile_h, tile_w = tiles[0].shape[:2]
    rows = math.ceil(len(tiles) / cols)
    sheet = np.full((rows * tile_h, cols * tile_w, 3), 40, dtype=np.uint8)
    for i, tile in enumerate(tiles):
        r, c = divmod(i, cols)
        sheet[r * tile_h:(r + 1) * tile_h, c * tile_w:(c + 1) * tile_w] = tile
    ok, buf = cv2.imencode(".jpg", sheet, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes(), cols, rows
