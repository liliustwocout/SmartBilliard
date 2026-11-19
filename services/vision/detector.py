"""YOLOv8 Person, Pose, and Cue Detectors via OpenCV DNN (CUDA FP16 / CPU).

Supports:
- YOLOv8 Detect (person class 0, output shape (1, 84, 8400))
- YOLOv8 Pose (person + 17 COCO keypoints, output shape (1, 56, 8400))
- YOLOv8 Cue Detect (custom single-class cue model, output shape (1, 5, 8400))
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from services.vision.contracts import Detection, Keypoint

logger = logging.getLogger("smartbilliard.vision.detector")

_POSE_CHANNELS = 56  # 4 bbox + 1 person conf + 17 * 3 keypoints
_NUM_COCO_KEYPOINTS = 17
_LEFT_ANKLE_IDX = 15
_RIGHT_ANKLE_IDX = 16


@dataclass(frozen=True)
class PersonDetection:
    bbox: tuple[float, float, float, float]  # (x1, y1, x2, y2) in [0..1]
    confidence: float
    foot_anchor: tuple[float, float]          # (x_foot, y_foot) in [0..1]
    class_id: int = 0
    track_id: int | None = None
    keypoints: tuple[Keypoint, ...] | None = None


def _configure_dnn_backend(net: cv2.dnn.Net, prefer_gpu: bool = True) -> str:
    """Configure CUDA FP16 backend when supported by OpenCV, otherwise CPU."""
    if prefer_gpu:
        try:
            cuda_count = cv2.cuda.getCudaEnabledDeviceCount() if hasattr(cv2, "cuda") else 0
        except Exception:
            cuda_count = 0
        if cuda_count > 0:
            try:
                net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA_FP16)
                return "CUDA_FP16"
            except Exception as err:
                logger.warning("CUDA FP16 backend unavailable (%s); falling back to CPU.", err)

    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    return "CPU"


def _load_onnx_net(model_path: Path, prefer_gpu: bool = True) -> tuple[cv2.dnn.Net | None, str]:
    """Load an ONNX network if the file exists, returning (net, backend_label)."""
    if not model_path.exists():
        logger.warning("Model file not found at %s. Detector running in offline fallback mode.", model_path)
        return None, "OFFLINE"
    try:
        net = cv2.dnn.readNetFromONNX(str(model_path))
        backend = _configure_dnn_backend(net, prefer_gpu=prefer_gpu)
        logger.info("Loaded YOLO model from %s (%s)", model_path, backend)
        return net, backend
    except Exception as err:
        logger.error("Failed to load ONNX model %s: %s", model_path, err)
        return None, "OFFLINE"


def _decode_box_xywh(
    cx: float,
    cy: float,
    w: float,
    h: float,
    pad_w: int,
    pad_h: int,
    ratio: float,
    orig_w: int,
    orig_h: int,
) -> list[int]:
    """Convert letterboxed [cx, cy, w, h] into clipped pixel [x, y, w, h]."""
    x1 = (cx - w / 2 - pad_w) / ratio
    y1 = (cy - h / 2 - pad_h) / ratio
    box_w = w / ratio
    box_h = h / ratio

    x1 = max(0.0, min(float(orig_w), x1))
    y1 = max(0.0, min(float(orig_h), y1))
    box_w = max(1.0, min(float(orig_w - x1), box_w))
    box_h = max(1.0, min(float(orig_h - y1), box_h))
    return [int(x1), int(y1), int(box_w), int(box_h)]


def _normalize_bbox(bx: int, by: int, bw: int, bh: int, orig_w: int, orig_h: int) -> tuple[float, float, float, float]:
    return (
        max(0.0, min(1.0, bx / orig_w)),
        max(0.0, min(1.0, by / orig_h)),
        max(0.0, min(1.0, (bx + bw) / orig_w)),
        max(0.0, min(1.0, (by + bh) / orig_h)),
    )


def _decode_pose_keypoints(
    raw_kps: np.ndarray,
    pad_w: int,
    pad_h: int,
    ratio: float,
    orig_w: int,
    orig_h: int,
) -> tuple[Keypoint, ...]:
    """Decode 17x3 flat YOLOv8-pose keypoints into normalized (x, y, conf) tuples."""
    kps: list[Keypoint] = []
    for idx in range(_NUM_COCO_KEYPOINTS):
        base = idx * 3
        kx = max(0.0, min(1.0, ((float(raw_kps[base]) - pad_w) / ratio) / orig_w))
        ky = max(0.0, min(1.0, ((float(raw_kps[base + 1]) - pad_h) / ratio) / orig_h))
        kconf = max(0.0, min(1.0, float(raw_kps[base + 2])))
        kps.append((kx, ky, kconf))
    return tuple(kps)


def _foot_anchor_from_result(
    bbox: tuple[float, float, float, float],
    keypoints: tuple[Keypoint, ...] | None,
    min_ankle_conf: float = 0.35,
) -> tuple[float, float]:
    """Prefer ankle keypoints when confident; fall back to bottom-center of bbox."""
    if keypoints is not None and len(keypoints) > _RIGHT_ANKLE_IDX:
        visible = [
            keypoints[idx]
            for idx in (_LEFT_ANKLE_IDX, _RIGHT_ANKLE_IDX)
            if keypoints[idx][2] >= min_ankle_conf
        ]
        if visible:
            fx = sum(pt[0] for pt in visible) / len(visible)
            fy = sum(pt[1] for pt in visible) / len(visible)
            return (max(0.0, min(1.0, fx)), max(0.0, min(1.0, fy)))

    x1, _, x2, y2 = bbox
    return (max(0.0, min(1.0, (x1 + x2) / 2.0)), y2)


def _forward_with_cpu_fallback(
    net: cv2.dnn.Net,
    blob: np.ndarray,
    backend_label: str,
) -> tuple[np.ndarray, str]:
    """Run forward pass and gracefully fall back to CPU if CUDA fails at runtime."""
    net.setInput(blob)
    try:
        return net.forward(), backend_label
    except cv2.error as err:
        if backend_label != "CPU":
            logger.warning("GPU inference failed (%s); switching detector to CPU.", err)
            net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            net.setInput(blob)
            return net.forward(), "CPU"
        raise


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
    """YOLOv8 person/pose detector using OpenCV DNN (GPU FP16 when available, else CPU)."""

    def __init__(
        self,
        model_path: str | Path = "models/yolov8n.onnx",
        *,
        conf_threshold: float = 0.45,
        nms_threshold: float = 0.45,
        input_size: tuple[int, int] = (640, 640),
        prefer_gpu: bool = True,
    ) -> None:
        self.model_path = Path(model_path).resolve()
        self.conf_threshold = conf_threshold
        self.nms_threshold = nms_threshold
        self.input_size = input_size
        self.prefer_gpu = prefer_gpu
        self._net: cv2.dnn.Net | None = None
        self.backend_label: str = "OFFLINE"
        self._load_net()

    def _load_net(self) -> None:
        self._net, self.backend_label = _load_onnx_net(self.model_path, prefer_gpu=self.prefer_gpu)

    @property
    def is_ready(self) -> bool:
        return self._net is not None

    def detect(self, frame: np.ndarray) -> list[PersonDetection]:
        """Run person/pose detection on a BGR frame and return normalized PersonDetection list."""
        if self._net is None or frame is None or frame.size == 0:
            return []

        orig_h, orig_w = frame.shape[:2]
        padded_img, ratio, (pad_w, pad_h) = letterbox(frame, self.input_size)

        blob = cv2.dnn.blobFromImage(
            padded_img, scalefactor=1.0 / 255.0, size=self.input_size, swapRB=True, crop=False
        )
        preds, self.backend_label = _forward_with_cpu_fallback(self._net, blob, self.backend_label)

        # Transpose (1, C, 8400) -> (8400, C)
        output = np.squeeze(preds, axis=0).T
        if output.ndim != 2 or output.shape[1] < 5:
            return []

        is_pose = output.shape[1] == _POSE_CHANNELS
        person_scores = output[:, 4]
        mask = person_scores >= self.conf_threshold
        filtered_preds = output[mask]
        filtered_scores = person_scores[mask]

        if len(filtered_preds) == 0:
            return []

        boxes: list[list[int]] = []
        confidences: list[float] = []
        raw_rows: list[np.ndarray] = []

        for pred, score in zip(filtered_preds, filtered_scores):
            cx, cy, w, h = pred[:4]
            boxes.append(_decode_box_xywh(cx, cy, w, h, pad_w, pad_h, ratio, orig_w, orig_h))
            confidences.append(float(score))
            raw_rows.append(pred)

        indices = cv2.dnn.NMSBoxes(boxes, confidences, self.conf_threshold, self.nms_threshold)
        if len(indices) == 0:
            return []

        results: list[PersonDetection] = []
        for i in indices.flatten():
            bx, by, bw, bh = boxes[i]
            bbox_norm = _normalize_bbox(bx, by, bw, bh, orig_w, orig_h)
            kps: tuple[Keypoint, ...] | None = None
            if is_pose:
                kps = _decode_pose_keypoints(raw_rows[i][5:], pad_w, pad_h, ratio, orig_w, orig_h)
            foot_anchor = _foot_anchor_from_result(bbox_norm, kps)

            results.append(
                PersonDetection(
                    bbox=bbox_norm,
                    confidence=confidences[i],
                    foot_anchor=foot_anchor,
                    class_id=0,
                    keypoints=kps,
                )
            )

        return results


class YoloPoseDetector(YoloPersonDetector):
    """YOLOv8-Pose detector extracting 17 COCO skeleton keypoints, with fallback to detect ONNX."""

    def __init__(
        self,
        model_path: str | Path = "models/yolov8n-pose.onnx",
        *,
        fallback_model_path: str | Path | None = "models/yolov8n.onnx",
        conf_threshold: float = 0.45,
        nms_threshold: float = 0.45,
        input_size: tuple[int, int] = (640, 640),
        prefer_gpu: bool = True,
    ) -> None:
        primary = Path(model_path)
        chosen = primary
        if not primary.exists() and fallback_model_path is not None:
            fallback = Path(fallback_model_path)
            if fallback.exists():
                logger.info("Pose model %s not found; falling back to %s", primary, fallback)
                chosen = fallback
        super().__init__(
            chosen,
            conf_threshold=conf_threshold,
            nms_threshold=nms_threshold,
            input_size=input_size,
            prefer_gpu=prefer_gpu,
        )


class YoloCueDetector:
    """YOLOv8 Cue Detector implementing the CueDetector protocol."""

    def __init__(
        self,
        model_path: str | Path = "models/yolov8n-cue.onnx",
        *,
        conf_threshold: float = 0.35,
        nms_threshold: float = 0.45,
        input_size: tuple[int, int] = (640, 640),
        prefer_gpu: bool = True,
    ) -> None:
        self.model_path = Path(model_path).resolve()
        self.conf_threshold = conf_threshold
        self.nms_threshold = nms_threshold
        self.input_size = input_size
        self.prefer_gpu = prefer_gpu
        self._net, self.backend_label = _load_onnx_net(self.model_path, prefer_gpu=prefer_gpu)

    @property
    def is_ready(self) -> bool:
        return self._net is not None

    @property
    def validated(self) -> bool:
        # Loading weights proves the graph can be read, not that cue detection
        # was validated on footage from this camera. Keep the cue gate closed.
        return False

    def detect(
        self,
        frame: object,
        *,
        camera_id: str = "cam-01",
        timestamp: float = 0.0,
    ) -> list[Detection]:
        """Detect billiard cues in a BGR frame and return normalized Detection objects."""
        if self._net is None or not isinstance(frame, np.ndarray) or frame.size == 0:
            return []

        orig_h, orig_w = frame.shape[:2]
        padded_img, ratio, (pad_w, pad_h) = letterbox(frame, self.input_size)
        blob = cv2.dnn.blobFromImage(
            padded_img, scalefactor=1.0 / 255.0, size=self.input_size, swapRB=True, crop=False
        )
        preds, self.backend_label = _forward_with_cpu_fallback(self._net, blob, self.backend_label)

        output = np.squeeze(preds, axis=0).T
        if output.ndim != 2 or output.shape[1] < 5:
            return []

        class_scores = output[:, 4:] if output.shape[1] > 5 else output[:, 4:5]
        cue_scores = np.max(class_scores, axis=1)
        mask = cue_scores >= self.conf_threshold
        filtered_preds = output[mask]
        filtered_scores = cue_scores[mask]

        if len(filtered_preds) == 0:
            return []

        boxes: list[list[int]] = []
        confidences: list[float] = []
        for pred, score in zip(filtered_preds, filtered_scores):
            cx, cy, w, h = pred[:4]
            boxes.append(_decode_box_xywh(cx, cy, w, h, pad_w, pad_h, ratio, orig_w, orig_h))
            confidences.append(float(score))

        indices = cv2.dnn.NMSBoxes(boxes, confidences, self.conf_threshold, self.nms_threshold)
        if len(indices) == 0:
            return []

        results: list[Detection] = []
        for i in indices.flatten():
            bx, by, bw, bh = boxes[i]
            bbox_norm = _normalize_bbox(bx, by, bw, bh, orig_w, orig_h)
            bw_norm = max(1e-6, bbox_norm[2] - bbox_norm[0])
            bh_norm = max(0.0, bbox_norm[3] - bbox_norm[1])
            angle_deg = round(math.degrees(math.atan2(bh_norm, bw_norm)), 2)

            results.append(
                Detection(
                    camera_id=camera_id,
                    timestamp=timestamp,
                    kind="cue",
                    bbox=bbox_norm,
                    confidence=confidences[i],
                    cue_angle_deg=angle_deg,
                )
            )
        return results
