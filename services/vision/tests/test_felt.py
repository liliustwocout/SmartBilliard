import cv2
import numpy as np
import pytest

from services.vision.felt import FeltMotionDetector, FeltMotionResult


def test_felt_motion_empty_and_degenerate():
    detector = FeltMotionDetector()
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    res = detector.detect_motion(empty, 1, [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)])
    assert not res.has_motion
    assert res.active_pixels == 0

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    res = detector.detect_motion(frame, 1, [(0.1, 0.1)])  # < 3 points
    assert not res.has_motion


def test_felt_motion_static_frames():
    detector = FeltMotionDetector()
    poly = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]
    frame = np.full((480, 640, 3), 100, dtype=np.uint8)

    # First frame establishes baseline
    r1 = detector.detect_motion(frame, 1, poly)
    assert not r1.has_motion

    # Identical second frame
    r2 = detector.detect_motion(frame, 1, poly)
    assert not r2.has_motion
    assert r2.active_pixels == 0


def test_felt_motion_detects_moving_ball():
    detector = FeltMotionDetector(min_active_pixels=10, min_motion_ratio=0.0001)
    poly = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]

    # Frame 1: Green felt background
    f1 = np.zeros((480, 640, 3), dtype=np.uint8)
    f1[:, :] = (35, 120, 35)

    # Frame 2: White ball rolled into (320, 240)
    f2 = f1.copy()
    cv2.circle(f2, (320, 240), 12, (255, 255, 255), -1)

    detector.detect_motion(f1, 1, poly)
    res = detector.detect_motion(f2, 1, poly)
    assert res.has_motion
    assert res.active_pixels > 20
    assert res.motion_energy > 0.0


def test_felt_motion_ignores_outside_movement():
    detector = FeltMotionDetector(min_active_pixels=10)
    # Center play area
    poly = [(0.3, 0.3), (0.7, 0.3), (0.7, 0.7), (0.3, 0.7)]

    f1 = np.zeros((480, 640, 3), dtype=np.uint8)
    f2 = f1.copy()

    # Movement outside the play polygon (at top-left corner (50, 50))
    cv2.circle(f2, (50, 50), 30, (255, 255, 255), -1)

    detector.detect_motion(f1, 1, poly)
    res = detector.detect_motion(f2, 1, poly)
    assert not res.has_motion
    assert res.active_pixels == 0


def test_felt_motion_reset():
    detector = FeltMotionDetector()
    poly = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]
    f1 = np.zeros((480, 640, 3), dtype=np.uint8)
    detector.detect_motion(f1, 1, poly)
    assert 1 in detector._prev_rois

    detector.reset(1)
    assert 1 not in detector._prev_rois
