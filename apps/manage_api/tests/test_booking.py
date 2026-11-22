from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.manage_api.config import ManageSettings
from apps.manage_api.main import create_app
from apps.manage_api.models import AuditLog, Booking, Deposit, Payment, User, Venue
from apps.manage_api.payments import MockPaymentProvider, provider_for
from apps.manage_api.security import hash_password

PASSWORD = "Billiard-2026!"
CUSTOMER_PASSWORD = "Khach-Hang-2026"
START = datetime(2026, 11, 22, 3, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


def at(minutes: float) -> str:
    return (START + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def client(app) -> TestClient:
    return TestClient(app, base_url="http://127.0.0.1")


def sign_in(app, login, password=PASSWORD, slug=None):
    c = client(app)
    response = c.post("/api/auth/login", json={"login": login, "password": password, "venue_slug": slug})
    assert response.status_code == 200, response.text
    c.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return c


def register(app, slug, phone, name="Khách", password=CUSTOMER_PASSWORD):
    c = client(app)
    response = c.post("/api/auth/register", json={"venue_slug": slug, "display_name": name, "phone": phone, "password": password})
    if response.status_code == 201:
        c.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return c, response


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
        env = {"app": app, "clock": clock, "a": ids[0], "b": ids[1], "owner": sign_in(app, "owner-a"), "staff": sign_in(app, "staff-a"),
               "owner_b": sign_in(app, "owner-b")}
        env["table"] = env["owner"].post(f"/api/venues/{env['a']}/tables", json={"name": "Bàn 1", "hourly_rate": 60000}).json()
        env["table2"] = env["owner"].post(f"/api/venues/{env['a']}/tables", json={"name": "Bàn 2", "hourly_rate": 60000}).json()
        env["cust"], _ = register(app, "quan-a", "0901111111", "An")
        yield env


def v(p, path, venue="a"):
    return f"/api/venues/{p[venue]}{path}"


def book(p, minutes=120, duration=60, table="table", who="cust"):
    return p[who].post(v(p, "/my/bookings"), json={"table_id": p[table]["id"], "start_at": at(minutes), "duration_minutes": duration})


def booked_and_paid(p, minutes=120, duration=60, table="table", who="cust"):
    created = book(p, minutes, duration, table, who).json()
    paid = p[who].post(v(p, f"/my/bookings/{created['id']}/deposit/mock-pay")).json()
    assert paid["status"] == "CONFIRMED"
    return paid


# ---------- đăng ký khách ----------

def test_registration_logs_the_customer_in_and_is_venue_scoped(p):
    c, response = register(p["app"], "quan-a", "+84 902 222 222", "Bình")
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "customer" and body["venue"]["slug"] == "quan-a" and "password" not in str(body).lower().replace("must_change_password", "")
    assert "httponly" in response.headers["set-cookie"].lower()
    assert c.get("/api/auth/me").json()["login"] == "0902222222"
    assert c.get(v(p, "/tables")).status_code == 403  # khách không vào khu vận hành
    assert c.get(v(p, "/availability?date=2026-11-22", "b")).status_code == 404  # khách chỉ thấy quán của mình
    assert c.get(v(p, "/my/bookings", "b")).status_code == 404
    assert c.post("/api/auth/register", json={"venue_slug": "quan-a", "display_name": "x", "phone": "0902222222", "password": CUSTOMER_PASSWORD}).status_code == 409
    _, other = register(p["app"], "quan-b", "0902222222", "Bình (B)")
    assert other.status_code == 201  # cùng SĐT ở quán khác là tài khoản độc lập
    assert sign_in(p["app"], "0902222222", CUSTOMER_PASSWORD, slug="quan-a").get("/api/auth/me").json()["venue"]["slug"] == "quan-a"


def test_registration_validation_and_suspended_venue(p):
    assert register(p["app"], "khong-co", "0903333333")[1].status_code == 404
    assert register(p["app"], "quan-a", "123")[1].status_code == 400
    assert register(p["app"], "quan-a", "0903333333", password="123")[1].status_code == 400
    assert register(p["app"], "quan-a", "0903333333", password="0000000000")[1].status_code == 400
    with Session(p["app"].state.engine) as db:
        db.get(Venue, p["b"]).status = "SUSPENDED"
        db.commit()
    assert register(p["app"], "quan-b", "0904444444")[1].status_code == 404
    assert client(p["app"]).get("/api/public/venues/quan-b").status_code == 404
    public = client(p["app"]).get("/api/public/venues/quan-a")
    assert public.status_code == 200 and public.json() == {"name": "Quán A", "slug": "quan-a"}


# ---------- cài đặt ----------

def test_booking_settings_permissions_and_bounds(p):
    default = p["staff"].get(v(p, "/booking-settings")).json()
    assert default["deposit_amount"] == 50000 and default["payment_is_mock"] is True
    assert p["cust"].get(v(p, "/booking-settings")).status_code == 200
    body = {"deposit_amount": 80000, "hold_minutes": 10, "refund_before_minutes": 120, "noshow_grace_minutes": 20}
    assert p["staff"].put(v(p, "/booking-settings"), json=body).status_code == 403
    assert p["cust"].put(v(p, "/booking-settings"), json=body).status_code == 403
    for bad in ({**body, "deposit_amount": -1}, {**body, "hold_minutes": 1}, {**body, "refund_before_minutes": 99999}, {**body, "noshow_grace_minutes": 0}):
        assert p["owner"].put(v(p, "/booking-settings"), json=bad).status_code == 422
    assert p["owner"].put(v(p, "/booking-settings"), json=body).json()["deposit_amount"] == 80000
    assert p["owner_b"].get(v(p, "/booking-settings", "b")).json()["deposit_amount"] == 50000  # quán khác không đổi
    assert p["owner_b"].put(v(p, "/booking-settings", "a"), json=body).status_code == 404


# ---------- đặt bàn ----------

def test_availability_hides_who_booked(p):
    booked_and_paid(p)
    other, _ = register(p["app"], "quan-a", "0905555555", "Khách khác")
    day = other.get(v(p, "/availability?date=2026-11-22")).json()
    table = next(t for t in day["tables"] if t["id"] == p["table"]["id"])
    assert table["busy"] == [{"start_at": at(120), "end_at": at(180)}]
    assert "customer" not in str(day) and "0901111111" not in str(day) and day["settings"]["deposit_amount"] == 50000
    assert other.get(v(p, "/availability?date=hôm-nay")).status_code == 400
    assert p["staff"].get(v(p, "/availability?date=2026-11-22")).status_code == 403


def test_booking_validation(p):
    post = lambda **kw: p["cust"].post(v(p, "/my/bookings"), json={"table_id": p["table"]["id"], "start_at": at(120), "duration_minutes": 60, **kw})
    assert post(start_at=at(-30)).status_code == 400  # đã qua
    assert post(start_at=at(60 * 24 * 15)).status_code == 400  # quá 14 ngày
    assert post(duration_minutes=45).status_code == 400
    assert post(start_at="2026-11-22T05:00:00").status_code == 400  # thiếu múi giờ
    assert post(table_id=99999).status_code == 404
    assert post(table_id=p["table"]["id"] + 1000).status_code == 404
    p["owner"].patch(v(p, f"/tables/{p['table2']['id']}"), json={"status": "INACTIVE"})
    assert post(table_id=p["table2"]["id"]).status_code == 404
    foreign = p["owner_b"].post(v(p, "/tables", "b"), json={"name": "B1", "hourly_rate": 1}).json()
    assert post(table_id=foreign["id"]).status_code == 404
    created = post()
    assert created.status_code == 201 and created.json()["status"] == "PENDING" and created.json()["deposit"]["amount"] == 50000
    assert created.json()["deposit"]["is_mock"] is True


def test_overlap_adjacent_slots_and_open_booking_limit(p):
    assert book(p, 120, 60).status_code == 201
    assert book(p, 150, 60).status_code == 409  # chồng giờ
    assert book(p, 90, 60).status_code == 409
    assert book(p, 180, 60).status_code == 201  # sát giờ, không chồng
    assert book(p, 120, 60, table="table2").status_code == 201  # bàn khác
    assert book(p, 300, 60).status_code == 409  # đã đủ 3 lịch chưa diễn ra
    other, _ = register(p["app"], "quan-a", "0906666666")
    assert book(p, 120, 60, who="cust").status_code == 409
    assert book(p, 120, 60, table="table", who="cust") .status_code == 409
    assert other.post(v(p, "/my/bookings"), json={"table_id": p["table"]["id"], "start_at": at(300), "duration_minutes": 60}).status_code == 201


def test_concurrent_bookings_for_the_same_slot_create_exactly_one(p):
    customers = [register(p["app"], "quan-a", f"09123456{n:02d}")[0] for n in range(6)]
    body = {"table_id": p["table"]["id"], "start_at": at(240), "duration_minutes": 60}
    with ThreadPoolExecutor(6) as pool:
        codes = list(pool.map(lambda c: c.post(v(p, "/my/bookings"), json=body).status_code, customers))
    assert codes.count(201) == 1 and codes.count(409) == 5


def test_zero_deposit_confirms_immediately_without_a_deposit_row(p):
    p["owner"].put(v(p, "/booking-settings"), json={"deposit_amount": 0, "hold_minutes": 15, "refund_before_minutes": 60, "noshow_grace_minutes": 30})
    created = book(p).json()
    assert created["status"] == "CONFIRMED" and created["deposit"] is None and created["expires_at"] is None


def test_unpaid_hold_expires_and_frees_the_slot(p):
    created = book(p).json()
    p["clock"].advance(minutes=16)
    other, _ = register(p["app"], "quan-a", "0907777777")
    assert other.post(v(p, "/my/bookings"), json={"table_id": p["table"]["id"], "start_at": at(120), "duration_minutes": 60}).status_code == 201
    assert p["cust"].post(v(p, f"/my/bookings/{created['id']}/deposit/mock-pay")).status_code == 409
    mine = {b["id"]: b for b in p["cust"].get(v(p, "/my/bookings")).json()}
    assert mine[created["id"]]["status"] == "EXPIRED" and mine[created["id"]]["deposit"]["status"] == "CANCELLED"


# ---------- cọc giả lập ----------

def test_mock_deposit_payment_confirms_once_and_only_for_the_owner(p):
    created = book(p).json()
    stranger, _ = register(p["app"], "quan-a", "0908888888")
    assert stranger.post(v(p, f"/my/bookings/{created['id']}/deposit/mock-pay")).status_code == 404
    paid = p["cust"].post(v(p, f"/my/bookings/{created['id']}/deposit/mock-pay")).json()
    assert paid["status"] == "CONFIRMED" and paid["deposit"]["status"] == "PAID" and paid["deposit"]["is_mock"] is True
    assert p["cust"].post(v(p, f"/my/bookings/{created['id']}/deposit/mock-pay")).status_code == 409
    with Session(p["app"].state.engine) as db:
        assert db.scalar(select(Deposit.provider)) == "mock"
        assert any(r.action == "deposit_paid_mock" for r in db.scalars(select(AuditLog)))


def test_payment_provider_is_mock_only(p):
    with pytest.raises(ValueError):
        ManageSettings(payment_provider="vnpay")
    with pytest.raises(ValueError):
        provider_for("vnpay")
    mock = MockPaymentProvider()
    charge = mock.create_charge(1000, "ref")
    assert charge.status == "PENDING" and charge.ref.startswith("mock_") and mock.is_real is False
    assert mock.confirm(charge.ref).status == "PAID" and mock.refund(charge.ref, 1000).startswith("mock_refund_")


# ---------- huỷ / vắng mặt ----------

def test_customer_cancellation_refund_window(p):
    early = booked_and_paid(p, minutes=300)
    done = p["cust"].post(v(p, f"/my/bookings/{early['id']}/cancel")).json()
    assert done["status"] == "CANCELLED" and done["deposit"]["status"] == "REFUNDED" and done["deposit"]["refunded_amount"] == 50000
    late = booked_and_paid(p, minutes=120)
    p["clock"].advance(minutes=90)  # còn 30 phút < 60 phút quy định
    late_cancel = p["cust"].post(v(p, f"/my/bookings/{late['id']}/cancel")).json()
    assert late_cancel["status"] == "CANCELLED" and late_cancel["deposit"]["status"] == "FORFEITED"
    pending = book(p, minutes=400).json()
    assert p["cust"].post(v(p, f"/my/bookings/{pending['id']}/cancel")).json()["deposit"]["status"] == "CANCELLED"
    assert p["cust"].post(v(p, f"/my/bookings/{pending['id']}/cancel")).status_code == 409


def test_customer_cannot_cancel_after_start_or_someone_elses_booking(p):
    created = booked_and_paid(p, minutes=60)
    stranger, _ = register(p["app"], "quan-a", "0909999999")
    assert stranger.post(v(p, f"/my/bookings/{created['id']}/cancel")).status_code == 404
    p["clock"].advance(minutes=61)
    assert p["cust"].post(v(p, f"/my/bookings/{created['id']}/cancel")).status_code == 409


def test_staff_cancellation_always_refunds_and_no_show_forfeits_after_grace(p):
    soon = booked_and_paid(p, minutes=30)
    assert p["staff"].post(v(p, f"/bookings/{soon['id']}/cancel")).json()["deposit"]["status"] == "REFUNDED"
    target = booked_and_paid(p, minutes=60)
    assert p["staff"].post(v(p, f"/bookings/{target['id']}/no-show")).status_code == 409  # chưa tới giờ
    p["clock"].advance(minutes=60 + 29)
    assert p["staff"].post(v(p, f"/bookings/{target['id']}/no-show")).status_code == 409  # chưa hết thời gian chờ
    p["clock"].advance(minutes=1)
    marked = p["staff"].post(v(p, f"/bookings/{target['id']}/no-show")).json()
    assert marked["status"] == "NO_SHOW" and marked["deposit"]["status"] == "FORFEITED"
    assert p["staff"].post(v(p, f"/bookings/{target['id']}/no-show")).status_code == 409


# ---------- nhận bàn & trừ cọc ----------

def test_check_in_rules(p):
    created = booked_and_paid(p, minutes=120)
    path = v(p, f"/bookings/{created['id']}/check-in")
    assert p["staff"].post(path).status_code == 409  # quá sớm (còn 120 phút)
    p["clock"].advance(minutes=95)  # còn 25 phút: trong cửa sổ nhận sớm
    assert p["cust"].post(path).status_code == 403
    assert p["owner_b"].post(v(p, f"/bookings/{created['id']}/check-in", "b")).status_code == 404
    busy = p["staff"].post(v(p, f"/tables/{p['table']['id']}/open"), json={})
    assert busy.status_code == 201
    assert p["staff"].post(path).status_code == 409  # bàn đang có người chơi
    p["staff"].post(v(p, f"/sessions/{busy.json()['id']}/checkout"), json={"payment_method": "cash"})
    result = p["staff"].post(path)
    assert result.status_code == 200 and result.json()["booking"]["status"] == "CHECKED_IN"
    assert p["staff"].post(path).status_code == 409
    session = p["staff"].get(v(p, f"/sessions/{result.json()['session_id']}/quote")).json()
    assert session["customer_id"] is not None


def test_deposit_is_deducted_at_checkout_and_the_excess_refunded(p):
    created = booked_and_paid(p, minutes=20, duration=120)  # cọc 50.000
    p["clock"].advance(minutes=10)
    session_id = p["staff"].post(v(p, f"/bookings/{created['id']}/check-in")).json()["session_id"]
    p["clock"].advance(minutes=120)  # 120 phút = 120.000
    quote = p["staff"].get(v(p, f"/sessions/{session_id}/quote")).json()
    assert quote["amount_vnd"] == 120000 and quote["deposit_applied"] == 50000 and quote["amount_due"] == 70000
    paid = p["staff"].post(v(p, f"/sessions/{session_id}/checkout"), json={"payment_method": "cash"}).json()
    assert paid["amount_vnd"] == 120000 and paid["deposit_applied"] == 50000 and paid["amount_due"] == 70000
    with Session(p["app"].state.engine) as db:
        assert db.scalar(select(Payment.amount).where(Payment.session_id == session_id)) == 70000  # tiền thu tại quầy
        deposit = db.scalar(select(Deposit))
        assert (deposit.status, deposit.applied_amount, deposit.refunded_amount) == ("APPLIED", 50000, 0)
    assert p["staff"].get(v(p, "/revenue/today")).json()["total_vnd"] == 120000  # doanh thu = tổng hoá đơn
    invoice = p["staff"].get(v(p, f"/sessions/{session_id}/invoice")).json()
    assert invoice["deposit_applied"] == 50000 and invoice["amount_due"] == 70000 and invoice["total"] == 120000
    again = p["staff"].post(v(p, f"/sessions/{session_id}/checkout"), json={"payment_method": "cash"}).json()
    assert again["duplicate"] is True and again["amount_due"] == 70000


def test_short_session_refunds_the_unused_deposit(p):
    created = booked_and_paid(p, minutes=10, duration=60)
    session_id = p["staff"].post(v(p, f"/bookings/{created['id']}/check-in")).json()["session_id"]
    p["clock"].advance(minutes=30)  # 30.000 < cọc 50.000
    paid = p["staff"].post(v(p, f"/sessions/{session_id}/checkout"), json={"payment_method": "cash"}).json()
    assert paid["amount_vnd"] == 30000 and paid["deposit_applied"] == 30000 and paid["amount_due"] == 0
    with Session(p["app"].state.engine) as db:
        deposit = db.scalar(select(Deposit))
        assert (deposit.applied_amount, deposit.refunded_amount) == (30000, 20000)


def test_sessions_without_a_booking_have_no_deposit(p):
    session = p["staff"].post(v(p, f"/tables/{p['table']['id']}/open"), json={}).json()
    p["clock"].advance(minutes=30)
    paid = p["staff"].post(v(p, f"/sessions/{session['id']}/checkout"), json={"payment_method": "cash"}).json()
    assert paid["deposit_applied"] == 0 and paid["amount_due"] == paid["amount_vnd"] == 30000


# ---------- danh sách ----------

def test_staff_booking_list_shows_customer_details_scoped_to_the_venue(p):
    booked_and_paid(p, minutes=120)
    listed = p["staff"].get(v(p, "/bookings")).json()
    assert len(listed) == 1 and listed[0]["customer"] == {"id": listed[0]["customer"]["id"], "name": "An", "phone": "0901111111"}
    assert p["owner_b"].get(v(p, "/bookings", "b")).json() == []
    assert p["owner_b"].get(v(p, "/bookings", "a")).status_code == 404
    assert p["cust"].get(v(p, "/bookings")).status_code == 403
    assert p["staff"].get(v(p, "/my/bookings")).status_code == 403


def test_customer_sees_only_own_bookings_and_paid_sessions(p):
    booked_and_paid(p, minutes=120)
    stranger, _ = register(p["app"], "quan-a", "0902020202")
    assert stranger.get(v(p, "/my/bookings")).json() == []
    assert len(p["cust"].get(v(p, "/my/bookings")).json()) == 1
    created = booked_and_paid(p, minutes=10, duration=60, table="table2")
    session_id = p["staff"].post(v(p, f"/bookings/{created['id']}/check-in")).json()["session_id"]
    p["clock"].advance(minutes=20)
    p["staff"].post(v(p, f"/sessions/{session_id}/checkout"), json={"payment_method": "cash"})
    mine = p["cust"].get(v(p, "/my/sessions")).json()
    assert mine["total"] == 1 and mine["items"][0]["total"] == 20000 and mine["items"][0]["deposit_applied"] == 20000
    assert stranger.get(v(p, "/my/sessions")).json()["total"] == 0
    with Session(p["app"].state.engine) as db:
        assert db.scalar(select(func.count()).select_from(Booking)) == 2
