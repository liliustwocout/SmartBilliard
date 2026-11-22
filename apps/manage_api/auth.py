"""Xác thực, phiên, CSRF, phân quyền và cô lập theo quán."""
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Annotated, Callable

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.manage_api.models import AuditLog, AuthSession, User, Venue
from apps.manage_api.security import DUMMY_HASH, hash_password, new_token, password_problem, token_digest, verify_password

COOKIE = "sb_manage_session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
SESSION_HOURS = 12
MAX_FAILED = 5
LOCK_MINUTES = 15
IP_WINDOW_SECONDS = 300
IP_MAX_ATTEMPTS = 30
GENERIC_LOGIN_ERROR = "Sai tài khoản hoặc mật khẩu."


def utc_naive(value: datetime) -> datetime:
    """SQLite lưu datetime không múi giờ; quy ước toàn bộ là UTC."""
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def audit(db: Session, now: datetime, action: str, *, actor: User | None = None, venue_id: int | None = None,
          target: str | None = None, detail: dict | None = None) -> None:
    db.add(AuditLog(at=utc_naive(now), actor_user_id=actor.id if actor else None,
                    venue_id=venue_id if venue_id is not None else (actor.venue_id if actor else None),
                    action=action, target=target, detail=detail or {}))


class LoginBody(BaseModel):
    login: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=200)
    venue_slug: str | None = Field(default=None, max_length=60)


