"""YOLOv8 Person Detector running on CPU via OpenCV DNN (SB-11).

Optimized for billiard hall tracking:
- Detects class 'person' (COCO class id 0).
- Calculates normalized bounding boxes [0..1].
- Extracts Foot Anchor (bottom-center point) for table assignment.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger("smartbilliard.vision.detector")


@dataclass(frozen=True)
class PersonDetection:
    bbox: tuple[float, float, float, float]  # (x1, y1, x2, y2) in [0..1]
    confidence: float
    foot_anchor: tuple[float, float]          # (x_foot, y_foot) in [0..1]
    class_id: int = 0
    track_id: int | None = None


def letterbox(
    img: np.ndarray,
    target_shape: tuple[int, int] = (640, 640),
    color: tuple[int, int, int] = (114, 114, 114),
) -> tuple[np.ndarray, float, tuple[int, int]]:
    """Resize image to target shape with aspect-ratio preserving padding."""
    shape = img.shape[:2]  # (h, w)
    target_w, target_h = target_shape

    # Scale ratio (new / old)
    r = min(target_w / shape[1], target_h / shape[0])
    new_unpad = (int(round(shape[1] * r)), int(round(shape[0] * r)))

    dw = target_w - new_unpad[0]
    dh = target_h - new_unpad[1]
    dw_pad = dw // 2
    dh_pad = dh // 2

    if shape[::-1] != new_unpad:
        img_resized = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
    else:
        img_resized = img

    top, bottom = dh_pad, dh - dh_pad
    left, right = dw_pad, dw - dw_pad
    img_padded = cv2.copyMakeBorder(
        img_resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color
    )
    return img_padded, r, (dw_pad, dh_pad)


class YoloPersonDetector:
    """YOLOv8 CPU detector using OpenCV DNN."""

    def __init__(
        self,
        model_path: str | Path = "models/yolov8n.onnx",
        *,
        conf_threshold: float = 0.45,
        nms_threshold: float = 0.45,
        input_size: tuple[int, int] = (640, 640),
    ) -> None:
        self.model_path = Path(model_path).resolve()
        self.conf_threshold = conf_threshold
        self.nms_threshold = nms_threshold
        self.input_size = input_size
        self._net: cv2.dnn.Net | None = None

        if self.model_path.exists():
            self._load_net()
        else:
            logger.warning("Model file not found at %s. Detector running in offline fallback mode.", self.model_path)

    def _load_net(self) -> None:
        try:
            self._net = cv2.dnn.readNetFromONNX(str(self.model_path))
            # Enable optimal CPU multi-threading
            self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            logger.info("Loaded YOLO model from %s", self.model_path)
        except Exception as err:
            logger.error("Failed to load ONNX model %s: %s", self.model_path, err)
            self._net = None

    @property
    def is_ready(self) -> bool:
        return self._net is not None

    def detect(self, frame: np.ndarray) -> list[PersonDetection]:
        """Run detection on a BGR image frame and return list of detected persons."""
        if self._net is None or frame is None or frame.size == 0:
            return []

        orig_h, orig_w = frame.shape[:2]
        padded_img, ratio, (pad_w, pad_h) = letterbox(frame, self.input_size)

        blob = cv2.dnn.blobFromImage(
            padded_img, scalefactor=1.0 / 255.0, size=self.input_size, swapRB=True, crop=False
        )
        self._net.setInput(blob)
        preds = self._net.forward()  # shape (1, 84, 8400)

        # Transpose to (8400, 84)
        output = np.squeeze(preds, axis=0).T

        boxes: list[list[int]] = []
        confidences: list[float] = []

        # YOLOv8 format: [cx, cy, w, h, class_0, class_1, ..., class_79]
        # Class 0 = person
        person_scores = output[:, 4]
        mask = person_scores >= self.conf_threshold

        filtered_preds = output[mask]
        filtered_scores = person_scores[mask]

        for pred, score in zip(filtered_preds, filtered_scores):
            cx, cy, w, h = pred[:4]

            # Convert from letterbox coordinates back to original frame
            x1 = (cx - w / 2 - pad_w) / ratio
            y1 = (cy - h / 2 - pad_h) / ratio
            box_w = w / ratio
            box_h = h / ratio

            # Clip to frame boundary
            x1 = max(0.0, min(float(orig_w), x1))
            y1 = max(0.0, min(float(orig_h), y1))
            box_w = max(1.0, min(float(orig_w - x1), box_w))
            box_h = max(1.0, min(float(orig_h - y1), box_h))

            boxes.append([int(x1), int(y1), int(box_w), int(box_h)])
            confidences.append(float(score))

        if not boxes:
            return []

        # Apply Non-Maximum Suppression
        indices = cv2.dnn.NMSBoxes(boxes, confidences, self.conf_threshold, self.nms_threshold)
        if len(indices) == 0:
            return []

        results: list[PersonDetection] = []
        for i in indices.flatten():
            bx, by, bw, bh = boxes[i]
            conf = confidences[i]

            x1_norm = max(0.0, min(1.0, bx / orig_w))
            y1_norm = max(0.0, min(1.0, by / orig_h))
            x2_norm = max(0.0, min(1.0, (bx + bw) / orig_w))
            y2_norm = max(0.0, min(1.0, (by + bh) / orig_h))

            # Foot anchor: center-x, bottom-y
            foot_x = max(0.0, min(1.0, (x1_norm + x2_norm) / 2.0))
            foot_y = y2_norm

            results.append(
                PersonDetection(
                    bbox=(x1_norm, y1_norm, x2_norm, y2_norm),
                    confidence=conf,
                    foot_anchor=(foot_x, foot_y),
                    class_id=0,
                )
            )

        return results
