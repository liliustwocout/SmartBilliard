from pathlib import Path

import cv2
import numpy as np
import pytest

from services.vision.preview import generate_reference_billiard_frame
from services.vision.table_segmenter import YoloTableSegmenter, auto_detect_with_best_method, fit_quad_from_contour


def test_yolo_table_segmenter_offline_fallback():
    non_existent = Path("models/non_existent_table_seg.onnx")
    segmenter = YoloTableSegmenter(model_path=non_existent)

    assert segmenter.is_available is False

    frame = generate_reference_billiard_frame(width=960, height=540)
    tables = segmenter.segment_tables(frame, max_tables=4)

    # Verifies graceful degradation to classical CV
    assert len(tables) == 4
    for t in tables:
        assert len(t.play_polygon) == 4
        assert len(t.standing_polygon) == 4


def test_auto_detect_with_best_method_fallback():
    non_existent = Path("models/non_existent_table_seg.onnx")
    frame = generate_reference_billiard_frame(width=960, height=540)

    tables, method = auto_detect_with_best_method(frame, max_tables=4, model_path=non_existent)

    assert len(tables) == 4
    assert "Classical Computer Vision" in method


def test_table_segmenter_empty_frame():
    segmenter = YoloTableSegmenter()
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    assert segmenter.segment_tables(empty) == []


def test_table_segmenter_black_frame():
    segmenter = YoloTableSegmenter(model_path="models/non_existent.onnx")
    black = np.zeros((480, 640, 3), dtype=np.uint8)
    assert segmenter.segment_tables(black) == []


def test_segment_tables_without_fallback_returns_empty_when_missing():
    non_existent = Path("models/non_existent_table_seg.onnx")
    segmenter = YoloTableSegmenter(model_path=non_existent)
    frame = generate_reference_billiard_frame(width=960, height=540)

    assert segmenter.segment_tables(frame, max_tables=4, allow_fallback=False) == []


def test_auto_detect_reports_honest_fallback_when_yolo_yields_nothing(tmp_path: Path):
    broken_onnx = tmp_path / "broken.onnx"
    broken_onnx.write_bytes(b"not-a-valid-onnx-model")

    frame = generate_reference_billiard_frame(width=960, height=540)
    tables, method = auto_detect_with_best_method(frame, max_tables=4, model_path=broken_onnx)

    assert len(tables) == 4
    assert "Classical Computer Vision" in method
    assert "fallback" in method
    assert method != "YOLOv8-seg (Deep Learning)"


def test_fit_quad_from_contour_preserves_thin_perspective_trapezoid():
    w, h = 1280, 720
    gt_pts = np.array([[280, 240], [640, 232], [662, 286], [260, 294]], dtype=np.int32)
    gt_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(gt_mask, [gt_pts], 255)

    # Simulate low-res 160x90 prototype mask upsampling with slightly rounded corners
    low = cv2.resize(gt_mask.astype(np.float32) / 255.0, (160, 90), interpolation=cv2.INTER_AREA)
    up = cv2.resize(low, (w, h), interpolation=cv2.INTER_LINEAR)
    sim_mask = (up > 0.5).astype(np.uint8) * 255

    contours, _ = cv2.findContours(sim_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    assert contours
    largest = max(contours, key=cv2.contourArea)

    quad = fit_quad_from_contour(largest)
    assert quad.shape == (4, 2)

    pred_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(pred_mask, [np.round(quad).astype(np.int32)], 255)
    inter = int(np.logical_and(gt_mask > 0, pred_mask > 0).sum())
    union = int(np.logical_or(gt_mask > 0, pred_mask > 0).sum())
    assert (inter / union) >= 0.90
