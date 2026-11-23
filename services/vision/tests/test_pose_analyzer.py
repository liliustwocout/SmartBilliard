"""Unit tests for PoseCueAnalyzer, YOLOv8-pose/cue decoding, and video pipeline scripts."""
from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from scripts.evaluate_video import evaluate_video, generate_synthetic_demo_video
from scripts.extract_frames import extract_dataset
from services.vision.calibration import CalibrationConfig, TableZone
from services.vision.contracts import Detection, Keypoint
from services.vision.detector import PersonDetection, YoloCueDetector, YoloPersonDetector
from services.vision.mapper import TableZoneMapper
from services.vision.pose_analyzer import PoseCueAnalyzer


def _make_keypoints(**overrides: tuple[int, tuple[float, float, float]]) -> tuple[Keypoint, ...]:
    kps: list[Keypoint] = [(0.0, 0.0, 0.0)] * 17
    for _, (idx, val) in overrides.items():
        kps[idx] = val
    return tuple(kps)


@pytest.fixture
def table_zone() -> CalibrationConfig:
    return CalibrationConfig(
        camera_id="cam-01",
        tables=[
            TableZone(
                table_id=1,
                enabled=True,
                play_polygon=[[0.15, 0.25], [0.45, 0.25], [0.45, 0.70], [0.15, 0.70]],
                standing_polygon=[[0.05, 0.15], [0.55, 0.15], [0.55, 0.85], [0.05, 0.85]],
            )
        ],
    )


def test_pose_analyzer_detects_playing_with_cue_and_wrist(table_zone: CalibrationConfig):
    mapper = TableZoneMapper(table_zone)
    # Player leaning with wrists near cue directed into play_polygon
    kps = _make_keypoints(
        ls=(5, (0.12, 0.42, 0.9)),
        rs=(6, (0.14, 0.43, 0.9)),
        le=(7, (0.14, 0.45, 0.9)),
        re=(8, (0.16, 0.46, 0.9)),
        lw=(9, (0.18, 0.48, 0.9)),
        rw=(10, (0.15, 0.48, 0.9)),
        lh=(11, (0.10, 0.47, 0.9)),
        rh=(12, (0.11, 0.48, 0.9)),
        la=(15, (0.10, 0.72, 0.9)),
        ra=(16, (0.12, 0.72, 0.9)),
    )
    person = Detection(
        camera_id="cam-01",
        timestamp=1.0,
        kind="person",
        bbox=(0.08, 0.35, 0.20, 0.74),
        confidence=0.92,
        track_id=1,
        foot_anchor=(0.11, 0.72),
        keypoints=kps,
    )
    cue = Detection(
        camera_id="cam-01",
        timestamp=1.0,
        kind="cue",
        bbox=(0.14, 0.46, 0.32, 0.50),
        confidence=0.86,
        cue_angle_deg=12.5,
    )
    _, summaries = mapper.map_frame([person, cue], timestamp=1.0)
    assert summaries[1].activity_state == "PLAYING"
    assert summaries[1].cue_confidence == pytest.approx(0.86)


def test_pose_analyzer_rejects_upright_spectator_even_with_vertical_cue(table_zone: CalibrationConfig):
    mapper = TableZoneMapper(table_zone)
    # Upright spectator outside play_polygon, holding a vertical cue stick
    kps = _make_keypoints(
        ls=(5, (0.08, 0.30, 0.9)),
        rs=(6, (0.12, 0.30, 0.9)),
        le=(7, (0.07, 0.42, 0.9)),
        re=(8, (0.13, 0.42, 0.9)),
        lw=(9, (0.07, 0.52, 0.9)),
        rw=(10, (0.12, 0.52, 0.9)),
        lh=(11, (0.08, 0.52, 0.9)),
        rh=(12, (0.12, 0.52, 0.9)),
        la=(15, (0.08, 0.80, 0.9)),
        ra=(16, (0.12, 0.80, 0.9)),
    )
    spectator = Detection(
        camera_id="cam-01",
        timestamp=1.0,
        kind="person",
        bbox=(0.06, 0.20, 0.14, 0.82),
        confidence=0.90,
        track_id=2,
        foot_anchor=(0.10, 0.80),
        keypoints=kps,
    )
    vertical_cue = Detection(
        camera_id="cam-01",
        timestamp=1.0,
        kind="cue",
        bbox=(0.06, 0.25, 0.08, 0.78),  # tall vertical stick outside play_polygon
        confidence=0.85,
        cue_angle_deg=88.0,
    )
    _, summaries = mapper.map_frame([spectator, vertical_cue], timestamp=1.0)
    assert summaries[1].present is True
    assert summaries[1].activity_state == "NOT_PLAYING"


