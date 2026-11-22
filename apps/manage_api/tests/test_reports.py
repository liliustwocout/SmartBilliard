import csv
import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.manage_api.config import ManageSettings
from apps.manage_api.main import create_app
from apps.manage_api.models import AuditLog, User, Venue
from apps.manage_api.report_api import csv_safe
from apps.manage_api.security import hash_password

PASSWORD = "Billiard-2026!"
START = datetime(2026, 11, 22, 3, 0, tzinfo=timezone.utc)  # 10:00 giờ VN, chủ nhật


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


def sign_in(app, login):
    c = TestClient(app, base_url="http://127.0.0.1")
    r = c.post("/api/auth/login", json={"login": login, "password": PASSWORD})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return c


@pytest.fixture
def p(tmp_path):
    clock = Clock()
    app = create_app(ManageSettings(database_url=f"sqlite:///{tmp_path / 'm.db'}"), clock)
    with TestClient(app, base_url="http://127.0.0.1"):
        naive = START.replace(tzinfo=None)
        with Session(app.state.engine) as db:
            a, b = Venue(name="Quán A", slug="quan-a", created_at=naive), Venue(name="Quán B", slug="quan-b", created_at=naive)
            db.add_all([a, b])
            db.flush()
            for role, name, venue in [("owner", "owner-a", a), ("staff", "staff-a", a), ("owner", "owner-b", b)]:
                db.add(User(role=role, login=name, display_name=name, password_hash=hash_password(PASSWORD), venue_id=venue.id, created_at=naive))
            db.commit()
            ids = (a.id, b.id)
        env = {"app": app, "clock": clock, "a": ids[0], "b": ids[1]}
        relogin(env)
        yield env


def relogin(p):
    p["owner"], p["staff"], p["owner_b"] = sign_in(p["app"], "owner-a"), sign_in(p["app"], "staff-a"), sign_in(p["app"], "owner-b")


def v(p, path, venue="a"):
    return f"/api/venues/{p[venue]}{path}"


def play(p, table_id, minutes, method="cash", items=(), venue="a", void=False):
    owner, staff = (p["owner"], p["staff"]) if venue == "a" else (p["owner_b"], p["owner_b"])
    session = staff.post(v(p, f"/tables/{table_id}/open", venue), json={}).json()
    for product_id, qty in items:
        staff.post(v(p, f"/sessions/{session['id']}/items", venue), json={"product_id": product_id, "quantity": qty})
    p["clock"].advance(minutes=minutes)
    if void:
        return owner.post(v(p, f"/sessions/{session['id']}/void", venue), json={"reason": "mở nhầm bàn"}).json()
    return staff.post(v(p, f"/sessions/{session['id']}/checkout", venue), json={"payment_method": method}).json()


@pytest.fixture
def data(p):
    t1 = p["owner"].post(v(p, "/tables"), json={"name": "Bàn 1", "hourly_rate": 60000}).json()["id"]
    t2 = p["owner"].post(v(p, "/tables"), json={"name": "=Bàn độc", "hourly_rate": 120000}).json()["id"]
    water = p["owner"].post(v(p, "/products"), json={"name": "Nước", "price": 10000}).json()["id"]
    s2_open = p["staff"].post(v(p, f"/tables/{t2}/open"), json={}).json()
    p["clock"].advance(minutes=0)
    first = play(p, t1, 60, "cash", [(water, 2)])  # 60.000 + 20.000 = 80.000
    p["clock"].advance(minutes=0)
    second = p["staff"].post(v(p, f"/sessions/{s2_open['id']}/checkout"), json={"payment_method": "transfer"}).json()  # 60 phút × 120.000
    p["clock"].advance(days=1)  # 2026-11-23 10:00 (thứ Hai)
    relogin(p)
    third = play(p, t1, 120, "cash")  # 120.000
    play(p, t2, 15, void=True)  # phiên huỷ: không tính
    p["staff"].post(v(p, f"/tables/{t2}/open"), json={})  # phiên đang chơi: không tính
    return {"t1": t1, "t2": t2, "first": first, "second": second, "third": third}


def report(p, query="", client="owner", venue="a"):
    return p[client].get(v(p, f"/reports/revenue{query}", venue))


