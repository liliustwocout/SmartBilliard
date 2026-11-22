from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.manage_api.config import ManageSettings
from apps.manage_api.main import create_app
from apps.manage_api.models import AuditLog, Payment, PlaySession, SessionItem, User, Venue
from apps.manage_api.security import hash_password
from apps.manage_api.shop_api import normalize_phone

PASSWORD = "Billiard-2026!"
START = datetime(2026, 11, 22, 3, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


def login(app, name, password=PASSWORD, slug=None):
    client = TestClient(app, base_url="http://127.0.0.1")
    response = client.post("/api/auth/login", json={"login": name, "password": password, "venue_slug": slug})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


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
                db.add(User(role=role, login=name, display_name=name, password_hash=hash_password(PASSWORD),
                            venue_id=venue.id, created_at=naive))
            db.commit()
            ids = (a.id, b.id)
        yield {"app": app, "clock": clock, "a": ids[0], "b": ids[1], "owner": login(app, "owner-a"),
               "staff": login(app, "staff-a"), "owner_b": login(app, "owner-b")}


def url(p, path, venue="a"):
    return f"/api/venues/{p[venue]}{path}"


def make_table(p, rate=60000):
    return p["owner"].post(url(p, "/tables"), json={"name": "Bàn 1", "hourly_rate": rate}).json()


def make_product(p, name="Nước suối", price=10000, client="owner", venue="a"):
    return p[client].post(url(p, "/products", venue), json={"name": name, "price": price})


def open_session(p, rate=60000):
    table = make_table(p, rate)
    return p["staff"].post(url(p, f"/tables/{table['id']}/open"), json={}).json()


def add_item(p, session_id, product_id, quantity=1, client="staff"):
    return p[client].post(url(p, f"/sessions/{session_id}/items"), json={"product_id": product_id, "quantity": quantity})


def checkout(p, session_id, client="staff"):
    return p[client].post(url(p, f"/sessions/{session_id}/checkout"), json={"payment_method": "cash"})


# ---------- nhân viên ----------

def test_owner_creates_staff_who_must_change_the_temp_password(p):
    created = p["owner"].post(url(p, "/staff"), json={"login": " Thu-Ngan-Lan ", "display_name": "Lan"})
    assert created.status_code == 201
    body = created.json()
    assert body["staff"]["login"] == "thu-ngan-lan" and body["staff"]["must_change_password"] is True
    assert body["temp_password"] not in p["owner"].get(url(p, "/staff")).text
    staff = TestClient(p["app"], base_url="http://127.0.0.1")
    first = staff.post("/api/auth/login", json={"login": "thu-ngan-lan", "password": body["temp_password"]}).json()
    assert first["role"] == "staff" and first["must_change_password"] is True and first["venue"]["slug"] == "quan-a"
    with Session(p["app"].state.engine) as db:
        blob = str([(r.action, r.target, r.detail) for r in db.scalars(select(AuditLog))])
    assert body["temp_password"] not in blob


def test_staff_management_is_owner_only_and_venue_scoped(p):
    assert p["staff"].get(url(p, "/staff")).status_code == 403
    assert p["staff"].post(url(p, "/staff"), json={"login": "x-y-z", "display_name": "X"}).status_code == 403
    assert p["owner_b"].get(url(p, "/staff")).status_code == 404
    other = p["owner_b"].post(url(p, "/staff", "b"), json={"login": "nv-b", "display_name": "NV B"}).json()["staff"]
    assert p["owner"].patch(url(p, f"/staff/{other['id']}"), json={"status": "DISABLED"}).status_code == 404
    assert p["owner"].post(url(p, f"/staff/{other['id']}/reset-password")).status_code == 404
    assert p["owner"].post(url(p, "/staff"), json={"login": "owner-a", "display_name": "Trùng"}).status_code == 409
    assert p["owner"].post(url(p, "/staff"), json={"login": "nv-b", "display_name": "Trùng toàn hệ thống"}).status_code == 409
    assert p["owner"].post(url(p, "/staff"), json={"login": "ab", "display_name": "Ngắn"}).status_code == 422


def test_disabling_staff_cuts_access_and_reset_password_works(p):
    staff_id = next(u["id"] for u in p["owner"].get(url(p, "/staff")).json() if u["login"] == "staff-a")
    assert p["staff"].get(url(p, "/tables")).status_code == 200
    assert p["owner"].patch(url(p, f"/staff/{staff_id}"), json={"status": "DISABLED"}).json()["status"] == "DISABLED"
    assert p["staff"].get(url(p, "/tables")).status_code == 401
    assert TestClient(p["app"], base_url="http://127.0.0.1").post("/api/auth/login", json={"login": "staff-a", "password": PASSWORD}).status_code == 401
    p["owner"].patch(url(p, f"/staff/{staff_id}"), json={"status": "ACTIVE", "display_name": "Lan (mới)"})
    reset = p["owner"].post(url(p, f"/staff/{staff_id}/reset-password")).json()
    assert reset["login"] == "staff-a"
    assert TestClient(p["app"], base_url="http://127.0.0.1").post("/api/auth/login", json={"login": "staff-a", "password": PASSWORD}).status_code == 401
    relogin = TestClient(p["app"], base_url="http://127.0.0.1").post("/api/auth/login", json={"login": "staff-a", "password": reset["temp_password"]}).json()
    assert relogin["must_change_password"] is True and relogin["display_name"] == "Lan (mới)"


# ---------- menu ----------

def test_menu_is_owner_managed_and_staff_read_only(p):
    assert make_product(p).status_code == 201
    assert make_product(p, client="staff").status_code == 403
    assert make_product(p).status_code == 409
    assert make_product(p, "Bia", price=-1).status_code == 422
    assert make_product(p, "Bia", price=10_000_001).status_code == 422
    assert make_product(p, "   ").status_code == 400
    assert make_product(p, "Nước suối", client="owner_b", venue="b").status_code == 201  # trùng tên ở quán khác vẫn được
    menu = p["staff"].get(url(p, "/products")).json()
    assert [m["name"] for m in menu] == ["Nước suối"]
    assert p["owner_b"].get(url(p, "/products")).status_code == 404
    pid = menu[0]["id"]
    assert p["staff"].patch(url(p, f"/products/{pid}"), json={"price": 1}).status_code == 403
    assert p["owner_b"].patch(url(p, f"/products/{pid}", "b"), json={"price": 1}).status_code == 404
    assert p["owner"].patch(url(p, f"/products/{pid}"), json={"price": 12000}).json()["price"] == 12000


# ---------- món trong phiên & tính tiền ----------

def test_items_are_added_merged_priced_by_snapshot_and_charged_at_checkout(p):
    session = open_session(p, rate=60000)
    water = make_product(p, "Nước suối", 10000).json()
    beer = make_product(p, "Bia", 25000).json()
    assert add_item(p, session["id"], water["id"], 2).status_code == 201
    assert add_item(p, session["id"], water["id"], 1).json()["items"][0]["quantity"] == 3  # gộp cùng món cùng giá
    assert add_item(p, session["id"], beer["id"], 2, client="owner").status_code == 201
    p["owner"].patch(url(p, f"/products/{water['id']}"), json={"price": 99000})  # đổi giá sau: dòng cũ giữ giá chốt
    lines = add_item(p, session["id"], water["id"], 1).json()["items"]
    assert sorted((i["name"], i["unit_price"], i["quantity"]) for i in lines) == [("Bia", 25000, 2), ("Nước suối", 10000, 3), ("Nước suối", 99000, 1)]

    p["clock"].advance(minutes=60)
    quote = p["staff"].get(url(p, f"/sessions/{session['id']}/quote")).json()
    items_total = 3 * 10000 + 2 * 25000 + 99000
    assert quote["table_amount"] == 60000 and quote["items_amount"] == items_total and quote["amount_vnd"] == 60000 + items_total
    listing = p["staff"].get(url(p, "/tables")).json()["tables"][0]["session"]
    assert listing["amount_vnd"] == quote["amount_vnd"]

    paid = checkout(p, session["id"]).json()
    assert paid["amount_vnd"] == 60000 + items_total and paid["table_amount"] == 60000 and paid["items_amount"] == items_total
    with Session(p["app"].state.engine) as db:
        assert db.scalar(select(Payment.amount)) == 60000 + items_total
    assert p["staff"].get(url(p, "/revenue/today")).json()["total_vnd"] == 60000 + items_total
    again = checkout(p, session["id"]).json()
    assert again["duplicate"] is True and again["amount_vnd"] == paid["amount_vnd"]


def test_remove_item_and_limits(p):
    session = open_session(p)
    product = make_product(p).json()
    items = add_item(p, session["id"], product["id"], 5).json()["items"]
    removed = p["staff"].delete(url(p, f"/sessions/{session['id']}/items/{items[0]['id']}")).json()
    assert removed["items"] == []
    assert p["staff"].delete(url(p, f"/sessions/{session['id']}/items/{items[0]['id']}")).status_code == 404
    assert add_item(p, session["id"], product["id"], 0).status_code == 422
    assert add_item(p, session["id"], product["id"], 100).status_code == 422
    assert add_item(p, session["id"], product["id"], 99).status_code == 201
    assert add_item(p, session["id"], product["id"], 1).status_code == 400  # vượt 99
    assert add_item(p, session["id"], 99999, 1).status_code == 400


def test_items_need_an_active_menu_product_of_the_same_venue_and_an_open_session(p):
    session = open_session(p)
    product = make_product(p).json()
    foreign = make_product(p, "Của quán B", client="owner_b", venue="b").json()
    assert add_item(p, session["id"], foreign["id"]).status_code == 400
    p["owner"].patch(url(p, f"/products/{product['id']}"), json={"status": "INACTIVE"})
    assert add_item(p, session["id"], product["id"]).status_code == 400
    p["owner"].patch(url(p, f"/products/{product['id']}"), json={"status": "ACTIVE"})
    line = add_item(p, session["id"], product["id"]).json()["items"][0]
    # Quán B không đụng được vào phiên của quán A.
    assert p["owner_b"].post(url(p, f"/sessions/{session['id']}/items", "b"), json={"product_id": foreign["id"]}).status_code == 404
    assert p["owner_b"].delete(url(p, f"/sessions/{session['id']}/items/{line['id']}", "b")).status_code == 404
    checkout(p, session["id"])
    assert add_item(p, session["id"], product["id"]).status_code == 409
    assert p["staff"].delete(url(p, f"/sessions/{session['id']}/items/{line['id']}")).status_code == 409


def test_void_zeroes_everything_including_items(p):
    session = open_session(p)
    product = make_product(p).json()
    add_item(p, session["id"], product["id"], 3)
    voided = p["owner"].post(url(p, f"/sessions/{session['id']}/void"), json={"reason": "mở nhầm bàn"}).json()
    assert voided["amount_vnd"] == 0 and voided["table_amount"] == 0 and voided["items_amount"] == 0
    assert p["staff"].get(url(p, "/revenue/today")).json()["total_vnd"] == 0


def test_checkout_racing_with_add_item_never_loses_or_double_counts_an_item(p):
    for round_ in range(5):
        p["clock"].advance(minutes=1)
        table = p["owner"].post(url(p, "/tables"), json={"name": f"Bàn r{round_}", "hourly_rate": 60000}).json()
        session = p["staff"].post(url(p, f"/tables/{table['id']}/open"), json={}).json()
        product = p["owner"].post(url(p, "/products"), json={"name": f"Món r{round_}", "price": 5000}).json()
        with ThreadPoolExecutor(2) as pool:
            add = pool.submit(add_item, p, session["id"], product["id"], 1)
            pay = pool.submit(checkout, p, session["id"])
            add_status, pay_status = add.result().status_code, pay.result().status_code
        assert pay_status == 200 and add_status in (201, 409)
        with Session(p["app"].state.engine) as db:
            row = db.get(PlaySession, session["id"])
            items = db.scalar(select(func.coalesce(func.sum(SessionItem.unit_price * SessionItem.quantity), 0))
                              .where(SessionItem.session_id == session["id"]))
            payment = db.scalar(select(Payment.amount).where(Payment.session_id == session["id"]))
        assert row.items_amount == items and row.total_amount == row.table_amount + items == payment


# ---------- hoá đơn ----------

def test_invoice_contents_and_access(p):
    session = open_session(p, rate=60000)
    product = make_product(p, "Phấn", 5000).json()
    add_item(p, session["id"], product["id"], 2)
    assert p["staff"].get(url(p, f"/sessions/{session['id']}/invoice")).status_code == 409  # chưa thanh toán
    p["clock"].advance(minutes=30)
    checkout(p, session["id"])
    invoice = p["staff"].get(url(p, f"/sessions/{session['id']}/invoice")).json()
    assert invoice["venue_name"] == "Quán A" and invoice["table_name"] == "Bàn 1" and invoice["billable_minutes"] == 30
    assert invoice["table_amount"] == 30000 and invoice["items_amount"] == 10000 and invoice["total"] == 40000
    assert invoice["items"][0]["name"] == "Phấn" and invoice["items"][0]["amount"] == 10000
    assert invoice["payment_method"] == "cash" and invoice["cashier"] == "staff-a" and invoice["customer"] is None
    assert len(invoice["invoice_no"]) == 8
    assert p["owner_b"].get(url(p, f"/sessions/{session['id']}/invoice", "b")).status_code == 404
    assert p["owner_b"].get(url(p, "/sessions/x/invoice", "a")).status_code == 404


# ---------- khách ----------

def test_phone_normalization():
    assert normalize_phone("+84 912 345 678") == "0912345678"
    assert normalize_phone("0912.345.678") == "0912345678"
    assert normalize_phone("84912345678") == "0912345678"
    assert normalize_phone("12345") == "12345"


def test_create_customer_who_can_log_in_through_the_venue_page(p):
    created = p["staff"].post(url(p, "/customers"), json={"display_name": "Anh Nam", "phone": "+84 912 345 678"})
    assert created.status_code == 201
    body = created.json()
    assert body["customer"]["login"] == "0912345678"
    assert p["staff"].post(url(p, "/customers"), json={"display_name": "Trùng", "phone": "0912345678"}).status_code == 409
    assert p["staff"].post(url(p, "/customers"), json={"display_name": "Sai", "phone": "123"}).status_code == 400
    assert p["owner_b"].post(url(p, "/customers", "b"), json={"display_name": "Nam (B)", "phone": "0912345678"}).status_code == 201
    login_response = TestClient(p["app"], base_url="http://127.0.0.1").post(
        "/api/auth/login", json={"login": "0912345678", "password": body["temp_password"], "venue_slug": "quan-a"})
    assert login_response.status_code == 200 and login_response.json()["role"] == "customer"
    assert body["temp_password"] == "1234567890"  # mật khẩu gốc của khách quầy tạo
    assert login_response.json()["must_change_password"] is True  # phải đổi ngay lần đăng nhập đầu


def test_customer_list_search_and_isolation(p):
    for name, phone in [("Nguyễn Văn Ánh", "0901111111"), ("Trần Thị Bình", "0902222222")]:
        p["staff"].post(url(p, "/customers"), json={"display_name": name, "phone": phone})
    p["owner_b"].post(url(p, "/customers", "b"), json={"display_name": "Khách quán B", "phone": "0903333333"})
    listed = p["staff"].get(url(p, "/customers")).json()
    assert listed["total"] == 2
    assert p["staff"].get(url(p, "/customers?q=anh")).json()["total"] == 1
    assert p["staff"].get(url(p, "/customers?q=0902")).json()["total"] == 1
    assert p["owner_b"].get(url(p, "/customers", "a")).status_code == 404
    assert p["owner_b"].get(url(p, "/customers", "b")).json()["total"] == 1


def test_only_owner_locks_customers_and_it_blocks_login(p):
    created = p["staff"].post(url(p, "/customers"), json={"display_name": "Khách", "phone": "0904444444"}).json()
    cid = created["customer"]["id"]
    path = url(p, f"/customers/{cid}/status")
    assert p["staff"].patch(path, json={"status": "DISABLED"}).status_code == 403
    assert p["owner_b"].patch(url(p, f"/customers/{cid}/status", "b"), json={"status": "DISABLED"}).status_code == 404
    assert p["owner"].patch(path, json={"status": "DISABLED"}).json()["status"] == "DISABLED"
    blocked = TestClient(p["app"], base_url="http://127.0.0.1").post(
        "/api/auth/login", json={"login": "0904444444", "password": created["temp_password"], "venue_slug": "quan-a"})
    assert blocked.status_code == 401
    staff_id = next(u["id"] for u in p["owner"].get(url(p, "/staff")).json())
    assert p["owner"].patch(url(p, f"/customers/{staff_id}/status"), json={"status": "DISABLED"}).status_code == 404  # không khoá nhân viên qua cổng khách


def test_attach_customer_to_a_running_session(p):
    session = open_session(p)
    mine = p["staff"].post(url(p, "/customers"), json={"display_name": "Khách A", "phone": "0905555555"}).json()["customer"]["id"]
    theirs = p["owner_b"].post(url(p, "/customers", "b"), json={"display_name": "Khách B", "phone": "0906666666"}).json()["customer"]["id"]
    path = url(p, f"/sessions/{session['id']}/customer")
    assert p["staff"].patch(path, json={"customer_id": theirs}).status_code == 400
    assert p["staff"].patch(path, json={"customer_id": mine}).json() == {"customer_id": mine}
    assert p["staff"].patch(path, json={"customer_id": None}).json() == {"customer_id": None}
    p["staff"].patch(path, json={"customer_id": mine})
    p["clock"].advance(minutes=10)
    checkout(p, session["id"])
    assert p["staff"].patch(path, json={"customer_id": None}).status_code == 409
    invoice = p["staff"].get(url(p, f"/sessions/{session['id']}/invoice")).json()
    assert invoice["customer"] == "Khách A"


def test_owner_can_backdate_session_start_but_staff_cannot_and_limits_apply(p):
    session = open_session(p)
    path = url(p, f"/sessions/{session['id']}/start")
    earlier = (START - timedelta(minutes=45)).isoformat()
    assert p["staff"].patch(path, json={"started_at": earlier}).status_code == 403
    assert p["owner_b"].patch(path.replace(str(p["a"]), str(p["b"])), json={"started_at": earlier}).status_code in (403, 404)
    assert p["owner"].patch(path, json={"started_at": (START + timedelta(minutes=1)).isoformat()}).status_code == 400
    assert p["owner"].patch(path, json={"started_at": (START - timedelta(hours=25)).isoformat()}).status_code == 400
    response = p["owner"].patch(path, json={"started_at": earlier})
    assert response.status_code == 200, response.text
    assert response.json()["elapsed_seconds"] == 45 * 60
    assert response.json()["started_at"].startswith("2026-11-22T02:15:00")
    with Session(p["app"].state.engine) as db:
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "session_start_changed")) == 1
    assert checkout(p, session["id"]).json()["billable_minutes"] == 45
    assert p["owner"].patch(path, json={"started_at": earlier}).status_code == 409  # đã thanh toán


