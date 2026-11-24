"""Camera and video source adapters for Phase 3 (SB-09).

Supports:
- FileVideoSource: Video file replay with loop and EOF options.
- USBCameraSource: Direct USB webcam capture with reconnection.
- RTSPCameraSource: IP Camera RTSP/HTTP streams with credential masking,
  exponential backoff reconnection, and stale frame dropping.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse, urlunparse

import cv2
import numpy as np

logger = logging.getLogger("smartbilliard.vision.adapters")

_PASSWORD_REGEX = re.compile(r":([^:@/]+)@")


def sanitize_uri(uri: str) -> str:
    """Mask credentials in RTSP or HTTP URIs for safe logging and display.

    Example:
        'rtsp://admin:secret123@192.168.1.100:554/stream'
        -> 'rtsp://admin:***@192.168.1.100:554/stream'
    """
    if not uri or "://" not in uri:
        return uri
    try:
        parsed = urlparse(uri)
        if parsed.password:
            # Replace password with '***'
            netloc = parsed.netloc
            user = parsed.username or ""
            host = parsed.hostname or ""
            port = f":{parsed.port}" if parsed.port else ""
            masked_netloc = f"{user}:***@{host}{port}"
            return urlunparse(parsed._replace(netloc=masked_netloc))
        return uri
    except Exception:
        # Fallback to regex replacement
        return _PASSWORD_REGEX.sub(":***@", uri)


class FileVideoSource:
    """Reads frames from a video file (mp4, mkv, avi, etc.)."""

    def __init__(
        self,
        file_path: str | Path,
        *,
        camera_id: str = "file-cam",
        loop: bool = True,
        realtime_pacing: bool = False,
        decoder_threads: int = 2,
    ) -> None:
        self.file_path = Path(file_path).resolve()
        if not self.file_path.exists():
            raise FileNotFoundError(f"Video file not found: {self.file_path}")

        self.camera_id = camera_id
        self.loop = loop
        self.realtime_pacing = realtime_pacing
        self.decoder_threads = decoder_threads
        self._cap: cv2.VideoCapture | None = None
        self._lock = threading.Lock()
        self._status: Literal["CONNECTED", "EOF", "ERROR", "CLOSED"] = "CLOSED"
        self._fps: float = 30.0
        self._width: int = 0
        self._height: int = 0
        self._last_frame_time: float = 0.0

        self._open()

    def _open(self) -> None:
        if hasattr(cv2, "CAP_PROP_N_THREADS"):
            self._cap = cv2.VideoCapture(str(self.file_path), cv2.CAP_FFMPEG,
                                         [cv2.CAP_PROP_N_THREADS, self.decoder_threads])
        else:
            self._cap = cv2.VideoCapture(str(self.file_path))
        if not self._cap.isOpened():
            self._cap.release()
            self._cap = cv2.VideoCapture(str(self.file_path))
        if not self._cap.isOpened():
            self._status = "ERROR"
            logger.error("Failed to open video file: %s", self.file_path)
            return

        self._fps = float(self._cap.get(cv2.CAP_PROP_FPS) or 30.0)
        self._width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        self._height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        self._status = "CONNECTED"

    @property
    def status(self) -> str:
        return self._status

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def resolution(self) -> tuple[int, int]:
        return (self._width, self._height)

    def read(self) -> tuple[bool, np.ndarray | None]:
        with self._lock:
            if self._status in ("CLOSED", "ERROR"):
                return False, None

            if self._cap is None or not self._cap.isOpened():
                return False, None

            if self.realtime_pacing and self._last_frame_time > 0:
                target_interval = 1.0 / max(self._fps, 1.0)
                elapsed = time.monotonic() - self._last_frame_time
                if elapsed < target_interval:
                    time.sleep(target_interval - elapsed)

            ret, frame = self._cap.read()
            self._last_frame_time = time.monotonic()

            if not ret or frame is None:
                if self.loop:
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self._cap.read()
                    if not ret or frame is None:
                        self._status = "EOF"
                        return False, None
                else:
                    self._status = "EOF"
                    return False, None

            return True, frame

    def close(self) -> None:
        with self._lock:
            self._status = "CLOSED"
            if self._cap is not None:
                self._cap.release()
                self._cap = None


class USBCameraSource:
    """Reads frames from a local USB camera by device index with auto-reconnect."""

    def __init__(
        self,
        device_index: int = 0,
        *,
        camera_id: str = "usb-cam-0",
        target_fps: float | None = None,
        target_resolution: tuple[int, int] | None = None,
        reconnect_delay: float = 2.0,
    ) -> None:
        self.device_index = device_index
        self.camera_id = camera_id
        self.target_fps = target_fps
        self.target_resolution = target_resolution
        self.reconnect_delay = reconnect_delay

        self._cap: cv2.VideoCapture | None = None
        self._lock = threading.Lock()
        self._status: Literal["CONNECTED", "CONNECTING", "ERROR", "CLOSED"] = "CONNECTING"
        self._fps: float = 30.0
        self._width: int = 0
        self._height: int = 0
        self._last_reconnect_attempt: float = 0.0

        self._open()

    def _open(self) -> bool:
        self._last_reconnect_attempt = time.monotonic()
        if self._cap is not None:
            self._cap.release()
            self._cap = None

        self._cap = cv2.VideoCapture(self.device_index)
        if not self._cap.isOpened():
            self._status = "CONNECTING"
            return False

        if self.target_resolution:
            w, h = self.target_resolution
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)

        if self.target_fps:
            self._cap.set(cv2.CAP_PROP_FPS, self.target_fps)

        self._fps = float(self._cap.get(cv2.CAP_PROP_FPS) or 30.0)
        self._width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        self._height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        self._status = "CONNECTED"
        return True

    @property
    def status(self) -> str:
        return self._status

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def resolution(self) -> tuple[int, int]:
        return (self._width, self._height)

    def read(self) -> tuple[bool, np.ndarray | None]:
        with self._lock:
            if self._status == "CLOSED":
                return False, None

            now = time.monotonic()
            if self._status == "CONNECTING":
                if now - self._last_reconnect_attempt >= self.reconnect_delay:
                    if not self._open():
                        return False, None
                else:
                    return False, None

            if self._cap is None:
                return False, None

            ret, frame = self._cap.read()
            if not ret or frame is None:
                logger.warning("Frame read failed for USB camera %s (index %d)", self.camera_id, self.device_index)
                self._status = "CONNECTING"
                self._last_reconnect_attempt = now
                return False, None

            return True, frame

    def close(self) -> None:
        with self._lock:
            self._status = "CLOSED"
            if self._cap is not None:
                self._cap.release()
                self._cap = None


class RTSPCameraSource:
    """Reads frames from an RTSP / HTTP network camera stream.

    Features:
    - Passwords in URI are masked in logs and representation.
    - Exponential backoff reconnection when stream drops.
    - Buffer management: grabs latest frame to prevent latency buildup.
    """

    def __init__(
        self,
        rtsp_url: str,
        *,
        camera_id: str = "rtsp-cam",
        reconnect_initial_delay: float = 1.0,
        reconnect_backoff_factor: float = 1.5,
        reconnect_max_delay: float = 15.0,
        drop_stale_frames: bool = True,
    ) -> None:
        self.rtsp_url = rtsp_url
        self.sanitized_url = sanitize_uri(rtsp_url)
        self.camera_id = camera_id
        self.reconnect_initial_delay = reconnect_initial_delay
        self.reconnect_backoff_factor = reconnect_backoff_factor
        self.reconnect_max_delay = reconnect_max_delay
        self.drop_stale_frames = drop_stale_frames

        self._cap: cv2.VideoCapture | None = None
        self._lock = threading.Lock()
        self._status: Literal["CONNECTED", "CONNECTING", "ERROR", "CLOSED"] = "CONNECTING"
        self._fps: float = 25.0
        self._width: int = 0
        self._height: int = 0

        self._current_reconnect_delay: float = reconnect_initial_delay
        self._last_reconnect_attempt: float = 0.0
        self._last_read_time: float = 0.0

        self._open()

    def __repr__(self) -> str:
        return f"<RTSPCameraSource camera_id={self.camera_id} url={self.sanitized_url} status={self._status}>"

    def _open(self) -> bool:
        self._last_reconnect_attempt = time.monotonic()
        self._last_read_time = 0.0
        if self._cap is not None:
            self._cap.release()
            self._cap = None

        if self.rtsp_url.lower().startswith(("rtsp://", "rtsps://")):
            # Enforce TCP transport and socket timeout to avoid UDP block artifacts on Wi-Fi cameras
            os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;5000000")
        logger.info("Connecting to RTSP stream: %s", self.sanitized_url)
        self._cap = cv2.VideoCapture(self.rtsp_url)

        if not self._cap.isOpened():
            self._status = "CONNECTING"
            # Update backoff
            self._current_reconnect_delay = min(
                self._current_reconnect_delay * self.reconnect_backoff_factor,
                self.reconnect_max_delay,
            )
            logger.warning(
                "RTSP stream %s failed to open. Next retry in %.1fs",
                self.sanitized_url,
                self._current_reconnect_delay,
            )
            return False

        # Set buffer size to 1 if supported by backend
        try:
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        self._fps = float(self._cap.get(cv2.CAP_PROP_FPS) or 25.0)
        self._width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        self._height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        self._status = "CONNECTED"
        self._current_reconnect_delay = self.reconnect_initial_delay
        logger.info("RTSP stream connected: %s (%dx%d @ %.1f FPS)", self.sanitized_url, self._width, self._height, self._fps)
        return True

    @property
    def status(self) -> str:
        return self._status

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def resolution(self) -> tuple[int, int]:
        return (self._width, self._height)

    def read(self) -> tuple[bool, np.ndarray | None]:
        with self._lock:
            if self._status == "CLOSED":
                return False, None

            now = time.monotonic()
            if self._status == "CONNECTING":
                if now - self._last_reconnect_attempt >= self._current_reconnect_delay:
                    if not self._open():
                        return False, None
                else:
                    return False, None

            if self._cap is None:
                return False, None

            # Only grab to flush stale buffer on initial read or after reading lag exceeds one frame period
            frame_period = 1.0 / (self._fps if self._fps > 1.0 else 25.0)
            if self.drop_stale_frames and (
                self._last_read_time == 0.0 or (now - self._last_read_time) >= 1.2 * frame_period
            ):
                self._cap.grab()

            ret, frame = self._cap.read()
            if not ret or frame is None:
                logger.warning("RTSP read failed for %s. Entering reconnection mode.", self.sanitized_url)
                self._status = "CONNECTING"
                self._last_reconnect_attempt = now
                self._last_read_time = 0.0
                self._current_reconnect_delay = self.reconnect_initial_delay
                return False, None

            self._last_read_time = time.monotonic()
            return True, frame

    def close(self) -> None:
        with self._lock:
            self._status = "CLOSED"
            if self._cap is not None:
                self._cap.release()
                self._cap = None


def create_video_source(
    source: str | int,
    *,
    camera_id: str = "cam-01",
    loop: bool = True,
    **kwargs: Any,
) -> FileVideoSource | USBCameraSource | RTSPCameraSource:
    """Factory creating the appropriate VideoSource based on source specification."""
    if isinstance(source, int):
        return USBCameraSource(device_index=source, camera_id=camera_id, **kwargs)

    source_str = str(source).strip()
    if source_str.isdigit():
        return USBCameraSource(device_index=int(source_str), camera_id=camera_id, **kwargs)

    lower = source_str.lower()
    if lower.startswith(("rtsp://", "rtsps://", "http://", "https://")):
        return RTSPCameraSource(rtsp_url=source_str, camera_id=camera_id, **kwargs)

    return FileVideoSource(file_path=source_str, camera_id=camera_id, loop=loop, **kwargs)
