import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Callable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from apps.api.billing import quote, utc
from apps.api.config import ROOT, Settings
from apps.api.runtime_settings import (RateUpdate, SettingsUpdate, apply_overrides, load_overrides,
                                       merge_decision, save_overrides)
from apps.api.models import Base, DetectionEvent, PlaySession, Table, LATEST_DETECTION_EVENTS_INDEX
from apps.api.schemas import (
    ExtractDatasetRequest,
    GenerateDemoRequest,
    IngestionObservation,
    SimulatedObservation,
    VideoActionRequest,
)
from scripts.evaluate_video import evaluate_video, generate_synthetic_demo_video
from scripts.extract_frames import VIDEO_EXTS, extract_dataset
from pydantic import ValidationError
from services.vision.adapters import sanitize_uri
from services.vision.decision import Memory, Observation, advance
from services.vision.annotator import create_standby_frame_jpeg
from services.vision.calibration import CalibrationConfig, load_calibration_config, save_calibration_config
from services.vision.auto_calibration import propose_table_zones
from services.vision.mapper import TableObservationSummary
from services.vision.preview import get_preview_frame_jpeg
from services.vision.runner import CameraRunner

logger = logging.getLogger("smartbilliard.api")


def _safe_video_filename(raw_name: str) -> str:
    base = Path(raw_name or "upload.mp4").name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    if not cleaned:
        cleaned = "upload.mp4"
    p = Path(cleaned)
    if not p.suffix:
        cleaned = f"{cleaned}.mp4"
    elif p.suffix.lower() not in VIDEO_EXTS:
        raise HTTPException(400, f"Định dạng video không hỗ trợ: {p.suffix}")
    return cleaned


def iso(value: datetime | None) -> str | None:
    return utc(value).isoformat() if value else None


