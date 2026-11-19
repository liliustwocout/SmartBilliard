"""Camera Vision Runner running background frame processing and event emission (SB-13).

Features:
- Runs VisionPipeline in a dedicated background thread (non-blocking).
- Throttles processing to target FPS (e.g. 8-10 FPS) to conserve CPU.
- Emits per-table observations directly to callback handlers (e.g., FastAPI event processor).
- Safely reports source_type ('CAMERA' or 'VIDEO') and connection status.
"""
from __future__ import annotations

import logging
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
        target_fps: float = 8.0,
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
        self.target_fps = target_fps
        self.on_observation = on_observation

        self._pipeline: VisionPipeline | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self.source_type = _infer_source_type(source)

        self._status: str = "STOPPED"
        self._last_processed_time: float = 0.0
        self._latest_frame: np.ndarray | None = None
        self._latest_detections: list[Detection] = []
        self._latest_summaries: dict[int, TableObservationSummary] = {}
        self._fps_measured: float = 0.0
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
        with self._lock:
            if self._latest_frame is None:
                return None
            import cv2
            ok, buf = cv2.imencode(".jpg", self._latest_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            return buf.tobytes() if ok else None

    def get_annotated_frame_jpeg(self) -> bytes | None:
        """Render AI detections, tracking IDs, and ROI zones onto latest frame as JPEG."""
        with self._lock:
            if self._latest_frame is None:
                return None
            frame = self._latest_frame.copy()
            detections = list(self._latest_detections)
            summaries = dict(self._latest_summaries)
            cfg = self._calibration_cfg
            fps = self._fps_measured
            src_type = self.source_type
            cam_id = self.camera_id

        from services.vision.annotator import draw_frame_annotations
        annotated = draw_frame_annotations(
            frame=frame,
            detections=detections,
            summaries=summaries,
            config=cfg,
            fps=fps,
            source_type=src_type,
            camera_id=cam_id,
        )
        import cv2
        ok, buf = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return buf.tobytes() if ok else None

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
                # 1. Initialize VideoSource
                video_src = create_video_source(self.source_spec, camera_id=self.camera_id, loop=True)

                # 2. Initialize calibration mapper
                calibration_cfg = load_calibration_config(self.zones_config_path, self.fallback_zones_path)
                self._calibration_cfg = calibration_cfg
                mapper = TableZoneMapper(calibration_cfg)

                # 3. Initialize pose + cue detectors & tracker
                detector = YoloPoseDetector(
                    model_path=self.model_path,
                    fallback_model_path=self.fallback_model_path,
                    prefer_gpu=self.prefer_gpu,
                )
                cue_detector = YoloCueDetector(
                    model_path=self.cue_model_path,
                    prefer_gpu=self.prefer_gpu,
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
        interval = 1.0 / max(1.0, self.target_fps)
        frame_times: list[float] = []

        while not self._stop_event.is_set():
            loop_start = time.monotonic()
            now_ts = time.time()

            try:
                if self._pipeline is not None:
                    paused = self.paused_tables
                    ok, frame, detections, summaries = self._pipeline.process_frame_for_tables(
                        timestamp=now_ts, paused_table_ids=paused)
                    summaries = {tid: item for tid, item in summaries.items() if tid not in paused}
                    with self._lock:
                        if ok and frame is not None:
                            self._latest_frame = frame
                            self._latest_detections = detections
                            self._latest_summaries = summaries
                            self._last_processed_time = now_ts

                    # Emit observations to callback
                    if ok and self.on_observation and summaries:
                        for table_id, summary in summaries.items():
                            try:
                                self.on_observation(table_id, summary, self.source_type)
                            except Exception as cb_err:
                                logger.error("Error in on_observation callback: %s", cb_err)

                # Measure FPS
                now_mono = time.monotonic()
                frame_times.append(now_mono)
                if len(frame_times) > 10:
                    frame_times.pop(0)
                if len(frame_times) >= 2:
                    self._fps_measured = (len(frame_times) - 1) / (frame_times[-1] - frame_times[0])

            except Exception as err:
                logger.error("Error in CameraRunner processing loop: %s", err)

            elapsed = time.monotonic() - loop_start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                self._stop_event.wait(timeout=sleep_time)
