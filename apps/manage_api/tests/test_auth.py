from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.manage_api.auth import COOKIE, LOCK_MINUTES, MAX_FAILED, SESSION_HOURS
from apps.manage_api.config import ManageSettings
from apps.manage_api.main import create_app
from apps.manage_api.models import AuditLog, AuthSession, User, Venue
from apps.manage_api.security import hash_password, password_problem, verify_password
from scripts.manage_create_admin import create_admin

PASSWORD = "Billiard-2026!"
NOW = datetime(2026, 11, 22, 3, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


@pytest.fixture
def env(tmp_path):
    clock = Clock()
    settings = ManageSettings(database_url=f"sqlite:///{tmp_path / 'manage.db'}")
    app = create_app(settings, clock)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        engine = app.state.engine
        naive = NOW.replace(tzinfo=None)
        with Session(engine) as db:
            a = Venue(name="Quán A", slug="quan-a", created_at=naive)
            b = Venue(name="Quán B", slug="quan-b", created_at=naive)
            db.add_all([a, b])
            db.flush()

            def user(role, login, venue=None, **extra):
                db.add(User(role=role, login=login, display_name=login, password_hash=hash_password(PASSWORD),
                            venue_id=venue.id if venue else None, created_at=naive, **extra))

            user("platform_admin", "admin")
            user("owner", "owner-a", a)
            user("staff", "staff-a", a)
            user("owner", "owner-b", b)
            user("customer", "0901234567", a)
            user("customer", "0901234567", b)
            db.commit()
            ids = {"a": a.id, "b": b.id}
        yield client, app, clock, ids


def login(client, name, password=PASSWORD, slug=None):
    body = {"login": name, "password": password}
    if slug:
        body["venue_slug"] = slug
    return client.post("/api/auth/login", json=body)


def csrf_headers(response):
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def fresh_client(app):
    return TestClient(app, base_url="http://127.0.0.1")


def test_login_sets_httponly_cookie_and_hides_password_hash(env):
    client, _, _, _ = env
    response = login(client, "owner-a")
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "owner" and body["venue"]["slug"] == "quan-a"
    assert not {"password", "password_hash", "token_hash"} & set(body)
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/api/auth/me").json()["login"] == "owner-a"


def test_token_is_stored_only_as_hash(env):
    client, app, _, _ = env
    login(client, "owner-a")
    raw = client.cookies.get(COOKIE)
    with Session(app.state.engine) as db:
        stored = db.scalars(select(AuthSession.token_hash)).all()
    assert raw and raw not in stored and len(stored[0]) == 64


def test_failures_are_generic_and_do_not_reveal_accounts(env):
    client, _, _, _ = env
    unknown = login(client, "nobody")
    wrong = login(client, "owner-a", "sai-mat-khau-1")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_lockout_blocks_even_the_correct_password_then_expires(env):
    client, _, clock, _ = env
    for _ in range(MAX_FAILED):
        assert login(client, "staff-a", "sai-mat-khau-1").status_code == 401
    assert login(client, "staff-a").status_code == 423
    clock.advance(minutes=LOCK_MINUTES + 1)
    assert login(client, "staff-a").status_code == 200


def test_write_requests_need_csrf_token(env):
    client, _, _, _ = env
    response = login(client, "owner-a")
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.post("/api/auth/logout", headers=csrf_headers(response)).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_session_expires_on_server_side(env):
    client, _, clock, _ = env
    login(client, "owner-a")
    clock.advance(hours=SESSION_HOURS, minutes=1)
    assert client.get("/api/auth/me").status_code == 401


def test_admin_endpoints_are_role_gated(env):
    client, app, _, _ = env
    assert client.get("/api/admin/audit").status_code == 401
    for name in ("owner-a", "staff-a"):
        other = fresh_client(app)
        login(other, name)
        assert other.get("/api/admin/audit").status_code == 403
    login(client, "admin")
    rows = client.get("/api/admin/audit").json()
    assert any(row["action"] == "login_ok" for row in rows)


def test_tenant_isolation_between_venues(env):
    client, app, _, ids = env
    login(client, "owner-a")
    assert client.get(f"/api/venues/{ids['a']}").json()["slug"] == "quan-a"
    # Quán khác: 404 (không lộ sự tồn tại), không phải dữ liệu.
    assert client.get(f"/api/venues/{ids['b']}").status_code == 404
    assert client.get("/api/venues/9999").status_code == 404

    customer = fresh_client(app)
    login(customer, "0901234567", slug="quan-a")
    assert customer.get(f"/api/venues/{ids['a']}").status_code == 200
    assert customer.get(f"/api/venues/{ids['b']}").status_code == 404

    admin = fresh_client(app)
    login(admin, "admin")
    assert admin.get(f"/api/venues/{ids['a']}").status_code == 200
    assert admin.get(f"/api/venues/{ids['b']}").status_code == 200


def test_customer_and_staff_login_paths_are_separate(env):
    client, _, _, _ = env
    assert login(client, "0901234567").status_code == 401  # khách không đăng nhập qua cổng nhân sự
    assert login(client, "owner-a", slug="quan-a").status_code == 401  # nhân sự không đăng nhập qua cổng khách
    assert login(client, "0901234567", slug="quan-a").json()["venue"]["slug"] == "quan-a"
    assert login(client, "0901234567", slug="quan-b").json()["venue"]["slug"] == "quan-b"
    assert login(client, "0901234567", slug="khong-co").status_code == 401


def test_same_customer_login_is_independent_per_venue_in_database(env):
    _, app, _, ids = env
    naive = NOW.replace(tzinfo=None)
    with Session(app.state.engine) as db:
        db.add(User(role="staff", login="owner-a", display_name="x", password_hash="x", venue_id=ids["b"], created_at=naive))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(User(role="customer", login="0901234567", display_name="x", password_hash="x", venue_id=ids["a"], created_at=naive))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(User(role="platform_admin", login="bad", display_name="x", password_hash="x", venue_id=ids["a"], created_at=naive))
        with pytest.raises(IntegrityError):
            db.commit()


def test_disabled_user_and_suspended_venue_lose_access_immediately(env):
    client, app, _, ids = env
    login(client, "staff-a")
    with Session(app.state.engine) as db:
        db.scalar(select(User).where(User.login == "staff-a")).status = "DISABLED"
        db.commit()
    assert client.get("/api/auth/me").status_code == 401
    assert login(client, "staff-a").status_code == 401

    owner = fresh_client(app)
    login(owner, "owner-b")
    with Session(app.state.engine) as db:
        db.get(Venue, ids["b"]).status = "SUSPENDED"
        db.commit()
    assert owner.get("/api/auth/me").status_code == 401
    assert login(fresh_client(app), "owner-b").status_code == 401


def test_forced_password_change_flow_and_other_sessions_revoked(env):
    client, app, _, ids = env
    with Session(app.state.engine) as db:
        db.scalar(select(User).where(User.login == "owner-a")).must_change_password = True
        db.commit()
    first = login(client, "owner-a")
    assert first.json()["must_change_password"] is True
    assert client.get("/api/auth/me").status_code == 200
    assert client.get(f"/api/venues/{ids['a']}").status_code == 403  # chặn tới khi đổi mật khẩu

    second = fresh_client(app)
    login(second, "owner-a")
    headers = csrf_headers(first)
    change = lambda current, new: client.post("/api/auth/change-password", headers=headers,
                                              json={"current_password": current, "new_password": new})
    assert change("sai-mat-khau", "Mat-khau-moi-2026").status_code == 400
    assert change(PASSWORD, "12345678901").status_code == 400  # toàn số
    assert change(PASSWORD, "short1").status_code == 400
    assert change(PASSWORD, PASSWORD).status_code == 400
    assert change(PASSWORD, "Mat-khau-moi-2026").status_code == 200
    assert client.get(f"/api/venues/{ids['a']}").status_code == 200
    assert second.get("/api/auth/me").status_code == 401  # thiết bị khác bị đăng xuất
    assert login(fresh_client(app), "owner-a", "Mat-khau-moi-2026").status_code == 200


def test_audit_trail_never_contains_secrets(env):
    client, app, _, _ = env
    login(client, "owner-a", "Sai-mat-khau-bi-mat-1")
    login(client, "owner-a")
    with Session(app.state.engine) as db:
        rows = db.scalars(select(AuditLog)).all()
    actions = [row.action for row in rows]
    assert "login_failed" in actions and "login_ok" in actions
    blob = str([(row.action, row.target, row.detail) for row in rows])
    assert "Sai-mat-khau-bi-mat-1" not in blob and PASSWORD not in blob


def test_login_requests_from_foreign_origin_are_rejected(env):
    client, _, _, _ = env
    response = client.post("/api/auth/login", json={"login": "admin", "password": PASSWORD},
                           headers={"origin": "http://evil.example"})
    assert response.status_code == 403


def test_password_hashing_properties():
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first != second and PASSWORD not in first
    assert verify_password(PASSWORD, first) and not verify_password("khac", first)
    assert not verify_password(PASSWORD, "not-a-hash") and not verify_password(PASSWORD, "md5$1$2$3$4$5")
    assert password_problem("abc") and password_problem("0000000000") and password_problem(PASSWORD) is None


def test_create_admin_script(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    assert create_admin(url, " Admin@Example.com ", "Quản trị", PASSWORD) == 1
    with pytest.raises(ValueError):
        create_admin(url, "admin@example.com", "Trùng", PASSWORD)
    with pytest.raises(ValueError):
        create_admin(url, "khac", "Yếu", "123")
