from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.manage_api.admin import slugify, temp_password
from apps.manage_api.config import ManageSettings
from apps.manage_api.main import create_app
from apps.manage_api.models import AuditLog, User, Venue
from apps.manage_api.security import hash_password, password_problem

PASSWORD = "Billiard-2026!"
NOW = datetime(2026, 11, 22, 3, 0, tzinfo=timezone.utc)


@pytest.fixture
def env(tmp_path):
    app = create_app(ManageSettings(database_url=f"sqlite:///{tmp_path / 'm.db'}"), lambda: NOW)
    with TestClient(app, base_url="http://127.0.0.1") as admin:
        with Session(app.state.engine) as db:
            db.add(User(role="platform_admin", login="admin", display_name="Admin", password_hash=hash_password(PASSWORD),
                        created_at=NOW.replace(tzinfo=None)))
            db.commit()
        response = admin.post("/api/auth/login", json={"login": "admin", "password": PASSWORD})
        admin.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        yield admin, app


def new_client(app):
    return TestClient(app, base_url="http://127.0.0.1")


def sign_in(client, login, password, slug=None):
    response = client.post("/api/auth/login", json={"login": login, "password": password, "venue_slug": slug})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response


def create_venue(admin, name="Bi-a Đại Nam", owner="chu-dai-nam", slug=None):
    body = {"name": name, "owner": {"login": owner, "display_name": "Chủ Đại Nam"}}
    if slug:
        body["slug"] = slug
    return admin.post("/api/admin/venues", json=body)


def add_customer(app, venue_id, login, name="Khách"):
    with Session(app.state.engine) as db:
        db.add(User(role="customer", login=login, display_name=name, password_hash=hash_password(PASSWORD),
                    venue_id=venue_id, created_at=NOW.replace(tzinfo=None)))
        db.commit()


def test_every_admin_endpoint_rejects_non_admins(env):
    admin, app = env
    venue = create_venue(admin).json()
    owner = new_client(app)
    sign_in(owner, "chu-dai-nam", venue["owner_temp_password"])  # đang buộc đổi mật khẩu: vẫn không có quyền admin
    anonymous = new_client(app)
    vid = venue["venue"]["id"]
    calls = [("get", "/api/admin/overview"), ("get", "/api/admin/venues"), ("get", f"/api/admin/venues/{vid}"),
             ("patch", f"/api/admin/venues/{vid}"), ("post", f"/api/admin/venues/{vid}/owner/reset-password"),
             ("get", f"/api/admin/venues/{vid}/customers"), ("patch", "/api/admin/users/2/status")]
    for method, path in calls:
        kwargs = {"json": {"status": "ACTIVE"}} if method == "patch" else {}
        assert getattr(anonymous, method)(path, **kwargs).status_code == 401, path
        assert getattr(owner, method)(path, **kwargs).status_code == 403, path
    assert anonymous.post("/api/admin/venues", json={}).status_code == 401


def test_admin_writes_need_csrf(env):
    admin, _ = env
    body = {"name": "Quán X", "owner": {"login": "chu-x", "display_name": "X"}}
    assert admin.post("/api/admin/venues", json=body, headers={"X-CSRF-Token": "sai"}).status_code == 403


def test_create_venue_issues_one_time_temp_password_and_forces_change(env):
    admin, app = env
    response = create_venue(admin)
    assert response.status_code == 201
    body = response.json()
    assert body["venue"]["slug"] == "bi-a-dai-nam" and body["venue"]["counts"]["owners"] == 1
    temp = body["owner_temp_password"]
    assert password_problem(temp) is None
    # Mật khẩu tạm chỉ xuất hiện đúng một lần.
    vid = body["venue"]["id"]
    assert temp not in admin.get(f"/api/admin/venues/{vid}").text
    assert temp not in admin.get("/api/admin/venues").text
    assert temp not in admin.get("/api/admin/audit").text
    owner = new_client(app)
    assert sign_in(owner, "chu-dai-nam", temp).json()["must_change_password"] is True
    assert owner.get(f"/api/venues/{vid}").status_code == 403


