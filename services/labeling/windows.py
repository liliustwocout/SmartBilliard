"""Pure logic for cutting per-person tracklets into fixed-length labeling windows
and for assigning clips to labelers. No OpenCV/Ultralytics dependency."""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass
from typing import Sequence

CORE_LABELS = ("SHOOTING", "AIMING", "WATCHING", "WALKING")
EXTRA_LABELS = ("UNSURE", "INVALID")
ALL_LABELS = CORE_LABELS + EXTRA_LABELS


@dataclass(frozen=True)
class Sample:
    """One tracked person at one sampled video frame (coordinates normalized 0..1)."""
    t: float
    frame_index: int
    bbox: tuple[float, float, float, float]
    keypoints: tuple[tuple[float, float, float], ...] | None = None


@dataclass(frozen=True)
class Window:
    track_id: int
    samples: tuple[Sample, ...]

    @property
    def t_start(self) -> float:
        return self.samples[0].t

    @property
    def t_end(self) -> float:
        return self.samples[-1].t


def _runs(samples: Sequence[Sample], max_gap_s: float) -> list[list[Sample]]:
    runs: list[list[Sample]] = []
    for sample in sorted(samples, key=lambda s: s.t):
        if runs and sample.t - runs[-1][-1].t <= max_gap_s:
            runs[-1].append(sample)
        else:
            runs.append([sample])
    return runs


def build_windows(track_samples: dict[int, list[Sample]], *, window_s: float = 3.0,
                  stride_s: float = 3.0, sample_fps: float = 8.0, min_fill: float = 0.75,
                  max_gap_s: float = 0.6, min_bbox_height: float = 0.12) -> list[Window]:
    """Cut every continuous run of a track into windows of ``window_s`` seconds.

    A window needs at least ``min_fill`` of the expected samples, and the person must be
    tall enough in frame (``min_bbox_height``) to be judged by a human.
    """
    if window_s <= 0 or stride_s <= 0 or sample_fps <= 0:
        raise ValueError("window_s, stride_s and sample_fps must be positive")
    expected = max(1, round(window_s * sample_fps))
    windows: list[Window] = []
    for track_id, samples in track_samples.items():
        for run in _runs(samples, max_gap_s):
            start = run[0].t
            while start + window_s - 1.0 / sample_fps <= run[-1].t + 1e-9:
                chunk = [s for s in run if start <= s.t < start + window_s]
                tall = sum(1 for s in chunk if (s.bbox[3] - s.bbox[1]) >= min_bbox_height)
                if len(chunk) >= expected * min_fill and tall >= len(chunk) * min_fill:
                    windows.append(Window(track_id, tuple(chunk)))
                start += stride_s
    return windows


def bend_score(window: Window, *, min_conf: float = 0.3, min_samples: int = 6,
               max_move: float = 0.2) -> float | None:
    """Heuristic 0..1 for "body bent over a table" (candidate AIMING/SHOOTING), higher = more bent.

    Uses the shoulder-to-hip distance relative to bbox height (COCO keypoints 5,6,11,12): it shrinks
    when someone leans over the cue. Only a ranking aid for sampling, never a label. Returns None when
    keypoints are missing or the person travels more than ``max_move`` (walking).
    """
    ratios: list[float] = []
    centres: list[tuple[float, float]] = []
    for s in window.samples:
        kp = s.keypoints
        height = s.bbox[3] - s.bbox[1]
        if not kp or len(kp) < 13 or height <= 0:
            continue
        pts = [kp[5], kp[6], kp[11], kp[12]]
        if min(p[2] for p in pts) < min_conf:
            continue
        shoulder_y = (pts[0][1] + pts[1][1]) / 2
        hip_y = (pts[2][1] + pts[3][1]) / 2
        ratios.append((hip_y - shoulder_y) / height)
        centres.append(((s.bbox[0] + s.bbox[2]) / 2, (s.bbox[1] + s.bbox[3]) / 2))
    if len(ratios) < min_samples:
        return None
    move = sum(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 for a, b in zip(centres, centres[1:]))
    if move > max_move:
        return None
    mean_ratio = sum(ratios) / len(ratios)
    return max(0.0, min(1.0, 1.0 - mean_ratio / 0.5))


def overlaps_any(video: str, t_start: float, t_end: float,
                 used: Sequence[tuple[str, float, float]]) -> bool:
    """True when [t_start, t_end] overlaps an already-used (video, start, end) span."""
    return any(v == video and t_start < e and t_end > b for v, b, e in used)


def pick_even(items: Sequence, count: int, seed: int = 0) -> list:
    """Random sample of ``count`` items, deterministic for a given seed."""
    if count >= len(items):
        return list(items)
    rng = random.Random(seed)
    return rng.sample(list(items), count)


def assign_clips(clip_ids: Sequence[str], members: Sequence[str], redundancy: int = 2,
                 seed: int = 0) -> dict[str, tuple[str, ...]]:
    """Give each clip to ``redundancy`` different members, spreading the load evenly.

    Rotating through all member combinations keeps every member's workload within one
    clip of the others when the combinations cycle evenly.
    """
    if not 1 <= redundancy <= len(members):
        raise ValueError("redundancy must be between 1 and the number of members")
    if len(set(members)) != len(members):
        raise ValueError("members must be unique")
    combos = list(itertools.combinations(members, redundancy))
    rng = random.Random(seed)
    order = list(clip_ids)
    rng.shuffle(order)
    return {cid: combos[i % len(combos)] for i, cid in enumerate(order)}
