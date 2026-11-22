from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from fastapi import FastAPI
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import StaticPool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from apps.manage_api.config import ManageSettings
from apps.manage_api.models import Base


def create_app(settings: ManageSettings | None = None,
               clock: Callable[[], datetime] | None = None) -> FastAPI:
    settings = settings or ManageSettings.from_env()
    clock = clock or (lambda: datetime.now(timezone.utc))
    url = make_url(settings.database_url)
    in_memory = url.database in (None, "", ":memory:")
    if not in_memory:
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False},
                           **({"poolclass": StaticPool} if in_memory else {}))

    @event.listens_for(engine, "connect")
    def sqlite_setup(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")

    @asynccontextmanager
    async def lifespan(_app):
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(title="SmartBilliard · Phòng quản lý", version="0.1.0", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    app.state.engine = engine
    app.state.settings = settings

    @app.middleware("http")
    async def same_origin_writes(request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin is not None and origin not in settings.allowed_origins:
                return JSONResponse({"detail": "Nguồn yêu cầu không được chấp nhận"}, status_code=403)
        return await call_next(request)

    @app.get("/api/health")
    async def health():
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "app": "manage", "time": clock().astimezone(timezone.utc).isoformat()}

    return app
