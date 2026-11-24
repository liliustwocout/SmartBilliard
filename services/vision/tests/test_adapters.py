"""Unit tests for Camera/Video Adapters (SB-09)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from services.vision.adapters import (
    FileVideoSource,
    RTSPCameraSource,
    USBCameraSource,
    create_video_source,
    sanitize_uri,
)
from services.vision.decision import DecisionConfig, Memory, Observation, advance


def test_sanitize_uri_masks_passwords():
    # RTSP with credentials
    raw = "rtsp://admin:super_secret_password_123@192.168.1.50:554/stream1"
    clean = sanitize_uri(raw)
    assert "super_secret_password_123" not in clean
    assert clean == "rtsp://admin:***@192.168.1.50:554/stream1"

    # HTTP with credentials
    raw_http = "http://operator:P@ssword!@10.0.0.12/mjpeg"
    clean_http = sanitize_uri(raw_http)
    assert "P@ssword!" not in clean_http
    assert clean_http == "http://operator:***@10.0.0.12/mjpeg"

    # URI without credentials remains unchanged
    clean_no_auth = sanitize_uri("rtsp://192.168.1.50:554/live")
    assert clean_no_auth == "rtsp://192.168.1.50:554/live"

    # Edge cases
    assert sanitize_uri("") == ""
    assert sanitize_uri("not_a_uri") == "not_a_uri"


def test_file_video_source_not_found(tmp_path: Path):
    missing_file = tmp_path / "nonexistent.mp4"
    with pytest.raises(FileNotFoundError, match="Video file not found"):
        FileVideoSource(missing_file)


def _create_synthetic_video(path: Path, frame_count: int = 5, width: int = 64, height: int = 48) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(path), fourcc, 10.0, (width, height))
    for i in range(frame_count):
        # Create a frame with solid color
        frame = np.full((height, width, 3), fill_value=i * 40, dtype=np.uint8)
        out.write(frame)
    out.release()


def test_file_video_source_reads_and_reaches_eof(tmp_path: Path):
    video_path = tmp_path / "test_synthetic.mp4"
    _create_synthetic_video(video_path, frame_count=3, width=64, height=48)

    source = FileVideoSource(video_path, camera_id="test-file", loop=False)
    assert source.camera_id == "test-file"
    assert source.status == "CONNECTED"
    assert source.resolution == (64, 48)

    # Read 3 frames
    for _ in range(3):
        ok, frame = source.read()
        assert ok is True
        assert frame is not None
        assert frame.shape == (48, 64, 3)

    # 4th read reaches EOF
    ok, frame = source.read()
    assert ok is False
    assert frame is None
    assert source.status == "EOF"

    source.close()
    assert source.status == "CLOSED"
    ok, frame = source.read()
    assert ok is False


def test_file_video_source_looping(tmp_path: Path):
    video_path = tmp_path / "test_loop.mp4"
    _create_synthetic_video(video_path, frame_count=2, width=32, height=32)

    source = FileVideoSource(video_path, camera_id="loop-cam", loop=True)
    # Read 6 frames from a 2-frame video -> loops cleanly
    for i in range(6):
        ok, frame = source.read()
        assert ok is True
        assert frame is not None
        assert frame.shape == (32, 32, 3)

    source.close()


def test_usb_camera_source_normal_and_reconnect():
    with patch("cv2.VideoCapture") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: 30.0 if prop == cv2.CAP_PROP_FPS else (640 if prop == cv2.CAP_PROP_FRAME_WIDTH else 480)
        mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        mock_cap_cls.return_value = mock_cap

        usb = USBCameraSource(device_index=0, camera_id="usb-01", reconnect_delay=0.1)
        assert usb.status == "CONNECTED"
        assert usb.resolution == (640, 480)

        # Successful read
        ok, frame = usb.read()
        assert ok is True
        assert frame is not None

        # Simulate frame read failure (e.g. cable unplugged)
        mock_cap.read.return_value = (False, None)
        ok, frame = usb.read()
        assert ok is False
        assert frame is None
        assert usb.status == "CONNECTING"

        # Read while in reconnect delay period
        ok, frame = usb.read()
        assert ok is False
        assert frame is None

        usb.close()
        assert usb.status == "CLOSED"
        mock_cap.release.assert_called()


def test_rtsp_camera_source_sanitization_and_backoff():
    with patch("cv2.VideoCapture") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, np.ones((720, 1280, 3), dtype=np.uint8))
        mock_cap_cls.return_value = mock_cap

        secret_url = "rtsp://admin:super_secret@192.168.1.200:554/stream"
        rtsp = RTSPCameraSource(
            rtsp_url=secret_url,
            camera_id="rtsp-table-1",
            reconnect_initial_delay=0.2,
            reconnect_backoff_factor=2.0,
            reconnect_max_delay=1.0,
            drop_stale_frames=True,
        )

        # Ensure credentials never leak in __repr__
        repr_str = repr(rtsp)
        assert "super_secret" not in repr_str
        assert "admin:***@192.168.1.200:554/stream" in repr_str
        assert rtsp.sanitized_url == "rtsp://admin:***@192.168.1.200:554/stream"
        assert rtsp.status == "CONNECTED"

        # Successful read triggers grab for stale frame drop
        ok, frame = rtsp.read()
        assert ok is True
        mock_cap.grab.assert_called()

        # Simulate stream disconnect
        mock_cap.read.return_value = (False, None)
        ok, frame = rtsp.read()
        assert ok is False
        assert rtsp.status == "CONNECTING"

        rtsp.close()
        assert rtsp.status == "CLOSED"


def test_rtsp_sets_tcp_transport_and_skips_redundant_grab_when_fresh(monkeypatch):
    import os
    monkeypatch.delenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", raising=False)
    with patch("cv2.VideoCapture") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: 25.0 if prop == cv2.CAP_PROP_FPS else 640.0
        mock_cap.read.return_value = (True, np.ones((480, 640, 3), dtype=np.uint8))
        mock_cap_cls.return_value = mock_cap

        rtsp = RTSPCameraSource(rtsp_url="rtsp://admin:pass@192.168.1.50:554/cam/realmonitor", drop_stale_frames=True)
        assert "rtsp_transport;tcp" in os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS", "")

        # First read always grabs stale initial buffer
        ok, _ = rtsp.read()
        assert ok is True
        assert mock_cap.grab.call_count == 1

        # Immediate back-to-back read (< 48ms) skips redundant grab()
        ok, _ = rtsp.read()
        assert ok is True
        assert mock_cap.grab.call_count == 1

        # Simulated lag (> 1.2 * frame_period = 48ms) triggers grab() again
        rtsp._last_read_time -= 0.10
        ok, _ = rtsp.read()
        assert ok is True
        assert mock_cap.grab.call_count == 2
        rtsp.close()


def test_create_video_source_factory(tmp_path: Path):
    video_file = tmp_path / "sample.mp4"
    _create_synthetic_video(video_file, frame_count=1)

    # Int index -> USBCameraSource
    with patch("cv2.VideoCapture"):
        usb_src = create_video_source(0, camera_id="cam-0")
        assert isinstance(usb_src, USBCameraSource)
        usb_src.close()

        # String digit index -> USBCameraSource
        usb_src_str = create_video_source("2", camera_id="cam-2")
        assert isinstance(usb_src_str, USBCameraSource)
        usb_src_str.close()

        # RTSP url -> RTSPCameraSource
        rtsp_src = create_video_source("rtsp://localhost/live", camera_id="cam-rtsp")
        assert isinstance(rtsp_src, RTSPCameraSource)
        rtsp_src.close()

        # File path -> FileVideoSource
        file_src = create_video_source(str(video_file), camera_id="cam-file")
        assert isinstance(file_src, FileVideoSource)
        file_src.close()


def test_loss_recovery_invariant_with_fsm():
    """Verify acceptance criterion: frame loss / recovery does NOT open session incorrectly."""
    config = DecisionConfig(presence_seconds=4.0)
    memory = Memory()
    now = 1000.0

    # Step 1: Normal presence starts accumulating candidate
    obs_present = Observation(present=True, confidence=0.85)
    decision = advance(memory, obs_present, now, config)
    memory = decision.memory
    assert memory.state == "CANDIDATE"

    # Step 2: Camera frame is lost (returned False, None -> translated to present=False)
    # Temporary frame drop within absence grace period
    obs_lost = Observation(present=False, confidence=0.0)
    decision = advance(memory, obs_lost, now + 1.0, config)
    memory = decision.memory
    assert decision.should_open is False

    # Step 3: Prolonged camera loss (exceeding grace period) resets candidate
    decision = advance(memory, obs_lost, now + 5.0, config)
    memory = decision.memory
    assert memory.state == "EMPTY"
    assert decision.should_open is False

    # Step 4: When camera recovers, candidate starts fresh from 0, NOT jumping to ACTIVE
    decision = advance(memory, obs_present, now + 6.0, config)
    memory = decision.memory
    assert memory.state == "CANDIDATE"
    assert decision.should_open is False  # Must wait for full presence_seconds
