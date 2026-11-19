"""Fast-forward video evaluator & benchmark for SmartBilliard Pose + Cue + FSM pipeline.

Runs VisionPipeline + TableZoneMapper + Temporal FSM using the video's internal
timestamp (frame_idx / video_fps), so a 6-minute video can be evaluated in seconds.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import tomllib
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.vision.adapters import FileVideoSource
from services.vision.annotator import draw_frame_annotations
from services.vision.calibration import load_calibration_config
from services.vision.decision import DecisionConfig, Memory, advance
from services.vision.detector import YoloCueDetector, YoloPoseDetector
from services.vision.mapper import TableZoneMapper
from services.vision.pipeline import VisionPipeline
from services.vision.tracker import ByteTracker


def generate_synthetic_demo_video(
    output_path: Path,
    *,
    duration_seconds: float = 340.0,
    fps: float = 6.0,
    width: int = 960,
    height: int = 540,
) -> Path:
    """Create a lightweight synthetic MP4 clip showing 2 billiard tables over ~5m40s.

    Intended strictly for smoke-testing video I/O, ROI calibration preview, and
    timeline formatting (does not contain real humans or replace real camera clips).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
    total_frames = max(1, int(round(duration_seconds * fps)))

    for idx in range(total_frames):
        t = idx / fps
        frame = np.full((height, width, 3), 24, dtype=np.uint8)

        # Draw 2 billiard tables matching configs/zones.example.json
        for tid, (x1f, y1f, x2f, y2f) in ((1, (0.10, 0.20, 0.42, 0.75)), (2, (0.58, 0.20, 0.90, 0.75))):
            p1 = (int(x1f * width), int(y1f * height))
            p2 = (int(x2f * width), int(y2f * height))
            cv2.rectangle(frame, p1, p2, (46, 108, 62), -1)
            cv2.rectangle(frame, p1, p2, (74, 145, 92), 4)
            cv2.putText(frame, f"TABLE {tid:02}", (p1[0] + 16, p1[1] + 34), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (220, 240, 225), 2)

        phase = "EMPTY"
        if 10 <= t < 25:
            phase = "SPECTATOR NEAR TABLE 1"
        elif 25 <= t < 340:
            phase = "SIMULATED ACTIVITY PHASE"

        cv2.putText(
            frame,
            f"SYNTHETIC DEMO VIDEO | t={int(t // 60):02d}:{int(t % 60):02d} | {phase}",
            (24, 34),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (235, 235, 235),
            2,
        )
        writer.write(frame)

    writer.release()
    return output_path


def load_decision_config(path: Path) -> DecisionConfig:
    if path.exists():
        with path.open("rb") as fh:
            return DecisionConfig.model_validate(tomllib.load(fh))
    return DecisionConfig()


