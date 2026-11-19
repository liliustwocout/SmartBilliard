"""Extract non-redundant frames from billiard hall videos for cue dataset labeling.

Supports splitting by video file (recommended) or by time-separated segments when
a single video is provided, preventing temporal data leakage between train/val/test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np

VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".webm"}


def collect_videos(inputs: list[Path]) -> list[Path]:
    videos: list[Path] = []
    for item in inputs:
        if item.is_file() and item.suffix.lower() in VIDEO_EXTS:
            videos.append(item)
        elif item.is_dir():
            videos.extend(sorted(p for p in item.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS))
    return sorted(set(videos))


def assign_splits_for_videos(videos: list[Path], val_ratio: float = 0.15, test_ratio: float = 0.15) -> dict[Path, str]:
    """Deterministically assign each video file to train, val, or test."""
    n = len(videos)
    if n == 0:
        return {}
    if n == 1:
        return {videos[0]: "SEGMENTED"}
    if n == 2:
        return {videos[0]: "train", videos[1]: "val"}

    n_test = max(1, round(n * test_ratio))
    n_val = max(1, round(n * val_ratio))
    if (n - n_val - n_test) <= 0:
        n_val = 1
        n_test = 1 if n >= 3 else 0
    mapping: dict[Path, str] = {}
    for idx, vid in enumerate(videos):
        if idx < n - n_val - n_test:
            mapping[vid] = "train"
        elif idx < n - n_test:
            mapping[vid] = "val"
        else:
            mapping[vid] = "test"
    return mapping


def _segment_split(progress: float, guard_gap: float = 0.03) -> str | None:
    """Split a single video chronologically with buffer gaps so adjacent frames never leak."""
    if progress < 0.70 - guard_gap:
        return "train"
    if progress < 0.70:
        return None
    if progress < 0.85 - guard_gap:
        return "val"
    if progress < 0.85:
        return None
    return "test"


def extract_dataset(
    inputs: list[Path],
    output_dir: Path,
    *,
    interval_seconds: float = 2.0,
    min_diff: float = 2.5,
    max_frames_per_video: int = 500,
    init_empty_labels: bool = False,
) -> dict:
    videos = collect_videos(inputs)
    if not videos:
        raise FileNotFoundError(f"No video files ({', '.join(sorted(VIDEO_EXTS))}) found in {inputs}")

    for split in ("train", "val", "test"):
        (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    video_splits = assign_splits_for_videos(videos)
    manifest_clips: list[dict] = []
    counts = {"train": 0, "val": 0, "test": 0}

    for vid_idx, video_path in enumerate(videos):
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            print(f"[warn] Cannot open video: {video_path}", file=sys.stderr)
            continue

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        step_frames = max(1, int(round(fps * interval_seconds)))
        mode_split = video_splits[video_path]

        prev_thumb: np.ndarray | None = None
        saved = 0
        frame_idx = 0
        clip_hash = hashlib.sha256(str(video_path.resolve()).encode("utf-8")).hexdigest()[:10]
        stem = f"{video_path.stem}_{clip_hash}"

        while saved < max_frames_per_video:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ok, frame = cap.read()
            if not ok or frame is None:
                break

            if mode_split == "SEGMENTED":
                progress = (frame_idx / total_frames) if total_frames > 0 else 0.0
                split = _segment_split(progress)
                if split is None:
                    frame_idx += step_frames
                    continue
            else:
                split = mode_split

            gray_thumb = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (160, 90))
            if prev_thumb is not None:
                mean_diff = float(np.mean(np.abs(gray_thumb.astype(np.float32) - prev_thumb.astype(np.float32))))
                if mean_diff < min_diff:
                    frame_idx += step_frames
                    continue
            prev_thumb = gray_thumb

            img_name = f"{stem}_f{frame_idx:06d}.jpg"
            img_out = output_dir / "images" / split / img_name
            cv2.imwrite(str(img_out), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])

            if init_empty_labels:
                lbl_out = output_dir / "labels" / split / f"{stem}_f{frame_idx:06d}.txt"
                if not lbl_out.exists():
                    lbl_out.write_text("", encoding="utf-8")

            counts[split] += 1
            saved += 1
            frame_idx += step_frames

        cap.release()
        manifest_clips.append(
            {
                "clip_id": f"clip-{vid_idx + 1:03d}",
                "source_file": video_path.name,
                "split": mode_split,
                "fps": round(fps, 2),
                "frames_extracted": saved,
            }
        )

    dataset_yaml = output_dir / "dataset.yaml"
    dataset_yaml.write_text(
        "\n".join(
            [
                f"path: {output_dir.resolve().as_posix()}",
                "train: images/train",
                "val: images/val",
                "test: images/test",
                "names:",
                "  0: cue",
                "",
            ]
        ),
        encoding="utf-8",
    )

    manifest = {
        "dataset_id": output_dir.name,
        "split_counts": counts,
        "total_images": sum(counts.values()),
        "interval_seconds": interval_seconds,
        "min_diff": min_diff,
        "clips": manifest_clips,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract training frames from existing billiard videos")
    parser.add_argument(
        "--input",
        nargs="+",
        default=["data/datasets/cue_v1/raw_videos"],
        help="Input video files or directories",
    )
    parser.add_argument("--output", default="data/datasets/cue_v1", help="Output YOLO dataset directory")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between sampled frames (default: 2.0)")
    parser.add_argument("--min-diff", type=float, default=2.5, help="Minimum grayscale delta to skip static duplicates")
    parser.add_argument("--max-per-video", type=int, default=500, help="Max extracted frames per video")
    parser.add_argument(
        "--init-empty-labels",
        action="store_true",
        help="Create empty .txt label files alongside images (useful before hard-negative review)",
    )
    args = parser.parse_args()

    manifest = extract_dataset(
        [Path(p) for p in args.input],
        Path(args.output),
        interval_seconds=args.interval,
        min_diff=args.min_diff,
        max_frames_per_video=args.max_per_video,
        init_empty_labels=args.init_empty_labels,
    )
    print(f"Extracted {manifest['total_images']} images -> {args.output}")
    print(f"Split counts: {manifest['split_counts']}")
    print(f"Dataset YAML: {Path(args.output) / 'dataset.yaml'}")


if __name__ == "__main__":
    main()
