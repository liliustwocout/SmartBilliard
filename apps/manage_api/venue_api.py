"""API vận hành của một quán: bàn, phiên chơi, thanh toán thủ công, lịch sử, doanh thu hôm nay.

Mọi truy vấn lọc theo venue_id của URL; người dùng chỉ vào được quán của mình (xem require_venue_roles).
Backend là nguồn thời gian, giá và tiền chính thức; client không gửi giờ hay số tiền."""
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
from apps.manage_api.billing import quote
from apps.manage_api.models import BilliardTable, Payment, PlaySession, SessionItem, User

TableType = Literal["pool", "carom", "snooker", "other"]
MAX_RATE = 10_000_000


class TableCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    table_type: TableType = "pool"
    hourly_rate: int = Field(ge=0, le=MAX_RATE)


class TableUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    table_type: TableType | None = None
    hourly_rate: int | None = Field(default=None, ge=0, le=MAX_RATE)
    status: Literal["ACTIVE", "INACTIVE"] | None = None


class OpenBody(BaseModel):
    customer_id: int | None = None


class CheckoutBody(BaseModel):
    payment_method: Literal["cash", "transfer"]


class VoidBody(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


def iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def build_venue_api(get_db: Callable, require_venue_roles: Callable, now_fn: Callable[[], datetime], timezone_name: str) -> APIRouter:
    router = APIRouter(prefix="/api/venues/{venue_id}", tags=["venue"])
    zone = ZoneInfo(timezone_name)
    Db = Annotated[Session, Depends(get_db)]
    Operator = Annotated[Principal, Depends(require_venue_roles("owner", "staff"))]
    OwnerOnly = Annotated[Principal, Depends(require_venue_roles("owner"))]

    def today_range() -> tuple[datetime, datetime]:
        """Khoảng [00:00, 24:00) hôm nay theo giờ của quán, quy về UTC không múi giờ."""
        local = now_fn().astimezone(zone)
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        to_utc = lambda value: value.astimezone(timezone.utc).replace(tzinfo=None)
        return to_utc(start), to_utc(start + timedelta(days=1))

    def table_or_404(db: Session, venue_id: int, table_id: int) -> BilliardTable:
        table = db.get(BilliardTable, table_id)
        if table is None or table.venue_id != venue_id:
            raise HTTPException(404, "Không tìm thấy bàn.")
        return table

    def session_or_404(db: Session, venue_id: int, session_id: str) -> PlaySession:
        session = db.get(PlaySession, session_id)
        if session is None or session.venue_id != venue_id:
            raise HTTPException(404, "Không tìm thấy phiên.")
        return session

    def items_sum(db: Session, session_ids: list[str]) -> dict[str, int]:
        if not session_ids:
            return {}
        rows = db.execute(select(SessionItem.session_id, func.sum(SessionItem.unit_price * SessionItem.quantity))
                          .where(SessionItem.session_id.in_(session_ids)).group_by(SessionItem.session_id)).all()
        return {sid: int(total) for sid, total in rows}

    def item_lines(db: Session, session_id: str) -> list[dict]:
        rows = db.scalars(select(SessionItem).where(SessionItem.session_id == session_id).order_by(SessionItem.id)).all()
        return [{"id": i.id, "product_id": i.product_id, "name": i.name_snapshot, "unit_price": i.unit_price,
                 "quantity": i.quantity, "amount": i.unit_price * i.quantity} for i in rows]

    def session_view(session: PlaySession, table_name: str | None, now: datetime, items_amount: int = 0,
                     items: list[dict] | None = None) -> dict:
        end = session.ended_at or utc_naive(now)
        live = quote(session.started_at, end, session.rate_snapshot)
        table_amount = session.table_amount if session.table_amount is not None else live["amount_vnd"]
        items_total = session.items_amount if session.items_amount is not None else items_amount
        view = {
            "id": session.id, "table_id": session.table_id, "table_name": table_name, "status": session.status,
            "started_at": iso(session.started_at), "ended_at": iso(session.ended_at), "rate_snapshot": session.rate_snapshot,
            "customer_id": session.customer_id, "void_reason": session.void_reason,
            "elapsed_seconds": live["elapsed_seconds"],
            "billable_minutes": session.billable_minutes if session.billable_minutes is not None else live["billable_minutes"],
            "table_amount": table_amount, "items_amount": items_total,
            "amount_vnd": session.total_amount if session.total_amount is not None else table_amount + items_total,
        }
        if items is not None:
            view["items"] = items
        return view

    def table_view(table: BilliardTable, session: PlaySession | None, now: datetime, items_amount: int = 0) -> dict:
        return {"id": table.id, "name": table.name, "table_type": table.table_type, "hourly_rate": table.hourly_rate,
                "status": table.status, "session": session_view(session, table.name, now, items_amount) if session else None}

    @router.get("/tables")
    def list_tables(venue_id: int, _: Operator, db: Db):
        now = now_fn()
        tables = db.scalars(select(BilliardTable).where(BilliardTable.venue_id == venue_id).order_by(BilliardTable.id)).all()
        active = {s.table_id: s for s in db.scalars(select(PlaySession).where(PlaySession.venue_id == venue_id, PlaySession.status == "ACTIVE"))}
        sums = items_sum(db, [s.id for s in active.values()])
        return {"server_time": iso(utc_naive(now)),
                "tables": [table_view(t, active.get(t.id), now, sums.get(active[t.id].id, 0) if t.id in active else 0) for t in tables]}

    @router.post("/tables", status_code=201)
    def create_table(venue_id: int, body: TableCreate, principal: OwnerOnly, db: Db):
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "Tên bàn không được để trống.")
        now = now_fn()
        table = BilliardTable(venue_id=venue_id, name=name, table_type=body.table_type, hourly_rate=body.hourly_rate,
                              created_at=utc_naive(now))
        db.add(table)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Quán đã có bàn trùng tên.")
        audit(db, now, "table_created", actor=principal.user, venue_id=venue_id, target=name, detail={"hourly_rate": body.hourly_rate})
        db.commit()
        return table_view(table, None, now)

    @router.patch("/tables/{table_id}")
    def update_table(venue_id: int, table_id: int, body: TableUpdate, principal: OwnerOnly, db: Db):
        table = table_or_404(db, venue_id, table_id)
        active = db.scalar(select(PlaySession).where(PlaySession.table_id == table.id, PlaySession.status == "ACTIVE"))
        changes: dict = {}
        if body.status == "INACTIVE" and active:
            raise HTTPException(409, "Bàn đang có phiên chơi. Hãy tính tiền hoặc huỷ phiên trước khi ngừng dùng bàn.")
        for field in ("name", "table_type", "hourly_rate", "status"):
            value = getattr(body, field)
            if value is None:
                continue
            value = value.strip() if isinstance(value, str) else value
            if value != getattr(table, field):
                changes[field] = [getattr(table, field), value]
                setattr(table, field, value)
        if changes:
            if "name" in changes and not table.name:
                raise HTTPException(400, "Tên bàn không được để trống.")
            audit(db, now_fn(), "table_updated", actor=principal.user, venue_id=venue_id, target=table.name, detail=changes)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                raise HTTPException(409, "Quán đã có bàn trùng tên.")
        return table_view(table, active, now_fn())

    @router.post("/tables/{table_id}/open", status_code=201)
    def open_table(venue_id: int, table_id: int, principal: Operator, db: Db, body: OpenBody | None = None):
        table = table_or_404(db, venue_id, table_id)
        if table.status != "ACTIVE":
            raise HTTPException(409, "Bàn đang ngừng sử dụng.")
        customer_id = body.customer_id if body else None
        if customer_id is not None:
            customer = db.get(User, customer_id)
            if customer is None or customer.role != "customer" or customer.venue_id != venue_id:
                raise HTTPException(400, "Khách không thuộc quán này.")
        now = now_fn()
        session = PlaySession(id=str(uuid4()), venue_id=venue_id, table_id=table.id, customer_id=customer_id,
                              started_at=utc_naive(now), status="ACTIVE", rate_snapshot=table.hourly_rate,
                              opened_by=principal.user.id)
        db.add(session)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Bàn đang có phiên chơi.")
        audit(db, now, "session_opened", actor=principal.user, venue_id=venue_id, target=table.name,
              detail={"session_id": session.id, "rate": table.hourly_rate})
        db.commit()
        return session_view(session, table.name, now)

    @router.get("/sessions/{session_id}/quote")
    def session_quote(venue_id: int, session_id: str, _: Operator, db: Db):
        session = session_or_404(db, venue_id, session_id)
        return session_view(session, db.get(BilliardTable, session.table_id).name, now_fn(),
                            items_sum(db, [session.id]).get(session.id, 0), item_lines(db, session.id))

    @router.post("/sessions/{session_id}/checkout")
    def checkout(venue_id: int, session_id: str, body: CheckoutBody, principal: Operator, db: Db):
        session = session_or_404(db, venue_id, session_id)
        table_name = db.get(BilliardTable, session.table_id).name
        now = now_fn()
        if session.status == "VOID":
            raise HTTPException(409, "Phiên đã bị huỷ.")
        if session.status == "PAID":  # bấm lặp / thử lại: trả đúng kết quả đã chốt, không tính tiền lần hai
            return {**session_view(session, table_name, now, items=item_lines(db, session.id)), "duplicate": True}
        end = utc_naive(now)
        result = quote(session.started_at, end, session.rate_snapshot)
        # Bước 1: chiếm quyền chốt phiên. Giao dịch giữ khoá ghi của SQLite tới khi commit nên không ai chen món vào được.
        claimed = db.execute(update(PlaySession).where(PlaySession.id == session.id, PlaySession.status == "ACTIVE").values(
            status="PAID", ended_at=end, closed_by=principal.user.id))
        if claimed.rowcount != 1:  # request khác vừa chốt phiên này
            db.rollback()
            db.refresh(session)
            return {**session_view(session, table_name, now, items=item_lines(db, session.id)), "duplicate": True}
        # Bước 2: tính tiền món trong cùng giao dịch rồi chốt các con số.
        items_total = items_sum(db, [session.id]).get(session.id, 0)
        total = result["amount_vnd"] + items_total
        db.execute(update(PlaySession).where(PlaySession.id == session.id).values(
            total_amount=total, table_amount=result["amount_vnd"], items_amount=items_total,
            billable_minutes=result["billable_minutes"]))
        db.add(Payment(session_id=session.id, venue_id=venue_id, method=body.payment_method, amount=total,
                       created_by=principal.user.id, created_at=end))
        audit(db, now, "session_paid", actor=principal.user, venue_id=venue_id, target=table_name,
              detail={"session_id": session.id, "amount": total, "table_amount": result["amount_vnd"],
                      "items_amount": items_total, "method": body.payment_method})
        db.commit()
        db.refresh(session)
        return {**session_view(session, table_name, now, items=item_lines(db, session.id)), "duplicate": False}

    @router.post("/sessions/{session_id}/void")
    def void_session(venue_id: int, session_id: str, body: VoidBody, principal: OwnerOnly, db: Db):
        session = session_or_404(db, venue_id, session_id)
        if session.status != "ACTIVE":
            raise HTTPException(409, "Chỉ huỷ được phiên đang chơi. Phiên đã thanh toán không huỷ được.")
        now = now_fn()
        session.status, session.ended_at, session.total_amount, session.billable_minutes = "VOID", utc_naive(now), 0, 0
        session.table_amount, session.items_amount = 0, 0
        session.closed_by, session.void_reason = principal.user.id, body.reason.strip()
        table_name = db.get(BilliardTable, session.table_id).name
        audit(db, now, "session_voided", actor=principal.user, venue_id=venue_id, target=table_name,
              detail={"session_id": session.id, "reason": session.void_reason})
        db.commit()
        return session_view(session, table_name, now)

    @router.get("/sessions")
    def list_sessions(venue_id: int, principal: Operator, db: Db, status: Literal["ACTIVE", "PAID", "VOID"] | None = None,
                      table_id: int | None = None, date_from: str | None = None, date_to: str | None = None,
                      limit: int = 25, offset: int = 0):
        """Lịch sử phiên. Nhân viên chỉ thấy hôm nay (bỏ qua tham số ngày); chủ quán lọc được theo khoảng ngày."""
        query = select(PlaySession).where(PlaySession.venue_id == venue_id)
        if principal.user.role == "staff":
            start, end = today_range()
            query = query.where(PlaySession.started_at >= start, PlaySession.started_at < end)
        else:
            def parse_day(value: str | None, plus: int = 0):
                if not value:
                    return None
                try:
                    local = datetime.fromisoformat(value).replace(tzinfo=zone) + timedelta(days=plus)
                except ValueError:
                    raise HTTPException(400, "Ngày không hợp lệ (định dạng YYYY-MM-DD).")
                return local.astimezone(timezone.utc).replace(tzinfo=None)
            lower, upper = parse_day(date_from), parse_day(date_to, 1)
            if lower:
                query = query.where(PlaySession.started_at >= lower)
            if upper:
                query = query.where(PlaySession.started_at < upper)
        if status:
            query = query.where(PlaySession.status == status)
        if table_id is not None:
            query = query.where(PlaySession.table_id == table_id)
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.order_by(PlaySession.started_at.desc()).limit(max(1, min(limit, 100))).offset(max(0, offset))).all()
        names = dict(db.execute(select(BilliardTable.id, BilliardTable.name).where(BilliardTable.venue_id == venue_id)).all())
        now = now_fn()
        return {"total": total, "items": [session_view(s, names.get(s.table_id), now) for s in rows]}

    @router.get("/revenue/today")
    def revenue_today(venue_id: int, _: Operator, db: Db):
        """Doanh thu hôm nay (phiên đã thanh toán, tính theo giờ chốt). Chủ quán và nhân viên đều xem được."""
        start, end = today_range()
        paid = db.execute(
            select(PlaySession.table_id, func.count(), func.coalesce(func.sum(PlaySession.total_amount), 0))
            .where(PlaySession.venue_id == venue_id, PlaySession.status == "PAID", PlaySession.ended_at >= start, PlaySession.ended_at < end)
            .group_by(PlaySession.table_id)).all()
        names = dict(db.execute(select(BilliardTable.id, BilliardTable.name).where(BilliardTable.venue_id == venue_id)).all())
        return {"date": now_fn().astimezone(zone).date().isoformat(), "total_vnd": sum(r[2] for r in paid),
                "session_count": sum(r[1] for r in paid),
                "by_table": [{"table_id": r[0], "table_name": names.get(r[0]), "sessions": r[1], "amount_vnd": r[2]} for r in paid]}

    return router
