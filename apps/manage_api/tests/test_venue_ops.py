from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.manage_api.billing import quote
from apps.manage_api.config import ManageSettings
from apps.manage_api.main import create_app
from apps.manage_api.models import AuditLog, Payment, PlaySession, User, Venue
from apps.manage_api.security import hash_password

PASSWORD = "Billiard-2026!"
START = datetime(2026, 11, 22, 3, 0, tzinfo=timezone.utc)  # 10:00 giờ Việt Nam


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


@pytest.fixture
def env(tmp_path):
    clock = Clock()
    app = create_app(ManageSettings(database_url=f"sqlite:///{tmp_path / 'm.db'}"), clock)
    with TestClient(app, base_url="http://127.0.0.1") as _:
        naive = START.replace(tzinfo=None)
        with Session(app.state.engine) as db:
            a, b = Venue(name="Quán A", slug="quan-a", created_at=naive), Venue(name="Quán B", slug="quan-b", created_at=naive)
            db.add_all([a, b])
            db.flush()
            for role, login, venue in [("platform_admin", "admin", None), ("owner", "owner-a", a), ("staff", "staff-a", a),
                                       ("owner", "owner-b", b), ("customer", "0901111111", a), ("customer", "0902222222", b)]:
                db.add(User(role=role, login=login, display_name=login, password_hash=hash_password(PASSWORD),
                            venue_id=venue.id if venue else None, created_at=naive))
            db.commit()
            ids = {"a": a.id, "b": b.id}
        yield app, clock, ids


def client_for(app, login, slug=None):
    client = TestClient(app, base_url="http://127.0.0.1")
    response = client.post("/api/auth/login", json={"login": login, "password": PASSWORD, "venue_slug": slug})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


@pytest.fixture
def people(env):
    app, clock, ids = env
    return {"owner": client_for(app, "owner-a"), "staff": client_for(app, "staff-a"), "owner_b": client_for(app, "owner-b"),
            "admin": client_for(app, "admin"), "customer": client_for(app, "0901111111", "quan-a"), "app": app,
            "clock": clock, "a": ids["a"], "b": ids["b"]}


def relogin(p):
    """Phiên đăng nhập hết hạn sau 12 giờ: đăng nhập lại khi test nhảy qua ngày."""
    for key, login in (("owner", "owner-a"), ("staff", "staff-a")):
        p[key] = client_for(p["app"], login)


def new_table(p, name="Bàn 1", rate=60000, client="owner", venue="a", **extra):
    return p[client].post(f"/api/venues/{p[venue]}/tables", json={"name": name, "hourly_rate": rate, **extra})


def open_table(p, table_id, client="staff", venue="a", body=None):
    return p[client].post(f"/api/venues/{p[venue]}/tables/{table_id}/open", json=body or {})


def checkout(p, session_id, method="cash", client="staff", venue="a"):
    return p[client].post(f"/api/venues/{p[venue]}/sessions/{session_id}/checkout", json={"payment_method": method})


# ---------- tính tiền ----------