def create_app(settings: Settings | None = None,
               clock: Callable[[], datetime] | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    clock = clock or (lambda: datetime.now(timezone.utc))
    url = make_url(settings.database_url)
    if url.database and url.database != ":memory:":
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        data_root = Path(url.database).resolve().parent
    else:
        data_root = ROOT / "data"
    base_settings = settings
    overrides_path = (data_root / "runtime_settings.json"
                      if url.database and url.database != ":memory:" else None)
    overrides = load_overrides(overrides_path)
    try:
        settings = apply_overrides(base_settings, overrides)
    except (ValidationError, ValueError) as err:
        logger.warning("Ignoring invalid runtime settings overrides: %s", err)
        overrides = {}
    recordings_dir = data_root / "recordings"
    datasets_dir = data_root / "datasets" / "cue_v1"
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False},
                           **({"poolclass": StaticPool} if url.database in (None, "", ":memory:") else {}))

    @event.listens_for(engine, "connect")
    def sqlite_setup(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            connection.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass

    lock = asyncio.Lock()
    clients: set[asyncio.Queue] = set()
    main_loop: asyncio.AbstractEventLoop | None = None

    def process_observation(db, table_id: int, event_id: str, present: bool,
                            confidence: float, ambiguous: bool, source: str,
                            cue_confidence: float | None = None,
                            normalized_payload: dict | None = None,
                            now: datetime | None = None,
                            activity_state: str | None = None,
                            felt_motion: bool = False,
                            sides_visited: int = 1):
        now = now or utc(clock())
        table = require_table(db, table_id)
        previous = db.get(DetectionEvent, str(event_id))
        normalized = normalized_payload or {
            "event_id": str(event_id), "table_id": table_id, "present": present,
            "confidence": confidence, "ambiguous": ambiguous,
            "cue_confidence": cue_confidence, "source": source,
            "felt_motion": felt_motion, "sides_visited": sides_visited,
        }
        if previous:
            if previous.payload != normalized:
                raise HTTPException(409, "event_id đã được dùng với nội dung khác")
            return {**previous.result, "duplicate": True}

        current = active_session(db, table.id)
        cue_ready = bool(runner.cue_detector_ready) if runner else False
        decision = advance(Memory(**table.memory), Observation(
            present=present, confidence=confidence,
            ambiguous=ambiguous, cue_confidence=cue_confidence,
            activity_state=activity_state,
            felt_motion=felt_motion,
            sides_visited=sides_visited,
        ), now.timestamp(), settings.decision, active=current is not None,
            auto_open=settings.auto_open, cue_detector_ready=cue_ready)
        table.memory = asdict(decision.memory)
        if decision.should_open and current is None:
            current = new_session(db, table, now, source, source)

        result = {
            "state": decision.memory.state,
            "reason": decision.reason,
            "session_id": current.id if current else None,
            "source": source,
            "activity_state": decision.memory.activity_state,
            "unbilled_alert": decision.memory.unbilled_alert,
        }
        event_type = "AMBIGUOUS" if ambiguous else ("PRESENCE" if present else "ABSENCE")
        db.add(DetectionEvent(id=str(event_id), table_id=table.id,
            event_type=event_type, confidence=confidence, timestamp=now,
            source=source, payload=normalized, result=result))
        return {**result, "duplicate": False}

    def sync_paused_tables(db) -> None:
        """Tables with an ACTIVE session need no AI; resume the models once they are free again."""
        if runner is None:
            return
        runner.set_paused_tables({s.table_id for s in db.scalars(
            select(PlaySession).where(PlaySession.status == "ACTIVE"))})

    def on_camera_observation(table_id: int, summary: TableObservationSummary, source_type: str):
        eid = str(uuid4())
        try:
            with Session(engine) as db:
                result = process_observation(
                    db, table_id, eid, summary.present, summary.confidence,
                    summary.ambiguous, source_type, summary.cue_confidence,
                    {
                        "event_id": eid, "table_id": table_id, "present": summary.present,
                        "confidence": summary.confidence, "ambiguous": summary.ambiguous,
                        "source": source_type, "track_ids": summary.track_ids,
                        "people_count": summary.people_count,
                        "activity_state": summary.activity_state,
                        "activity_reason": summary.activity_reason,
                        "felt_motion": summary.felt_motion,
                        "sides_visited": summary.sides_visited,
                    },
                    activity_state=summary.activity_state,
                    felt_motion=summary.felt_motion,
                    sides_visited=summary.sides_visited,
                )
                db.commit()
                if result["state"] == "ACTIVE":
                    sync_paused_tables(db)
            changed()
        except Exception:
            pass

    runner = CameraRunner(
        source=settings.camera_source,
        camera_id=settings.camera_id,
        zones_config_path=settings.zones_config,
        fallback_zones_path=ROOT / "configs/zones.example.json",
        model_path=ROOT / "models/yolov8n-pose.onnx",
        fallback_model_path=ROOT / "models/yolov8n.onnx",
        cue_model_path=ROOT / "models/yolov8n-cue.onnx",
        performance=settings.vision,
        on_observation=on_camera_observation,
    )

    @asynccontextmanager
    async def lifespan(_app):
        nonlocal main_loop
        main_loop = asyncio.get_running_loop()
        Base.metadata.create_all(engine)
        # create_all does not add new indexes to tables that already exist.
        LATEST_DETECTION_EVENTS_INDEX.create(engine, checkfirst=True)
        with Session(engine) as db:
            for number in range(1, settings.table_count + 1):
                if not db.get(Table, number):
                    db.add(Table(id=number, name=f"Bàn {number:02}", hourly_rate=settings.hourly_rate,
                                 memory=asdict(Memory())))
            db.commit()
            sync_paused_tables(db)
        if settings.camera_enabled:
            runner.start()
        yield
        runner.stop()
        engine.dispose()

    app = FastAPI(title="SmartBilliard · Phase 2", version="0.1.0", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    app.state.engine = engine
    app.state.settings = settings
    app.state.runner = runner

    allowed_origins = {"http://127.0.0.1:5173", "http://localhost:5173",
                       "http://127.0.0.1:8000", "http://localhost:8000"}

    @app.middleware("http")
    async def local_origin(request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin is not None and origin not in allowed_origins:
                return JSONResponse({"detail": "Chỉ chấp nhận thao tác từ giao diện cục bộ"}, status_code=403)
        return await call_next(request)

    def changed():
        nonlocal main_loop
        if main_loop is not None and not main_loop.is_closed():
            def _notify():
                for queue in tuple(clients):
                    if queue.empty():
                        try:
                            queue.put_nowait(True)
                        except Exception:
                            pass
            try:
                main_loop.call_soon_threadsafe(_notify)
            except RuntimeError:
                pass
        else:
            for queue in tuple(clients):
                if queue.empty():
                    try:
                        queue.put_nowait(True)
                    except Exception:
                        pass

    def require_table(db, table_id):
        table = db.get(Table, table_id)
        if table is None:
            raise HTTPException(404, "Không tìm thấy bàn")
        return table

    def active_session(db, table_id):
        return db.scalar(select(PlaySession).where(
            PlaySession.table_id == table_id, PlaySession.status == "ACTIVE"))

    def serialize_session(session, now):
        return {
            "id": session.id, "table_id": session.table_id, "started_at": iso(session.started_at),
            "ended_at": iso(session.ended_at), "status": session.status,
            "hourly_rate_snapshot": session.hourly_rate_snapshot,
            "total_amount": session.total_amount, "trigger_source": session.trigger_source,
            "evidence_source": session.evidence_source,
            **quote(session.started_at, session.ended_at or now, session.hourly_rate_snapshot),
        }

    def new_session(db, table, now, source, evidence=None):
        session = PlaySession(id=str(uuid4()), table_id=table.id, started_at=now,
                              hourly_rate_snapshot=table.hourly_rate, trigger_source=source,
                              evidence_source=evidence, status="ACTIVE")
        db.add(session)
        table.memory = asdict(Memory(state="ACTIVE"))
        return session

    def snapshot():
        now = utc(clock())
        now_ts = now.timestamp()
        try:
            cal_cfg = load_calibration_config(Path(settings.zones_config), ROOT / "configs/zones.example.json")
            zones_by_id = {z.table_id: z for z in cal_cfg.tables}
        except Exception:
            zones_by_id = {}
        with Session(engine) as db:
            active = {s.table_id: s for s in db.scalars(
                select(PlaySession).where(PlaySession.status == "ACTIVE"))}
            tables = []
            for table in db.scalars(select(Table).where(Table.id <= settings.table_count).order_by(Table.id)):
                memory = Memory(**table.memory)
                state = "ACTIVE" if table.id in active else memory.state
                stale = memory.last_positive is not None and now_ts - memory.last_positive > settings.decision.absence_grace_seconds
                play_held = (
                    memory.playing_since is not None
                    and memory.last_playing is not None
                    and (now_ts - memory.last_playing) <= settings.decision.playing_hold_grace_seconds
                )
                if state == "CANDIDATE" and stale:
                    state = "EMPTY"
                if state == "NEEDS_CONFIRMATION" and stale and not play_held:
                    state = "EMPTY"

                if table.id not in active and memory.playing_since is not None and play_held:
                    unbilled_seconds = max(0, int(now_ts - memory.playing_since))
                    unbilled_alert = bool(
                        memory.unbilled_alert or unbilled_seconds >= settings.decision.unbilled_alert_seconds
                    )
                    playing_since_iso = iso(datetime.fromtimestamp(memory.playing_since, tz=timezone.utc))
                else:
                    unbilled_seconds = 0
                    unbilled_alert = False
                    playing_since_iso = None

                if stale and table.id not in active and not play_held:
                    ai_activity = "NOT_PLAYING"
                else:
                    ai_activity = memory.activity_state or "NOT_PLAYING"

                tables.append({
                    "id": table.id, "name": table.name, "status": state,
                    "hourly_rate": table.hourly_rate,
                    "session": serialize_session(active[table.id], now) if table.id in active else None,
                    "candidate_seconds": max(0, int((memory.last_positive or 0) - (memory.candidate_since or memory.last_positive or 0))),
                    "cooldown_remaining": max(0, int(memory.cooldown_until - now_ts + .999)),
                    "evidence_stale": stale,
                    "ai_activity": ai_activity,
                    "ai_paused": table.id in active,
                    "roi_calibrated": table.id in zones_by_id,
                    "roi_enabled": bool(zones_by_id[table.id].enabled) if table.id in zones_by_id else False,
                    "unbilled_playing_seconds": unbilled_seconds,
                    "unbilled_alert": unbilled_alert,
                    "playing_since": playing_since_iso,
                })
            events = [{
                "id": item.id, "table_id": item.table_id, "event_type": item.event_type,
                "confidence": item.confidence, "timestamp": iso(item.timestamp), "source": item.source,
                **item.result,
            } for item in db.scalars(select(DetectionEvent).order_by(
                DetectionEvent.timestamp.desc(), DetectionEvent.id.desc()).limit(30))]
            revenue = db.scalar(select(func.coalesce(func.sum(PlaySession.total_amount), 0)).where(
                PlaySession.status == "PAID"))
            cam_online = bool(runner and runner.is_running and runner.status in ("CONNECTED", "RUNNING"))
            if runner and runner.is_running:
                sys_mode = f"{runner.source_type}_LIVE"
            elif settings.simulation_enabled:
                sys_mode = "SIMULATED"
            else:
                sys_mode = "MANUAL_ONLY"

            unbilled_alerts = [
                {
                    "table_id": item["id"],
                    "name": item["name"],
                    "unbilled_playing_seconds": item["unbilled_playing_seconds"],
                    "playing_since": item["playing_since"],
                }
                for item in tables
                if item["unbilled_alert"]
            ]

            return {
                "type": "snapshot", "server_time": iso(now), "timezone": settings.timezone,
                "mode": sys_mode,
                "simulation_enabled": settings.simulation_enabled, "auto_open_enabled": settings.auto_open,
                "camera_ready": cam_online,
                "camera_status": runner.status if runner else "DISABLED",
                "model_status": runner.get_model_status(),
                "cue_detector_ready": runner.cue_detector_ready if runner else False,
                "decision_config": settings.decision.model_dump(), "tables": tables, "events": events,
                "active_count": len(active), "revenue_vnd": revenue,
                "running_amount_vnd": sum(quote(s.started_at, now, s.hourly_rate_snapshot)["amount_vnd"] for s in active.values()),
                "unbilled_alerts": unbilled_alerts,
            }

    @app.get("/api/health")
    async def health():
        cam_online = bool(runner and runner.is_running and runner.status in ("CONNECTED", "RUNNING"))
        return {"status": "ok", "phase": 2, "camera_ready": cam_online,
                "camera_status": runner.status if runner else "DISABLED"}

    @app.get("/api/dashboard")
    async def dashboard():
        async with lock:
            return snapshot()

    @app.get("/api/tables")
    async def tables():
        async with lock:
            return snapshot()["tables"]

    @app.get("/api/sessions")
    async def sessions(limit: int = 100, offset: int = 0):
        if not 1 <= limit <= 500 or offset < 0:
            raise HTTPException(422, "limit phải từ 1 đến 500; offset không âm")
        async with lock:
            with Session(engine) as db:
                return [serialize_session(item, utc(clock())) for item in db.scalars(
                    select(PlaySession).order_by(PlaySession.started_at.desc(), PlaySession.id.desc())
                    .offset(offset).limit(limit))]

    @app.post("/api/tables/{table_id}/open")
    async def open_table(table_id: int, backdate_to_ai: bool = False):
        async with lock:
            now = utc(clock())
            with Session(engine) as db:
                table = require_table(db, table_id)
                session = active_session(db, table_id)
                if session is None:
                    confirmed = table.memory.get("state") == "NEEDS_CONFIRMATION"
                    started_at = now
                    playing_since = table.memory.get("playing_since")
                    if backdate_to_ai and isinstance(playing_since, (int, float)) and playing_since <= now.timestamp():
                        started_at = utc(datetime.fromtimestamp(playing_since, tz=timezone.utc))
                    session = new_session(db, table, started_at, "STAFF_CONFIRMATION" if confirmed else "STAFF",
                                          "SIMULATED" if confirmed else None)
                    db.commit()
                sync_paused_tables(db)
                result = serialize_session(session, now)
            changed()
            return result

    @app.get("/api/sessions/{session_id}/quote")
    async def session_quote(session_id: str):
        async with lock:
            with Session(engine) as db:
                session = db.get(PlaySession, session_id)
                if session is None:
                    raise HTTPException(404, "Không tìm thấy phiên")
                return serialize_session(session, utc(clock()))

    @app.post("/api/sessions/{session_id}/checkout")
    async def checkout(session_id: str):
        async with lock:
            now = utc(clock())
            with Session(engine) as db:
                session = db.get(PlaySession, session_id)
                if session is None:
                    raise HTTPException(404, "Không tìm thấy phiên")
                if session.status == "ACTIVE":
                    session.ended_at = now
                    session.total_amount = quote(session.started_at, now, session.hourly_rate_snapshot)["amount_vnd"]
                    session.status = "PAID"
                    table = require_table(db, session.table_id)
                    table.memory = asdict(Memory(state="CLOSED", cooldown_until=now.timestamp() + settings.decision.cooldown_seconds))
                    db.commit()
                sync_paused_tables(db)
                result = serialize_session(session, now)
            changed()
            return result

    @app.post("/api/simulations/observations")
    async def simulate(payload: SimulatedObservation):
        if not settings.simulation_enabled:
            raise HTTPException(403, "Chế độ mô phỏng đã tắt")
        async with lock:
            with Session(engine) as db:
                result = process_observation(
                    db, payload.table_id, str(payload.event_id),
                    payload.present, payload.confidence, payload.ambiguous,
                    "SIMULATED", payload.cue_confidence, payload.model_dump(mode="json"),
                    activity_state=payload.activity_state,
                    felt_motion=payload.felt_motion,
                    sides_visited=payload.sides_visited,
                )
                db.commit()
                if result["state"] == "ACTIVE":
                    sync_paused_tables(db)
            changed()
            return result

    @app.post("/api/ingestion/events")
    async def ingest_camera_event(payload: IngestionObservation):
        async with lock:
            with Session(engine) as db:
                result = process_observation(
                    db, payload.table_id, str(payload.event_id),
                    payload.present, payload.confidence, payload.ambiguous,
                    payload.source, payload.cue_confidence, payload.model_dump(mode="json"),
                    activity_state=payload.activity_state,
                    felt_motion=payload.felt_motion,
                    sides_visited=payload.sides_visited,
                )
                db.commit()
                if result["state"] == "ACTIVE":
                    sync_paused_tables(db)
            changed()
            return result

    def settings_view():
        return {
            "decision": settings.decision.model_dump(),
            "decision_defaults": base_settings.decision.model_dump(),
            "auto_open": settings.auto_open,
            "camera_source": sanitize_uri(str(runner.source_spec)),
            "camera_source_default": sanitize_uri(base_settings.camera_source),
            "overridden": sorted(overrides),
            "persisted": overrides_path is not None,
        }

    def apply_settings(new: Settings) -> None:
        nonlocal settings
        settings = new
        app.state.settings = new

    @app.get("/api/settings")
    async def get_settings():
        return settings_view()

    @app.post("/api/settings")
    async def update_settings(payload: SettingsUpdate):
        async with lock:
            new_decision = settings.decision
            partial = payload.decision.model_dump(exclude_none=True) if payload.decision else {}
            if partial:
                try:
                    new_decision = merge_decision(settings.decision, partial)
                except ValidationError as err:
                    detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in err.errors())
                    raise HTTPException(422, f"Ngưỡng không hợp lệ: {detail}") from err
            if payload.auto_open is True and not settings.auto_open and not payload.confirm_auto_open:
                raise HTTPException(422, "Bật tự mở bàn cần xác nhận rõ ràng (confirm_auto_open)")
            changes = {"decision": new_decision}
            if payload.auto_open is not None:
                changes["auto_open"] = payload.auto_open
            source_changed = payload.camera_source is not None and payload.camera_source.strip() != str(runner.source_spec)
            if payload.camera_source is not None:
                changes["camera_source"] = payload.camera_source.strip()
            updated = {**overrides}
            if partial:
                updated["decision"] = {**overrides.get("decision", {}), **partial}
            if payload.auto_open is not None:
                updated["auto_open"] = payload.auto_open
            if payload.camera_source is not None:
                updated["camera_source"] = payload.camera_source.strip()
            save_overrides(overrides_path, updated)
            overrides.clear()
            overrides.update(updated)
            apply_settings(replace(settings, **changes))
        if source_changed:
            await asyncio.to_thread(runner.configure_source, changes["camera_source"])
        changed()
        return settings_view()

    @app.post("/api/settings/reset")
    async def reset_settings():
        async with lock:
            save_overrides(overrides_path, {})
            overrides.clear()
            apply_settings(base_settings)
        if str(runner.source_spec) != str(base_settings.camera_source):
            await asyncio.to_thread(runner.configure_source, base_settings.camera_source)
        changed()
        return settings_view()

    @app.post("/api/tables/{table_id}/rate")
    async def set_table_rate(table_id: int, payload: RateUpdate):
        async with lock:
            with Session(engine) as db:
                table = require_table(db, table_id)
                if table.id > settings.table_count:
                    raise HTTPException(404, "Không tìm thấy bàn")
                table.hourly_rate = payload.hourly_rate
                db.commit()
        changed()
        return {"table_id": table_id, "hourly_rate": payload.hourly_rate}

    @app.get("/api/camera/status")
    async def camera_status():
        return {
            "enabled": settings.camera_enabled,
            "running": runner.is_running,
            "status": runner.status,
            "source_type": runner.source_type,
            "camera_id": settings.camera_id,
            "camera_source": str(runner.source_spec),
            "fps": runner.measured_fps,
            "inference_fps": runner.inference_fps,
            "source_fps": runner.source_fps,
            "target_fps": runner.target_fps,
            "models": runner.get_model_status(),
            "paused_tables": sorted(runner.paused_tables),
            "inference_paused": runner.inference_paused,
        }

    @app.post("/api/camera/start")
    async def camera_start():
        ok = runner.start()
        changed()
        return {"success": ok, "status": runner.status}

    @app.post("/api/camera/stop")
    async def camera_stop():
        runner.stop()
        changed()
        return {"success": True, "status": runner.status}

    @app.get("/api/camera/stream")
    async def camera_stream(annotated: bool = True):
        """MJPEG video stream with real-time detection bounding boxes, foot anchors, and ROI zones."""
        async def frame_generator():
            boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
            last_sequence = -1
            while True:
                try:
                    if runner and runner.is_running:
                        sequence, frame_bytes = await asyncio.to_thread(runner.get_stream_frame, annotated)
                        if sequence == last_sequence:
                            await asyncio.sleep(.001)
                            continue
                        last_sequence = sequence
                    else:
                        frame_bytes = create_standby_frame_jpeg(
                            message="CAMERA DANG TAT",
                            sub_message="Nhan 'Bat Camera AI' de xem luong video truc tiep",
                        )
                    if frame_bytes:
                        yield boundary + frame_bytes + b"\r\n"
                    # The producer already paces real frames. Polling for its next sequence
                    # avoids compounding producer and asyncio timer rounding on Windows.
                    await asyncio.sleep(.001 if runner.is_running else .5)
                except asyncio.CancelledError:
                    break
                except Exception:
                    await asyncio.sleep(0.5)

        return StreamingResponse(
            frame_generator(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/api/camera/frame")
    async def camera_frame(annotated: bool = True):
        """Get latest camera frame as a standalone JPEG (annotated or raw)."""
        jpeg_bytes = None
        if runner and runner.is_running:
            jpeg_bytes = runner.get_annotated_frame_jpeg() if annotated else runner.get_latest_frame_jpeg()
        if jpeg_bytes is None:
            jpeg_bytes = create_standby_frame_jpeg()
        return Response(content=jpeg_bytes, media_type="image/jpeg",
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

    @app.get("/api/calibration/zones")
    async def get_calibration_zones():
        zones_path = Path(settings.zones_config)
        fallback = ROOT / "configs/zones.example.json"
        try:
            cfg = load_calibration_config(zones_path, fallback)
        except Exception as err:
            raise HTTPException(500, f"Không thể tải cấu hình ROI: {err}")
        overlaps = cfg.detect_overlaps()
        return {
            "config": cfg.model_dump(),
            "overlaps": [o.model_dump() for o in overlaps],
        }

    @app.post("/api/calibration/zones")
    async def save_calibration_zones(payload: CalibrationConfig):
        zones_path = Path(settings.zones_config)
        try:
            save_calibration_config(payload, zones_path)
            if runner and runner.is_running:
                runner.reload_calibration_config()
        except Exception as err:
            raise HTTPException(500, f"Không thể lưu cấu hình ROI: {err}")
        changed()
        overlaps = payload.detect_overlaps()
        return {
            "config": payload.model_dump(),
            "overlaps": [o.model_dump() for o in overlaps],
            "message": "Đã lưu cấu hình ROI thành công",
        }

    @app.post("/api/calibration/auto-detect")
    async def auto_detect_table_zones(payload: CalibrationConfig):
        if not runner.is_running or runner.status != "CONNECTED":
            raise HTTPException(409, "Bật camera hoặc phát video thật trước khi tự nhận diện bàn.")
        frame = runner.get_latest_frame()
        if frame is None:
            raise HTTPException(409, "Chưa có khung hình camera để nhận diện bàn.")
        try:
            result = await asyncio.to_thread(
                propose_table_zones,
                frame,
                payload,
                settings.table_count,
                settings.auto_roi,
                model_path=ROOT / "models/yolov8n-table-seg.onnx",
            )
        except ValueError as err:
            raise HTTPException(422, str(err)) from err
        return {**result, "captured_at": iso(clock())}

    def _resolve_recording(filename: str) -> Path:
        safe = _safe_video_filename(filename)
        recordings_dir.mkdir(parents=True, exist_ok=True)
        target = (recordings_dir / safe).resolve()
        if target.parent != recordings_dir.resolve() or not target.is_file():
            raise HTTPException(404, f"Không tìm thấy video: {safe}")
        return target

    def _run_video_eval(video_path: Path) -> dict:
        return evaluate_video(
            video_path,
            zones_path=Path(settings.zones_config),
            fallback_zones_path=ROOT / "configs/zones.example.json",
            pose_model_path=ROOT / "models/yolov8n-pose.onnx",
            fallback_person_model_path=ROOT / "models/yolov8n.onnx",
            cue_model_path=ROOT / "models/yolov8n-cue.onnx",
            decision_config_path=ROOT / "configs/decision.toml",
        )

    async def _release_if_active_file(dest: Path) -> None:
        if runner and runner.is_running:
            try:
                if Path(str(runner.source_spec)).resolve() == dest.resolve():
                    await asyncio.to_thread(runner.stop)
            except OSError:
                pass

    @app.get("/api/videos")
    async def list_videos():
        recordings_dir.mkdir(parents=True, exist_ok=True)
        active_path = None
        try:
            active_path = Path(str(runner.source_spec)).resolve()
        except OSError:
            active_path = None
        items = []
        for item in sorted(recordings_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if item.is_file() and item.suffix.lower() in VIDEO_EXTS:
                items.append({
                    "filename": item.name,
                    "size_bytes": item.stat().st_size,
                    "active": active_path is not None and item.resolve() == active_path and runner.is_running,
                })
        return {
            "videos": items,
            "runner_running": runner.is_running,
            "runner_status": runner.status,
            "models": {
                "pose": (ROOT / "models/yolov8n-pose.onnx").exists(),
                "person": (ROOT / "models/yolov8n.onnx").exists(),
                "cue": (ROOT / "models/yolov8n-cue.onnx").exists(),
            },
        }

    @app.post("/api/videos/upload")
    async def upload_video(
        request: Request,
        filename: str = "upload.mp4",
        auto_start: bool = True,
        auto_evaluate: bool = True,
    ):
        safe_name = _safe_video_filename(filename)
        recordings_dir.mkdir(parents=True, exist_ok=True)
        dest = (recordings_dir / safe_name).resolve()
        if dest.parent != recordings_dir.resolve():
            raise HTTPException(400, "Tên file không hợp lệ")

        await _release_if_active_file(dest)
        total_bytes = 0
        try:
            with dest.open("wb") as fh:
                async for chunk in request.stream():
                    if chunk:
                        fh.write(chunk)
                        total_bytes += len(chunk)
        except Exception as err:
            dest.unlink(missing_ok=True)
            raise HTTPException(500, f"Lỗi lưu file video: {err}")

        if total_bytes == 0:
            dest.unlink(missing_ok=True)
            raise HTTPException(400, "File video tải lên bị rỗng")

        live_started = False
        if auto_start:
            live_started = await asyncio.to_thread(runner.switch_source, str(dest))
            changed()

        evaluation = None
        if auto_evaluate:
            evaluation = await asyncio.to_thread(_run_video_eval, dest)

        return {
            "filename": safe_name,
            "size_bytes": total_bytes,
            "live_started": live_started,
            "runner_status": runner.status,
            "evaluation": evaluation,
        }

    @app.post("/api/videos/activate")
    async def activate_video(payload: VideoActionRequest):
        target = _resolve_recording(payload.filename)
        ok = await asyncio.to_thread(runner.switch_source, str(target))
        changed()
        return {"success": ok, "status": runner.status, "filename": target.name}

    @app.post("/api/videos/evaluate")
    async def evaluate_uploaded_video(payload: VideoActionRequest):
        target = _resolve_recording(payload.filename)
        return await asyncio.to_thread(_run_video_eval, target)

    @app.post("/api/videos/generate-demo")
    async def generate_and_run_demo_video(payload: GenerateDemoRequest | None = None):
        duration_s = payload.duration_seconds if payload else 35.0
        recordings_dir.mkdir(parents=True, exist_ok=True)
        dest = (recordings_dir / "demo_auto.mp4").resolve()
        await _release_if_active_file(dest)
        await asyncio.to_thread(generate_synthetic_demo_video, dest, duration_seconds=duration_s, fps=6.0)
        live_started = await asyncio.to_thread(runner.switch_source, str(dest))
        changed()
        evaluation = await asyncio.to_thread(_run_video_eval, dest)
        return {
            "filename": dest.name,
            "size_bytes": dest.stat().st_size,
            "live_started": live_started,
            "runner_status": runner.status,
            "evaluation": evaluation,
        }

    @app.post("/api/videos/extract-dataset")
    async def extract_video_dataset(payload: ExtractDatasetRequest):
        target = _resolve_recording(payload.filename)
        manifest = await asyncio.to_thread(
            extract_dataset,
            [target],
            datasets_dir,
            interval_seconds=payload.interval,
            init_empty_labels=True,
        )
        return {**manifest, "dataset_yaml": str((datasets_dir / "dataset.yaml").as_posix())}

    @app.post("/api/videos/delete")
    async def delete_video(payload: VideoActionRequest):
        target = _resolve_recording(payload.filename)
        was_running = False
        try:
            points_to_target = Path(str(runner.source_spec)).resolve() == target.resolve()
        except OSError:
            points_to_target = False
        if points_to_target:
            was_running = bool(runner and runner.is_running)
            await _release_if_active_file(target)
            fallback_source = settings.camera_source
            try:
                if Path(str(fallback_source)).resolve() == target.resolve():
                    fallback_source = base_settings.camera_source
            except OSError:
                pass
            await asyncio.to_thread(runner.configure_source, fallback_source)
        target.unlink()
        if was_running:
            changed()
        return {"deleted": True, "filename": target.name, "stopped_live": was_running}

    @app.get("/api/calibration/preview")
    async def get_calibration_preview():
        try:
            jpeg_bytes = None
            if runner and runner.is_running:
                jpeg_bytes = runner.get_latest_frame_jpeg()
            if jpeg_bytes is None:
                jpeg_bytes = get_preview_frame_jpeg(str(runner.source_spec), settings.camera_id)
            return Response(content=jpeg_bytes, media_type="image/jpeg",
                            headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
        except Exception as err:
            raise HTTPException(500, f"Lỗi tạo ảnh preview: {err}")

    @app.websocket("/ws")
    async def websocket(socket: WebSocket):
        # The API is loopback-only; reject cross-site browser control of the local dashboard.
        origin = socket.headers.get("origin")
        if origin and origin not in allowed_origins:
            await socket.close(code=1008)
            return
        await socket.accept()
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        clients.add(queue)
        try:
            while True:
                try:
                    async with lock:
                        data = snapshot()
                    await socket.send_json(data)
                except (WebSocketDisconnect, OSError):
                    break
                except Exception as ex:
                    logger.warning("WebSocket snapshot error: %s", ex)
                    await asyncio.sleep(0.5)
                    continue

                try:
                    await asyncio.wait_for(queue.get(), timeout=1)
                except asyncio.TimeoutError:
                    pass
        except (WebSocketDisconnect, OSError, RuntimeError):
            pass
        finally:
            clients.discard(queue)

    # Built assets let the entire demo run from one loopback origin, including offline.
    dist = ROOT / "apps/web/dist"
    if (dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="dashboard")
    return app


app = create_app()
