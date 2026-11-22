"""Báo cáo doanh thu cho chủ quán và xuất CSV.

Doanh thu = tổng hoá đơn của phiên đã thanh toán (sau voucher, TRƯỚC khi trừ cọc), tính theo ngày chốt phiên
theo giờ của quán. "Tiền thu tại quầy" tách riêng theo hình thức thanh toán (đã trừ cọc). Nhân viên không xem
được báo cáo; họ chỉ có doanh thu hôm nay (venue_api)."""
import csv
import io
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Callable, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.manage_api.auth import Principal, audit
from apps.manage_api.models import BilliardTable, Payment, PlaySession, SessionItem, User

MAX_DAYS = 366
TOP_ITEMS = 10


def csv_safe(value) -> str:
    """Chống chèn công thức khi mở CSV bằng Excel/Sheets: ô bắt đầu bằng = + - @ được thêm dấu nháy."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def build_report_api(get_db: Callable, require_venue_roles: Callable, now_fn: Callable[[], datetime], timezone_name: str) -> APIRouter:
    router = APIRouter(prefix="/api/venues/{venue_id}/reports", tags=["reports"])
    zone = ZoneInfo(timezone_name)
    Db = Annotated[Session, Depends(get_db)]
    OwnerOnly = Annotated[Principal, Depends(require_venue_roles("owner"))]

    def parse_range(date_from: str | None, date_to: str | None) -> tuple[date, date, datetime, datetime]:
        today = now_fn().astimezone(zone).date()
        try:
            end_day = date.fromisoformat(date_to) if date_to else today
            start_day = date.fromisoformat(date_from) if date_from else end_day - timedelta(days=29)
        except ValueError:
            raise HTTPException(400, "Ngày không hợp lệ (định dạng YYYY-MM-DD).")
        if start_day > end_day:
            raise HTTPException(400, "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
        if (end_day - start_day).days + 1 > MAX_DAYS:
            raise HTTPException(400, f"Chỉ xem tối đa {MAX_DAYS} ngày mỗi lần.")
        to_utc = lambda d: datetime(d.year, d.month, d.day, tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
        return start_day, end_day, to_utc(start_day), to_utc(end_day + timedelta(days=1))

    def local(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc).astimezone(zone)

    def bucket(day: date, group: str) -> str:
        if group == "week":
            return (day - timedelta(days=day.weekday())).isoformat()  # thứ Hai đầu tuần
        if group == "month":
            return day.strftime("%Y-%m")
        return day.isoformat()

    def paid_sessions(db: Session, venue_id: int, start: datetime, end: datetime) -> list[PlaySession]:
        return list(db.scalars(select(PlaySession).where(
            PlaySession.venue_id == venue_id, PlaySession.status == "PAID", PlaySession.ended_at >= start, PlaySession.ended_at < end)
            .order_by(PlaySession.ended_at)))

    @router.get("/revenue")
    def revenue(venue_id: int, _: OwnerOnly, db: Db, date_from: str | None = None, date_to: str | None = None,
                group: Literal["day", "week", "month"] = "day"):
        start_day, end_day, start, end = parse_range(date_from, date_to)
        sessions = paid_sessions(db, venue_id, start, end)
        ids = [s.id for s in sessions]
        names = dict(db.execute(select(BilliardTable.id, BilliardTable.name).where(BilliardTable.venue_id == venue_id)).all())

        # chuỗi theo kỳ, điền 0 cho kỳ không có doanh thu
        series: dict[str, dict] = {}
        day = start_day
        while day <= end_day:
            series.setdefault(bucket(day, group), {"key": bucket(day, group), "revenue": 0, "sessions": 0})
            day += timedelta(days=1)
        by_table: dict[int, dict] = {}
        hours = [0] * 24
        for s in sessions:
            row = series[bucket(local(s.ended_at).date(), group)]
            row["revenue"] += s.total_amount or 0
            row["sessions"] += 1
            t = by_table.setdefault(s.table_id, {"table_id": s.table_id, "table_name": names.get(s.table_id), "sessions": 0, "minutes": 0, "revenue": 0})
            t["sessions"] += 1
            t["minutes"] += s.billable_minutes or 0
            t["revenue"] += s.total_amount or 0
            hours[local(s.started_at).hour] += 1

        methods = {"cash": 0, "transfer": 0}
        if ids:
            for method, amount in db.execute(select(Payment.method, Payment.amount).where(Payment.session_id.in_(ids))).all():
                methods[method] += amount
        items: dict[str, dict] = defaultdict(lambda: {"quantity": 0, "amount": 0})
        if ids:
            for name, qty, price in db.execute(select(SessionItem.name_snapshot, SessionItem.quantity, SessionItem.unit_price).where(SessionItem.session_id.in_(ids))).all():
                items[name]["quantity"] += qty
                items[name]["amount"] += qty * price
        top = sorted(({"name": n, **v} for n, v in items.items()), key=lambda r: (-r["amount"], r["name"]))[:TOP_ITEMS]
        return {
            "from": start_day.isoformat(), "to": end_day.isoformat(), "group": group,
            "totals": {"revenue": sum(s.total_amount or 0 for s in sessions), "sessions": len(sessions),
                       "table_amount": sum(s.table_amount or 0 for s in sessions), "items_amount": sum(s.items_amount or 0 for s in sessions),
                       "voucher_discount": sum(s.voucher_discount or 0 for s in sessions), "deposit_applied": sum(s.deposit_applied or 0 for s in sessions),
                       "collected_cash": methods["cash"], "collected_transfer": methods["transfer"]},
            "series": list(series.values()),
            "by_table": sorted(by_table.values(), key=lambda r: -r["revenue"]),
            "top_items": top,
            "sessions_by_start_hour": hours,
        }

    @router.get("/export.csv")
    def export_csv(venue_id: int, principal: OwnerOnly, db: Db, date_from: str | None = None, date_to: str | None = None):
        start_day, end_day, start, end = parse_range(date_from, date_to)
        sessions = paid_sessions(db, venue_id, start, end)
        tables = dict(db.execute(select(BilliardTable.id, BilliardTable.name).where(BilliardTable.venue_id == venue_id)).all())
        payments = {p.session_id: p for p in db.scalars(select(Payment).where(Payment.venue_id == venue_id))}
        users = {u.id: u.display_name for u in db.scalars(select(User).where(User.venue_id == venue_id))}
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["Mã hoá đơn", "Bàn", "Bắt đầu", "Kết thúc", "Số phút", "Tiền giờ", "Dịch vụ", "Voucher", "Tổng hoá đơn", "Đã trừ cọc",
                         "Thu tại quầy", "Hình thức", "Thu ngân", "Khách"])
        for s in sessions:
            pay = payments.get(s.id)
            writer.writerow([csv_safe(s.id[:8].upper()), csv_safe(tables.get(s.table_id)), local(s.started_at).strftime("%Y-%m-%d %H:%M"),
                             local(s.ended_at).strftime("%Y-%m-%d %H:%M"), s.billable_minutes or 0, s.table_amount or 0, s.items_amount or 0,
                             s.voucher_discount or 0, s.total_amount or 0, s.deposit_applied or 0, pay.amount if pay else 0,
                             {"cash": "Tiền mặt", "transfer": "Chuyển khoản"}.get(pay.method, "") if pay else "",
                             csv_safe(users.get(s.closed_by)), csv_safe(users.get(s.customer_id))])
        audit(db, now_fn(), "report_exported", actor=principal.user, venue_id=venue_id,
              detail={"from": start_day.isoformat(), "to": end_day.isoformat(), "rows": len(sessions)})
        db.commit()
        filename = f"hoa-don_{start_day.isoformat()}_{end_day.isoformat()}.csv"
        # BOM để Excel đọc đúng tiếng Việt UTF-8.
        return Response("﻿" + out.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    return router
