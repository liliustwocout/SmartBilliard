"""Inference is skipped only while every calibrated table has an open session."""
import numpy as np

from services.vision.calibration import CalibrationConfig, TableZone
from services.vision.mapper import TableZoneMapper
from services.vision.pipeline import VisionPipeline
from services.vision.tracker import ByteTracker


class FakeSource:
    camera_id = "cam-test"

    def read(self):
        return True, np.zeros((48, 64, 3), dtype=np.uint8)


class CountingDetector:
    def __init__(self):
        self.calls = 0

    def detect(self, frame):
        self.calls += 1
        return []


def _pipeline():
    zone = lambda n: TableZone(table_id=n, enabled=True,
                               play_polygon=[[.1, .1], [.4, .1], [.4, .4], [.1, .4]],
                               standing_polygon=[[.05, .05], [.5, .05], [.5, .5], [.05, .5]])
    cfg = CalibrationConfig(camera_id="cam-test", calibration_status="CALIBRATED",
                            coordinate_system="normalized_xy_0_1", tables=[zone(1), zone(2)])
    detector = CountingDetector()
    pipe = VisionPipeline(FakeSource(), detector=detector, tracker=ByteTracker(),
                          mapper=TableZoneMapper(cfg), cue_detector=None)
    return pipe, detector


def test_detector_runs_when_some_table_is_free():
    pipe, detector = _pipeline()
    ok, frame, _, _ = pipe.process_frame_for_tables(paused_table_ids={1})
    assert ok and frame is not None and detector.calls == 1 and not pipe.inference_skipped


def test_detector_skipped_when_all_tables_paused_but_frame_still_flows():
    pipe, detector = _pipeline()
    ok, frame, detections, summaries = pipe.process_frame_for_tables(paused_table_ids={1, 2})
    assert ok and frame is not None and detections == [] and summaries == {}
    assert detector.calls == 0 and pipe.inference_skipped


def test_tracker_reset_and_detector_resume_after_pause():
    pipe, detector = _pipeline()
    pipe.process_frame_for_tables(paused_table_ids={1, 2})
    pipe.tracker._next_id = 99
    pipe.process_frame_for_tables(paused_table_ids={2})
    assert detector.calls == 1 and not pipe.inference_skipped and pipe.tracker._next_id == 1


def test_detector_skipped_when_all_enabled_tables_paused_ignoring_disabled_tables():
    zone = lambda n, en: TableZone(table_id=n, enabled=en,
                                   play_polygon=[[.1, .1], [.4, .1], [.4, .4], [.1, .4]],
                                   standing_polygon=[[.05, .05], [.5, .05], [.5, .5], [.05, .5]])
    cfg = CalibrationConfig(camera_id="cam-test", calibration_status="CALIBRATED",
                            coordinate_system="normalized_xy_0_1", tables=[zone(1, True), zone(2, False)])
    detector = CountingDetector()
    pipe = VisionPipeline(FakeSource(), detector=detector, tracker=ByteTracker(),
                          mapper=TableZoneMapper(cfg), cue_detector=None)
    ok, frame, _, _ = pipe.process_frame_for_tables(paused_table_ids={1})
    assert ok and frame is not None and detector.calls == 0 and pipe.inference_skipped is True
