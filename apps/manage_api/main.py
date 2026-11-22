from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url
from sqlalchemy.pool import StaticPool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from apps.manage_api.config import ManageSettings
from apps.manage_api.admin import build_admin
from apps.manage_api.auth import Principal, build_auth
from apps.manage_api.textutil import fold
from apps.manage_api.models import AuditLog, Base, User, Venue


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
        connection.create_function("fold", 1, fold, deterministic=True)

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

    def get_db():
        with Session(engine) as db:
            yield db

    auth_router, current_principal, require_roles, venue_scope = build_auth(get_db, clock, settings.cookie_secure)
    app.include_router(auth_router)
    app.include_router(build_admin(get_db, require_roles, clock))
    app.state.clock = clock

    @app.get("/api/venues/{venue_id}")
    def get_venue(venue_id: int, principal: Annotated[Principal, Depends(venue_scope)],
                  db: Annotated[Session, Depends(get_db)]):
        venue = db.get(Venue, venue_id)
        if venue is None:
            raise HTTPException(404, "Không tìm thấy quán.")
        return {"id": venue.id, "name": venue.name, "slug": venue.slug, "status": venue.status}

    @app.get("/api/admin/audit")
    def admin_audit(_: Annotated[Principal, Depends(require_roles("platform_admin"))],
                    db: Annotated[Session, Depends(get_db)], limit: int = 100):
        rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(max(1, min(limit, 500)))).all()
        logins = dict(db.execute(select(User.id, User.login).where(User.id.in_({r.actor_user_id for r in rows if r.actor_user_id}))).all())
        return [{"id": r.id, "at": r.at.isoformat() + "Z", "actor_user_id": r.actor_user_id,
                 "actor_login": logins.get(r.actor_user_id), "venue_id": r.venue_id,
                 "action": r.action, "target": r.target, "detail": r.detail} for r in rows]

    @app.get("/api/health")
    async def health():
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "app": "manage", "time": clock().astimezone(timezone.utc).isoformat()}

    return app