def test_pose_analyzer_rejects_fast_table_cleaning_motion(table_zone: CalibrationConfig):
    mapper = TableZoneMapper(table_zone)
    for step, x in enumerate((0.10, 0.16, 0.22, 0.28)):
        ts = step * 0.4
        kps = _make_keypoints(
            ls=(5, (x, 0.40, 0.9)),
            rs=(6, (x + 0.04, 0.40, 0.9)),
            lw=(9, (x + 0.02 + (step % 2) * 0.08, 0.46, 0.9)),
            rw=(10, (x + 0.04 + (step % 2) * 0.08, 0.46, 0.9)),
            lh=(11, (x, 0.55, 0.9)),
            rh=(12, (x + 0.04, 0.55, 0.9)),
        )
        cleaner = Detection(
            camera_id="cam-01",
            timestamp=ts,
            kind="person",
            bbox=(x - 0.02, 0.30, x + 0.08, 0.78),
            confidence=0.89,
            track_id=7,
            foot_anchor=(x + 0.02, 0.78),
            keypoints=kps,
        )
        _, summaries = mapper.map_frame([cleaner], timestamp=ts)
    assert summaries[1].activity_state == "NOT_PLAYING"
    assert summaries[1].activity_reason == "CLEANING_MOTION"


def test_pose_and_cue_onnx_output_decoding_on_synthetic_tensors():
    # Mock a (1, 56, 8400) YOLOv8-pose output tensor
    pose_preds = np.zeros((1, 56, 8400), dtype=np.float32)
    pose_preds[0, 0, 0] = 320.0  # cx
    pose_preds[0, 1, 0] = 320.0  # cy
    pose_preds[0, 2, 0] = 120.0  # w
    pose_preds[0, 3, 0] = 240.0  # h
    pose_preds[0, 4, 0] = 0.92   # person conf
    # Set confident left/right ankles (15, 16)
    pose_preds[0, 5 + 15 * 3 : 5 + 15 * 3 + 3, 0] = [300.0, 430.0, 0.9]
    pose_preds[0, 5 + 16 * 3 : 5 + 16 * 3 + 3, 0] = [340.0, 430.0, 0.9]

    person_det = YoloPersonDetector(model_path="models/nonexistent-pose.onnx")
    person_det._net = MagicMock()
    person_det._net.forward.return_value = pose_preds
    person_det.backend_label = "CPU"

    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    persons = person_det.detect(frame)
    assert len(persons) == 1
    assert persons[0].keypoints is not None and len(persons[0].keypoints) == 17
    assert persons[0].foot_anchor == pytest.approx((0.5, 430.0 / 640.0), abs=0.01)

    # Mock a (1, 5, 8400) 1-class YOLOv8 cue output tensor
    cue_preds = np.zeros((1, 5, 8400), dtype=np.float32)
    cue_preds[0, 0, 0] = 320.0
    cue_preds[0, 1, 0] = 300.0
    cue_preds[0, 2, 0] = 180.0
    cue_preds[0, 3, 0] = 24.0
    cue_preds[0, 4, 0] = 0.88

    cue_det = YoloCueDetector(model_path="models/nonexistent-cue.onnx")
    cue_det._net = MagicMock()
    cue_det._net.forward.return_value = cue_preds
    cue_det.backend_label = "CPU"

    cues = cue_det.detect(frame, camera_id="cam-test", timestamp=5.0)
    assert len(cues) == 1
    assert cues[0].kind == "cue"
    assert cues[0].cue_angle_deg is not None and cues[0].cue_angle_deg < 15.0


