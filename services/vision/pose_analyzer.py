"""Pose & Cue Action Analyzer for SmartBilliard (PLAYING / NOT_PLAYING / UNKNOWN).

Combines COCO 17 keypoints, cue detections, table polygons, and short-term
track motion history to distinguish real players from spectators and table cleaners.
Pure Python + NumPy (no OpenCV/Ultralytics dependency).
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Any

from services.vision.calibration import Point, Polygon, TableZone, point_in_polygon, segments_intersect
from services.vision.contracts import ActivityState, Detection, Keypoint

# COCO-17 keypoint indices
LEFT_SHOULDER = 5
RIGHT_SHOULDER = 6
LEFT_ELBOW = 7
RIGHT_ELBOW = 8
LEFT_WRIST = 9
RIGHT_WRIST = 10
LEFT_HIP = 11
RIGHT_HIP = 12

_MIN_KP_CONF = 0.35


@dataclass(frozen=True)
class PersonAnalysis:
    track_id: int | None
    activity: ActivityState
    aiming_posture: bool
    has_active_cue: bool
    cleaning_motion: bool
    cue_confidence: float | None
    reason: str


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _point_to_segment_distance(pt: Point, a: Point, b: Point) -> float:
    px, py = pt
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    len_sq = dx * dx + dy * dy
    if len_sq <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / len_sq))
    proj_x = ax + t * dx
    proj_y = ay + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def point_to_box_distance(pt: Point, bbox: tuple[float, float, float, float]) -> float:
    """Euclidean distance from point to axis-aligned bbox (0.0 if inside)."""
    px, py = pt
    x1, y1, x2, y2 = bbox
    dx = max(x1 - px, 0.0, px - x2)
    dy = max(y1 - py, 0.0, py - y2)
    return math.hypot(dx, dy)


def point_to_polygon_distance(pt: Point, poly: Polygon) -> float:
    """Euclidean distance from point to polygon (0.0 if inside)."""
    if len(poly) < 3:
        return float("inf")
    if point_in_polygon(pt, poly):
        return 0.0
    return min(
        _point_to_segment_distance(pt, poly[i], poly[(i + 1) % len(poly)])
        for i in range(len(poly))
    )


def _cue_reaches_polygon(bbox: tuple[float, float, float, float], poly: Polygon, margin: float = 0.06) -> bool:
    """Check whether a cue bounding box overlaps or reaches close to the table play polygon."""
    if len(poly) < 3:
        return False
    x1, y1, x2, y2 = bbox
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    sample_pts: list[Point] = [
        (cx, cy),
        (x1, y1),
        (x2, y1),
        (x2, y2),
        (x1, y2),
    ]
    for pt in sample_pts:
        if point_to_polygon_distance(pt, poly) <= margin:
            return True

    # Check both diagonals of the cue box against polygon edges
    diagonals = [((x1, y1), (x2, y2)), ((x1, y2), (x2, y1))]
    for d1, d2 in diagonals:
        for i in range(len(poly)):
            if segments_intersect(d1, d2, poly[i], poly[(i + 1) % len(poly)]):
                return True
    return False


def _angle_deg(a: Point, b: Point, c: Point) -> float | None:
    """Return interior angle ABC in degrees, or None if degenerate."""
    v1x, v1y = a[0] - b[0], a[1] - b[1]
    v2x, v2y = c[0] - b[0], c[1] - b[1]
    n1 = math.hypot(v1x, v1y)
    n2 = math.hypot(v2x, v2y)
    if n1 <= 1e-6 or n2 <= 1e-6:
        return None
    cos_val = max(-1.0, min(1.0, (v1x * v2x + v1y * v2y) / (n1 * n2)))
    return math.degrees(math.acos(cos_val))


def _confident_kp(keypoints: tuple[Keypoint, ...] | None, idx: int) -> Point | None:
    if keypoints is None or idx >= len(keypoints):
        return None
    x, y, conf = keypoints[idx]
    if conf < _MIN_KP_CONF:
        return None
    return (x, y)


def _midpoint(p1: Point | None, p2: Point | None) -> Point | None:
    if p1 is not None and p2 is not None:
        return ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
    return p1 or p2


class PoseCueAnalyzer:
    """Analyzes skeleton posture, hand-cue proximity, and motion to classify table activity."""

    def __init__(
        self,
        *,
        wrist_cue_max_distance: float = 0.14,
        wrist_table_margin: float = 0.03,
        lean_torso_ratio: float = 0.24,
        hip_cleaning_speed: float = 0.08,
        wrist_cleaning_speed: float = 0.18,
        history_window: int = 20,
        track_ttl_seconds: float = 30.0,
    ) -> None:
        self.wrist_cue_max_distance = wrist_cue_max_distance
        self.wrist_table_margin = wrist_table_margin
        self.lean_torso_ratio = lean_torso_ratio
        self.hip_cleaning_speed = hip_cleaning_speed
        self.wrist_cleaning_speed = wrist_cleaning_speed
        self.track_ttl_seconds = track_ttl_seconds
        # track_id -> deque of (timestamp, hip_mid, wrist_mid)
        self._history: dict[int, deque[tuple[float, Point, Point | None]]] = {}
        self._history_window = history_window

    def _prune_history(self, now: float) -> None:
        stale = [
            tid
            for tid, hist in self._history.items()
            if not hist or (now - hist[-1][0]) > self.track_ttl_seconds
        ]
        for tid in stale:
            del self._history[tid]

    def _update_motion_history(
        self,
        track_id: int | None,
        keypoints: tuple[Keypoint, ...] | None,
        timestamp: float,
    ) -> tuple[float, float]:
        """Record track kinematics and return (hip_speed, wrist_speed) in normalized units/sec."""
        if track_id is None or keypoints is None:
            return 0.0, 0.0

        hip_mid = _midpoint(
            _confident_kp(keypoints, LEFT_HIP),
            _confident_kp(keypoints, RIGHT_HIP),
        )
        if hip_mid is None:
            return 0.0, 0.0

        lw = _confident_kp(keypoints, LEFT_WRIST)
        rw = _confident_kp(keypoints, RIGHT_WRIST)
        wrist_mid = _midpoint(lw, rw)

        hist = self._history.setdefault(track_id, deque(maxlen=self._history_window))
        if not hist or timestamp > hist[-1][0]:
            hist.append((timestamp, hip_mid, wrist_mid))

        if len(hist) < 3:
            return 0.0, 0.0

        dt = hist[-1][0] - hist[0][0]
        if dt < 0.25:
            return 0.0, 0.0

        hip_path = sum(_dist(hist[i - 1][1], hist[i][1]) for i in range(1, len(hist)))
        hip_speed = hip_path / dt

        wrist_pts = [(t, w) for t, _, w in hist if w is not None]
        wrist_speed = 0.0
        if len(wrist_pts) >= 2:
            w_dt = wrist_pts[-1][0] - wrist_pts[0][0]
            if w_dt >= 0.2:
                wrist_path = sum(_dist(wrist_pts[i - 1][1], wrist_pts[i][1]) for i in range(1, len(wrist_pts)))
                wrist_speed = wrist_path / w_dt

        return hip_speed, wrist_speed

    def _match_active_cue(
        self,
        det: Any,
        keypoints: tuple[Keypoint, ...] | None,
        cue_detections: list[Detection],
        play_poly: Polygon,
    ) -> float | None:
        """Return max confidence of a cue held near wrists and oriented toward the table."""
        if not cue_detections:
            return None

        wrists = [
            pt
            for pt in (_confident_kp(keypoints, LEFT_WRIST), _confident_kp(keypoints, RIGHT_WRIST))
            if pt is not None
        ]
        bbox = getattr(det, "bbox", None)

        best_conf: float | None = None
        for cue in cue_detections:
            cx1, cy1, cx2, cy2 = cue.bbox
            cw = max(1e-6, cx2 - cx1)
            ch = max(0.0, cy2 - cy1)
            reaches_table = _cue_reaches_polygon(cue.bbox, play_poly)

            # Exclude vertical cues held idly outside the play zone (e.g., leaning on stick chatting)
            if (ch / cw) > 2.2 and not reaches_table:
                continue
            if not reaches_table:
                continue

            if wrists:
                near_hand = any(point_to_box_distance(w, cue.bbox) <= self.wrist_cue_max_distance for w in wrists)
            elif bbox is not None:
                # Fallback to upper torso bbox when pose keypoints are unavailable
                px1, py1, px2, py2 = bbox
                upper_pts = [
                    ((px1 + px2) / 2.0, py1 + 0.35 * (py2 - py1)),
                    (px1, py1 + 0.45 * (py2 - py1)),
                    (px2, py1 + 0.45 * (py2 - py1)),
                ]
                near_hand = any(point_to_box_distance(p, cue.bbox) <= self.wrist_cue_max_distance for p in upper_pts)
            else:
                near_hand = False

            if near_hand:
                best_conf = max(best_conf or 0.0, float(cue.confidence))

        return best_conf

    def _check_aiming_posture(
        self,
        det: Any,
        keypoints: tuple[Keypoint, ...] | None,
        play_poly: Polygon,
    ) -> tuple[bool, bool]:
        """Return (has_pose_signal, is_aiming_posture)."""
        if keypoints is None:
            return False, False

        ls = _confident_kp(keypoints, LEFT_SHOULDER)
        rs = _confident_kp(keypoints, RIGHT_SHOULDER)
        lh = _confident_kp(keypoints, LEFT_HIP)
        rh = _confident_kp(keypoints, RIGHT_HIP)
        lw = _confident_kp(keypoints, LEFT_WRIST)
        rw = _confident_kp(keypoints, RIGHT_WRIST)
        le = _confident_kp(keypoints, LEFT_ELBOW)
        re = _confident_kp(keypoints, RIGHT_ELBOW)

        shoulder_mid = _midpoint(ls, rs)
        hip_mid = _midpoint(lh, rh)
        wrists = [w for w in (lw, rw) if w is not None]

        has_pose_signal = (shoulder_mid is not None and hip_mid is not None) or bool(wrists)
        if not has_pose_signal:
            return False, False

        bbox = getattr(det, "bbox", (0.0, 0.0, 1.0, 1.0))
        bbox_h = max(1e-4, float(bbox[3] - bbox[1]))

        # Elbow angles for bridge/stroke arm verification
        elbow_angles = [
            ang
            for ang in (
                _angle_deg(ls, le, lw) if ls and le and lw else None,
                _angle_deg(rs, re, rw) if rs and re and rw else None,
            )
            if ang is not None
        ]
        arm_bent = any(45.0 <= ang <= 165.0 for ang in elbow_angles)

        # Wrist reaching inside or close to felt play zone
        wrist_dists = [point_to_polygon_distance(w, play_poly) for w in wrists]
        wrist_on_table = any(d <= self.wrist_table_margin for d in wrist_dists)
        wrist_near_table = any(d <= 0.12 for d in wrist_dists)

        leaning = False
        if shoulder_mid is not None and hip_mid is not None:
            torso_ratio = abs(hip_mid[1] - shoulder_mid[1]) / bbox_h
            # Leaning over the table compresses vertical shoulder-hip span; require hand near table to reject upright standing
            leaning = torso_ratio < self.lean_torso_ratio and (wrist_near_table or not wrists)

        aiming = leaning or (wrist_on_table and (arm_bent or not elbow_angles))
        return True, aiming

    def analyze_person(
        self,
        det: Any,
        table: TableZone,
        cue_detections: list[Detection],
        timestamp: float,
    ) -> PersonAnalysis:
        """Classify a single assigned person at a billiard table."""
        play_poly: Polygon = [tuple(p) for p in table.play_polygon]
        keypoints: tuple[Keypoint, ...] | None = getattr(det, "keypoints", None)
        track_id: int | None = getattr(det, "track_id", None)

        cue_conf = self._match_active_cue(det, keypoints, cue_detections, play_poly)
        has_active_cue = cue_conf is not None
        has_pose_signal, aiming = self._check_aiming_posture(det, keypoints, play_poly)
        hip_speed, wrist_speed = self._update_motion_history(track_id, keypoints, timestamp)

        cleaning = (
            not has_active_cue
            and hip_speed > self.hip_cleaning_speed
            and wrist_speed > self.wrist_cleaning_speed
        )

        if cleaning:
            return PersonAnalysis(
                track_id=track_id,
                activity="NOT_PLAYING",
                aiming_posture=False,
                has_active_cue=False,
                cleaning_motion=True,
                cue_confidence=cue_conf,
                reason="CLEANING_MOTION",
            )

        if has_active_cue or aiming:
            return PersonAnalysis(
                track_id=track_id,
                activity="PLAYING",
                aiming_posture=aiming,
                has_active_cue=has_active_cue,
                cleaning_motion=False,
                cue_confidence=cue_conf,
                reason="PLAYING_ACTIVE",
            )

        if has_pose_signal:
            return PersonAnalysis(
                track_id=track_id,
                activity="NOT_PLAYING",
                aiming_posture=False,
                has_active_cue=False,
                cleaning_motion=False,
                cue_confidence=None,
                reason="SPECTATOR_POSTURE",
            )

        return PersonAnalysis(
            track_id=track_id,
            activity="UNKNOWN",
            aiming_posture=False,
            has_active_cue=False,
            cleaning_motion=False,
            cue_confidence=None,
            reason="BBOX_ONLY",
        )

    def analyze_table(
        self,
        table: TableZone,
        unambiguous_assignments: list[Any],
        ambiguous_assignments: list[Any],
        cue_detections: list[Detection],
        timestamp: float,
    ) -> tuple[ActivityState, float | None, str]:
        """Aggregate person & cue evidence at one table into (activity_state, max_cue_conf, reason)."""
        self._prune_history(timestamp)

        if not unambiguous_assignments and not ambiguous_assignments:
            return "NOT_PLAYING", None, "EMPTY_TABLE"

        if not unambiguous_assignments and ambiguous_assignments:
            return "UNKNOWN", None, "AMBIGUOUS_ZONE"

        analyses = [
            self.analyze_person(assign.detection, table, cue_detections, timestamp)
            for assign in unambiguous_assignments
        ]

        playing = [a for a in analyses if a.activity == "PLAYING"]
        if playing:
            cue_confs = [a.cue_confidence for a in playing if a.cue_confidence is not None]
            return "PLAYING", (max(cue_confs) if cue_confs else None), "PLAYING_ACTIVE"

        if any(a.activity == "NOT_PLAYING" for a in analyses) and not any(a.activity == "UNKNOWN" for a in analyses):
            reason = "CLEANING_MOTION" if any(a.cleaning_motion for a in analyses) else "SPECTATOR_OR_CLEANING"
            return "NOT_PLAYING", None, reason

        return "UNKNOWN", None, "BBOX_ONLY"
