"""Đặt bàn kèm cọc (giả lập) cho khách, và quản lý đặt bàn tại quầy.

Quy tắc:
- Đặt bàn cần cọc (nếu quán đặt > 0): PENDING giữ chỗ `hold_minutes`; trả cọc (giả lập) -> CONFIRMED; quá hạn -> EXPIRED.
- Huỷ trước giờ hẹn >= `refund_before_minutes`: hoàn cọc; muộn hơn: mất cọc. Quầy huỷ thì luôn hoàn.
- Không đến sau `noshow_grace_minutes`: quầy đánh dấu NO_SHOW, mất cọc.
- Nhận bàn (check-in) mở phiên gắn với đặt bàn; khi tính tiền, cọc được trừ vào hoá đơn, phần thừa hoàn lại.
Mọi thời gian do backend quyết định; client chỉ gửi giờ muốn đặt (UTC)."""
from datetime import datetime, timedelta, timezone
from typing import Annotated, Callable, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.manage_api.auth import Principal, audit, utc_naive
from apps.manage_api.models import BilliardTable, Booking, Deposit, PlaySession, User, Venue, VenueBookingSettings
from apps.manage_api.payments import PaymentProvider

DURATIONS = (30, 60, 90, 120, 180, 240)
MAX_DAYS_AHEAD = 14
MAX_OPEN_BOOKINGS = 3
EARLY_CHECKIN_MINUTES = 30
BLOCKING = ("PENDING", "CONFIRMED", "CHECKED_IN")


class SettingsBody(BaseModel):
    deposit_amount: int = Field(ge=0, le=1_000_000)
    hold_minutes: int = Field(ge=5, le=120)
    refund_before_minutes: int = Field(ge=0, le=2880)
    noshow_grace_minutes: int = Field(ge=5, le=240)


class BookingCreate(BaseModel):
    table_id: int
    start_at: datetime
    duration_minutes: int


def iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def build_booking_api(get_db: Callable, require_venue_roles: Callable, now_fn: Callable[[], datetime],
                      timezone_name: str, provider: PaymentProvider) -> tuple[APIRouter, APIRouter]:
    router = APIRouter(prefix="/api/venues/{venue_id}", tags=["booking"])
    public = APIRouter(prefix="/api/public", tags=["public"])
    zone = ZoneInfo(timezone_name)
    Db = Annotated[Session, Depends(get_db)]
    Customer = Annotated[Principal, Depends(require_venue_roles("customer"))]
    Operator = Annotated[Principal, Depends(require_venue_roles("owner", "staff"))]
    OwnerOnly = Annotated[Principal, Depends(require_venue_roles("owner"))]
    Anyone = Annotated[Principal, Depends(require_venue_roles("owner", "staff", "customer"))]

    # ---------------- helpers ----------------
    def settings_for(db: Session, venue_id: int) -> VenueBookingSettings:
        row = db.get(VenueBookingSettings, venue_id)
        if row is None:
            row = VenueBookingSettings(venue_id=venue_id, deposit_amount=50000, hold_minutes=15,
                                       refund_before_minutes=60, noshow_grace_minutes=30)
            db.add(row)
            db.flush()
        return row

    def settings_view(row: VenueBookingSettings) -> dict:
        return {"deposit_amount": row.deposit_amount, "hold_minutes": row.hold_minutes,
                "refund_before_minutes": row.refund_before_minutes, "noshow_grace_minutes": row.noshow_grace_minutes}

    def expire_stale(db: Session, venue_id: int, now: datetime) -> None:
        stale = db.scalars(select(Booking).where(Booking.venue_id == venue_id, Booking.status == "PENDING",
                                                 Booking.expires_at <= utc_naive(now))).all()
        for booking in stale:
            booking.status = "EXPIRED"
            deposit = db.scalar(select(Deposit).where(Deposit.booking_id == booking.id))
            if deposit and deposit.status == "PENDING":
                deposit.status, deposit.settled_at = "CANCELLED", utc_naive(now)
        if stale:
            db.commit()

    def booking_or_404(db: Session, venue_id: int, booking_id: str, customer_id: int | None = None) -> Booking:
        booking = db.get(Booking, booking_id)
        if booking is None or booking.venue_id != venue_id or (customer_id is not None and booking.customer_id != customer_id):
            raise HTTPException(404, "Không tìm thấy lịch đặt.")
        return booking

    def deposit_view(d: Deposit | None) -> dict | None:
        if d is None:
            return None
        return {"amount": d.amount, "status": d.status, "provider": d.provider, "is_mock": d.provider == "mock",
                "applied_amount": d.applied_amount, "refunded_amount": d.refunded_amount}

    def booking_view(db: Session, b: Booking, with_customer: bool = False) -> dict:
        table = db.get(BilliardTable, b.table_id)
        view = {"id": b.id, "table_id": b.table_id, "table_name": table.name if table else None, "status": b.status,
                "start_at": iso(b.start_at), "end_at": iso(b.end_at), "expires_at": iso(b.expires_at),
                "session_id": b.session_id, "created_at": iso(b.created_at),
                "deposit": deposit_view(db.scalar(select(Deposit).where(Deposit.booking_id == b.id)))}
        if with_customer:
            customer = db.get(User, b.customer_id)
            view["customer"] = {"id": customer.id, "name": customer.display_name, "phone": customer.login}
        return view

    def lock_table(db: Session, table_id: int) -> None:
        """Chiếm khoá ghi (UPDATE rỗng) để hai lượt đặt cùng bàn không kiểm tra trùng giờ song song."""
        db.execute(update(BilliardTable).where(BilliardTable.id == table_id).values(id=table_id))

    def overlapping(db: Session, table_id: int, start: datetime, end: datetime, now: datetime, exclude: str | None = None) -> bool:
        query = select(func.count()).select_from(Booking).where(
            Booking.table_id == table_id, Booking.start_at < end, Booking.end_at > start,
            Booking.status.in_(BLOCKING), (Booking.status != "PENDING") | (Booking.expires_at > utc_naive(now)))
        if exclude:
            query = query.where(Booking.id != exclude)
        return bool(db.scalar(query))

    def refund_deposit(db: Session, booking: Booking, now: datetime, forfeit: bool) -> None:
        deposit = db.scalar(select(Deposit).where(Deposit.booking_id == booking.id))
        if deposit is None:
            return
        if deposit.status == "PAID":
            if forfeit:
                deposit.status = "FORFEITED"
            else:
                provider.refund(deposit.provider_ref, deposit.amount)
                deposit.status, deposit.refunded_amount = "REFUNDED", deposit.amount
            deposit.settled_at = utc_naive(now)
        elif deposit.status == "PENDING":
            deposit.status, deposit.settled_at = "CANCELLED", utc_naive(now)

    # ---------------- công khai ----------------
    @public.get("/venues/{slug}")
    def public_venue(slug: str, db: Db):
        venue = db.scalar(select(Venue).where(Venue.slug == slug.strip().lower()))
        if venue is None or venue.status != "ACTIVE":
            raise HTTPException(404, "Không tìm thấy quán.")
        return {"name": venue.name, "slug": venue.slug}

    # ---------------- cài đặt đặt bàn ----------------
    @router.get("/booking-settings")
    def get_settings(venue_id: int, _: Anyone, db: Db):
        row = settings_for(db, venue_id)
        db.commit()
        return {**settings_view(row), "payment_is_mock": not provider.is_real}

    @router.put("/booking-settings")
    def put_settings(venue_id: int, body: SettingsBody, principal: OwnerOnly, db: Db):
        row = settings_for(db, venue_id)
        before = settings_view(row)
        for key, value in body.model_dump().items():
            setattr(row, key, value)
        audit(db, now_fn(), "booking_settings_changed", actor=principal.user, venue_id=venue_id, detail={"from": before, "to": body.model_dump()})
        db.commit()
        return {**settings_view(row), "payment_is_mock": not provider.is_real}

    # ---------------- khách: lịch trống ----------------
    @router.get("/availability")
    def availability(venue_id: int, _: Customer, db: Db, date: str):
        try:
            day = datetime.fromisoformat(date).replace(tzinfo=zone)
        except ValueError:
            raise HTTPException(400, "Ngày không hợp lệ (định dạng YYYY-MM-DD).")
        now = now_fn()
        expire_stale(db, venue_id, now)
        start = day.astimezone(timezone.utc).replace(tzinfo=None)
        end = (day + timedelta(days=1)).astimezone(timezone.utc).replace(tzinfo=None)
        tables = db.scalars(select(BilliardTable).where(BilliardTable.venue_id == venue_id, BilliardTable.status == "ACTIVE").order_by(BilliardTable.id)).all()
        busy_now = set(db.scalars(select(PlaySession.table_id).where(PlaySession.venue_id == venue_id, PlaySession.status == "ACTIVE")))
        rows = db.scalars(select(Booking).where(
            Booking.venue_id == venue_id, Booking.start_at < end, Booking.end_at > start, Booking.status.in_(BLOCKING),
            (Booking.status != "PENDING") | (Booking.expires_at > utc_naive(now)))).all()
        settings = settings_for(db, venue_id)
        db.commit()
        return {
            "server_time": iso(utc_naive(now)), "settings": {**settings_view(settings), "payment_is_mock": not provider.is_real},
            "durations": list(DURATIONS),
            "tables": [{"id": t.id, "name": t.name, "table_type": t.table_type, "hourly_rate": t.hourly_rate, "playing_now": t.id in busy_now,
                        # Chỉ trả khoảng bận, không lộ ai đặt.
                        "busy": [{"start_at": iso(b.start_at), "end_at": iso(b.end_at)} for b in rows if b.table_id == t.id]} for t in tables],
        }

    # ---------------- khách: đặt bàn ----------------
    @router.post("/my/bookings", status_code=201)
    def create_booking(venue_id: int, body: BookingCreate, principal: Customer, db: Db):
        now = now_fn()
        expire_stale(db, venue_id, now)
        table = db.get(BilliardTable, body.table_id)
        if table is None or table.venue_id != venue_id or table.status != "ACTIVE":
            raise HTTPException(404, "Không tìm thấy bàn.")
        if body.duration_minutes not in DURATIONS:
            raise HTTPException(400, f"Thời lượng hợp lệ: {', '.join(map(str, DURATIONS))} phút.")
        if body.start_at.tzinfo is None:
            raise HTTPException(400, "Giờ đặt cần kèm múi giờ (UTC).")
        start = utc_naive(body.start_at)
        naive_now = utc_naive(now)
        if start < naive_now - timedelta(minutes=1):
            raise HTTPException(400, "Không đặt được giờ đã qua.")
        if start > naive_now + timedelta(days=MAX_DAYS_AHEAD):
            raise HTTPException(400, f"Chỉ đặt trước tối đa {MAX_DAYS_AHEAD} ngày.")
        end = start + timedelta(minutes=body.duration_minutes)
        lock_table(db, table.id)
        open_count = db.scalar(select(func.count()).select_from(Booking).where(
            Booking.customer_id == principal.user.id, Booking.status.in_(BLOCKING), Booking.end_at > naive_now,
            (Booking.status != "PENDING") | (Booking.expires_at > naive_now)))
        if open_count >= MAX_OPEN_BOOKINGS:
            db.rollback()
            raise HTTPException(409, f"Bạn đang có {MAX_OPEN_BOOKINGS} lịch đặt chưa diễn ra. Hãy huỷ hoặc dùng bớt trước khi đặt thêm.")
        if overlapping(db, table.id, start, end, now):
            db.rollback()
            raise HTTPException(409, "Bàn đã có người đặt trong khung giờ này. Hãy chọn giờ hoặc bàn khác.")
        settings = settings_for(db, venue_id)
        booking = Booking(id=str(uuid4()), venue_id=venue_id, table_id=table.id, customer_id=principal.user.id, start_at=start, end_at=end,
                          created_at=naive_now, status="CONFIRMED" if settings.deposit_amount == 0 else "PENDING",
                          expires_at=None if settings.deposit_amount == 0 else naive_now + timedelta(minutes=settings.hold_minutes))
        db.add(booking)
        db.flush()
        if settings.deposit_amount > 0:
            charge = provider.create_charge(settings.deposit_amount, booking.id)
            db.add(Deposit(booking_id=booking.id, venue_id=venue_id, amount=settings.deposit_amount, status="PENDING",
                           provider=charge.provider, provider_ref=charge.ref, created_at=naive_now))
        audit(db, now, "booking_created", actor=principal.user, venue_id=venue_id, target=table.name,
              detail={"booking_id": booking.id, "start": iso(start), "minutes": body.duration_minutes, "deposit": settings.deposit_amount})
        db.commit()
        return booking_view(db, booking)

    @router.get("/my/bookings")
    def my_bookings(venue_id: int, principal: Customer, db: Db):
        expire_stale(db, venue_id, now_fn())
        rows = db.scalars(select(Booking).where(Booking.venue_id == venue_id, Booking.customer_id == principal.user.id)
                          .order_by(Booking.start_at.desc()).limit(50)).all()
        return [booking_view(db, b) for b in rows]

    @router.post("/my/bookings/{booking_id}/deposit/mock-pay")
    def mock_pay(venue_id: int, booking_id: str, principal: Customer, db: Db):
        """GIẢ LẬP việc khách trả cọc. Không thu tiền thật. Bị chặn nếu nhà cung cấp thanh toán là thật."""
        if provider.is_real:
            raise HTTPException(404, "Không có chức năng này.")
        now = now_fn()
        expire_stale(db, venue_id, now)
        booking = booking_or_404(db, venue_id, booking_id, principal.user.id)
        deposit = db.scalar(select(Deposit).where(Deposit.booking_id == booking.id))
        if booking.status == "EXPIRED":
            raise HTTPException(409, "Lịch giữ chỗ đã hết hạn. Hãy đặt lại.")
        if booking.status != "PENDING" or deposit is None or deposit.status != "PENDING":
            raise HTTPException(409, "Lịch đặt này không cần trả cọc.")
        charge = provider.confirm(deposit.provider_ref)
        if charge.status == "PAID":
            deposit.status, deposit.paid_at = "PAID", utc_naive(now)
            booking.status, booking.expires_at = "CONFIRMED", None
            audit(db, now, "deposit_paid_mock", actor=principal.user, venue_id=venue_id, detail={"booking_id": booking.id, "amount": deposit.amount})
            db.commit()
        return booking_view(db, booking)

    @router.post("/my/bookings/{booking_id}/cancel")
    def cancel_my_booking(venue_id: int, booking_id: str, principal: Customer, db: Db):
        now = now_fn()
        expire_stale(db, venue_id, now)
        booking = booking_or_404(db, venue_id, booking_id, principal.user.id)
        if booking.status not in ("PENDING", "CONFIRMED"):
            raise HTTPException(409, "Lịch đặt này không huỷ được.")
        if utc_naive(now) >= booking.start_at:
            raise HTTPException(409, "Đã quá giờ hẹn, hãy liên hệ quầy.")
        settings = settings_for(db, venue_id)
        refundable = utc_naive(now) <= booking.start_at - timedelta(minutes=settings.refund_before_minutes)
        refund_deposit(db, booking, now, forfeit=not refundable)
        booking.status, booking.cancelled_at = "CANCELLED", utc_naive(now)
        audit(db, now, "booking_cancelled", actor=principal.user, venue_id=venue_id, detail={"booking_id": booking.id, "refunded": refundable})
        db.commit()
        return booking_view(db, booking)

    @router.get("/my/sessions")
    def my_sessions(venue_id: int, principal: Customer, db: Db, limit: int = 25, offset: int = 0):
        query = select(PlaySession).where(PlaySession.venue_id == venue_id, PlaySession.customer_id == principal.user.id, PlaySession.status == "PAID")
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.order_by(PlaySession.started_at.desc()).limit(max(1, min(limit, 100))).offset(max(0, offset))).all()
        names = dict(db.execute(select(BilliardTable.id, BilliardTable.name).where(BilliardTable.venue_id == venue_id)).all())
        return {"total": total, "items": [{
            "id": s.id, "table_name": names.get(s.table_id), "started_at": iso(s.started_at), "ended_at": iso(s.ended_at),
            "billable_minutes": s.billable_minutes, "total": s.total_amount, "deposit_applied": s.deposit_applied or 0} for s in rows]}

    # ---------------- quầy: quản lý đặt bàn ----------------
    @router.get("/bookings")
    def list_bookings(venue_id: int, _: Operator, db: Db, scope: Literal["upcoming", "all"] = "upcoming", limit: int = 100):
        now = now_fn()
        expire_stale(db, venue_id, now)
        query = select(Booking).where(Booking.venue_id == venue_id)
        if scope == "upcoming":
            query = query.where(Booking.status.in_(("PENDING", "CONFIRMED", "CHECKED_IN")), Booking.end_at > utc_naive(now) - timedelta(hours=3))
        rows = db.scalars(query.order_by(Booking.start_at.asc() if scope == "upcoming" else Booking.start_at.desc()).limit(max(1, min(limit, 200)))).all()
        return [booking_view(db, b, with_customer=True) for b in rows]

    @router.post("/bookings/{booking_id}/check-in")
    def check_in(venue_id: int, booking_id: str, principal: Operator, db: Db):
        now = now_fn()
        expire_stale(db, venue_id, now)
        booking = booking_or_404(db, venue_id, booking_id)
        naive_now = utc_naive(now)
        if booking.status != "CONFIRMED":
            raise HTTPException(409, "Chỉ nhận bàn cho lịch đã xác nhận cọc.")
        if naive_now < booking.start_at - timedelta(minutes=EARLY_CHECKIN_MINUTES):
            raise HTTPException(409, f"Chỉ nhận bàn sớm nhất {EARLY_CHECKIN_MINUTES} phút trước giờ hẹn.")
        if naive_now > booking.end_at:
            raise HTTPException(409, "Lịch đặt đã qua giờ.")
        table = db.get(BilliardTable, booking.table_id)
        if table.status != "ACTIVE":
            raise HTTPException(409, "Bàn đang ngừng sử dụng.")
        session = PlaySession(id=str(uuid4()), venue_id=venue_id, table_id=table.id, customer_id=booking.customer_id, started_at=naive_now,
                              status="ACTIVE", rate_snapshot=table.hourly_rate, opened_by=principal.user.id, booking_id=booking.id)
        db.add(session)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Bàn đang có phiên chơi. Hãy tính tiền bàn đó trước.")
        booking.status, booking.session_id = "CHECKED_IN", session.id
        audit(db, now, "booking_checked_in", actor=principal.user, venue_id=venue_id, target=table.name, detail={"booking_id": booking.id, "session_id": session.id})
        db.commit()
        return {"booking": booking_view(db, booking, with_customer=True), "session_id": session.id}

    @router.post("/bookings/{booking_id}/no-show")
    def no_show(venue_id: int, booking_id: str, principal: Operator, db: Db):
        now = now_fn()
        booking = booking_or_404(db, venue_id, booking_id)
        settings = settings_for(db, venue_id)
        if booking.status != "CONFIRMED":
            raise HTTPException(409, "Chỉ đánh dấu không đến cho lịch đã xác nhận.")
        if utc_naive(now) < booking.start_at + timedelta(minutes=settings.noshow_grace_minutes):
            raise HTTPException(409, f"Chỉ đánh dấu không đến sau giờ hẹn {settings.noshow_grace_minutes} phút.")
        refund_deposit(db, booking, now, forfeit=True)
        booking.status = "NO_SHOW"
        audit(db, now, "booking_no_show", actor=principal.user, venue_id=venue_id, detail={"booking_id": booking.id})
        db.commit()
        return booking_view(db, booking, with_customer=True)

    @router.post("/bookings/{booking_id}/cancel")
    def cancel_booking(venue_id: int, booking_id: str, principal: Operator, db: Db):
        now = now_fn()
        expire_stale(db, venue_id, now)
        booking = booking_or_404(db, venue_id, booking_id)
        if booking.status not in ("PENDING", "CONFIRMED"):
            raise HTTPException(409, "Lịch đặt này không huỷ được.")
        refund_deposit(db, booking, now, forfeit=False)  # quầy huỷ: luôn hoàn cọc
        booking.status, booking.cancelled_at = "CANCELLED", utc_naive(now)
        audit(db, now, "booking_cancelled_by_staff", actor=principal.user, venue_id=venue_id, detail={"booking_id": booking.id})
        db.commit()
        return booking_view(db, booking, with_customer=True)

    return router, public
