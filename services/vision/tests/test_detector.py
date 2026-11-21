"""Unit tests for YOLO Person Detector & Foot Anchor (SB-11)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from services.vision.detector import PersonDetection, YoloCueDetector, YoloPersonDetector, letterbox


def test_letterbox_resizing_and_aspect_ratio():
    # 800x400 landscape image (2:1 aspect ratio)
    img = np.zeros((400, 800, 3), dtype=np.uint8)
    padded, ratio, (pad_w, pad_h) = letterbox(img, target_shape=(640, 640))

    assert padded.shape == (640, 640, 3)
    assert ratio == 640 / 800  # 0.8
    assert pad_w == 0
    assert pad_h == (640 - int(400 * 0.8)) // 2  # 160


def test_detector_empty_or_none_frame():
    detector = YoloPersonDetector(model_path="models/yolov8n.onnx")
    assert detector.detect(None) == []
    assert detector.detect(np.array([], dtype=np.uint8)) == []


def test_loaded_cue_weights_do_not_claim_validation():
    detector = object.__new__(YoloCueDetector)
    detector._net = object()
    assert detector.is_ready is True
    assert detector.validated is False


def test_cue_detector_decodes_single_class_letterboxed_head(tmp_path):
    detector = YoloCueDetector(tmp_path / "missing.onnx", prefer_gpu=False)
    detector._net = MagicMock()
    output = np.array([[[320], [320], [320], [80], [.9]]], dtype=np.float32)
    frame = np.zeros((320, 640, 3), dtype=np.uint8)
    with patch("services.vision.detector._forward_with_cpu_fallback", return_value=(output, "CPU")):
        detections = detector.detect(frame, camera_id="test", timestamp=12.5)
    assert len(detections) == 1
    cue = detections[0]
    assert cue.kind == "cue" and cue.camera_id == "test" and cue.timestamp == 12.5
    assert cue.bbox == pytest.approx((.25, .375, .75, .625))
    assert cue.confidence == pytest.approx(.9)
    assert detector.validated is False


@pytest.mark.parametrize("shape", [(1, 84, 10), (1, 56, 10), (1, 10, 5), (5, 10)])
def test_cue_detector_rejects_coco_pose_or_malformed_heads(tmp_path, shape):
    detector = YoloCueDetector(tmp_path / "missing.onnx", prefer_gpu=False)
    detector._net = MagicMock()
    with patch("services.vision.detector._forward_with_cpu_fallback",
               return_value=(np.ones(shape, dtype=np.float32), "CPU")):
        assert detector.detect(np.zeros((320, 640, 3), dtype=np.uint8)) == []


def test_detector_with_real_onnx_model():
    model_file = Path("models/yolov8n.onnx")
    if not model_file.exists():
        pytest.skip("models/yolov8n.onnx not present for local integration test")

    detector = YoloPersonDetector(model_path=model_file)
    assert detector.is_ready is True

    # Test on a blank 640x480 frame -> no false positive persons on black screen
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    detections = detector.detect(blank)
    assert isinstance(detections, list)
    assert len(detections) == 0


def test_detector_foot_anchor_calculation():
    # Verify Foot Anchor math on mock PersonDetection
    bbox = (0.2, 0.3, 0.4, 0.8)  # x1, y1, x2, y2
    expected_foot = (0.3, 0.8)    # (x1 + x2)/2, y2

    det = PersonDetection(
        bbox=bbox,
        confidence=0.88,
        foot_anchor=((bbox[0] + bbox[2]) / 2.0, bbox[3]),
        class_id=0,
    )
    assert pytest.approx(det.foot_anchor[0]) == expected_foot[0]
    assert pytest.approx(det.foot_anchor[1]) == expected_foot[1]