def evaluate_video(
    video_path: Path,
    *,
    zones_path: Path = Path("configs/zones.json"),
    fallback_zones_path: Path = Path("configs/zones.example.json"),
    pose_model_path: Path = Path("models/yolov8n-pose.onnx"),
    fallback_person_model_path: Path = Path("models/yolov8n.onnx"),
    cue_model_path: Path = Path("models/yolov8n-cue.onnx"),
    decision_config_path: Path = Path("configs/decision.toml"),
    target_fps: float = 6.0,
    prefer_gpu: bool = True,
    output_video: Path | None = None,
) -> dict:
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    cfg = load_calibration_config(zones_path, fallback_zones_path)
    decision_cfg = load_decision_config(decision_config_path)

    source = FileVideoSource(video_path, camera_id="video-eval", loop=False, realtime_pacing=False)
    detector = YoloPoseDetector(
        pose_model_path,
        fallback_model_path=fallback_person_model_path,
        prefer_gpu=prefer_gpu,
    )
    cue_detector = YoloCueDetector(cue_model_path, prefer_gpu=prefer_gpu)
    mapper = TableZoneMapper(cfg)
    pipeline = VisionPipeline(
        source=source,
        detector=detector,
        tracker=ByteTracker(),
        mapper=mapper,
        cue_detector=cue_detector,
    )

    video_fps = max(1.0, source.fps)
    stride = max(1, int(round(video_fps / max(1.0, target_fps))))

    writer: cv2.VideoWriter | None = None
    if output_video is not None:
        output_video.parent.mkdir(parents=True, exist_ok=True)
        w, h = source.resolution
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(output_video), fourcc, max(1.0, video_fps / stride), (w or 960, h or 540))

    memories: dict[int, Memory] = {t.table_id: Memory() for t in cfg.tables}
    stats: dict[int, dict] = {
        t.table_id: {
            "PLAYING_seconds": 0.0,
            "NOT_PLAYING_seconds": 0.0,
            "UNKNOWN_seconds": 0.0,
            "first_needs_confirmation_at_s": None,
            "first_unbilled_alert_at_s": None,
            "final_state": "EMPTY",
            "unbilled_alert_triggered": False,
        }
        for t in cfg.tables
    }

    dt = stride / video_fps
    raw_idx = 0
    processed_frames = 0
    wall_start = time.monotonic()

    try:
        while True:
            if (raw_idx % stride) != 0:
                if source._cap is not None and not source._cap.grab():
                    break
                raw_idx += 1
                continue

            ts = raw_idx / video_fps
            ok, frame, detections, summaries = pipeline.process_frame_for_tables(timestamp=ts)
            if not ok or frame is None:
                break

            processed_frames += 1
            for tid, summary in summaries.items():
                dec = advance(
                    memories[tid],
                    summary.to_observation(),
                    ts,
                    decision_cfg,
                    active=False,
                    auto_open=False,
                    cue_detector_ready=cue_detector.validated,
                )
                memories[tid] = dec.memory
                st = stats[tid]
                st[f"{summary.activity_state}_seconds"] += dt
                st["final_state"] = dec.memory.state
                if dec.memory.state == "NEEDS_CONFIRMATION" and st["first_needs_confirmation_at_s"] is None:
                    st["first_needs_confirmation_at_s"] = round(ts, 2)
                if dec.memory.unbilled_alert:
                    st["unbilled_alert_triggered"] = True
                    if st["first_unbilled_alert_at_s"] is None:
                        st["first_unbilled_alert_at_s"] = round(ts, 2)

            if writer is not None:
                annotated = draw_frame_annotations(
                    frame,
                    detections=detections,
                    summaries=summaries,
                    config=cfg,
                    fps=target_fps,
                    source_type="VIDEO",
                    camera_id=video_path.name,
                )
                writer.write(annotated)

            raw_idx += 1
    finally:
        source.close()
        if writer is not None:
            writer.release()

    wall_elapsed = max(1e-6, time.monotonic() - wall_start)
    for st in stats.values():
        for key in ("PLAYING_seconds", "NOT_PLAYING_seconds", "UNKNOWN_seconds"):
            st[key] = round(st[key], 2)

    return {
        "video_path": str(video_path),
        "video_fps": round(video_fps, 2),
        "sampled_fps": round(video_fps / stride, 2),
        "processed_frames": processed_frames,
        "video_duration_seconds": round(raw_idx / video_fps, 2),
        "wall_seconds": round(wall_elapsed, 3),
        "processing_fps": round(processed_frames / wall_elapsed, 2),
        "person_pose_model_ready": detector.is_ready,
        "person_pose_backend": detector.backend_label,
        "cue_model_ready": cue_detector.is_ready,
        "cue_backend": cue_detector.backend_label,
        "unbilled_alert_threshold_seconds": decision_cfg.unbilled_alert_seconds,
        "tables": stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fast-forward video evaluation for SmartBilliard AI + FSM")
    parser.add_argument("--video", type=Path, default=Path("data/recordings/demo.mp4"))
    parser.add_argument("--zones", type=Path, default=Path("configs/zones.json"))
    parser.add_argument("--pose-model", type=Path, default=Path("models/yolov8n-pose.onnx"))
    parser.add_argument("--cue-model", type=Path, default=Path("models/yolov8n-cue.onnx"))
    parser.add_argument("--decision-config", type=Path, default=Path("configs/decision.toml"))
    parser.add_argument("--target-fps", type=float, default=6.0)
    parser.add_argument("--cpu", action="store_true", help="Force CPU inference instead of GPU FP16")
    parser.add_argument("--output-video", type=Path, default=None, help="Optional annotated output MP4 path")
    parser.add_argument("--report-json", type=Path, default=None, help="Optional path to save JSON report")
    parser.add_argument(
        "--generate-demo-video",
        action="store_true",
        help="Generate a synthetic demo video at --video before evaluating",
    )
    parser.add_argument("--demo-seconds", type=float, default=340.0, help="Duration of synthetic demo video")
    args = parser.parse_args()

    if args.generate_demo_video:
        generate_synthetic_demo_video(args.video, duration_seconds=args.demo_seconds, fps=args.target_fps)
        print(f"Generated synthetic demo video -> {args.video}")

    report = evaluate_video(
        args.video,
        zones_path=args.zones,
        pose_model_path=args.pose_model,
        cue_model_path=args.cue_model,
        decision_config_path=args.decision_config,
        target_fps=args.target_fps,
        prefer_gpu=not args.cpu,
        output_video=args.output_video,
    )

    if not report["person_pose_model_ready"]:
        print(
            "[warning] Person/Pose ONNX model not found in models/. "
            "Run `python scripts/train_cue.py --export-pose --skip-train` to export models/yolov8n-pose.onnx.",
            file=sys.stderr,
        )

    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