def test_video_extract_and_evaluate_scripts_end_to_end(tmp_path: Path):
    video_file = tmp_path / "demo_2tables.mp4"
    # Create a tiny synthetic 4-second video with moving bar so duplicate filter keeps frames
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_file), fourcc, 6.0, (320, 240))
    for i in range(24):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.rectangle(frame, (20 + i * 8, 40), (90 + i * 8, 120), (80, 200, 100), -1)
        writer.write(frame)
    writer.release()

    dataset_dir = tmp_path / "cue_v1"
    manifest = extract_dataset(
        [video_file],
        dataset_dir,
        interval_seconds=0.5,
        min_diff=0.5,
        init_empty_labels=True,
    )
    assert manifest["total_images"] >= 3
    assert (dataset_dir / "dataset.yaml").exists()
    assert (dataset_dir / "manifest.json").exists()

    demo_clip = tmp_path / "eval_demo.mp4"
    generate_synthetic_demo_video(demo_clip, duration_seconds=2.0, fps=6.0, width=320, height=240)
    out_vid = tmp_path / "annotated.mp4"
    report = evaluate_video(
        demo_clip,
        zones_path=Path("configs/zones.example.json"),
        pose_model_path=tmp_path / "missing-pose.onnx",
        fallback_person_model_path=tmp_path / "missing-person.onnx",
        cue_model_path=tmp_path / "missing-cue.onnx",
        output_video=out_vid,
    )
    assert report["processed_frames"] >= 10
    assert out_vid.exists() and out_vid.stat().st_size > 500
    assert 1 in report["tables"] and 2 in report["tables"]


def test_pose_analyzer_multi_side_navigation(table_zone: CalibrationConfig):
    mapper = TableZoneMapper(table_zone)
    # Player moves from Left Rail (0.10, 0.45) to Foot Rail (0.30, 0.78)
    positions = [
        (0.10, 0.45),
        (0.12, 0.46),
        (0.20, 0.65),
        (0.30, 0.78),
    ]
    for idx, (fx, fy) in enumerate(positions):
        ts = idx * 0.4
        person = Detection(
            camera_id="cam-01",
            timestamp=ts,
            kind="person",
            bbox=(fx - 0.04, fy - 0.4, fx + 0.04, fy),
            confidence=0.91,
            track_id=5,
            foot_anchor=(fx, fy),
        )
        _, summaries = mapper.map_frame([person], timestamp=ts)

    # After navigating multiple sides of the table
    summary = summaries[1]
    assert summary.activity_state == "PLAYING"
    assert summary.activity_reason == "PLAYER_NAVIGATING"


def test_pose_analyzer_felt_motion_confirms_playing(table_zone: CalibrationConfig):
    table = table_zone.tables[0]
    analyzer = PoseCueAnalyzer()

    # Upright person with spectator posture
    kps = _make_keypoints(
        ls=(5, (0.10, 0.35, 0.9)),
        rs=(6, (0.14, 0.35, 0.9)),
        lh=(11, (0.10, 0.55, 0.9)),
        rh=(12, (0.14, 0.55, 0.9)),
    )
    person = Detection(
        camera_id="cam-01",
        timestamp=1.0,
        kind="person",
        bbox=(0.08, 0.25, 0.16, 0.80),
        confidence=0.90,
        track_id=10,
        foot_anchor=(0.12, 0.80),
        keypoints=kps,
    )
    assign = mapper = MagicMock(detection=person)

    # Without felt motion -> SPECTATOR_POSTURE
    res_no_felt = analyzer.analyze_table(table, [assign], [], [], 1.0, felt_motion=False)
    assert res_no_felt.activity_state == "NOT_PLAYING"

    # With felt motion (ball moving) -> Confirms PLAYING
    res_felt = analyzer.analyze_table(table, [assign], [], [], 1.0, felt_motion=True)
    assert res_felt.activity_state == "PLAYING"
    assert res_felt.activity_reason == "PLAYING_FELT_MOTION"

