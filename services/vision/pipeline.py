"""Vision Processing Pipeline (SB-11 & SB-12).

Chains VideoSource -> YoloPersonDetector -> ByteTracker -> TableZoneMapper -> per-table Observations.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np

from services.vision.contracts import CueDetector, Detection, VideoSource
from services.vision.detector import YoloCueDetector, YoloPersonDetector, YoloPoseDetector
from services.vision.felt import FeltMotionDetector, FeltMotionResult
from services.vision.mapper import TableObservationSummary, TableZoneMapper
from services.vision.tracker import ByteTracker

logger = logging.getLogger("smartbilliard.vision.pipeline")


class VisionPipeline:
    """Connects camera input with YOLO Pose/Cue detection, ByteTrack tracking, and Table Zone Mapping."""

    def __init__(
        self,
        source: VideoSource,
        detector: YoloPersonDetector | None = None,
        tracker: ByteTracker | None = None,
        mapper: TableZoneMapper | None = None,
        cue_detector: CueDetector | None = None,
        felt_detector: FeltMotionDetector | None = None,
    ) -> None:
        self.source = source
        self.detector = detector or YoloPoseDetector()
        self.tracker = tracker or ByteTracker()
        self.mapper = mapper
        self.cue_detector = cue_detector or YoloCueDetector()
        self.felt_detector = felt_detector or FeltMotionDetector()
        self.inference_skipped = False


    def process_next_frame(
        self, timestamp: float | None = None
    ) -> tuple[bool, np.ndarray | None, list[Detection]]:
        """Read frame from source, run pose/cue detectors and tracker, and return standardized Detections."""
        ok, frame = self.source.read()
        if not ok or frame is None:
            return False, None, []

        ts = timestamp if timestamp is not None else time.time()

        # Run person/pose detection
        raw_detections = self.detector.detect(frame)

        # Run tracker to associate IDs and smooth bboxes
        tracked_persons = self.tracker.update(raw_detections)

        # Convert to standardized project Detection objects
        results: list[Detection] = []
        for p in tracked_persons:
            results.append(
                Detection(
                    camera_id=self.source.camera_id,
                    timestamp=ts,
                    kind="person",
                    bbox=p.bbox,
                    confidence=p.confidence,
                    track_id=p.track_id,
                    foot_anchor=p.foot_anchor,
                    keypoints=getattr(p, "keypoints", None),
                )
            )

        # Run cue detector only when at least one person is detected (saves GPU/CPU load on empty frames)
        if tracked_persons and self.cue_detector is not None and self.cue_detector.is_ready:
            cue_dets = self.cue_detector.detect(
                frame,
                camera_id=self.source.camera_id,
                timestamp=ts,
            )
            results.extend(cue_dets)

        return True, frame, results

    def process_frame_for_tables(
        self,
        timestamp: float | None = None,
        paused_table_ids: frozenset[int] | set[int] = frozenset(),
    ) -> tuple[bool, np.ndarray | None, list[Detection], dict[int, TableObservationSummary]]:
        """Run full pipeline including table assignment, pose-cue analysis, and ambiguity resolution.

        When every calibrated table is in ``paused_table_ids`` (all have an open session), the
        frame is still read so the live view keeps updating, but detection/tracking are skipped.
        """
        ts = timestamp if timestamp is not None else time.time()
        if self.mapper is not None and paused_table_ids:
            table_ids = {t.table_id for t in self.mapper.config.tables if t.enabled}
            if table_ids and table_ids <= set(paused_table_ids):
                ok, frame = self.source.read()
                if not ok or frame is None:
                    return False, None, [], {}
                self.inference_skipped = True
                return True, frame, [], {}
        if self.inference_skipped:
            # Tracks from before the pause are stale; start clean when inference resumes.
            self.tracker.reset()
            if self.felt_detector is not None:
                self.felt_detector.reset()
            self.inference_skipped = False
        ok, frame, detections = self.process_next_frame(timestamp=ts)
        if not ok or frame is None or self.mapper is None:
            return ok, frame, detections, {}

        # Experimental cue boxes are visible in the preview, but cannot influence the FSM.
        trusted_detections = detections
        if not getattr(self.cue_detector, "validated", False):
            trusted_detections = [d for d in detections if d.kind != "cue"]

        felt_results: dict[int, FeltMotionResult] = {}
        if self.felt_detector is not None:
            person_bboxes = [
                d.bbox
                for d in detections
                if getattr(d, "kind", "person") == "person" and hasattr(d, "bbox")
            ]
            for table in self.mapper.config.tables:
                if table.enabled and table.table_id not in paused_table_ids:
                    felt_results[table.table_id] = self.felt_detector.detect_motion(
                        frame,
                        table.table_id,
                        table.play_polygon,
                        exclude_bboxes=person_bboxes,
                    )

        _, table_summaries = self.mapper.map_frame(
            trusted_detections, timestamp=ts, felt_results=felt_results
        )
        return True, frame, detections, table_summaries