def test_totals_series_tables_items_and_hours_reconcile_with_paid_invoices(p, data):
    assert data["first"]["amount_vnd"] == 80000 and data["second"]["amount_vnd"] == 120000 and data["third"]["amount_vnd"] == 120000
    r = report(p, "?date_from=2026-11-22&date_to=2026-11-25").json()
    totals = r["totals"]
    assert totals["revenue"] == 80000 + 120000 + 120000 and totals["sessions"] == 3
    assert totals["table_amount"] == 60000 + 120000 + 120000 and totals["items_amount"] == 20000
    assert totals["collected_cash"] == 80000 + 120000 and totals["collected_transfer"] == 120000
    assert totals["voucher_discount"] == 0 and totals["deposit_applied"] == 0
    # Tổng chuỗi theo ngày phải khớp tổng doanh thu; ngày không có doanh thu điền 0.
    assert [(x["key"], x["revenue"], x["sessions"]) for x in r["series"]] == [
        ("2026-11-22", 200000, 2), ("2026-11-23", 120000, 1), ("2026-11-24", 0, 0), ("2026-11-25", 0, 0)]
    assert sum(x["revenue"] for x in r["series"]) == totals["revenue"]
    assert [(t["table_name"], t["sessions"], t["minutes"], t["revenue"]) for t in r["by_table"]] == [("Bàn 1", 2, 180, 200000), ("=Bàn độc", 1, 60, 120000)]
    assert r["top_items"] == [{"name": "Nước", "quantity": 2, "amount": 20000}]
    assert r["sessions_by_start_hour"][10] == 2 and r["sessions_by_start_hour"][11] == 1 and sum(r["sessions_by_start_hour"]) == 3


def test_grouping_by_week_and_month(p, data):
    week = report(p, "?date_from=2026-11-22&date_to=2026-11-23&group=week").json()["series"]
    assert [(x["key"], x["revenue"]) for x in week] == [("2026-11-16", 200000), ("2026-11-23", 120000)]  # tuần bắt đầu thứ Hai
    month = report(p, "?date_from=2026-11-01&date_to=2026-12-31&group=month").json()["series"]
    assert [(x["key"], x["revenue"]) for x in month] == [("2026-11", 320000), ("2026-12", 0)]
    assert report(p, "?group=year").status_code == 422


def test_range_selects_only_sessions_ended_inside_it(p, data):
    only_monday = report(p, "?date_from=2026-11-23&date_to=2026-11-23").json()
    assert only_monday["totals"]["revenue"] == 120000 and only_monday["totals"]["sessions"] == 1
    assert report(p, "?date_from=2026-11-01&date_to=2026-11-21").json()["totals"]["revenue"] == 0


def test_sessions_are_assigned_to_the_venue_day_of_the_closing_time(p):
    t = p["owner"].post(v(p, "/tables"), json={"name": "Bàn đêm", "hourly_rate": 60000}).json()["id"]
    p["clock"].now = datetime(2026, 11, 22, 16, 50, tzinfo=timezone.utc)  # 23:50 giờ VN, ngày 22
    relogin(p)
    play(p, t, 15)  # kết thúc 17:05 UTC = 00:05 ngày 23 giờ VN
    r = report(p, "?date_from=2026-11-22&date_to=2026-11-23").json()
    assert [(x["key"], x["revenue"]) for x in r["series"]] == [("2026-11-22", 0), ("2026-11-23", 15000)]
    assert r["sessions_by_start_hour"][23] == 1  # bắt đầu lúc 23:50 giờ VN


def test_default_range_is_the_last_30_days_and_validation(p, data):
    r = report(p).json()
    assert len(r["series"]) == 30 and r["to"] == "2026-11-23" and r["from"] == "2026-10-25"
    assert report(p, "?date_from=2026-11-25&date_to=2026-11-22").status_code == 400
    assert report(p, "?date_from=2025-01-01&date_to=2026-11-22").status_code == 400  # > 366 ngày
    assert report(p, "?date_from=hôm-qua").status_code == 400
    assert report(p, "?date_from=2025-11-23&date_to=2026-11-23").status_code == 200  # đúng 366 ngày