def test_create_venue_validation_and_duplicates(env):
    admin, _ = env
    assert create_venue(admin).status_code == 201
    assert create_venue(admin, owner="chu-khac").status_code == 409  # trùng slug từ cùng tên
    assert create_venue(admin, name="Quán khác", owner="chu-dai-nam").status_code == 409  # trùng tên đăng nhập
    assert create_venue(admin, name="Quán Y", owner="chu-y", slug="Bad Slug!").status_code == 400
    assert create_venue(admin, name="Quán Y", owner="chu-y", slug="ab").status_code == 400
    assert create_venue(admin, name="Quán Y", owner="chu-y", slug="admin").status_code == 400
    assert admin.post("/api/admin/venues", json={"name": "Q", "owner": {"login": "x", "display_name": ""}}).status_code == 422
    assert create_venue(admin, name="Quán Y", owner="chu-y", slug="quan-y").status_code == 201


def test_list_search_and_pagination(env):
    admin, _ = env
    for i in range(3):
        create_venue(admin, name=f"Quán số {i}", owner=f"chu-{i}")
    page = admin.get("/api/admin/venues?limit=2").json()
    assert page["total"] == 3 and len(page["items"]) == 2
    assert admin.get("/api/admin/venues?q=SỐ 1").json()["total"] == 1  # không phân biệt hoa/thường, có/không dấu
    assert admin.get("/api/admin/venues?q=quan so 1").json()["total"] == 1
    assert admin.get("/api/admin/venues?q=khong-ton-tai").json()["total"] == 0
    assert admin.get("/api/admin/venues?limit=2&offset=2").json()["items"][0]["slug"] == "quan-so-0"


def test_suspending_a_venue_cuts_access_and_reactivating_restores_it(env):
    admin, app = env
    created = create_venue(admin).json()
    vid, temp = created["venue"]["id"], created["owner_temp_password"]
    owner = new_client(app)
    sign_in(owner, "chu-dai-nam", temp)
    assert admin.patch(f"/api/admin/venues/{vid}", json={"status": "SUSPENDED"}).json()["status"] == "SUSPENDED"
    assert owner.get("/api/auth/me").status_code == 401
    assert new_client(app).post("/api/auth/login", json={"login": "chu-dai-nam", "password": temp}).status_code == 401
    admin.patch(f"/api/admin/venues/{vid}", json={"status": "ACTIVE", "name": "Bi-a Đại Nam 2"})
    assert sign_in(new_client(app), "chu-dai-nam", temp).json()["venue"]["name"] == "Bi-a Đại Nam 2"
    assert admin.patch("/api/admin/venues/999", json={"status": "ACTIVE"}).status_code == 404
    assert admin.patch(f"/api/admin/venues/{vid}", json={"status": "DELETED"}).status_code == 422


def test_reset_owner_password(env):
    admin, app = env
    created = create_venue(admin).json()
    vid, old = created["venue"]["id"], created["owner_temp_password"]
    owner = new_client(app)
    sign_in(owner, "chu-dai-nam", old)
    reset = admin.post(f"/api/admin/venues/{vid}/owner/reset-password").json()
    assert reset["owner_login"] == "chu-dai-nam" and reset["owner_temp_password"] != old
    assert owner.get("/api/auth/me").status_code == 401
    assert new_client(app).post("/api/auth/login", json={"login": "chu-dai-nam", "password": old}).status_code == 401
    assert sign_in(new_client(app), "chu-dai-nam", reset["owner_temp_password"]).json()["must_change_password"] is True
    assert admin.post("/api/admin/venues/999/owner/reset-password").status_code == 404


