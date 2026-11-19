"""Lightweight ByteTrack Multi-Object Tracker in pure Python + NumPy (SB-11).

Key capabilities:
- Two-stage association (high-confidence + low-confidence) for occlusion resilience.
- Greedy IoU bipartite matching.
- Maintains persistent track_id when players walk, bend over, or stand still.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from services.vision.detector import PersonDetection

logger = logging.getLogger("smartbilliard.vision.tracker")


def calculate_iou(box_a: tuple[float, float, float, float], box_b: tuple[float, float, float, float]) -> float:
    """Compute IoU between two bounding boxes (x1, y1, x2, y2)."""
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union_area = area_a + area_b - inter_area

    if union_area <= 0.0:
        return 0.0
    return inter_area / union_area


@dataclass
class STrack:
    track_id: int
    bbox: tuple[float, float, float, float]
    confidence: float
    foot_anchor: tuple[float, float]
    keypoints: tuple[tuple[float, float, float], ...] | None = None
    state: Literal["NEW", "TRACKED", "LOST", "REMOVED"] = "NEW"
    age: int = 0
    time_since_update: int = 0
    hits: int = 1

    def update(self, det: PersonDetection) -> None:
        # Smooth bounding box with exponential moving average
        alpha = 0.7
        ox1, oy1, ox2, oy2 = self.bbox
        nx1, ny1, nx2, ny2 = det.bbox

        smooth_box = (
            alpha * nx1 + (1 - alpha) * ox1,
            alpha * ny1 + (1 - alpha) * oy1,
            alpha * nx2 + (1 - alpha) * ox2,
            alpha * ny2 + (1 - alpha) * oy2,
        )
        self.bbox = smooth_box
        self.confidence = det.confidence
        self.keypoints = det.keypoints
        if det.keypoints is not None:
            self.foot_anchor = det.foot_anchor
        else:
            self.foot_anchor = ((smooth_box[0] + smooth_box[2]) / 2.0, smooth_box[3])
        self.state = "TRACKED"
        self.time_since_update = 0
        self.hits += 1
        self.age += 1

    def mark_missed(self) -> None:
        self.time_since_update += 1
        self.age += 1
        if self.state == "NEW" or self.time_since_update > 2:
            self.state = "LOST"


class ByteTracker:
    """ByteTrack two-stage data association tracker."""

    def __init__(
        self,
        *,
        high_threshold: float = 0.5,
        low_threshold: float = 0.15,
        match_threshold: float = 0.3,
        max_lost_frames: int = 30,
    ) -> None:
        self.high_threshold = high_threshold
        self.low_threshold = low_threshold
        self.match_threshold = match_threshold
        self.max_lost_frames = max_lost_frames

        self._next_id: int = 1
        self.tracked_stracks: list[STrack] = []
        self.lost_stracks: list[STrack] = []

    def reset(self) -> None:
        """Drop all tracks, e.g. after inference was paused and old tracks are stale."""
        self._next_id = 1
        self.tracked_stracks = []
        self.lost_stracks = []

    def _match_tracks(
        self,
        tracks: list[STrack],
        detections: list[PersonDetection],
        iou_threshold: float,
    ) -> tuple[list[tuple[int, int]], list[int], list[int]]:
        """Greedy matching between tracks and detections based on IoU."""
        if not tracks or not detections:
            return [], list(range(len(tracks))), list(range(len(detections)))

        # Build IoU matrix
        num_tracks = len(tracks)
        num_dets = len(detections)
        iou_matrix = np.zeros((num_tracks, num_dets), dtype=np.float32)

        for t_idx, track in enumerate(tracks):
            for d_idx, det in enumerate(detections):
                iou_matrix[t_idx, d_idx] = calculate_iou(track.bbox, det.bbox)

        matches: list[tuple[int, int]] = []
        matched_tracks: set[int] = set()
        matched_dets: set[int] = set()

        # Sort all pairs by descending IoU
        flat_indices = np.argsort(-iou_matrix, axis=None)
        for idx in flat_indices:
            t_idx = idx // num_dets
            d_idx = idx % num_dets
            val = iou_matrix[t_idx, d_idx]
            if val < iou_threshold:
                break
            if t_idx in matched_tracks or d_idx in matched_dets:
                continue

            matches.append((t_idx, d_idx))
            matched_tracks.add(t_idx)
            matched_dets.add(d_idx)

        unmatched_tracks = [i for i in range(num_tracks) if i not in matched_tracks]
        unmatched_dets = [j for j in range(num_dets) if j not in matched_dets]
        return matches, unmatched_tracks, unmatched_dets

    def update(self, detections: list[PersonDetection]) -> list[PersonDetection]:
        """Update tracker with detections from current frame."""
        # 1. Split detections into high and low confidence
        high_dets: list[PersonDetection] = []
        low_dets: list[PersonDetection] = []

        for det in detections:
            if det.confidence >= self.high_threshold:
                high_dets.append(det)
            elif det.confidence >= self.low_threshold:
                low_dets.append(det)

        # Active candidates = currently tracked + lost
        active_candidates = self.tracked_stracks + self.lost_stracks

        # Stage 1: Match high-confidence detections with active tracks
        matches_1, unmatched_tracks_1, unmatched_dets_1 = self._match_tracks(
            active_candidates, high_dets, self.match_threshold
        )

        for t_idx, d_idx in matches_1:
            active_candidates[t_idx].update(high_dets[d_idx])

        # Stage 2: Match remaining tracks with low-confidence detections
        remaining_tracks = [active_candidates[i] for i in unmatched_tracks_1]
        matches_2, unmatched_tracks_2, _ = self._match_tracks(
            remaining_tracks, low_dets, self.match_threshold
        )

        for t_idx, d_idx in matches_2:
            remaining_tracks[t_idx].update(low_dets[d_idx])

        # Tracks that still weren't matched in Stage 2 mark as missed
        unmatched_final_tracks = [remaining_tracks[i] for i in unmatched_tracks_2]
        for track in unmatched_final_tracks:
            track.mark_missed()

        # Stage 3: Create new tracks for unmatched high-confidence detections
        new_tracks: list[STrack] = []
        for d_idx in unmatched_dets_1:
            det = high_dets[d_idx]
            new_track = STrack(
                track_id=self._next_id,
                bbox=det.bbox,
                confidence=det.confidence,
                foot_anchor=det.foot_anchor,
                keypoints=det.keypoints,
                state="TRACKED",
            )
            self._next_id += 1
            new_tracks.append(new_track)

        # Re-organize pools
        all_pool = active_candidates + new_tracks
        self.tracked_stracks = []
        self.lost_stracks = []

        for track in all_pool:
            if track.state == "TRACKED":
                self.tracked_stracks.append(track)
            elif track.state in ("NEW", "LOST"):
                if track.time_since_update <= self.max_lost_frames:
                    self.lost_stracks.append(track)
                else:
                    track.state = "REMOVED"

        # Return tracked detections
        output: list[PersonDetection] = []
        for track in self.tracked_stracks:
            output.append(
                PersonDetection(
                    bbox=track.bbox,
                    confidence=track.confidence,
                    foot_anchor=track.foot_anchor,
                    class_id=0,
                    track_id=track.track_id,
                    keypoints=track.keypoints,
                )
            )
        return output
