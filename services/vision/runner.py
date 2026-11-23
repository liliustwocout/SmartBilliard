"""Camera Vision Runner running background frame processing and event emission (SB-13).

Features:
- Runs VisionPipeline in a dedicated background thread (non-blocking).
- Throttles processing to target FPS (e.g. 8-10 FPS) to conserve CPU.
- Emits per-table observations directly to callback handlers (e.g., FastAPI event processor).
- Safely reports source_type ('CAMERA' or 'VIDEO') and connection status.
"""
from __future__ import annotations

import logging
from collections import deque
import threading
import time
from pathlib import Path
from typing import Callable
from uuid import uuid4

import numpy as np

from services.vision.adapters import FileVideoSource, RTSPCameraSource, USBCameraSource, create_video_source
from services.vision.calibration import CalibrationConfig, load_calibration_config
from services.vision.contracts import Detection, VideoSource
from services.vision.detector import YoloCueDetector, YoloPoseDetector
from services.vision.mapper import TableObservationSummary, TableZoneMapper
from services.vision.pipeline import VisionPipeline
from services.vision.tracker import ByteTracker
from services.vision.performance import VisionPerformanceConfig

logger = logging.getLogger("smartbilliard.vision.runner")

ObservationCallback = Callable[[int, TableObservationSummary, str], None]


def _infer_source_type(source: str | int) -> str:
    source_str = str(source).strip().lower()
    if isinstance(source, int) or source_str.isdigit():
        return "CAMERA"
    if source_str.startswith(("rtsp://", "rtsps://", "http://", "https://")):
        return "CAMERA"
    return "VIDEO"