def test_reports_are_owner_only_and_venue_isolated(p, data):
    assert report(p, client="staff").status_code == 403
    assert p["staff"].get(v(p, "/reports/export.csv")).status_code == 403
    assert report(p, client="owner_b", venue="a").status_code == 404
    assert TestClient(p["app"], base_url="http://127.0.0.1").get(v(p, "/reports/revenue")).status_code == 401
    other = report(p, "?date_from=2026-11-01&date_to=2026-11-30", client="owner_b", venue="b").json()
    assert other["totals"]["revenue"] == 0 and other["by_table"] == []
    # Quán B có doanh thu riêng: không lẫn vào quán A.
    tb = p["owner_b"].post(v(p, "/tables", "b"), json={"name": "B1", "hourly_rate": 60000}).json()["id"]
    play(p, tb, 30, venue="b")
    assert report(p, "?date_from=2026-11-01&date_to=2026-11-30").json()["totals"]["revenue"] == 320000
    assert report(p, "?date_from=2026-11-01&date_to=2026-11-30", client="owner_b", venue="b").json()["totals"]["revenue"] == 30000


def test_voucher_and_deposit_are_reported_separately(p):
    table = p["owner"].post(v(p, "/tables"), json={"name": "Bàn cọc", "hourly_rate": 60000}).json()["id"]
    with Session(p["app"].state.engine) as db:
        from apps.manage_api.models import PlaySession
        # phiên đã thanh toán có voucher 10.000 và cọc 20.000 (dựng trực tiếp để cô lập phép tính báo cáo)
        db.add(PlaySession(id="x" * 36, venue_id=p["a"], table_id=table, started_at=START.replace(tzinfo=None), ended_at=(START + timedelta(hours=1)).replace(tzinfo=None),
                           status="PAID", rate_snapshot=60000, total_amount=50000, table_amount=60000, items_amount=0, voucher_discount=10000,
                           deposit_applied=20000, billable_minutes=60, opened_by=1, closed_by=1))
        db.commit()
    totals = report(p, "?date_from=2026-11-22&date_to=2026-11-22").json()["totals"]
    assert totals["revenue"] == 50000 and totals["voucher_discount"] == 10000 and totals["deposit_applied"] == 20000
    assert totals["table_amount"] == 60000


# ---------- CSV ----------

def test_csv_export_matches_the_report_and_is_safe_for_spreadsheets(p, data):
    response = p["owner"].get(v(p, "/reports/export.csv?date_from=2026-11-22&date_to=2026-11-25"))
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    assert 'attachment; filename="hoa-don_2026-11-22_2026-11-25.csv"' in response.headers["content-disposition"]
    assert response.content.startswith("﻿".encode())
    rows = list(csv.reader(io.StringIO(response.text.lstrip("﻿"))))
    assert rows[0][:3] == ["Mã hoá đơn", "Bàn", "Bắt đầu"] and len(rows) == 4
    header = rows[0]
    total_col = header.index("Tổng hoá đơn")
    assert sum(int(r[total_col]) for r in rows[1:]) == 320000
    assert "'=Bàn độc" in [r[1] for r in rows[1:]]  # không có ô nào bắt đầu bằng "="
    assert not any(cell.startswith(("=", "+", "@")) for r in rows[1:] for cell in r)
    assert rows[1][2].startswith("2026-11-22 10:")  # giờ địa phương của quán
    assert {r[header.index("Hình thức")] for r in rows[1:]} == {"Tiền mặt", "Chuyển khoản"}
    with Session(p["app"].state.engine) as db:
        logged = [r for r in db.scalars(select(AuditLog)) if r.action == "report_exported"]
        assert len(logged) == 1 and logged[0].detail["rows"] == 3


def test_csv_empty_range_and_validation(p, data):
    empty = p["owner"].get(v(p, "/reports/export.csv?date_from=2026-01-01&date_to=2026-01-02"))
    assert len(list(csv.reader(io.StringIO(empty.text.lstrip("﻿"))))) == 1  # chỉ có dòng tiêu đề
    assert p["owner"].get(v(p, "/reports/export.csv?date_from=2026-02-01&date_to=2026-01-01")).status_code == 400


def test_csv_safe_helper():
    assert csv_safe("=1+1") == "'=1+1" and csv_safe("@x") == "'@x" and csv_safe("-5") == "'-5" and csv_safe("+84") == "'+84"
    assert csv_safe("Bàn 1") == "Bàn 1" and csv_safe(None) == "" and csv_safe(12) == "12"
