from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, text
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


class BilliardTable(Base):
    __tablename__ = "billiard_tables"
    __table_args__ = (
        CheckConstraint("hourly_rate >= 0 AND hourly_rate <= 10000000"),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')"),
        Index("uq_table_name_per_venue", "venue_id", "name", unique=True),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    table_type: Mapped[str] = mapped_column(String(20), default="pool")
    hourly_rate: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime)


class PlaySession(Base):
    """Phiên chơi. Giá chốt (rate_snapshot) lúc mở bàn; tiền do backend tính khi checkout."""
    __tablename__ = "play_sessions"
    __table_args__ = (
        Index("one_active_session_per_table", "table_id", unique=True, sqlite_where=text("status = 'ACTIVE'")),
        CheckConstraint("status IN ('ACTIVE', 'PAID', 'VOID')"),
        CheckConstraint("rate_snapshot >= 0"),
        CheckConstraint("total_amount IS NULL OR total_amount >= 0"),
        Index("ix_sessions_venue_started", "venue_id", "started_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"))
    table_id: Mapped[int] = mapped_column(ForeignKey("billiard_tables.id"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE")
    rate_snapshot: Mapped[int] = mapped_column(Integer)
    total_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    table_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    items_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    billable_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opened_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    booking_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    deposit_applied: Mapped[int | None] = mapped_column(Integer, nullable=True)
    voucher_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    voucher_discount: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Payment(Base):
    """Ghi nhận thanh toán thủ công (tiền mặt/chuyển khoản). Chưa có cổng thanh toán."""
    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("method IN ('cash', 'transfer')"), CheckConstraint("amount >= 0"))
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("play_sessions.id"), unique=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), index=True)
    method: Mapped[str] = mapped_column(String(10))
    amount: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Product(Base):
    """Món/dịch vụ bán thêm trong phiên (nước uống, phấn, đồ ăn...)."""
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price >= 0 AND price <= 10000000"),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')"),
        Index("uq_product_name_per_venue", "venue_id", "name", unique=True),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    price: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime)


class SessionItem(Base):
    """Dòng dịch vụ của một phiên; tên và giá được chốt lúc thêm."""
    __tablename__ = "session_items"
    __table_args__ = (CheckConstraint("quantity >= 1 AND quantity <= 99"), CheckConstraint("unit_price >= 0"))
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("play_sessions.id"), index=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    name_snapshot: Mapped[str] = mapped_column(String(80))
    unit_price: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class VenueBookingSettings(Base):
    """Luật đặt bàn của từng quán (chủ quán chỉnh)."""
    __tablename__ = "venue_booking_settings"
    __table_args__ = (
        CheckConstraint("deposit_amount >= 0 AND deposit_amount <= 1000000"),
        CheckConstraint("hold_minutes >= 5 AND hold_minutes <= 120"),
        CheckConstraint("refund_before_minutes >= 0 AND refund_before_minutes <= 2880"),
        CheckConstraint("noshow_grace_minutes >= 5 AND noshow_grace_minutes <= 240"),
    )
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), primary_key=True)
    deposit_amount: Mapped[int] = mapped_column(Integer, default=50000)
    hold_minutes: Mapped[int] = mapped_column(Integer, default=15)
    refund_before_minutes: Mapped[int] = mapped_column(Integer, default=60)
    noshow_grace_minutes: Mapped[int] = mapped_column(Integer, default=30)


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'CONFIRMED', 'CHECKED_IN', 'CANCELLED', 'EXPIRED', 'NO_SHOW')"),
        CheckConstraint("end_at > start_at"),
        Index("ix_bookings_table_start", "table_id", "start_at"),
        Index("ix_bookings_venue_start", "venue_id", "start_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"))
    table_id: Mapped[int] = mapped_column(ForeignKey("billiard_tables.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(12), default="PENDING")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Deposit(Base):
    """Tiền cọc đặt bàn. Hiện chỉ có nhà cung cấp 'mock' (giả lập, không thu tiền thật)."""
    __tablename__ = "deposits"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'PAID', 'APPLIED', 'REFUNDED', 'FORFEITED', 'CANCELLED')"),
        CheckConstraint("amount > 0 AND applied_amount >= 0 AND refunded_amount >= 0"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), unique=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="PENDING")
    provider: Mapped[str] = mapped_column(String(20))
    provider_ref: Mapped[str] = mapped_column(String(60))
    applied_amount: Mapped[int] = mapped_column(Integer, default=0)
    refunded_amount: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---------------- Gamification ----------------

class VenueNetwork(Base):
    """IP/CIDR công cộng của quán, dùng để xác minh check-in qua wifi quán."""
    __tablename__ = "venue_networks"
    __table_args__ = (Index("uq_network_per_venue", "venue_id", "cidr", unique=True),)
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), index=True)
    cidr: Mapped[str] = mapped_column(String(50))
    label: Mapped[str | None] = mapped_column(String(60), nullable=True)


