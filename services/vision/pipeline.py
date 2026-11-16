"""Vision Processing Pipeline (SB-11 & SB-12).

Chains VideoSource -> YoloPersonDetector -> ByteTracker -> TableZoneMapper -> per-table Observations.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np

from services.vision.contracts import Detection, VideoSource
from services.vision.detector import YoloPersonDetector
from services.vision.mapper import TableObservationSummary, TableZoneMapper
from services.vision.tracker import ByteTracker

logger = logging.getLogger("smartbilliard.vision.pipeline")


class VisionPipeline:
    """Connects camera input with YOLO detection, ByteTrack tracking, and Table Zone Mapping."""

    def __init__(
        self,
        source: VideoSource,
        detector: YoloPersonDetector | None = None,
        tracker: ByteTracker | None = None,
        mapper: TableZoneMapper | None = None,
    ) -> None:
        self.source = source
        self.detector = detector or YoloPersonDetector()
        self.tracker = tracker or ByteTracker()
        self.mapper = mapper

    def process_next_frame(
        self, timestamp: float | None = None
    ) -> tuple[bool, np.ndarray | None, list[Detection]]:
        """Read frame from source, run detector and tracker, and return standardized Detections."""
        ok, frame = self.source.read()
        if not ok or frame is None:
            return False, None, []

        ts = timestamp if timestamp is not None else time.time()

        # Run person detection
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
                )
            )

        return True, frame, results

    def process_frame_for_tables(
        self, timestamp: float | None = None
    ) -> tuple[bool, np.ndarray | None, list[Detection], dict[int, TableObservationSummary]]:
        """Run full pipeline including table assignment and ambiguity resolution."""
        ok, frame, detections = self.process_next_frame(timestamp=timestamp)
        if not ok or frame is None or self.mapper is None:
            return ok, frame, detections, {}

        assignments, table_summaries = self.mapper.map_frame(detections)
        return True, frame, detections, table_summaries
