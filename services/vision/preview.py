"""Reference frame capture and synthetic preview generator for calibration (SB-10).

Isolates cv2 image drawing/encoding inside vision services.
"""
from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

from services.vision.adapters import create_video_source

logger = logging.getLogger("smartbilliard.vision.preview")


def generate_reference_billiard_frame(width: int = 960, height: int = 540) -> np.ndarray:
    """Generate a clean reference background of a billiard room for calibration preview."""
    # Dark floor background
    img = np.full((height, width, 3), fill_value=24, dtype=np.uint8)

    # Floor tile lines
    grid_size = 40
    for x in range(0, width, grid_size):
        cv2.line(img, (x, 0), (x, height), (32, 32, 36), 1)
    for y in range(0, height, grid_size):
        cv2.line(img, (0, y), (width, y), (32, 32, 36), 1)

    # Draw 4 default table areas with wooden borders and green felt
    tables = [
        (1, 0.12, 0.12, 0.35, 0.35),
        (2, 0.65, 0.12, 0.88, 0.35),
        (3, 0.12, 0.65, 0.35, 0.88),
        (4, 0.65, 0.65, 0.88, 0.88),
    ]

    for tid, x1_norm, y1_norm, x2_norm, y2_norm in tables:
        x1 = int(x1_norm * width)
        y1 = int(y1_norm * height)
        x2 = int(x2_norm * width)
        y2 = int(y2_norm * height)

        # Standing zone hint (subtle dash)
        sx1 = max(0, int((x1_norm - 0.08) * width))
        sy1 = max(0, int((y1_norm - 0.08) * height))
        sx2 = min(width - 1, int((x2_norm + 0.08) * width))
        sy2 = min(height - 1, int((y2_norm + 0.08) * height))
        cv2.rectangle(img, (sx1, sy1), (sx2, sy2), (45, 55, 65), 1)

        # Wooden cushion
        cv2.rectangle(img, (x1 - 6, y1 - 6), (x2 + 6, y2 + 6), (42, 60, 92), -1)
        # Green cloth
        cv2.rectangle(img, (x1, y1), (x2, y2), (50, 110, 40), -1)

        # Pockets
        pockets = [(x1, y1), ((x1 + x2) // 2, y1), (x2, y1), (x1, y2), ((x1 + x2) // 2, y2), (x2, y2)]
        for px, py in pockets:
            cv2.circle(img, (px, py), 5, (15, 15, 15), -1)

        # Table label
        label = f"BAN {tid:02}"
        cv2.putText(img, label, ((x1 + x2) // 2 - 32, (y1 + y2) // 2 + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 240, 220), 1)

    # Top overlay header
    cv2.rectangle(img, (0, 0), (width, 28), (15, 15, 18), -1)
    cv2.putText(img, "SMARTBILLIARD CAMERA CALIBRATION PREVIEW", (12, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

    return img


def get_preview_frame_jpeg(source: str | int = "0", camera_id: str = "cam-01") -> bytes:
    """Capture a live frame from VideoSource or return synthetic reference frame as JPEG."""
    frame: np.ndarray | None = None
    try:
        video_src = create_video_source(source, camera_id=camera_id, loop=False)
        ok, captured = video_src.read()
        if ok and captured is not None:
            frame = captured
        video_src.close()
    except Exception as err:
        logger.debug("Live preview capture not available (%s), using synthetic reference.", err)

    if frame is None:
        frame = generate_reference_billiard_frame()

    # Encode to JPEG
    encode_ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not encode_ok:
        raise RuntimeError("Failed to encode preview frame to JPEG")
    return buffer.tobytes()