class GameSettings(Base):
    __tablename__ = "game_settings"
    __table_args__ = (
        CheckConstraint("checkin_mode IN ('off', 'wifi', 'code', 'wifi_or_code', 'wifi_and_code')"),
        CheckConstraint("checkin_points >= 0 AND checkin_points <= 1000"),
        CheckConstraint("min_daily_prizes >= 0 AND min_daily_prizes <= 2"),
        CheckConstraint("max_daily_prizes >= min_daily_prizes AND max_daily_prizes <= 50"),
        CheckConstraint("expected_daily_checkins >= 1 AND expected_daily_checkins <= 1000"),
        CheckConstraint("spin_expiry_days >= 1 AND spin_expiry_days <= 14"),
        CheckConstraint("code_rotation_seconds >= 60 AND code_rotation_seconds <= 3600"),
    )
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), primary_key=True)
    checkin_mode: Mapped[str] = mapped_column(String(16), default="wifi")
    checkin_points: Mapped[int] = mapped_column(Integer, default=10)
    streak_milestones: Mapped[list] = mapped_column(JSON, default=list)
    wheel_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    min_daily_prizes: Mapped[int] = mapped_column(Integer, default=1)
    max_daily_prizes: Mapped[int] = mapped_column(Integer, default=2)
    expected_daily_checkins: Mapped[int] = mapped_column(Integer, default=20)
    spin_expiry_days: Mapped[int] = mapped_column(Integer, default=1)
    code_secret: Mapped[str] = mapped_column(String(64), default="")
    code_rotation_seconds: Mapped[int] = mapped_column(Integer, default=300)


class CustomerGame(Base):
    __tablename__ = "customer_game"
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    points: Mapped[int] = mapped_column(Integer, default=0)
    streak: Mapped[int] = mapped_column(Integer, default=0)
    best_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_checkin_day: Mapped[str | None] = mapped_column(String(10), nullable=True)


class Checkin(Base):
    __tablename__ = "checkins"
    __table_args__ = (Index("uq_checkin_per_day", "venue_id", "customer_id", "day", unique=True),)
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    day: Mapped[str] = mapped_column(String(10))
    method: Mapped[str] = mapped_column(String(20))
    ip: Mapped[str] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class PointLedger(Base):
    """Sổ điểm chỉ thêm. (reason, ref) duy nhất theo khách nên mọi khoản cộng đều idempotent."""
    __tablename__ = "point_ledger"
    __table_args__ = (Index("uq_ledger_ref", "venue_id", "customer_id", "reason", "ref", unique=True),)
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(30))
    ref: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class WheelPrize(Base):
    __tablename__ = "wheel_prizes"
    __table_args__ = (
        CheckConstraint("kind IN ('points', 'discount_vnd', 'free_minutes', 'nothing')"),
        CheckConstraint("weight_bp >= 0 AND weight_bp <= 10000"),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')"),
        CheckConstraint("value >= 0"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(16))
    value: Mapped[int] = mapped_column(Integer, default=0)
    weight_bp: Mapped[int] = mapped_column(Integer)  # 10000 = 100%
    stock_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = không giới hạn
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE")
    position: Mapped[int] = mapped_column(Integer, default=0)
    voucher_valid_days: Mapped[int] = mapped_column(Integer, default=30)


class WheelDailyPlan(Base):
    """Kế hoạch thưởng đảm bảo của một ngày: vị trí các lượt quay được định sẵn là trúng."""
    __tablename__ = "wheel_daily_plan"
    __table_args__ = (Index("uq_plan_day", "venue_id", "day", unique=True),)
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"))
    day: Mapped[str] = mapped_column(String(10))
    expected: Mapped[int] = mapped_column(Integer)
    guaranteed: Mapped[list] = mapped_column(JSON, default=list)
    min_prizes: Mapped[int] = mapped_column(Integer)
    max_prizes: Mapped[int] = mapped_column(Integer)
    spin_count: Mapped[int] = mapped_column(Integer, default=0)
    prizes_given: Mapped[int] = mapped_column(Integer, default=0)
    guaranteed_given: Mapped[int] = mapped_column(Integer, default=0)


class SpinTicket(Base):
    __tablename__ = "spin_tickets"
    __table_args__ = (CheckConstraint("status IN ('UNUSED', 'USED', 'EXPIRED')"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    day: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(8), default="UNUSED")
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    checkin_id: Mapped[int] = mapped_column(ForeignKey("checkins.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class SpinResult(Base):
    """Kết quả quay: lưu bản chụp giải và tỷ lệ tại thời điểm quay."""
    __tablename__ = "spin_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("spin_tickets.id"), unique=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    prize_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prize_name: Mapped[str] = mapped_column(String(80))
    prize_kind: Mapped[str] = mapped_column(String(16))
    prize_value: Mapped[int] = mapped_column(Integer)
    odds_bp: Mapped[int] = mapped_column(Integer)
    spin_index: Mapped[int] = mapped_column(Integer)
    forced: Mapped[bool] = mapped_column(Boolean, default=False)
    day: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Voucher(Base):
    __tablename__ = "vouchers"
    __table_args__ = (
        CheckConstraint("kind IN ('discount_vnd', 'free_minutes')"),
        CheckConstraint("status IN ('UNUSED', 'USED', 'EXPIRED')"),
        CheckConstraint("value > 0"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    code: Mapped[str] = mapped_column(String(12), unique=True)
    kind: Mapped[str] = mapped_column(String(16))
    value: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(8), default="UNUSED")
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    source_result_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
