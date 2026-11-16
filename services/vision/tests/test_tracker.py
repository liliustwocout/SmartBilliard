"""Unit tests for ByteTrack Multi-Object Tracker & Vision Pipeline (SB-11)."""
from unittest.mock import MagicMock

import numpy as np
import pytest

from services.vision.contracts import Detection, VideoSource
from services.vision.detector import PersonDetection, YoloPersonDetector
from services.vision.pipeline import VisionPipeline
from services.vision.tracker import ByteTracker, calculate_iou


def test_calculate_iou():
    # Exactly identical boxes
    box_a = (0.1, 0.1, 0.5, 0.5)
    assert pytest.approx(calculate_iou(box_a, box_a)) == 1.0

    # Disjoint boxes
    box_b = (0.6, 0.6, 0.9, 0.9)
    assert calculate_iou(box_a, box_b) == 0.0

    # Overlapping boxes
    box_c = (0.3, 0.1, 0.7, 0.5)
    # Area A = 0.4*0.4 = 0.16. Area C = 0.4*0.4 = 0.16.
    # Intersection = (0.5-0.3)*(0.5-0.1) = 0.2*0.4 = 0.08.
    # Union = 0.16 + 0.16 - 0.08 = 0.24.
    # IoU = 0.08 / 0.24 = 1/3.
    assert pytest.approx(calculate_iou(box_a, box_c)) == 1.0 / 3.0


def test_tracker_single_object_persistent_id():
    tracker = ByteTracker(high_threshold=0.5, match_threshold=0.3)

    # Frame 1: person appears
    det1 = PersonDetection(bbox=(0.2, 0.2, 0.3, 0.6), confidence=0.85, foot_anchor=(0.25, 0.6))
    tracks_1 = tracker.update([det1])
    assert len(tracks_1) == 1
    track_id_1 = tracks_1[0].track_id
    assert track_id_1 is not None

    # Frame 2: person takes a small step
    det2 = PersonDetection(bbox=(0.21, 0.2, 0.31, 0.6), confidence=0.82, foot_anchor=(0.26, 0.6))
    tracks_2 = tracker.update([det2])
    assert len(tracks_2) == 1
    assert tracks_2[0].track_id == track_id_1

    # Frame 3: person takes another small step
    det3 = PersonDetection(bbox=(0.22, 0.2, 0.32, 0.6), confidence=0.80, foot_anchor=(0.27, 0.6))
    tracks_3 = tracker.update([det3])
    assert len(tracks_3) == 1
    assert tracks_3[0].track_id == track_id_1


def test_tracker_multi_object_unique_ids():
    tracker = ByteTracker()

    # Two distinct players at table 1 and table 2
    p1 = PersonDetection(bbox=(0.1, 0.1, 0.2, 0.5), confidence=0.9, foot_anchor=(0.15, 0.5))
    p2 = PersonDetection(bbox=(0.6, 0.6, 0.7, 0.9), confidence=0.88, foot_anchor=(0.65, 0.9))

    tracks = tracker.update([p1, p2])
    assert len(tracks) == 2
    id1 = tracks[0].track_id
    id2 = tracks[1].track_id
    assert id1 != id2

    # Next frame
    p1_next = PersonDetection(bbox=(0.11, 0.1, 0.21, 0.5), confidence=0.88, foot_anchor=(0.16, 0.5))
    p2_next = PersonDetection(bbox=(0.61, 0.6, 0.71, 0.9), confidence=0.87, foot_anchor=(0.66, 0.9))
    tracks_next = tracker.update([p1_next, p2_next])
    assert len(tracks_next) == 2
    current_ids = {t.track_id for t in tracks_next}
    assert current_ids == {id1, id2}


def test_tracker_two_stage_occlusion_recovery():
    """Verify ByteTrack low-confidence matching when player bends over."""
    tracker = ByteTracker(high_threshold=0.5, low_threshold=0.2, match_threshold=0.3)

    # Frame 1: Standing tall, high confidence
    det_stand = PersonDetection(bbox=(0.3, 0.3, 0.4, 0.7), confidence=0.85, foot_anchor=(0.35, 0.7))
    t1 = tracker.update([det_stand])[0]
    initial_id = t1.track_id

    # Frame 2: Bending down to aim cue, confidence drops to 0.35 (below high_threshold 0.5)
    det_bend = PersonDetection(bbox=(0.29, 0.35, 0.42, 0.7), confidence=0.35, foot_anchor=(0.355, 0.7))
    t2 = tracker.update([det_bend])
    assert len(t2) == 1
    # ByteTrack stage 2 successfully matches the track and preserves ID!
    assert t2[0].track_id == initial_id


def test_tracker_lost_and_removed_after_timeout():
    tracker = ByteTracker(max_lost_frames=3)

    det = PersonDetection(bbox=(0.4, 0.4, 0.5, 0.8), confidence=0.9, foot_anchor=(0.45, 0.8))
    t1 = tracker.update([det])[0]
    assert t1.track_id is not None

    # Person disappears for 3 frames
    tracker.update([])
    tracker.update([])
    tracker.update([])
    assert len(tracker.lost_stracks) == 1

    # 4th frame without detection -> exceeds max_lost_frames, removed
    tracker.update([])
    assert len(tracker.tracked_stracks) == 0
    assert len(tracker.lost_stracks) == 0


def test_vision_pipeline_integration():
    mock_source = MagicMock(spec=VideoSource)
    mock_source.camera_id = "cam-mock"
    mock_source.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))

    mock_detector = MagicMock(spec=YoloPersonDetector)
    mock_detector.detect.return_value = [
        PersonDetection(bbox=(0.2, 0.2, 0.3, 0.6), confidence=0.85, foot_anchor=(0.25, 0.6))
    ]

    pipeline = VisionPipeline(source=mock_source, detector=mock_detector)
    ok, frame, detections = pipeline.process_next_frame(timestamp=123456.0)

    assert ok is True
    assert frame is not None
    assert len(detections) == 1
    det = detections[0]
    assert det.camera_id == "cam-mock"
    assert det.timestamp == 123456.0
    assert det.kind == "person"
    assert det.confidence == 0.85
    assert det.track_id is not None
    assert det.foot_anchor == (0.25, 0.6)


def test_vision_pipeline_with_zone_mapper():
    mock_source = MagicMock(spec=VideoSource)
    mock_source.camera_id = "cam-mock"
    mock_source.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))

    mock_detector = MagicMock(spec=YoloPersonDetector)
    mock_detector.detect.return_value = [
        PersonDetection(bbox=(0.2, 0.2, 0.3, 0.6), confidence=0.88, foot_anchor=(0.25, 0.6))
    ]

    mock_mapper = MagicMock()
    mock_mapper.map_frame.return_value = ([], {1: MagicMock(present=True, table_id=1)})

    pipeline = VisionPipeline(source=mock_source, detector=mock_detector, mapper=mock_mapper)
    ok, frame, detections, summaries = pipeline.process_frame_for_tables()

    assert ok is True
    assert 1 in summaries
    assert summaries[1].present is True
