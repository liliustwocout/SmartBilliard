"""Measure real decoded frames through inference, mapping, overlays and JPEG.

This unpaced benchmark measures capacity, not real-time playback or accuracy.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2
import numpy as np

from services.vision.adapters import FileVideoSource
from services.vision.annotator import draw_frame_annotations
from services.vision.detector import YoloCueDetector, YoloPoseDetector
from services.vision.mapper import TableZoneMapper
from services.vision.performance import VisionPerformanceConfig
from services.vision.pipeline import VisionPipeline


def benchmark(video: Path, zones: Path, *, frames: int = 120, warmup: int = 10,
              gpu: bool = True, performance: VisionPerformanceConfig | None = None) -> dict:
    if frames < 1 or warmup < 0:
        raise ValueError("frames must be positive and warmup non-negative")
    cfg = performance or VisionPerformanceConfig()
    cv2.setNumThreads(cfg.opencv_threads)
    source = FileVideoSource(video, loop=False, decoder_threads=cfg.decoder_threads)
    pose = YoloPoseDetector(ROOT / "models/yolov8n-pose.onnx", prefer_gpu=gpu, dml_device_id=cfg.dml_device_id)
    cue = YoloCueDetector(ROOT / "models/yolov8n-cue.onnx", prefer_gpu=gpu,
                          dml_device_id=cfg.dml_device_id, enabled=cfg.cue_enabled)
    if not pose.is_ready or (cfg.cue_enabled and not cue.is_ready):
        source.close()
        raise RuntimeError("Benchmark requires the enabled real ONNX models")
    mapper = TableZoneMapper.from_file(zones)
    pipeline = VisionPipeline(source, detector=pose, cue_detector=cue, mapper=mapper)
    durations: list[float] = []
    people = cues = 0
    try:
        for index in range(frames + warmup):
            started = time.perf_counter()
            ok, frame, detections, summaries = pipeline.process_frame_for_tables(timestamp=index / source.fps)
            if not ok or frame is None:
                break
            if frame.shape[1] > cfg.preview_width:
                scale = cfg.preview_width / frame.shape[1]
                frame = cv2.resize(frame, (cfg.preview_width, round(frame.shape[0] * scale)))
            frame = draw_frame_annotations(frame, detections=detections, summaries=summaries, config=mapper.config)
            encoded, _ = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, cfg.jpeg_quality])
            if not encoded:
                raise RuntimeError("JPEG encoding failed")
            if index >= warmup:
                durations.append(time.perf_counter() - started)
                people += sum(item.kind == "person" for item in detections)
                cues += sum(item.kind == "cue" for item in detections)
    finally:
        source.close()
    if not durations:
        raise RuntimeError("No measured frames")
    return {"video": str(video.resolve()), "source_fps": source.fps, "frames": len(durations),
            "warmup_frames": warmup, "pose_backend": pose.backend_label, "cue_backend": cue.backend_label,
            "input_size": [640, 640], "preview_width": cfg.preview_width,
            "processing_fps": round(len(durations) / sum(durations), 2),
            "p50_ms": round(float(np.percentile(durations, 50)) * 1000, 2),
            "p95_ms": round(float(np.percentile(durations, 95)) * 1000, 2),
            "person_detections": people, "cue_detections": cues,
            "includes": ["decode", "pose", "cue_if_people" if cfg.cue_enabled else "cue_disabled", "tracking", "mapping", "overlay", "JPEG"],
            "excludes": ["SQLite callbacks", "HTTP delivery", "browser rendering"],
            "unpaced": True, "accuracy_evaluated": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--zones", type=Path, default=ROOT / "configs/zones.json")
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--opencv-cpu", action="store_true")
    parser.add_argument("--with-cue", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with (ROOT / "configs/vision.toml").open("rb") as file:
        performance = VisionPerformanceConfig.model_validate(tomllib.load(file))
    if args.with_cue:
        performance = performance.model_copy(update={"cue_enabled": True})
    result = benchmark(args.video, args.zones, frames=args.frames, gpu=not args.opencv_cpu, performance=performance)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
