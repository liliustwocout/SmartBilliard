import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
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
from apps.api.schemas import SimulatedObservation
from services.vision.decision import Memory, Observation, advance


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

    @asynccontextmanager
    async def lifespan(_app):
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            for number in range(1, settings.table_count + 1):
                if not db.get(Table, number):
                    db.add(Table(id=number, name=f"Bàn {number:02}", hourly_rate=settings.hourly_rate,
                                 memory=asdict(Memory())))
            db.commit()
        yield
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
            return {
                "type": "snapshot", "server_time": iso(now), "timezone": settings.timezone,
                "mode": "SIMULATED" if settings.simulation_enabled else "MANUAL_ONLY",
                "simulation_enabled": settings.simulation_enabled, "auto_open_enabled": settings.auto_open,
                "camera_ready": False, "cue_detector_ready": False,
                "decision_config": settings.decision.model_dump(), "tables": tables, "events": events,
                "active_count": len(active), "revenue_vnd": revenue,
                "running_amount_vnd": sum(quote(s.started_at, now, s.hourly_rate_snapshot)["amount_vnd"] for s in active.values()),
            }

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "phase": 2, "camera_ready": False}

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
            now = utc(clock())
            with Session(engine) as db:
                table = require_table(db, payload.table_id)
                previous = db.get(DetectionEvent, str(payload.event_id))
                normalized = payload.model_dump(mode="json")
                if previous:
                    if previous.payload != normalized:
                        raise HTTPException(409, "event_id đã được dùng với nội dung khác")
                    return {**previous.result, "duplicate": True}
                current = active_session(db, table.id)
                decision = advance(Memory(**table.memory), Observation(
                    present=payload.present, confidence=payload.confidence,
                    ambiguous=payload.ambiguous, cue_confidence=payload.cue_confidence,
                ), now.timestamp(), settings.decision, active=current is not None,
                    auto_open=settings.auto_open, cue_detector_ready=False)
                table.memory = asdict(decision.memory)
                if decision.should_open and current is None:
                    current = new_session(db, table, now, "SIMULATED", "SIMULATED")
                result = {"state": decision.memory.state, "reason": decision.reason,
                          "session_id": current.id if current else None, "source": "SIMULATED"}
                db.add(DetectionEvent(id=str(payload.event_id), table_id=table.id,
                    event_type="AMBIGUOUS" if payload.ambiguous else "PRESENCE" if payload.present else "ABSENCE",
                    confidence=payload.confidence, timestamp=now, source="SIMULATED",
                    payload=normalized, result=result))
                db.commit()
            changed()
            return {**result, "duplicate": False}

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
