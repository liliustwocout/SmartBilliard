"""Unit tests for frame visual annotator and standby frame generator."""
import numpy as np
import pytest

from services.vision.annotator import create_standby_frame_jpeg, draw_frame_annotations
from services.vision.calibration import CalibrationConfig, TableZone
from services.vision.contracts import Detection
from services.vision.mapper import TableObservationSummary


def test_standby_frame_generator():
    frame_bytes = create_standby_frame_jpeg("CAMERA OFF", "Press Start")
    assert isinstance(frame_bytes, bytes)
    assert len(frame_bytes) > 500
    assert frame_bytes.startswith(b"\xff\xd8")  # JPEG SOI marker


def test_draw_frame_annotations_empty_frame():
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    res = draw_frame_annotations(empty)
    assert res.shape == (0, 0, 3)


def test_draw_frame_annotations_with_zones_and_detections():
    frame = np.zeros((540, 960, 3), dtype=np.uint8)
    cfg = CalibrationConfig(
        camera_id="cam-01",
        resolution=(960, 540),
        tables=[
            TableZone(
                table_id=1,
                name="Bàn 01",
                play_polygon=[(0.1, 0.1), (0.4, 0.1), (0.4, 0.4), (0.1, 0.4)],
                standing_polygon=[(0.05, 0.05), (0.45, 0.05), (0.45, 0.45), (0.05, 0.45)],
            )
        ],
    )
    detections = [
        Detection(camera_id="cam-01", timestamp=100.0, kind="person", bbox=(0.15, 0.15, 0.35, 0.38), confidence=0.88, track_id=1, foot_anchor=(0.25, 0.38)),
        Detection(camera_id="cam-01", timestamp=100.0, kind="person", bbox=(0.60, 0.60, 0.80, 0.90), confidence=0.72, track_id=2, foot_anchor=(0.70, 0.90)),
    ]
    summaries = {
        1: TableObservationSummary(
            table_id=1, present=True, confidence=0.88, people_count=1, track_ids=[1]
        )
    }

    annotated = draw_frame_annotations(
        frame=frame,
        detections=detections,
        summaries=summaries,
        config=cfg,
        fps=8.5,
        source_type="VIDEO",
        camera_id="cam-01",
    )

    assert annotated.shape == (540, 960, 3)
    # Annotated frame should not be all zeros anymore
    assert np.any(annotated > 0)