def test_billing_rounds_up_to_the_minute_and_integer_vnd():
    t0 = START
    assert quote(t0, t0, 60000) == {"elapsed_seconds": 0, "billable_minutes": 0, "amount_vnd": 0}
    assert quote(t0, t0 + timedelta(seconds=1), 60000)["billable_minutes"] == 1
    assert quote(t0, t0 + timedelta(seconds=61), 60000)["billable_minutes"] == 2
    assert quote(t0, t0 + timedelta(minutes=90), 60000)["amount_vnd"] == 90000
    assert quote(t0, t0 + timedelta(minutes=3), 59999)["amount_vnd"] == -(-3 * 59999 // 60)  # làm tròn lên
    assert quote(t0, t0 - timedelta(minutes=5), 60000)["amount_vnd"] == 0  # giờ âm không sinh tiền âm


# ---------- phân quyền & cô lập ----------

def test_only_the_owner_can_manage_tables_and_roles_are_enforced(people):
    p = people
    assert new_table(p, client="staff").status_code == 403
    assert new_table(p, client="customer").status_code == 403
    assert new_table(p, client="admin").status_code == 403
    table = new_table(p).json()
    assert p["staff"].get(f"/api/venues/{p['a']}/tables").status_code == 200
    assert p["staff"].patch(f"/api/venues/{p['a']}/tables/{table['id']}", json={"hourly_rate": 1}).status_code == 403
    assert p["customer"].get(f"/api/venues/{p['a']}/tables").status_code == 403
    assert p["admin"].get(f"/api/venues/{p['a']}/tables").status_code == 403


def test_tenant_isolation_for_tables_and_sessions(people):
    p = people
    table = new_table(p).json()
    session = open_table(p, table["id"]).json()
    other = p["owner_b"]
    assert other.get(f"/api/venues/{p['a']}/tables").status_code == 404
    assert other.post(f"/api/venues/{p['a']}/tables", json={"name": "X", "hourly_rate": 1}).status_code == 404
    # Dùng id của quán A qua URL quán B cũng phải 404.
    assert other.patch(f"/api/venues/{p['b']}/tables/{table['id']}", json={"hourly_rate": 1}).status_code == 404
    assert other.post(f"/api/venues/{p['b']}/tables/{table['id']}/open", json={}).status_code == 404
    assert other.get(f"/api/venues/{p['b']}/sessions/{session['id']}/quote").status_code == 404
    assert other.post(f"/api/venues/{p['b']}/sessions/{session['id']}/checkout", json={"payment_method": "cash"}).status_code == 404
    assert other.post(f"/api/venues/{p['b']}/sessions/{session['id']}/void", json={"reason": "thử"}).status_code == 404
    assert other.get(f"/api/venues/{p['b']}/sessions").json()["total"] == 0
    assert other.get(f"/api/venues/{p['b']}/tables").json()["tables"] == []
    assert p["owner"].get(f"/api/venues/{p['a']}/tables").json()["tables"][0]["session"]["id"] == session["id"]


def test_same_table_name_is_allowed_in_different_venues(people):
    p = people
    assert new_table(p, "Bàn 1").status_code == 201
    assert new_table(p, "Bàn 1").status_code == 409
    assert new_table(p, "Bàn 1", client="owner_b", venue="b").status_code == 201


def test_table_validation(people):
    p = people
    assert new_table(p, rate=-1).status_code == 422
    assert new_table(p, "B2", rate=10_000_001).status_code == 422
    assert new_table(p, "B3", table_type="khong-co").status_code == 422
    assert new_table(p, "   ").status_code == 400
    assert new_table(p, "B4", rate=0).status_code == 201


# ---------- mở bàn / giá chốt ----------

def test_open_snapshots_the_rate_and_blocks_a_second_active_session(people):
    p = people
    table = new_table(p, rate=60000).json()
    first = open_table(p, table["id"])
    assert first.status_code == 201 and first.json()["rate_snapshot"] == 60000
    assert open_table(p, table["id"]).status_code == 409
    # Đổi giá giữa phiên không ảnh hưởng phiên đang chạy.
    assert p["owner"].patch(f"/api/venues/{p['a']}/tables/{table['id']}", json={"hourly_rate": 100000}).status_code == 200
    p["clock"].advance(minutes=60)
    paid = checkout(p, first.json()["id"]).json()
    assert paid["amount_vnd"] == 60000
    # Phiên mới dùng giá mới.
    assert open_table(p, table["id"]).json()["rate_snapshot"] == 100000


def test_concurrent_open_creates_exactly_one_session(people):
    p = people
    table = new_table(p).json()
    with ThreadPoolExecutor(6) as pool:
        codes = list(pool.map(lambda _: open_table(p, table["id"]).status_code, range(6)))
    assert codes.count(201) == 1 and codes.count(409) == 5
    with Session(p["app"].state.engine) as db:
        assert db.scalar(select(func.count()).select_from(PlaySession).where(PlaySession.status == "ACTIVE")) == 1


def test_inactive_table_rules(people):
    p = people
    table = new_table(p).json()
    session = open_table(p, table["id"]).json()
    deactivate = lambda: p["owner"].patch(f"/api/venues/{p['a']}/tables/{table['id']}", json={"status": "INACTIVE"})
    assert deactivate().status_code == 409  # đang có phiên
    checkout(p, session["id"])
    assert deactivate().json()["status"] == "INACTIVE"
    assert open_table(p, table["id"]).status_code == 409


def test_open_validates_customer_belongs_to_the_venue(people):
    p = people
    table = new_table(p).json()
    with Session(p["app"].state.engine) as db:
        mine = db.scalar(select(User.id).where(User.login == "0901111111"))
        theirs = db.scalar(select(User.id).where(User.login == "0902222222"))
        staff = db.scalar(select(User.id).where(User.login == "staff-a"))
    assert open_table(p, table["id"], body={"customer_id": theirs}).status_code == 400
    assert open_table(p, table["id"], body={"customer_id": staff}).status_code == 400
    assert open_table(p, table["id"], body={"customer_id": mine}).json()["customer_id"] == mine


# ---------- checkout ----------

def test_checkout_uses_server_time_records_payment_and_is_idempotent(people):
    p = people
    table = new_table(p, rate=60000).json()
    session = open_table(p, table["id"]).json()
    p["clock"].advance(hours=1, seconds=1)  # 61 phút tính tiền
    first = checkout(p, session["id"], "transfer")
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "PAID" and body["billable_minutes"] == 61 and body["amount_vnd"] == 61000 and body["duplicate"] is False
    p["clock"].advance(hours=5)  # thử lại muộn hơn: không đổi số tiền đã chốt
    again = checkout(p, session["id"], "cash").json()
    assert again["duplicate"] is True and again["amount_vnd"] == 61000 and again["ended_at"] == body["ended_at"]
    with Session(p["app"].state.engine) as db:
        payments = db.scalars(select(Payment)).all()
    assert len(payments) == 1 and payments[0].amount == 61000 and payments[0].method == "transfer"
    assert open_table(p, table["id"]).status_code == 201  # bàn trống lại


def test_checkout_rejects_unknown_payment_method_and_client_cannot_set_amounts(people):
    p = people
    session = open_table(p, new_table(p).json()["id"]).json()
    url = f"/api/venues/{p['a']}/sessions/{session['id']}/checkout"
    assert p["staff"].post(url, json={"payment_method": "bitcoin"}).status_code == 422
    assert p["staff"].post(url, json={}).status_code == 422
    p["clock"].advance(minutes=30)
    paid = p["staff"].post(url, json={"payment_method": "cash", "amount_vnd": 1, "ended_at": "2020-01-01T00:00:00Z"}).json()
    assert paid["amount_vnd"] == 30000  # trường lạ bị bỏ qua


def test_concurrent_checkouts_charge_once(people):
    p = people
    session = open_table(p, new_table(p).json()["id"]).json()
    p["clock"].advance(minutes=45)
    with ThreadPoolExecutor(5) as pool:
        results = list(pool.map(lambda _: checkout(p, session["id"]).json(), range(5)))
    assert {r["amount_vnd"] for r in results} == {45000}
    assert sum(1 for r in results if not r["duplicate"]) == 1
    with Session(p["app"].state.engine) as db:
        assert db.scalar(select(func.count()).select_from(Payment)) == 1


# ---------- huỷ phiên ----------

def test_void_rules(people):
    p = people
    table = new_table(p).json()
    session = open_table(p, table["id"]).json()
    url = f"/api/venues/{p['a']}/sessions/{session['id']}/void"
    assert p["staff"].post(url, json={"reason": "mở nhầm bàn"}).status_code == 403
    assert p["owner"].post(url, json={}).status_code == 422
    assert p["owner"].post(url, json={"reason": "ab"}).status_code == 422
    p["clock"].advance(minutes=20)
    voided = p["owner"].post(url, json={"reason": "Mở nhầm bàn"}).json()
    assert voided["status"] == "VOID" and voided["amount_vnd"] == 0 and voided["void_reason"] == "Mở nhầm bàn"
    assert checkout(p, session["id"]).status_code == 409
    assert p["owner"].post(url, json={"reason": "lần hai"}).status_code == 409
    paid = open_table(p, table["id"]).json()
    p["clock"].advance(minutes=10)
    checkout(p, paid["id"])
    assert p["owner"].post(f"/api/venues/{p['a']}/sessions/{paid['id']}/void", json={"reason": "muốn hoàn"}).status_code == 409
    assert p["owner"].get(f"/api/venues/{p['a']}/revenue/today").json()["total_vnd"] == 10000  # phiên huỷ không tính


# ---------- lịch sử & doanh thu ----------

def test_staff_sees_only_today_while_owner_can_filter_by_date(people):
    p = people
    table = new_table(p).json()
    old = open_table(p, table["id"]).json()
    p["clock"].advance(minutes=30)
    checkout(p, old["id"])
    p["clock"].advance(days=1)  # sang ngày hôm sau
    relogin(p)
    today = open_table(p, table["id"]).json()
    p["clock"].advance(minutes=15)
    checkout(p, today["id"])

    staff_view = p["staff"].get(f"/api/venues/{p['a']}/sessions?date_from=2026-11-01&date_to=2026-11-30").json()
    assert [s["id"] for s in staff_view["items"]] == [today["id"]]  # tham số ngày bị bỏ qua với nhân viên
    owner_all = p["owner"].get(f"/api/venues/{p['a']}/sessions").json()
    assert owner_all["total"] == 2
    only_old = p["owner"].get(f"/api/venues/{p['a']}/sessions?date_from=2026-11-22&date_to=2026-11-22").json()
    assert [s["id"] for s in only_old["items"]] == [old["id"]]
    assert p["owner"].get(f"/api/venues/{p['a']}/sessions?status=VOID").json()["total"] == 0
    assert p["owner"].get(f"/api/venues/{p['a']}/sessions?limit=1&offset=1").json()["items"][0]["id"] == old["id"]
    assert p["owner"].get(f"/api/venues/{p['a']}/sessions?date_from=hôm-qua").status_code == 400


def test_revenue_today_counts_only_todays_paid_sessions_in_local_time(people):
    p = people
    t1, t2 = new_table(p, "Bàn 1", 60000).json(), new_table(p, "Bàn 2", 120000).json()
    s1, s2 = open_table(p, t1["id"]).json(), open_table(p, t2["id"]).json()
    p["clock"].advance(minutes=60)
    checkout(p, s1["id"])
    checkout(p, s2["id"])
    open_table(p, t1["id"])  # đang chơi: chưa tính
    revenue = p["staff"].get(f"/api/venues/{p['a']}/revenue/today").json()
    assert revenue["total_vnd"] == 60000 + 120000 and revenue["session_count"] == 2 and revenue["date"] == "2026-11-22"
    assert {r["table_name"]: r["amount_vnd"] for r in revenue["by_table"]} == {"Bàn 1": 60000, "Bàn 2": 120000}
    assert p["owner_b"].get(f"/api/venues/{p['b']}/revenue/today").json()["total_vnd"] == 0
    # 17:30 UTC = 00:30 ngày 23 giờ Việt Nam: sang ngày mới, doanh thu hôm nay về 0.
    p["clock"].now = datetime(2026, 11, 22, 17, 30, tzinfo=timezone.utc)
    relogin(p)
    after_midnight = p["owner"].get(f"/api/venues/{p['a']}/revenue/today").json()
    assert after_midnight["date"] == "2026-11-23" and after_midnight["total_vnd"] == 0


def test_tables_listing_reports_live_amounts_from_the_server(people):
    p = people
    table = new_table(p, rate=60000).json()
    open_table(p, table["id"])
    p["clock"].advance(minutes=10, seconds=5)
    listing = p["staff"].get(f"/api/venues/{p['a']}/tables").json()
    session = listing["tables"][0]["session"]
    assert session["elapsed_seconds"] == 605 and session["billable_minutes"] == 11 and session["amount_vnd"] == 11000
    assert listing["server_time"].endswith("Z")


def test_operations_leave_an_audit_trail(people):
    p = people
    table = new_table(p).json()
    session = open_table(p, table["id"]).json()
    p["clock"].advance(minutes=5)
    checkout(p, session["id"])
    with Session(p["app"].state.engine) as db:
        actions = [row.action for row in db.scalars(select(AuditLog).order_by(AuditLog.id))]
    assert {"table_created", "session_opened", "session_paid"} <= set(actions)
