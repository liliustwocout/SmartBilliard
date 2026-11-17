"""Utility script to record a test video clip from a USB camera or webcam (SB-15).

Usage:
    python scripts/record_camera.py --seconds 15 --output data/recordings/my_test.mp4
"""
import argparse
import time
from pathlib import Path

import cv2


def record(camera_index: int, duration_sec: float, output_path: Path, fps: float = 20.0) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"Error: Could not open camera with index {camera_index}")
        return

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    print(f"Recording {duration_sec}s from camera {camera_index} ({width}x{height} @ {fps}fps)...")
    print(f"Saving to: {output_path}")

    start_time = time.monotonic()
    frame_count = 0

    while time.monotonic() - start_time < duration_sec:
        ret, frame = cap.read()
        if not ret or frame is None:
            print("Warning: Failed to grab frame")
            break
        out.write(frame)
        frame_count += 1
        time.sleep(1.0 / fps)

    cap.release()
    out.release()
    elapsed = time.monotonic() - start_time
    print(f"Done! Recorded {frame_count} frames in {elapsed:.1f}s.")
    print(f"To use this video in SmartBilliard, set in your .env:")
    print(f"CAMERA_SOURCE={output_path}")


def main():
    parser = argparse.ArgumentParser(description="Record test video from webcam")
    parser.add_argument("--camera", type=int, default=0, help="Camera device index (default: 0)")
    parser.add_argument("--seconds", type=float, default=15.0, help="Recording duration in seconds (default: 15.0)")
    parser.add_argument("--output", type=str, default="data/recordings/my_test.mp4", help="Output file path")
    parser.add_argument("--fps", type=float, default=20.0, help="Frames per second (default: 20.0)")
    args = parser.parse_args()

    record(args.camera, args.seconds, Path(args.output), args.fps)


if __name__ == "__main__":
    main()