def test_owner_resets_customer_password_to_default_and_forces_change(p):
    made = p["staff"].post(url(p, "/customers"), json={"display_name": "Anh Nam", "phone": "0912345678"}).json()["customer"]
    guest = TestClient(p["app"], base_url="http://127.0.0.1")
    login = lambda pw: guest.post("/api/auth/login", json={"login": "0912345678", "password": pw, "venue_slug": "quan-a"})
    first = login("1234567890").json()
    guest.headers["X-CSRF-Token"] = first["csrf_token"]
    assert guest.post("/api/auth/change-password", json={"current_password": "1234567890", "new_password": "Mat-Khau-Moi-2026"}).status_code == 200
    assert login("1234567890").status_code == 401
    path = url(p, f"/customers/{made['id']}/reset-password")
    assert p["staff"].post(path).status_code == 403
    assert p["owner_b"].post(path.replace(f"/venues/{p['a']}/", f"/venues/{p['b']}/")).status_code == 404
    reset = p["owner"].post(path)
    assert reset.status_code == 200 and reset.json()["temp_password"] == "1234567890"
    after = login("1234567890")
    assert after.status_code == 200 and after.json()["must_change_password"] is True
    assert login("Mat-Khau-Moi-2026").status_code == 401


def test_counter_can_choose_the_initial_customer_password(p):
    ok = p["staff"].post(url(p, "/customers"), json={"display_name": "A", "phone": "0911111111", "password": "Mat-Khau-Tam-1"})
    assert ok.status_code == 201 and ok.json()["temp_password"] == "Mat-Khau-Tam-1"
    guest = TestClient(p["app"], base_url="http://127.0.0.1")
    first = guest.post("/api/auth/login", json={"login": "0911111111", "password": "Mat-Khau-Tam-1", "venue_slug": "quan-a"}).json()
    assert first["must_change_password"] is True
    assert p["staff"].post(url(p, "/customers"), json={"display_name": "B", "phone": "0922222222", "password": "abc"}).status_code == 400
    blank = p["staff"].post(url(p, "/customers"), json={"display_name": "C", "phone": "0933333333", "password": ""})
    assert blank.json()["temp_password"] == "1234567890"
