"""Table Zone Mapper and Ambiguity Resolution (SB-12).

Maps person foot anchors to table standing zones:
- Foot inside exactly 1 table's standing zone -> Assigned to that table.
- Foot inside >1 table's standing zone -> AMBIGUOUS (disputed boundary).
- Foot outside all tables -> OUTSIDE.
- Aggregates frame detections into per-table Observation for the Temporal FSM.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from services.vision.calibration import (
    CalibrationConfig,
    Point,
    TableZone,
    load_calibration_config,
    point_in_polygon,
    polygon_area,
)
from services.vision.contracts import ActivityState, Detection
from services.vision.decision import Observation
from services.vision.pose_analyzer import (
    LEFT_ELBOW,
    LEFT_HIP,
    LEFT_SHOULDER,
    LEFT_WRIST,
    RIGHT_ELBOW,
    RIGHT_HIP,
    RIGHT_SHOULDER,
    RIGHT_WRIST,
    PoseCueAnalyzer,
    _confident_kp,
    _midpoint,
    point_to_polygon_distance,
)

logger = logging.getLogger("smartbilliard.vision.mapper")


@dataclass(frozen=True)
class PersonAssignment:
    detection: Any  # Detection or PersonDetection
    foot_anchor: Point
    status: str  # "ASSIGNED", "AMBIGUOUS", "OUTSIDE"
    matched_tables: list[int] = field(default_factory=list)
    track_id: int | None = None


@dataclass(frozen=True)
class TableObservationSummary:
    table_id: int
    present: bool
    confidence: float
    ambiguous: bool = False
    people_count: int = 0
    track_ids: list[int] = field(default_factory=list)
    cue_confidence: float | None = None
    activity_state: ActivityState = "UNKNOWN"
    activity_reason: str = "WAITING"
    felt_motion: bool = False
    motion_energy: float = 0.0
    sides_visited: int = 1
    spatial_dispersion: float = 0.0

    def to_observation(self) -> Observation:
        """Convert to the Decision Engine's Observation contract."""
        return Observation(
            present=self.present,
            confidence=self.confidence,
            ambiguous=self.ambiguous,
            cue_confidence=self.cue_confidence,
            activity_state=self.activity_state,
            activity_reason=self.activity_reason,
            felt_motion=self.felt_motion,
            sides_visited=self.sides_visited,
        )



