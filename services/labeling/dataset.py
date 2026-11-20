"""Turn labeled clips (clips_index.json + labels_final.jsonl) into fixed-size skeleton arrays.

Pure numpy; no OpenCV/Ultralytics. Coordinates stay in the normalized 0..1 frame space of the
index, so x/y are scaled by the same factor (aspect ratio of the camera is not restored).
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from services.labeling.windows import CORE_LABELS

NUM_KEYPOINTS = 17
L_SHOULDER, R_SHOULDER, L_HIP, R_HIP = 5, 6, 11, 12


def _center(kp: np.ndarray, bbox: Sequence[float], min_conf: float) -> np.ndarray:
    for pair in ((L_HIP, R_HIP), (L_SHOULDER, R_SHOULDER)):
        pts = kp[list(pair)]
        if (pts[:, 2] >= min_conf).all():
            return pts[:, :2].mean(axis=0)
    return np.array([(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2])


def clip_to_array(entry: dict[str, Any], length: int = 24, min_conf: float = 0.3) -> np.ndarray | None:
    """Return (length, 17, 3) [x, y, conf]: centered on hips, scaled by person height, resampled.

    Frames without keypoints are filled from the nearest frame that has them; None when no frame has any.
    """
    frames = []
    for kps, bbox in zip(entry["keypoints"], entry["bboxes"]):
        if not kps or len(kps) != NUM_KEYPOINTS:
            frames.append(None)
            continue
        kp = np.asarray(kps, dtype=np.float32)
        height = max(float(bbox[3] - bbox[1]), 1e-3)
        out = kp.copy()
        out[:, :2] = (kp[:, :2] - _center(kp, bbox, min_conf)) / height
        out[kp[:, 2] < min_conf, :2] = 0.0
        frames.append(out)
    valid = [i for i, f in enumerate(frames) if f is not None]
    if not valid:
        return None
    filled = [frames[min(valid, key=lambda j: abs(j - i))] for i in range(len(frames))]
    pick = np.linspace(0, len(filled) - 1, length).round().astype(int)
    return np.stack([filled[i] for i in pick])


def assign_splits(clips: dict[str, dict[str, Any]], test_camera: str, val_video: str | None) -> dict[str, str]:
    """Split by camera/video, never by clip: one camera is test, optionally one video is val."""
    split = {}
    for cid, entry in clips.items():
        if entry["camera_id"] == test_camera:
            split[cid] = "test"
        elif val_video is not None and entry["video"] == val_video:
            split[cid] = "val"
        else:
            split[cid] = "train"
    return split


def build_dataset(index: dict[str, dict[str, Any]], labels: dict[str, str], test_camera: str,
                  val_video: str | None = None, length: int = 24) -> dict[str, np.ndarray]:
    rows = []
    for cid in sorted(labels):
        label = labels[cid]
        if cid not in index or label not in CORE_LABELS:
            continue
        arr = clip_to_array(index[cid], length)
        if arr is not None:
            rows.append((cid, label, arr))
    if not rows:
        raise ValueError("không có clip nào dùng được")
    subset = {cid: index[cid] for cid, _, _ in rows}
    split = assign_splits(subset, test_camera, val_video)
    return {
        "x": np.stack([a for _, _, a in rows]),
        "y": np.array([CORE_LABELS.index(l) for _, l, _ in rows], dtype=np.int64),
        "clip_id": np.array([c for c, _, _ in rows]),
        "camera": np.array([index[c]["camera_id"] for c, _, _ in rows]),
        "video": np.array([index[c]["video"] for c, _, _ in rows]),
        "split": np.array([split[c] for c, _, _ in rows]),
        "label_names": np.array(CORE_LABELS),
    }


FLIP_PAIRS = ((1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16))


def augment(x: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """One light augmentation of a (T, 17, 3) clip: random mirror, scale, rotation and keypoint jitter."""
    out = x.copy()
    if rng.random() < 0.5:
        out[:, :, 0] *= -1
        for a, b in FLIP_PAIRS:
            out[:, [a, b]] = out[:, [b, a]]
    angle = np.deg2rad(rng.uniform(-8, 8))
    c, s = np.cos(angle), np.sin(angle)
    xy = out[:, :, :2] @ np.array([[c, -s], [s, c]], dtype=np.float32).T
    visible = out[:, :, 2:3] > 0
    out[:, :, :2] = np.where(visible, xy * rng.uniform(0.9, 1.1) + rng.normal(0, 0.01, xy.shape), 0.0)
    return out.astype(np.float32)


def class_weights(y: np.ndarray, num_classes: int) -> np.ndarray:
    """Inverse-frequency weights, normalized to mean 1 over the classes present (0 for absent classes)."""
    counts = np.bincount(y, minlength=num_classes).astype(np.float64)
    w = np.where(counts > 0, counts.sum() / (num_classes * np.maximum(counts, 1)), 0.0)
    return (w / w[counts > 0].mean()).astype(np.float32)


def balance_train(x: np.ndarray, y: np.ndarray, seed: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Oversample minority classes up to the largest class using augmented copies.

    Only for the TRAIN split; val/test must stay untouched. Returns (x, y, is_augmented).
    """
    rng = np.random.default_rng(seed)
    target = int(np.bincount(y).max())
    xs, ys, aug = [x], [y], [np.zeros(len(y), dtype=bool)]
    for cls in np.unique(y):
        idx = np.flatnonzero(y == cls)
        need = target - len(idx)
        if need > 0:
            picks = rng.choice(idx, size=need, replace=True)
            xs.append(np.stack([augment(x[i], rng) for i in picks]))
            ys.append(np.full(need, cls, dtype=y.dtype))
            aug.append(np.ones(need, dtype=bool))
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(aug)
