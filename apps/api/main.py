import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
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
from apps.api.models import Base, DetectionEvent, PlaySession, Table
from apps.api.schemas import IngestionObservation, SimulatedObservation
from services.vision.decision import Memory, Observation, advance
from services.vision.annotator import create_standby_frame_jpeg
from services.vision.calibration import CalibrationConfig, load_calibration_config, save_calibration_config
from services.vision.mapper import TableObservationSummary
from services.vision.preview import get_preview_frame_jpeg
from services.vision.runner import CameraRunner


def iso(value: datetime | None) -> str | None:
    return utc(value).isoformat() if value else None


def create_app(settings: Settings | None = None,
               clock: Callable[[], datetime] | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    clock = clock or (lambda: datetime.now(timezone.utc))
    url = make_url(settings.database_url)
    if url.database and url.database != ":memory:":
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False},
                           **({"poolclass": StaticPool} if url.database in (None, "", ":memory:") else {}))

    @event.listens_for(engine, "connect")
    def sqlite_setup(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")

    lock = asyncio.Lock()
    clients: set[asyncio.Queue] = set()

    def process_observation(db, table_id: int, event_id: str, present: bool,
                            confidence: float, ambiguous: bool, source: str,
                            cue_confidence: float | None = None,
                            normalized_payload: dict | None = None,
                            now: datetime | None = None):
        now = now or utc(clock())
        table = require_table(db, table_id)
        previous = db.get(DetectionEvent, str(event_id))
        normalized = normalized_payload or {
            "event_id": str(event_id), "table_id": table_id, "present": present,
            "confidence": confidence, "ambiguous": ambiguous,
            "cue_confidence": cue_confidence, "source": source,
        }
        if previous:
            if previous.payload != normalized:
                raise HTTPException(409, "event_id đã được dùng với nội dung khác")
            return {**previous.result, "duplicate": True}

        current = active_session(db, table.id)
        decision = advance(Memory(**table.memory), Observation(
            present=present, confidence=confidence,
            ambiguous=ambiguous, cue_confidence=cue_confidence,
        ), now.timestamp(), settings.decision, active=current is not None,
            auto_open=settings.auto_open, cue_detector_ready=False)
        table.memory = asdict(decision.memory)
        if decision.should_open and current is None:
            current = new_session(db, table, now, source, source)

        result = {"state": decision.memory.state, "reason": decision.reason,
                  "session_id": current.id if current else None, "source": source}
        event_type = "AMBIGUOUS" if ambiguous else ("PRESENCE" if present else "ABSENCE")
        db.add(DetectionEvent(id=str(event_id), table_id=table.id,
            event_type=event_type, confidence=confidence, timestamp=now,
            source=source, payload=normalized, result=result))
        return {**result, "duplicate": False}

    def on_camera_observation(table_id: int, summary: TableObservationSummary, source_type: str):
        eid = str(uuid4())
        try:
            with Session(engine) as db:
                process_observation(
                    db, table_id, eid, summary.present, summary.confidence,
                    summary.ambiguous, source_type, summary.cue_confidence,
                    {
                        "event_id": eid, "table_id": table_id, "present": summary.present,
                        "confidence": summary.confidence, "ambiguous": summary.ambiguous,
                        "source": source_type, "track_ids": summary.track_ids,
                        "people_count": summary.people_count,
                    }
                )
                db.commit()
            changed()
        except Exception:
            pass

    runner = CameraRunner(
        source=settings.camera_source,
        camera_id=settings.camera_id,
        zones_config_path=settings.zones_config,
        fallback_zones_path=ROOT / "configs/zones.example.json",
        model_path=ROOT / "models/yolov8n.onnx",
        on_observation=on_camera_observation,
    )

    @asynccontextmanager
    async def lifespan(_app):
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            for number in range(1, settings.table_count + 1):
                if not db.get(Table, number):
                    db.add(Table(id=number, name=f"Bàn {number:02}", hourly_rate=settings.hourly_rate,
                                 memory=asdict(Memory())))
            db.commit()
        if settings.camera_enabled:
            runner.start()
        yield
        runner.stop()
        engine.dispose()

    app = FastAPI(title="SmartBilliard · Phase 2", version="0.1.0", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    app.state.engine = engine
    app.state.settings = settings

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
        for queue in tuple(clients):
            if queue.empty():
                queue.put_nowait(True)

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
        with Session(engine) as db:
            active = {s.table_id: s for s in db.scalars(
                select(PlaySession).where(PlaySession.status == "ACTIVE"))}
            tables = []
            for table in db.scalars(select(Table).order_by(Table.id)):
                memory = Memory(**table.memory)
                state = "ACTIVE" if table.id in active else memory.state
                stale = memory.last_positive is not None and now.timestamp() - memory.last_positive > settings.decision.absence_grace_seconds
                if state == "CANDIDATE" and stale:
                    state = "EMPTY"
                tables.append({
                    "id": table.id, "name": table.name, "status": state,
                    "hourly_rate": table.hourly_rate,
                    "session": serialize_session(active[table.id], now) if table.id in active else None,
                    "candidate_seconds": max(0, int((memory.last_positive or 0) - (memory.candidate_since or memory.last_positive or 0))),
                    "cooldown_remaining": max(0, int(memory.cooldown_until - now.timestamp() + .999)),
                    "evidence_stale": stale,
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

            return {
                "type": "snapshot", "server_time": iso(now), "timezone": settings.timezone,
                "mode": sys_mode,
                "simulation_enabled": settings.simulation_enabled, "auto_open_enabled": settings.auto_open,
                "camera_ready": cam_online,
                "camera_status": runner.status if runner else "DISABLED",
                "cue_detector_ready": False,
                "decision_config": settings.decision.model_dump(), "tables": tables, "events": events,
                "active_count": len(active), "revenue_vnd": revenue,
                "running_amount_vnd": sum(quote(s.started_at, now, s.hourly_rate_snapshot)["amount_vnd"] for s in active.values()),
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
    async def open_table(table_id: int):
        async with lock:
            now = utc(clock())
            with Session(engine) as db:
                table = require_table(db, table_id)
                session = active_session(db, table_id)
                if session is None:
                    confirmed = table.memory.get("state") == "NEEDS_CONFIRMATION"
                    session = new_session(db, table, now, "STAFF_CONFIRMATION" if confirmed else "STAFF",
                                          "SIMULATED" if confirmed else None)
                    db.commit()
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
                )
                db.commit()
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
                )
                db.commit()
            changed()
            return result

    @app.get("/api/camera/status")
    async def camera_status():
        return {
            "enabled": settings.camera_enabled,
            "running": runner.is_running,
            "status": runner.status,
            "source_type": runner.source_type,
            "camera_id": settings.camera_id,
            "camera_source": settings.camera_source,
            "fps": runner.measured_fps,
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
    async def camera_stream():
        """MJPEG video stream with real-time detection bounding boxes, foot anchors, and ROI zones."""
        async def frame_generator():
            boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
            while True:
                try:
                    if runner and runner.is_running:
                        frame_bytes = runner.get_annotated_frame_jpeg()
                    else:
                        frame_bytes = create_standby_frame_jpeg(
                            message="CAMERA DANG TAT",
                            sub_message="Nhan 'Bat Camera AI' de xem luong video truc tiep",
                        )
                    if frame_bytes:
                        yield boundary + frame_bytes + b"\r\n"
                    # Throttle stream output to ~10 FPS for local bandwidth/CPU efficiency
                    await asyncio.sleep(0.1)
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
        overlaps = payload.detect_overlaps()
        return {
            "config": payload.model_dump(),
            "overlaps": [o.model_dump() for o in overlaps],
            "message": "Đã lưu cấu hình ROI thành công",
        }

    @app.get("/api/calibration/preview")
    async def get_calibration_preview():
        try:
            jpeg_bytes = None
            if runner and runner.is_running:
                jpeg_bytes = runner.get_latest_frame_jpeg()
            if jpeg_bytes is None:
                jpeg_bytes = get_preview_frame_jpeg(settings.camera_source, settings.camera_id)
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
                async with lock:
                    data = snapshot()
                await socket.send_json(data)
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