class TableZoneMapper:
    """Maps detected persons and cues to billiard tables based on calibration zones."""

    def __init__(self, config: CalibrationConfig, analyzer: PoseCueAnalyzer | None = None) -> None:
        self.config = config
        self.analyzer = analyzer or PoseCueAnalyzer()

    @classmethod
    def from_file(cls, path: str | Path, fallback: str | Path | None = None) -> TableZoneMapper:
        cfg = load_calibration_config(Path(path), Path(fallback) if fallback else None)
        return cls(cfg)

    def update_config(self, config: CalibrationConfig) -> None:
        self.config = config

    def _resolve_by_play_surface_affinity(self, det: Any, standing_matched: list[int]) -> int | None:
        """Assign ambiguous/occluded player by upper-body & hand reach onto a single table's play_polygon."""
        del standing_matched
        keypoints = getattr(det, "keypoints", None)
        if keypoints is None:
            return None

        lw = _confident_kp(keypoints, LEFT_WRIST)
        rw = _confident_kp(keypoints, RIGHT_WRIST)
        le = _confident_kp(keypoints, LEFT_ELBOW)
        re = _confident_kp(keypoints, RIGHT_ELBOW)
        hand_pts = [p for p in (lw, rw, le, re) if p is not None]
        if not hand_pts:
            return None

        shoulder_mid = _midpoint(
            _confident_kp(keypoints, LEFT_SHOULDER),
            _confident_kp(keypoints, RIGHT_SHOULDER),
        )
        hip_mid = _midpoint(
            _confident_kp(keypoints, LEFT_HIP),
            _confident_kp(keypoints, RIGHT_HIP),
        )
        upper = shoulder_mid or hip_mid

        candidates: list[tuple[float, int]] = []
        for table in self.config.tables:
            if not table.enabled:
                continue
            play_poly = [tuple(p) for p in table.play_polygon]
            if len(play_poly) < 3:
                continue
            table_scale = max(0.05, math.sqrt(polygon_area(play_poly)))
            reach_margin = max(0.018, min(0.038, 0.16 * table_scale))
            min_hand_dist = min(point_to_polygon_distance(p, play_poly) for p in hand_pts)
            if min_hand_dist > reach_margin:
                continue

            upper_dist = 0.0
            if upper is not None:
                upper_dist = point_to_polygon_distance(upper, play_poly)
                if upper_dist > max(0.14, 0.85 * table_scale):
                    continue
            if shoulder_mid is not None and hip_mid is not None:
                if point_to_polygon_distance(shoulder_mid, play_poly) > point_to_polygon_distance(hip_mid, play_poly) + 0.03:
                    continue

            score = min_hand_dist + 0.3 * upper_dist
            candidates.append((score, table.table_id))

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        if len(candidates) == 1 or (candidates[0][0] + 0.025) < candidates[1][0]:
            return candidates[0][1]
        return None

    def map_person(self, det: Any) -> PersonAssignment:
        """Map a single person detection to matching tables using foot anchor and play-surface affinity."""
        # Extract foot anchor
        if hasattr(det, "foot_anchor") and det.foot_anchor is not None:
            foot = det.foot_anchor
        elif hasattr(det, "bbox"):
            x1, y1, x2, y2 = det.bbox
            foot = ((x1 + x2) / 2.0, y2)
        else:
            foot = (0.5, 0.5)

        track_id = getattr(det, "track_id", None)

        # Check against all enabled tables
        matched: list[int] = []
        for table in self.config.tables:
            if not table.enabled:
                continue
            poly = [tuple(p) for p in table.standing_polygon]
            if point_in_polygon(foot, poly):
                matched.append(table.table_id)

        affinity_table = self._resolve_by_play_surface_affinity(det, matched)
        if affinity_table is not None:
            matched = [affinity_table]
            status = "ASSIGNED"
        elif len(matched) == 0:
            status = "OUTSIDE"
        elif len(matched) == 1:
            status = "ASSIGNED"
        else:
            status = "AMBIGUOUS"

        return PersonAssignment(
            detection=det,
            foot_anchor=foot,
            status=status,
            matched_tables=matched,
            track_id=track_id,
        )

    def map_frame(
        self,
        detections: list[Any],
        timestamp: float | None = None,
        felt_results: dict[int, Any] | None = None,
    ) -> tuple[list[PersonAssignment], dict[int, TableObservationSummary]]:
        """Map all detections in a frame to tables and return per-table observation summaries."""
        person_detections = [d for d in detections if getattr(d, "kind", "person") == "person"]
        cue_detections = [d for d in detections if getattr(d, "kind", None) == "cue"]

        ts = timestamp
        if ts is None:
            ts = next((float(d.timestamp) for d in detections if hasattr(d, "timestamp")), time.time())

        assignments: list[PersonAssignment] = [self.map_person(d) for d in person_detections]

        # Group assignments by table
        table_unambiguous: dict[int, list[PersonAssignment]] = {t.table_id: [] for t in self.config.tables}
        table_ambiguous: dict[int, list[PersonAssignment]] = {t.table_id: [] for t in self.config.tables}

        for assign in assignments:
            if assign.status == "ASSIGNED":
                t_id = assign.matched_tables[0]
                if t_id in table_unambiguous:
                    table_unambiguous[t_id].append(assign)
            elif assign.status == "AMBIGUOUS":
                for t_id in assign.matched_tables:
                    if t_id in table_ambiguous:
                        table_ambiguous[t_id].append(assign)

        summaries: dict[int, TableObservationSummary] = {}
        for table in self.config.tables:
            if not table.enabled:
                continue
            tid = table.table_id
            unambig_list = table_unambiguous.get(tid, [])
            ambig_list = table_ambiguous.get(tid, [])

            felt_res = felt_results.get(tid) if felt_results else None
            has_felt_motion = getattr(felt_res, "has_motion", False) if felt_res else False
            felt_energy = getattr(felt_res, "motion_energy", 0.0) if felt_res else 0.0

            table_analysis = self.analyzer.analyze_table(
                table, unambig_list, ambig_list, cue_detections, ts, felt_motion=has_felt_motion
            )
            activity_state, cue_conf, activity_reason = table_analysis
            sides_visited = getattr(table_analysis, "max_sides_visited", 1)
            spatial_dispersion = getattr(table_analysis, "max_spatial_dispersion", 0.0)

            if unambig_list:
                # We have at least one person clearly at this table
                max_conf = max(getattr(a.detection, "confidence", 0.9) for a in unambig_list)
                track_ids = [a.track_id for a in unambig_list if a.track_id is not None]
                summaries[tid] = TableObservationSummary(
                    table_id=tid,
                    present=True,
                    confidence=max_conf,
                    ambiguous=False,
                    people_count=len(unambig_list),
                    track_ids=track_ids,
                    cue_confidence=cue_conf,
                    activity_state=activity_state,
                    activity_reason=activity_reason,
                    felt_motion=has_felt_motion,
                    motion_energy=felt_energy,
                    sides_visited=sides_visited,
                    spatial_dispersion=spatial_dispersion,
                )
            elif ambig_list:
                # Only ambiguous people on border
                max_conf = max(getattr(a.detection, "confidence", 0.9) for a in ambig_list)
                track_ids = [a.track_id for a in ambig_list if a.track_id is not None]
                summaries[tid] = TableObservationSummary(
                    table_id=tid,
                    present=True,
                    confidence=max_conf,
                    ambiguous=True,
                    people_count=len(ambig_list),
                    track_ids=track_ids,
                    cue_confidence=cue_conf,
                    activity_state=activity_state,
                    activity_reason=activity_reason,
                    felt_motion=has_felt_motion,
                    motion_energy=felt_energy,
                    sides_visited=sides_visited,
                    spatial_dispersion=spatial_dispersion,
                )
            else:
                # No people at this table
                summaries[tid] = TableObservationSummary(
                    table_id=tid,
                    present=False,
                    confidence=0.0,
                    ambiguous=False,
                    people_count=0,
                    track_ids=[],
                    cue_confidence=None,
                    activity_state="NOT_PLAYING",
                    activity_reason="EMPTY_TABLE",
                    felt_motion=has_felt_motion,
                    motion_energy=felt_energy,
                    sides_visited=1,
                    spatial_dispersion=0.0,
                )

        return assignments, summaries