def test_customers_are_listed_per_venue_and_can_be_disabled(env):
    admin, app = env
    a = create_venue(admin, "Quán A", "chu-a").json()["venue"]["id"]
    b = create_venue(admin, "Quán B", "chu-b").json()["venue"]["id"]
    add_customer(app, a, "0901111111", "An")
    add_customer(app, a, "0902222222", "Bình")
    add_customer(app, b, "0901111111", "An (quán B)")
    listed = admin.get(f"/api/admin/venues/{a}/customers").json()
    assert listed["total"] == 2 and {c["login"] for c in listed["items"]} == {"0901111111", "0902222222"}
    assert "password" not in str(listed).lower()
    assert admin.get(f"/api/admin/venues/{a}/customers?q=BINH").json()["total"] == 1
    assert admin.get(f"/api/admin/venues/{b}/customers").json()["items"][0]["display_name"] == "An (quán B)"

    customer = new_client(app)
    sign_in(customer, "0901111111", PASSWORD, slug="quan-a")
    target = next(c["id"] for c in listed["items"] if c["login"] == "0901111111")
    assert admin.patch(f"/api/admin/users/{target}/status", json={"status": "DISABLED"}).json()["status"] == "DISABLED"
    assert customer.get("/api/auth/me").status_code == 401
    assert new_client(app).post("/api/auth/login", json={"login": "0901111111", "password": PASSWORD, "venue_slug": "quan-a"}).status_code == 401
    assert sign_in(new_client(app), "0901111111", PASSWORD, slug="quan-b")  # tài khoản cùng SĐT ở quán B không ảnh hưởng
    admin.patch(f"/api/admin/users/{target}/status", json={"status": "ACTIVE"})
    assert sign_in(new_client(app), "0901111111", PASSWORD, slug="quan-a")


def test_admin_account_cannot_be_disabled_through_the_api(env):
    admin, app = env
    with Session(app.state.engine) as db:
        admin_id = db.scalar(select(User.id).where(User.role == "platform_admin"))
    assert admin.patch(f"/api/admin/users/{admin_id}/status", json={"status": "DISABLED"}).status_code == 404
    assert admin.patch("/api/admin/users/9999/status", json={"status": "DISABLED"}).status_code == 404


def test_overview_counts_and_audit_trail(env):
    admin, app = env
    vid = create_venue(admin).json()["venue"]["id"]
    add_customer(app, vid, "0903333333")
    admin.patch(f"/api/admin/venues/{vid}", json={"status": "SUSPENDED"})
    overview = admin.get("/api/admin/overview").json()
    assert overview["venues"] == {"active": 0, "suspended": 1}
    assert overview["users"] == {"owner": 1, "staff": 0, "customer": 1}
    with Session(app.state.engine) as db:
        actions = [row.action for row in db.scalars(select(AuditLog).order_by(AuditLog.id))]
    assert "venue_created" in actions and "venue_updated" in actions


def test_slug_and_temp_password_helpers():
    assert slugify("Bi-a Đại Nam") == "bi-a-dai-nam"
    assert slugify("  Quán  Số 1!! ") == "quan-so-1"
    assert slugify("!!!") == ""
    assert len({temp_password() for _ in range(50)}) == 50
    assert all(password_problem(temp_password()) is None for _ in range(50))
    assert not set(temp_password()) & set("0OIl1")


def test_audit_filters_by_action_venue_text_and_vietnam_day(env):
    admin, app = env
    vid = create_venue(admin).json()["venue"]["id"]
    admin.patch(f"/api/admin/venues/{vid}", json={"status": "SUSPENDED"})
    everything = admin.get("/api/admin/audit?limit=500").json()
    created = admin.get("/api/admin/audit?action=venue_created").json()
    assert created and all(r["action"] == "venue_created" for r in created) and len(created) < len(everything)
    assert all(r["venue_id"] == vid and r["venue_name"] for r in admin.get(f"/api/admin/audit?venue_id={vid}").json())
    assert admin.get("/api/admin/audit?venue_id=99999").json() == []
    target = created[0]["target"]
    assert [r["id"] for r in admin.get(f"/api/admin/audit?q={target[:4].upper()}").json()] != []
    assert admin.get("/api/admin/audit?q=khong-co-chuoi-nay-dau").json() == []
    day = everything[0]["at"][:10]
    assert admin.get(f"/api/admin/audit?date_from={day}&date_to={day}").status_code == 200
    assert admin.get("/api/admin/audit?date_from=2000-01-01&date_to=2000-01-02").json() == []
    assert admin.get("/api/admin/audit?date_from=bad").status_code == 400