class ChangePasswordBody(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


def public_user(user: User, venue: Venue | None, csrf_token: str | None = None) -> dict:
    return {
        "id": user.id, "role": user.role, "login": user.login, "display_name": user.display_name,
        "must_change_password": user.must_change_password,
        "venue": {"id": venue.id, "name": venue.name, "slug": venue.slug} if venue else None,
        **({"csrf_token": csrf_token} if csrf_token else {}),
    }


class Principal:
    """Người đang đăng nhập đã được xác minh cho request hiện tại."""
    def __init__(self, user: User, session: AuthSession, venue: Venue | None):
        self.user, self.session, self.venue = user, session, venue


def build_auth(get_db: Callable, now_fn: Callable[[], datetime], cookie_secure: bool):
    """Tạo router + dependency gắn với DB/clock của app (không dùng biến toàn cục)."""
    router = APIRouter(prefix="/api/auth", tags=["auth"])
    ip_hits: dict[str, deque] = defaultdict(deque)

    def client_ip(request: Request) -> str:
        # Không tin X-Forwarded-For ở M1; reverse proxy sẽ được cấu hình rõ khi triển khai.
        return request.client.host if request.client else "unknown"

    def throttle(request: Request) -> None:
        now = now_fn().timestamp()
        hits = ip_hits[client_ip(request)]
        while hits and now - hits[0] > IP_WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= IP_MAX_ATTEMPTS:
            raise HTTPException(429, "Thử đăng nhập quá nhiều lần. Đợi vài phút rồi thử lại.")
        hits.append(now)

    def current_principal(request: Request, db: Annotated[Session, Depends(get_db)],
                          token: Annotated[str | None, Cookie(alias=COOKIE)] = None,
                          csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None) -> Principal:
        if not token:
            raise HTTPException(401, "Cần đăng nhập.")
        now = utc_naive(now_fn())
        session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(token)))
        if session is None or session.expires_at <= now:
            raise HTTPException(401, "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.")
        user = db.get(User, session.user_id)
        venue = db.get(Venue, user.venue_id) if user and user.venue_id else None
        if user is None or user.status != "ACTIVE" or (venue is not None and venue.status != "ACTIVE"):
            raise HTTPException(401, "Tài khoản hoặc quán đã bị khoá.")
        if request.method not in SAFE_METHODS and not (csrf and csrf == session.csrf_token):
            raise HTTPException(403, "Thiếu hoặc sai mã CSRF.")
        session.last_seen_at = now
        db.commit()
        return Principal(user, session, venue)

    def require_roles(*roles: str) -> Callable:
        def dependency(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
            if principal.user.role not in roles:
                raise HTTPException(403, "Bạn không có quyền thực hiện thao tác này.")
            if principal.user.must_change_password:
                raise HTTPException(403, "Cần đổi mật khẩu trước khi tiếp tục.")
            return principal
        return dependency

    def venue_scope(venue_id: int, principal: Annotated[Principal, Depends(require_roles("platform_admin", "owner", "staff", "customer"))]) -> Principal:
        """Cô lập quán: người dùng thuộc quán chỉ truy cập đúng quán của mình. Admin được xem mọi quán."""
        if principal.user.role != "platform_admin" and principal.user.venue_id != venue_id:
            # 404 thay vì 403 để không lộ quán khác có tồn tại hay không.
            raise HTTPException(404, "Không tìm thấy quán.")
        return principal

    def require_venue_roles(*roles: str) -> Callable:
        """Vai trò trong ĐÚNG quán của URL. Quản trị nền tảng không vận hành quán nên không nằm trong các vai trò này."""
        def dependency(venue_id: int, principal: Annotated[Principal, Depends(require_roles(*roles))]) -> Principal:
            if principal.user.venue_id != venue_id:
                raise HTTPException(404, "Không tìm thấy quán.")
            return principal
        return dependency

    @router.post("/login")
    def login(body: LoginBody, request: Request, response: Response, db: Annotated[Session, Depends(get_db)]):
        throttle(request)
        now = now_fn()
        naive_now = utc_naive(now)
        login_id = body.login.strip().lower()
        query = select(User).where(User.login == login_id)
        venue = None
        if body.venue_slug:
            venue = db.scalar(select(Venue).where(Venue.slug == body.venue_slug))
            query = query.where(User.role == "customer", User.venue_id == (venue.id if venue else -1))
        else:
            query = query.where(User.role != "customer")
        user = db.scalar(query)

        if user is None:
            verify_password(body.password, DUMMY_HASH)
            audit(db, now, "login_failed", target=login_id, detail={"reason": "unknown"})
            db.commit()
            raise HTTPException(401, GENERIC_LOGIN_ERROR)
        if user.locked_until and user.locked_until > naive_now:
            audit(db, now, "login_blocked_locked", actor=user)
            db.commit()
            raise HTTPException(423, "Tài khoản tạm khoá do nhập sai nhiều lần. Thử lại sau ít phút.")
        if not verify_password(body.password, user.password_hash):
            user.failed_attempts += 1
            if user.failed_attempts >= MAX_FAILED:
                user.locked_until = naive_now + timedelta(minutes=LOCK_MINUTES)
                user.failed_attempts = 0
                audit(db, now, "account_locked", actor=user)
            audit(db, now, "login_failed", actor=user, detail={"reason": "bad_password"})
            db.commit()
            raise HTTPException(401, GENERIC_LOGIN_ERROR)
        user_venue = db.get(Venue, user.venue_id) if user.venue_id else None
        if user.status != "ACTIVE" or (user_venue is not None and user_venue.status != "ACTIVE"):
            audit(db, now, "login_blocked_disabled", actor=user)
            db.commit()
            raise HTTPException(401, GENERIC_LOGIN_ERROR)

        user.failed_attempts = 0
        user.locked_until = None
        token, csrf = new_token(), new_token()
        db.add(AuthSession(token_hash=token_digest(token), csrf_token=csrf, user_id=user.id, created_at=naive_now,
                           last_seen_at=naive_now, expires_at=naive_now + timedelta(hours=SESSION_HOURS)))
        audit(db, now, "login_ok", actor=user)
        db.commit()
        response.set_cookie(COOKIE, token, max_age=SESSION_HOURS * 3600, httponly=True, samesite="lax",
                            secure=cookie_secure, path="/")
        return public_user(user, user_venue, csrf)

    @router.get("/me")
    def me(principal: Annotated[Principal, Depends(current_principal)]):
        return public_user(principal.user, principal.venue, principal.session.csrf_token)

    @router.post("/logout")
    def logout(response: Response, principal: Annotated[Principal, Depends(current_principal)],
               db: Annotated[Session, Depends(get_db)]):
        db.delete(db.get(AuthSession, principal.session.id))
        audit(db, now_fn(), "logout", actor=principal.user)
        db.commit()
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @router.post("/change-password")
    def change_password(body: ChangePasswordBody, principal: Annotated[Principal, Depends(current_principal)],
                        db: Annotated[Session, Depends(get_db)]):
        user = principal.user
        if not verify_password(body.current_password, user.password_hash):
            raise HTTPException(400, "Mật khẩu hiện tại không đúng.")
        problem = password_problem(body.new_password)
        if problem:
            raise HTTPException(400, problem)
        if body.new_password == body.current_password:
            raise HTTPException(400, "Mật khẩu mới phải khác mật khẩu hiện tại.")
        user.password_hash = hash_password(body.new_password)
        user.must_change_password = False
        # Đăng xuất mọi thiết bị khác.
        for other in db.scalars(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.id != principal.session.id)):
            db.delete(other)
        audit(db, now_fn(), "password_changed", actor=user)
        db.commit()
        return {"ok": True}

    return router, current_principal, require_roles, venue_scope, require_venue_roles
