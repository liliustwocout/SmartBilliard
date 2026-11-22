"""API của admin nền tảng: quản lý quán, tài khoản chủ quán và khách theo quán."""
import re
import secrets
import unicodedata
from datetime import datetime
from typing import Annotated, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.manage_api.auth import Principal, audit, utc_naive
from apps.manage_api.models import AuthSession, User, Venue
from apps.manage_api.security import hash_password
from apps.manage_api.textutil import fold

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RESERVED_SLUGS = {"admin", "api", "assets", "login", "static", "c", "shop", "health"}
_TEMP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFD", name.replace("đ", "d").replace("Đ", "D"))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:40].strip("-")


def temp_password() -> str:
    """Mật khẩu tạm, bỏ ký tự dễ nhầm (0/O, 1/l/I). Chỉ trả cho admin đúng một lần."""
    return "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(14))


class OwnerBody(BaseModel):
    login: str = Field(min_length=3, max_length=120)
    display_name: str = Field(min_length=1, max_length=120)


class VenueCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str | None = Field(default=None, max_length=60)
    owner: OwnerBody


class VenueUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    status: Literal["ACTIVE", "SUSPENDED"] | None = None


class UserStatus(BaseModel):
    status: Literal["ACTIVE", "DISABLED"]


def build_admin(get_db: Callable, require_roles: Callable, now_fn: Callable[[], datetime]) -> APIRouter:
    router = APIRouter(prefix="/api/admin", tags=["admin"])
    AdminOnly = Annotated[Principal, Depends(require_roles("platform_admin"))]
    Db = Annotated[Session, Depends(get_db)]

    def venue_or_404(db: Session, venue_id: int) -> Venue:
        venue = db.get(Venue, venue_id)
        if venue is None:
            raise HTTPException(404, "Không tìm thấy quán.")
        return venue

    def counts(db: Session, venue_id: int) -> dict:
        rows = dict(db.execute(select(User.role, func.count()).where(User.venue_id == venue_id).group_by(User.role)).all())
        return {"owners": rows.get("owner", 0), "staff": rows.get("staff", 0), "customers": rows.get("customer", 0)}

    def view(db: Session, venue: Venue) -> dict:
        owner = db.scalar(select(User).where(User.venue_id == venue.id, User.role == "owner").order_by(User.id))
        return {
            "id": venue.id, "name": venue.name, "slug": venue.slug, "status": venue.status,
            "created_at": venue.created_at.isoformat() + "Z", "counts": counts(db, venue.id),
            "owner": {"id": owner.id, "login": owner.login, "display_name": owner.display_name, "status": owner.status,
                      "must_change_password": owner.must_change_password} if owner else None,
        }

    def revoke_sessions(db: Session, user_ids) -> None:
        for session in db.scalars(select(AuthSession).where(AuthSession.user_id.in_(list(user_ids)))):
            db.delete(session)

    @router.get("/overview")
    def overview(_: AdminOnly, db: Db):
        venues = dict(db.execute(select(Venue.status, func.count()).group_by(Venue.status)).all())
        users = dict(db.execute(select(User.role, func.count()).group_by(User.role)).all())
        return {"venues": {"active": venues.get("ACTIVE", 0), "suspended": venues.get("SUSPENDED", 0)},
                "users": {role: users.get(role, 0) for role in ("owner", "staff", "customer")}}

    @router.get("/venues")
    def list_venues(_: AdminOnly, db: Db, q: str = "", limit: int = 50, offset: int = 0):
        query = select(Venue).order_by(Venue.id.desc())
        if q.strip():
            like = f"%{fold(q.strip())}%"
            query = query.where(or_(func.fold(Venue.name).like(like), Venue.slug.like(like)))
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.limit(max(1, min(limit, 200))).offset(max(0, offset))).all()
        return {"total": total, "items": [view(db, v) for v in rows]}

    @router.post("/venues", status_code=201)
    def create_venue(body: VenueCreate, principal: AdminOnly, db: Db):
        slug = (body.slug or slugify(body.name)).strip().lower()
        if not SLUG_RE.fullmatch(slug) or not 3 <= len(slug) <= 40:
            raise HTTPException(400, "Địa chỉ quán chỉ gồm chữ thường, số và dấu gạch ngang (3–40 ký tự).")
        if slug in RESERVED_SLUGS:
            raise HTTPException(400, "Địa chỉ quán này được hệ thống giữ chỗ. Hãy chọn tên khác.")
        login = body.owner.login.strip().lower()
        if db.scalar(select(Venue.id).where(Venue.slug == slug)):
            raise HTTPException(409, "Địa chỉ quán đã được dùng.")
        if db.scalar(select(User.id).where(User.login == login, User.role != "customer")):
            raise HTTPException(409, "Tên đăng nhập của chủ quán đã tồn tại.")
        now = now_fn()
        password = temp_password()
        venue = Venue(name=body.name.strip(), slug=slug, created_at=utc_naive(now))
        db.add(venue)
        try:
            db.flush()
            db.add(User(role="owner", login=login, display_name=body.owner.display_name.strip(),
                        password_hash=hash_password(password), venue_id=venue.id, must_change_password=True,
                        created_at=utc_naive(now)))
            audit(db, now, "venue_created", actor=principal.user, venue_id=venue.id, target=slug,
                  detail={"name": venue.name, "owner_login": login})
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Quán hoặc tài khoản chủ quán bị trùng.")
        return {"venue": view(db, venue), "owner_temp_password": password}

    @router.get("/venues/{venue_id}")
    def get_venue(venue_id: int, _: AdminOnly, db: Db):
        return view(db, venue_or_404(db, venue_id))

    @router.patch("/venues/{venue_id}")
    def update_venue(venue_id: int, body: VenueUpdate, principal: AdminOnly, db: Db):
        venue = venue_or_404(db, venue_id)
        changes = {}
        if body.name is not None and body.name.strip() != venue.name:
            changes["name"] = [venue.name, body.name.strip()]
            venue.name = body.name.strip()
        if body.status is not None and body.status != venue.status:
            changes["status"] = [venue.status, body.status]
            venue.status = body.status
            if body.status == "SUSPENDED":
                revoke_sessions(db, db.scalars(select(User.id).where(User.venue_id == venue.id)))
        if changes:
            audit(db, now_fn(), "venue_updated", actor=principal.user, venue_id=venue.id, target=venue.slug, detail=changes)
            db.commit()
        return view(db, venue)

    @router.post("/venues/{venue_id}/owner/reset-password")
    def reset_owner_password(venue_id: int, principal: AdminOnly, db: Db):
        venue = venue_or_404(db, venue_id)
        owner = db.scalar(select(User).where(User.venue_id == venue.id, User.role == "owner").order_by(User.id))
        if owner is None:
            raise HTTPException(404, "Quán chưa có chủ quán.")
        password = temp_password()
        owner.password_hash = hash_password(password)
        owner.must_change_password = True
        owner.failed_attempts, owner.locked_until = 0, None
        revoke_sessions(db, [owner.id])
        audit(db, now_fn(), "owner_password_reset", actor=principal.user, venue_id=venue.id, target=owner.login)
        db.commit()
        return {"owner_login": owner.login, "owner_temp_password": password}

    @router.get("/venues/{venue_id}/customers")
    def venue_customers(venue_id: int, _: AdminOnly, db: Db, q: str = "", limit: int = 50, offset: int = 0):
        venue = venue_or_404(db, venue_id)
        query = select(User).where(User.venue_id == venue.id, User.role == "customer").order_by(User.id.desc())
        if q.strip():
            like = f"%{fold(q.strip())}%"
            query = query.where(or_(func.fold(User.display_name).like(like), User.login.like(like)))
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.limit(max(1, min(limit, 200))).offset(max(0, offset))).all()
        return {"total": total, "items": [{"id": u.id, "login": u.login, "display_name": u.display_name, "status": u.status,
                                           "created_at": u.created_at.isoformat() + "Z"} for u in rows]}

    @router.patch("/users/{user_id}/status")
    def set_user_status(user_id: int, body: UserStatus, principal: AdminOnly, db: Db):
        user = db.get(User, user_id)
        if user is None or user.role == "platform_admin":
            raise HTTPException(404, "Không tìm thấy tài khoản.")
        if user.status != body.status:
            before, user.status = user.status, body.status
            if body.status == "DISABLED":
                revoke_sessions(db, [user.id])
            audit(db, now_fn(), "user_status_changed", actor=principal.user, venue_id=user.venue_id, target=user.login,
                  detail={"role": user.role, "from": before, "to": body.status})
            db.commit()
        return {"id": user.id, "status": user.status}

    return router
