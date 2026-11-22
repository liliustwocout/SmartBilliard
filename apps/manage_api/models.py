from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ROLES = ("platform_admin", "owner", "staff", "customer")


class Base(DeclarativeBase):
    """Metadata riêng của phòng quản lý; không dùng chung với apps.api.models.Base."""


class Venue(Base):
    """Một quán (tenant). Mọi dữ liệu nghiệp vụ sau này đều gắn venue_id."""
    __tablename__ = "venues"
    __table_args__ = (CheckConstraint("status IN ('ACTIVE', 'SUSPENDED')"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('platform_admin', 'owner', 'staff', 'customer')"),
        CheckConstraint("status IN ('ACTIVE', 'DISABLED')"),
        # Admin/chủ quán/nhân viên: tên đăng nhập duy nhất toàn hệ thống.
        Index("uq_staff_login", "login", unique=True, sqlite_where=text("role != 'customer'")),
        # Khách: duy nhất trong từng quán (cùng SĐT ở hai quán là hai tài khoản độc lập).
        Index("uq_customer_login_per_venue", "venue_id", "login", unique=True, sqlite_where=text("role = 'customer'")),
        # Admin không thuộc quán nào; các vai trò còn lại bắt buộc có quán.
        CheckConstraint("(role = 'platform_admin' AND venue_id IS NULL) OR (role != 'platform_admin' AND venue_id IS NOT NULL)"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(20))
    login: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")
    must_change_password: Mapped[bool] = mapped_column(default=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class AuthSession(Base):
    """Phiên đăng nhập. Chỉ lưu băm của token; csrf_token dùng cho request ghi."""
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class AuditLog(Base):
    """Sổ ghi chỉ thêm: ai làm gì, lúc nào. Không chứa mật khẩu/token."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(60))
    target: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