class CameraRunner:
    """Background camera processing runner feeding events into FSM."""

    def __init__(
        self,
        source: str | int = "0",
        *,
        camera_id: str = "cam-01",
        zones_config_path: str | Path = "configs/zones.json",
        fallback_zones_path: str | Path = "configs/zones.example.json",
        model_path: str | Path = "models/yolov8n-pose.onnx",
        fallback_model_path: str | Path = "models/yolov8n.onnx",
        cue_model_path: str | Path = "models/yolov8n-cue.onnx",
        prefer_gpu: bool = True,
        target_fps: float | None = None,
        performance: VisionPerformanceConfig | None = None,
        on_observation: ObservationCallback | None = None,
    ) -> None:
        self.source_spec = source
        self.camera_id = camera_id
        self.zones_config_path = Path(zones_config_path)
        self.fallback_zones_path = Path(fallback_zones_path)
        self.model_path = Path(model_path)
        self.fallback_model_path = Path(fallback_model_path)
        self.cue_model_path = Path(cue_model_path)
        self.prefer_gpu = prefer_gpu
        self.performance = performance or VisionPerformanceConfig()
        self.target_fps = target_fps if target_fps is not None else self.performance.target_fps
        self.on_observation = on_observation

        self._pipeline: VisionPipeline | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._jpeg_lock = threading.Lock()
        self._jpeg_cache: dict[bool, tuple[tuple[int, int], bytes]] = {}
        self._frame_sequence = 0

        self.source_type = _infer_source_type(source)

        self._status: str = "STOPPED"
        self._last_processed_time: float = 0.0
        self._latest_frame: np.ndarray | None = None
        self._latest_detections: list[Detection] = []
        self._latest_summaries: dict[int, TableObservationSummary] = {}
        self._fps_measured: float = 0.0
        self._inference_fps_measured: float = 0.0
        self._calibration_cfg: CalibrationConfig | None = None
        self._paused_tables: frozenset[int] = frozenset()

    def set_paused_tables(self, table_ids: set[int] | frozenset[int]) -> None:
        """Tables with an open session: no observations are emitted for them, and the models
        are not run at all while every calibrated table is paused."""
        with self._lock:
            self._paused_tables = frozenset(int(t) for t in table_ids)

    @property
    def paused_tables(self) -> frozenset[int]:
        with self._lock:
            return self._paused_tables

    @property
    def inference_paused(self) -> bool:
        with self._lock:
            return bool(self._pipeline and self._pipeline.inference_skipped)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def status(self) -> str:
        with self._lock:
            if not self.is_running:
                return "STOPPED"
            if self._pipeline and hasattr(self._pipeline.source, "status"):
                return self._pipeline.source.status
            return self._status

    @property
    def measured_fps(self) -> float:
        return self._fps_measured

    @property
    def inference_fps(self) -> float:
        return self._inference_fps_measured

    @property
    def source_fps(self) -> float:
        with self._lock:
            return float(getattr(self._pipeline.source, "fps", 0)) if self._pipeline else 0.0

    @property
    def cue_detector_ready(self) -> bool:
        with self._lock:
            if self._pipeline and self._pipeline.cue_detector:
                return bool(getattr(self._pipeline.cue_detector, "validated", False))
            return False

    def get_model_status(self) -> dict[str, dict[str, str | bool]]:
        """Report models actually loaded by the active pipeline, not files on disk."""
        with self._lock:
            person = self._pipeline.detector if self._pipeline else None
            cue = self._pipeline.cue_detector if self._pipeline else None
            return {
                "person": {
                    "name": Path(person.model_path).name if person else self.model_path.name,
                    "loaded": bool(person and person.is_ready),
                    "backend": str(getattr(person, "backend_label", "OFFLINE")),
                },
                "cue": {
                    "name": Path(cue.model_path).name if cue else self.cue_model_path.name,
                    "loaded": bool(cue and cue.is_ready),
                    "backend": str(getattr(cue, "backend_label", "OFFLINE")),
                    "validated": bool(cue and getattr(cue, "validated", False)),
                },
            }

    def get_latest_frame(self) -> np.ndarray | None:
        with self._lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    def get_latest_frame_jpeg(self) -> bytes | None:
        return self.get_stream_frame(annotated=False)[1]

    def get_annotated_frame_jpeg(self) -> bytes | None:
        return self.get_stream_frame(annotated=True)[1]

    def get_stream_frame(self, annotated: bool = True) -> tuple[int, bytes | None]:
        """Encode each processed frame once per mode, shared by all viewers."""
        import cv2
        from services.vision.annotator import draw_frame_annotations

        with self._jpeg_lock:
            with self._lock:
                sequence = self._frame_sequence
                if self._latest_frame is None:
                    return sequence, None
                key = (sequence, id(self._calibration_cfg))
                cached = self._jpeg_cache.get(annotated)
                if cached and cached[0] == key:
                    return sequence, cached[1]
                frame = self._latest_frame.copy()
                detections = list(self._latest_detections)
                summaries = dict(self._latest_summaries)
                cfg = self._calibration_cfg
                fps, ai_fps = self._fps_measured, self._inference_fps_measured
            if annotated:
                if frame.shape[1] > self.performance.preview_width:
                    scale = self.performance.preview_width / frame.shape[1]
                    frame = cv2.resize(frame, (self.performance.preview_width, round(frame.shape[0] * scale)))
                frame = draw_frame_annotations(frame=frame, detections=detections, summaries=summaries,
                                               config=cfg, fps=fps, inference_fps=ai_fps,
                                               source_type=self.source_type, camera_id=self.camera_id)
            quality = self.performance.jpeg_quality if annotated else 85
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            data = buf.tobytes() if ok else None
            if data is not None:
                self._jpeg_cache[annotated] = (key, data)
            return sequence, data

    def reload_calibration_config(self) -> None:
        """Hot-reload zone configuration into active pipeline without restarting."""
        with self._lock:
            try:
                cfg = load_calibration_config(self.zones_config_path, self.fallback_zones_path)
                self._calibration_cfg = cfg
                if self._pipeline:
                    self._pipeline.mapper = TableZoneMapper(cfg)
                logger.info("Hot-reloaded calibration config with %d tables", len(cfg.tables))
            except Exception as err:
                logger.warning("Could not reload calibration config: %s", err)

    def get_latest_summaries(self) -> dict[int, TableObservationSummary]:
        with self._lock:
            return dict(self._latest_summaries)

    def start(self) -> bool:
        """Initialize components and start the background capture thread."""
        with self._lock:
            if self.is_running:
                return True

            logger.info("Starting CameraRunner for source %s (%s)", self.source_spec, self.source_type)
            try:
                import cv2
                cv2.setNumThreads(self.performance.opencv_threads)
                # 1. Initialize VideoSource
                source_options = {"decoder_threads": self.performance.decoder_threads} if self.source_type == "VIDEO" else {}
                video_src = create_video_source(self.source_spec, camera_id=self.camera_id, loop=True, **source_options)

                # 2. Initialize calibration mapper
                calibration_cfg = load_calibration_config(self.zones_config_path, self.fallback_zones_path)
                self._calibration_cfg = calibration_cfg
                mapper = TableZoneMapper(calibration_cfg)

                # 3. Initialize pose + cue detectors & tracker
                detector = YoloPoseDetector(
                    model_path=self.model_path,
                    fallback_model_path=self.fallback_model_path,
                    prefer_gpu=self.prefer_gpu,
                    dml_device_id=self.performance.dml_device_id,
                )
                cue_detector = YoloCueDetector(
                    model_path=self.cue_model_path,
                    prefer_gpu=self.prefer_gpu,
                    dml_device_id=self.performance.dml_device_id,
                    enabled=self.performance.cue_enabled,
                )
                tracker = ByteTracker()

                # 4. Assemble pipeline
                self._pipeline = VisionPipeline(
                    source=video_src,
                    detector=detector,
                    tracker=tracker,
                    mapper=mapper,
                    cue_detector=cue_detector,
                )
            except Exception as err:
                logger.error("Failed to initialize VisionPipeline: %s", err)
                self._status = "ERROR"
                return False

            self._stop_event.clear()
            self._latest_frame = None
            self._latest_detections = []
            self._latest_summaries = {}
            self._fps_measured = self._inference_fps_measured = 0.0
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="CameraRunnerThread")
            self._thread.start()
            self._status = "RUNNING"
            return True

    def stop(self) -> None:
        """Signal background thread to stop and release video resources."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None

        with self._lock:
            if self._pipeline:
                try:
                    self._pipeline.source.close()
                except Exception:
                    pass
                self._pipeline = None
            self._status = "STOPPED"
            self._fps_measured = self._inference_fps_measured = 0.0
            logger.info("CameraRunner stopped")

    def configure_source(self, new_source: str | int) -> bool:
        """Change the source; restart only if the runner is currently running."""
        if self.is_running:
            return self.switch_source(new_source)
        with self._lock:
            self.source_spec = str(new_source)
            self.source_type = _infer_source_type(new_source)
        return True

    def switch_source(self, new_source: str | int) -> bool:
        """Stop current capture, switch video/camera source, and restart pipeline."""
        self.stop()
        with self._lock:
            self.source_spec = str(new_source)
            self.source_type = _infer_source_type(new_source)
            self._latest_frame = None
            self._latest_detections = []
            self._latest_summaries = {}
            self._fps_measured = 0.0
        return self.start()

    def _run_loop(self) -> None:
        """Main loop running in background thread."""
        rate = self.target_fps
        if self.source_type == "VIDEO" and self.source_fps > 0:
            rate = min(rate, self.source_fps)
        interval = 1.0 / max(1.0, rate)
        frame_times: deque[float] = deque(maxlen=60)
        inference_times: deque[float] = deque(maxlen=60)
        last_emit = float("-inf")

        while not self._stop_event.is_set():
            loop_start = time.perf_counter()
            now_ts = time.time()

            try:
                if self._pipeline is not None:
                    paused = self.paused_tables
                    ok, frame, detections, summaries = self._pipeline.process_frame_for_tables(
                        timestamp=now_ts, paused_table_ids=paused)
                    summaries = {tid: item for tid, item in summaries.items() if tid not in paused}
                    with self._lock:
                        if ok and frame is not None:
                            self._frame_sequence += 1
                            self._latest_frame = frame
                            self._latest_detections = detections
                            self._latest_summaries = summaries
                            self._last_processed_time = now_ts

                    if not ok or frame is None:
                        self._fps_measured = self._inference_fps_measured = 0.0
                    else:
                        now_mono = time.perf_counter()
                        frame_times.append(now_mono)
                        if len(frame_times) >= 2:
                            self._fps_measured = (len(frame_times) - 1) / max(1e-6, frame_times[-1] - frame_times[0])
                        if not self._pipeline.inference_skipped and self._pipeline.detector.is_ready:
                            inference_times.append(now_mono)
                            if len(inference_times) >= 2:
                                self._inference_fps_measured = (len(inference_times) - 1) / max(1e-6, inference_times[-1] - inference_times[0])
                        else:
                            inference_times.clear()
                            self._inference_fps_measured = 0.0

                    # Emit observations to callback
                    if ok and self.on_observation and summaries and loop_start - last_emit >= 1 / self.performance.observation_fps:
                        last_emit = loop_start
                        for table_id, summary in summaries.items():
                            try:
                                self.on_observation(table_id, summary, self.source_type)
                            except Exception as cb_err:
                                logger.error("Error in on_observation callback: %s", cb_err)

            except Exception as err:
                self._fps_measured = self._inference_fps_measured = 0.0
                logger.error("Error in CameraRunner processing loop: %s", err)

            elapsed = time.perf_counter() - loop_start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                # Python 3.11 sleep uses a high-resolution Windows waitable timer;
                # Event.wait can round these short waits to a ~16 ms system tick.
                time.sleep(sleep_time)
