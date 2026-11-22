from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.manage_api import game_api
from apps.manage_api.config import ManageSettings
from apps.manage_api.main import create_app
from apps.manage_api.models import (AuditLog, Checkin, CustomerGame, PointLedger, SpinResult, SpinTicket, User, Venue, Voucher,
                                    WheelDailyPlan, WheelPrize)
from apps.manage_api.netutil import client_ip, ip_in_networks, normalize_cidr
from apps.manage_api.security import hash_password

PASSWORD = "Billiard-2026!"
CUSTOMER_PASSWORD = "Khach-Hang-2026"
WIFI_IP = "203.0.113.7"
OUTSIDE_IP = "198.51.100.9"
START = datetime(2026, 11, 22, 3, 0, tzinfo=timezone.utc)  # 10:00 giờ Việt Nam


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


def web(app, ip="127.0.0.1", headers=None):
    return TestClient(app, base_url="http://127.0.0.1", client=(ip, 50000), headers=headers or {})


def sign_in(app, login, password=PASSWORD, slug=None, ip="127.0.0.1"):
    c = web(app, ip)
    response = c.post("/api/auth/login", json={"login": login, "password": password, "venue_slug": slug})
    assert response.status_code == 200, response.text
    c.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return c


def register(app, slug, phone, ip=WIFI_IP):
    c = web(app, ip)
    response = c.post("/api/auth/register", json={"venue_slug": slug, "display_name": f"Khách {phone[-4:]}", "phone": phone, "password": CUSTOMER_PASSWORD})
    assert response.status_code == 201, response.text
    c.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return c


SETTINGS = {"checkin_mode": "wifi", "checkin_points": 10, "streak_milestones": [{"days": 3, "bonus": 20}, {"days": 7, "bonus": 50}],
            "wheel_enabled": True, "min_daily_prizes": 1, "max_daily_prizes": 2, "expected_daily_checkins": 20, "spin_expiry_days": 1,
            "code_rotation_seconds": 300}
WHEEL = [
    {"name": "+20 điểm", "kind": "points", "value": 20, "weight_bp": 4000},
    {"name": "Giảm 10.000₫", "kind": "discount_vnd", "value": 10000, "weight_bp": 1000, "stock": 5},
    {"name": "Chúc may mắn", "kind": "nothing", "weight_bp": 5000},
]


@pytest.fixture
def p(tmp_path):
    clock = Clock()
    app = create_app(ManageSettings(database_url=f"sqlite:///{tmp_path / 'm.db'}", trusted_proxies=("10.0.0.0/8",)), clock)
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
        assert env["owner"].put(f"/api/venues/{ids[0]}/game-settings", json=SETTINGS).status_code == 200
        assert env["owner"].put(f"/api/venues/{ids[0]}/networks", json={"networks": [{"cidr": "203.0.113.0/24", "label": "Wifi quán"}]}).status_code == 200
        assert env["owner"].put(f"/api/venues/{ids[0]}/wheel", json={"prizes": WHEEL}).status_code == 200
        env["cust"] = register(app, "quan-a", "0901111111")
        yield env


def v(p, path, venue="a"):
    return f"/api/venues/{p[venue]}{path}"


def configure(p, **changes):
    assert p["owner"].put(v(p, "/game-settings"), json={**SETTINGS, **changes}).status_code == 200


def set_wheel(p, prizes):
    response = p["owner"].put(v(p, "/wheel"), json={"prizes": prizes})
    assert response.status_code == 200, response.text
    return response.json()


def relogin(p, phone="0901111111", ip=WIFI_IP):
    return sign_in(p["app"], phone, CUSTOMER_PASSWORD, "quan-a", ip)


def relogin_staff(p):
    """Phiên đăng nhập hết hạn sau 12 giờ: đăng nhập lại khi test nhảy qua nhiều ngày."""
    p["owner"], p["staff"], p["owner_b"] = sign_in(p["app"], "owner-a"), sign_in(p["app"], "staff-a"), sign_in(p["app"], "owner-b")


def checkin(client, p, code=None):
    return client.post(v(p, "/my/checkin"), json={"code": code})


def spin(client, p, ticket_id):
    return client.post(v(p, f"/my/spins/{ticket_id}/spin"))


def checked_in_ticket(client, p):
    response = checkin(client, p)
    assert response.status_code == 200, response.text
    return response.json()["ticket_id"]


# ---------- tiện ích mạng ----------

def test_network_helpers():
    assert ip_in_networks("203.0.113.7", ["203.0.113.0/24"]) and not ip_in_networks("198.51.100.1", ["203.0.113.0/24"])
    assert ip_in_networks("::ffff:203.0.113.7", ["203.0.113.0/24"])  # IPv4 map qua IPv6
    assert not ip_in_networks("testclient", ["203.0.113.0/24"]) and not ip_in_networks("203.0.113.7", ["rác"])
    assert normalize_cidr("203.0.113.7") == "203.0.113.7/32" and normalize_cidr(" 203.0.113.9/24 ") == "203.0.113.0/24"
    for bad in ("0.0.0.0/0", "10.0.0.0/8", "abc", "300.1.1.1", "2001:db8::/32"):
        with pytest.raises(ValueError):
            normalize_cidr(bad)


def test_client_ip_trusts_forwarded_header_only_from_trusted_proxies():
    trusted = ["10.0.0.0/8"]
    assert client_ip("198.51.100.9", "203.0.113.7", trusted) == "198.51.100.9"  # không phải proxy: header là giả
    assert client_ip("10.0.0.5", "203.0.113.7", trusted) == "203.0.113.7"
    assert client_ip("10.0.0.5", "1.2.3.4, 203.0.113.7", trusted) == "203.0.113.7"  # lấy IP ngoài cùng bên phải không tin cậy
    assert client_ip("10.0.0.5", "203.0.113.7, 10.0.0.9", trusted) == "203.0.113.7"
    assert client_ip("10.0.0.5", "không-phải-ip", trusted) == "10.0.0.5"
    assert client_ip("10.0.0.5", "203.0.113.7", []) == "10.0.0.5"
    assert client_ip(None, None, trusted) == ""


# ---------- cài đặt ----------

def test_settings_are_owner_only_validated_and_audited(p):
    assert p["staff"].get(v(p, "/game-settings")).status_code == 403
    assert p["staff"].put(v(p, "/game-settings"), json=SETTINGS).status_code == 403
    assert p["cust"].get(v(p, "/game-settings")).status_code == 403
    assert p["owner_b"].get(v(p, "/game-settings", "a")).status_code == 404
    put = lambda **kw: p["owner"].put(v(p, "/game-settings"), json={**SETTINGS, **kw})
    assert put(max_daily_prizes=0, min_daily_prizes=1).status_code == 400
    assert put(streak_milestones=[{"days": 3, "bonus": 1}, {"days": 3, "bonus": 2}]).status_code == 400
    for bad in ({"checkin_mode": "bluetooth"}, {"min_daily_prizes": 3}, {"checkin_points": -1}, {"expected_daily_checkins": 0},
                {"spin_expiry_days": 99}, {"code_rotation_seconds": 5}, {"streak_milestones": [{"days": 1, "bonus": 1}]}):
        assert put(**bad).status_code == 422, bad
    assert put(checkin_points=15, streak_milestones=[{"days": 7, "bonus": 70}, {"days": 3, "bonus": 30}]).json()["streak_milestones"] == [
        {"days": 3, "bonus": 30}, {"days": 7, "bonus": 70}]
    other = p["owner_b"].get(v(p, "/game-settings", "b")).json()
    assert other["checkin_points"] == 10 and other["checkin_mode"] == "wifi"  # quán B không bị đổi theo
    with Session(p["app"].state.engine) as db:
        assert "game_settings_changed" in [r.action for r in db.scalars(select(AuditLog))]


def test_networks_validation_and_replacement(p):
    got = p["owner"].get(v(p, "/networks")).json()
    assert got["networks"] == [{"cidr": "203.0.113.0/24", "label": "Wifi quán"}] and got["your_ip"] == "127.0.0.1"
    assert p["staff"].get(v(p, "/networks")).status_code == 403
    put = lambda nets: p["owner"].put(v(p, "/networks"), json={"networks": nets})
    assert put([{"cidr": "0.0.0.0/0"}]).status_code == 400 and put([{"cidr": "xyz"}]).status_code == 400
    assert put([{"cidr": f"192.168.{i}.1"} for i in range(11)]).status_code == 422
    assert put([{"cidr": "198.51.100.5"}, {"cidr": "198.51.100.5/32", "label": "trùng"}]).json()["networks"] == [{"cidr": "198.51.100.5/32", "label": "trùng"}]
    assert p["owner_b"].put(v(p, "/networks", "a"), json={"networks": []}).status_code == 404


# ---------- check-in ----------

def test_wifi_checkin_awards_points_once_and_rejects_outsiders(p):
    outsider = relogin(p, ip=OUTSIDE_IP)
    assert checkin(outsider, p).status_code == 403
    spoof = web(p["app"], OUTSIDE_IP, {"X-Forwarded-For": WIFI_IP})
    spoof.headers["X-CSRF-Token"] = outsider.headers["X-CSRF-Token"]
    spoof.cookies.update(outsider.cookies)
    assert checkin(spoof, p).status_code == 403  # header giả không có tác dụng khi peer không phải proxy tin cậy
    with Session(p["app"].state.engine) as db:
        assert db.scalar(select(func.count()).select_from(Checkin)) == 0

    first = checkin(p["cust"], p).json()
    assert first["already_checked_in"] is False and first["points_added"] == 10 and first["streak"] == 1 and first["ticket_id"]
    again = checkin(p["cust"], p).json()
    assert again["already_checked_in"] is True and again["points_added"] == 0 and again["ticket_id"] is None
    with Session(p["app"].state.engine) as db:
        assert db.scalar(select(func.count()).select_from(PointLedger)) == 1
        assert db.scalar(select(func.count()).select_from(SpinTicket)) == 1
        assert db.scalar(select(Checkin.method)) == "wifi"
    assert p["cust"].get(v(p, "/my/game")).json()["points"] == 10


def test_trusted_proxy_forwarded_ip_is_used(p):
    behind_proxy = web(p["app"], "10.0.0.5", {"X-Forwarded-For": WIFI_IP})
    r = behind_proxy.post("/api/auth/login", json={"login": "0901111111", "password": CUSTOMER_PASSWORD, "venue_slug": "quan-a"})
    behind_proxy.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    assert checkin(behind_proxy, p).status_code == 200


def test_checkin_mode_off_and_missing_networks(p):
    configure(p, checkin_mode="off")
    assert checkin(p["cust"], p).status_code == 409
    configure(p, checkin_mode="wifi")
    p["owner"].put(v(p, "/networks"), json={"networks": []})
    assert checkin(p["cust"], p).status_code == 409


def test_staff_and_owner_cannot_use_customer_endpoints(p):
    assert checkin(p["staff"], p).status_code == 403
    assert p["owner"].get(v(p, "/my/game")).status_code == 403
    outsider = register(p["app"], "quan-b", "0901234000")
    assert outsider.get(v(p, "/my/game", "a")).status_code == 404  # khách quán B không vào được dữ liệu quán A
    assert checkin(outsider, p).status_code == 404


def test_code_modes(p):
    configure(p, checkin_mode="code")
    assert p["cust"].get(v(p, "/checkin-code")).status_code == 403
    code = p["staff"].get(v(p, "/checkin-code")).json()
    assert code["enabled"] is True and len(code["code"]) == 6 and 0 < code["expires_in_seconds"] <= 300
    outsider = relogin(p, ip=OUTSIDE_IP)  # chế độ mã: không cần wifi
    assert checkin(outsider, p, "SAIMA1").status_code == 403
    assert checkin(outsider, p, None).status_code == 403
    ok = checkin(outsider, p, code["code"].lower())
    assert ok.status_code == 200 and ok.json()["points_added"] == 10
    with Session(p["app"].state.engine) as db:
        assert db.scalar(select(Checkin.method)) == "code"


def test_code_rotates_and_old_codes_expire(p):
    configure(p, checkin_mode="code")
    old = p["staff"].get(v(p, "/checkin-code")).json()["code"]
    p["clock"].advance(seconds=300)
    assert p["staff"].get(v(p, "/checkin-code")).json()["code"] != old
    assert checkin(p["cust"], p, old).status_code == 200  # mã kỳ trước vẫn được chấp nhận thêm một kỳ
    second = register(p["app"], "quan-a", "0902222222")
    p["clock"].advance(seconds=600)
    assert checkin(second, p, old).status_code == 403  # mã cũ hơn hai kỳ thì hết hạn


def test_wrong_code_attempts_are_limited(p):
    configure(p, checkin_mode="code")
    codes = [checkin(p["cust"], p, f"BAD{n:03d}").status_code for n in range(game_api.CODE_ATTEMPTS + 2)]
    assert codes[:game_api.CODE_ATTEMPTS] == [403] * game_api.CODE_ATTEMPTS and codes[-1] == 429
    good = p["staff"].get(v(p, "/checkin-code")).json()["code"]
    assert checkin(p["cust"], p, good).status_code == 429  # đang bị khoá thử mã


def test_wifi_and_code_and_wifi_or_code(p):
    configure(p, checkin_mode="wifi_and_code")
    code = p["staff"].get(v(p, "/checkin-code")).json()["code"]
    outsider = relogin(p, ip=OUTSIDE_IP)
    assert checkin(outsider, p, code).status_code == 403  # có mã nhưng không ở wifi
    assert checkin(p["cust"], p, None).status_code == 403  # ở wifi nhưng thiếu mã
    assert checkin(p["cust"], p, code).status_code == 200
    configure(p, checkin_mode="wifi_or_code")
    second = register(p["app"], "quan-a", "0903333333")
    assert checkin(second, p).status_code == 200  # chỉ wifi
    third = register(p["app"], "quan-a", "0904444444", ip=OUTSIDE_IP)
    assert checkin(third, p).status_code == 403
    assert checkin(third, p, code).status_code == 200  # chỉ mã


# ---------- streak ----------

def test_streak_grows_resets_and_pays_milestone_bonus_once(p):
    assert checkin(p["cust"], p).json()["streak"] == 1
    for expected in (2, 3):
        p["clock"].advance(days=1)
        client = relogin(p)
        response = checkin(client, p).json()
        assert response["streak"] == expected
    assert response["streak_bonus"] == 20 and response["points_added"] == 10
    with Session(p["app"].state.engine) as db:
        game = db.get(CustomerGame, (p["a"], db.scalar(select(User.id).where(User.login == "0901111111"))))
        assert (game.streak, game.points) == (3, 3 * 10 + 20)
        assert db.scalar(select(func.count()).select_from(PointLedger).where(PointLedger.reason == "streak_bonus")) == 1
    p["clock"].advance(days=2)  # bỏ lỡ một ngày
    client = relogin(p)
    assert client.get(v(p, "/my/game")).json()["streak"] == 0  # chuỗi đã đứt (chưa check-in lại)
    reset = checkin(client, p).json()
    assert reset["streak"] == 1 and "streak_bonus" not in reset or reset.get("streak_bonus") == 0
    assert client.get(v(p, "/my/game")).json()["best_streak"] == 3


def test_streak_uses_the_venue_day_not_utc(p):
    p["clock"].now = datetime(2026, 11, 22, 16, 59, tzinfo=timezone.utc)  # 23:59 giờ VN
    client = relogin(p)
    assert checkin(client, p).json()["streak"] == 1
    p["clock"].now = datetime(2026, 11, 22, 17, 1, tzinfo=timezone.utc)  # 00:01 ngày hôm sau giờ VN
    client = relogin(p)
    assert checkin(client, p).json()["streak"] == 2  # hai ngày liên tiếp theo giờ VN dù cùng ngày UTC
    with Session(p["app"].state.engine) as db:
        assert sorted(db.scalars(select(Checkin.day))) == ["2026-11-22", "2026-11-23"]


def test_game_state_reports_calendar_level_and_next_milestone(p):
    checkin(p["cust"], p)
    state = p["cust"].get(v(p, "/my/game")).json()
    assert state["checked_in_today"] is True and state["streak"] == 1 and state["level"] == {"name": "Đồng", "next_at": 100}
    assert state["next_milestone"] == {"days": 3, "bonus": 20} and len(state["calendar"]) == 14 and state["calendar"][-1] == {"day": "2026-11-22", "checked": True}
    assert state["wheel"]["enabled"] is True and state["wheel"]["daily_guarantee"] is True
    assert sum(pz["percent"] for pz in state["wheel"]["prizes"]) == 100
    assert game_api.level_for(100)["name"] == "Bạc" and game_api.level_for(5000) == {"name": "Kim cương", "next_at": None}


# ---------- cấu hình vòng quay ----------

def test_wheel_validation(p):
    put = lambda prizes: p["owner"].put(v(p, "/wheel"), json={"prizes": prizes})
    nothing = {"name": "Chúc may mắn", "kind": "nothing", "weight_bp": 5000}
    pts = {"name": "+10", "kind": "points", "value": 10, "weight_bp": 5000}
    assert put([pts, {**nothing, "weight_bp": 4000}]).status_code == 400  # tổng 90%
    assert put([{**pts, "weight_bp": 6000}, nothing]).status_code == 400  # tổng 110%
    assert put([pts, {**pts, "name": "+20", "weight_bp": 5000}]).status_code == 400  # thiếu ô "chúc may mắn"
    assert put([pts, {**nothing, "name": "+10"}]).status_code == 400  # trùng tên
    assert put([pts]).status_code == 422 and put([]).status_code == 422
    assert put([{**pts, "value": 0}, nothing]).status_code == 400
    assert put([{"name": "Giảm", "kind": "discount_vnd", "value": 5, "weight_bp": 5000}, nothing]).status_code == 400
    assert put([{"name": "Miễn phí", "kind": "free_minutes", "value": 1, "weight_bp": 5000}, nothing]).status_code == 400
    assert put([{**pts, "weight_bp": -1}, nothing]).status_code == 422
    assert put([{**pts, "stock": 0}, nothing]).status_code == 400  # đảm bảo thưởng nhưng hết hàng
    assert p["staff"].put(v(p, "/wheel"), json={"prizes": [pts, nothing]}).status_code == 403
    assert p["cust"].get(v(p, "/wheel")).status_code == 403
    ok = put([pts, nothing]).json()
    assert ok["total_bp"] == 10000 and [x["name"] for x in ok["prizes"]] == ["+10", "Chúc may mắn"]


def test_wheel_replace_keeps_stock_and_deactivates_removed(p):
    prizes = p["owner"].get(v(p, "/wheel")).json()["prizes"]
    voucher = next(x for x in prizes if x["kind"] == "discount_vnd")
    assert voucher["stock"] == 5 and voucher["weight_bp"] == 1000
    payload = [{"id": x["id"], "name": x["name"], "kind": x["kind"], "value": x["value"], "weight_bp": x["weight_bp"], "stock": x["stock"]}
               for x in prizes if x["kind"] != "points"]
    payload[0]["weight_bp"] += 4000
    result = p["owner"].put(v(p, "/wheel"), json={"prizes": payload}).json()
    assert [x["kind"] for x in result["prizes"]] == ["discount_vnd", "nothing"] and result["prizes"][0]["id"] == voucher["id"]
    with Session(p["app"].state.engine) as db:
        assert db.scalar(select(func.count()).select_from(WheelPrize).where(WheelPrize.status == "INACTIVE")) == 1
    state = p["cust"].get(v(p, "/my/game")).json()
    assert len(state["wheel"]["prizes"]) == 2


# ---------- quay ----------

def test_wheel_not_issued_when_disabled_and_spin_ownership(p):
    configure(p, wheel_enabled=False)
    assert checkin(p["cust"], p).json()["ticket_id"] is None
    configure(p, wheel_enabled=True)
    p["clock"].advance(days=1)
    relogin_staff(p)
    mine = relogin(p)
    ticket = checked_in_ticket(mine, p)
    other = register(p["app"], "quan-a", "0905555555")
    assert spin(other, p, ticket).status_code == 404
    assert spin(register(p["app"], "quan-b", "0906060606"), p, ticket).status_code == 404  # khách quán khác
    assert spin(mine, p, 99999).status_code == 404


def test_spin_is_idempotent_per_ticket_and_pays_once(p, monkeypatch):
    set_wheel(p, [{"name": "+20 điểm", "kind": "points", "value": 20, "weight_bp": 10000}, {"name": "Chúc may mắn", "kind": "nothing", "weight_bp": 0}])
    monkeypatch.setattr(game_api.secrets, "randbelow", lambda n: 0)
    ticket = checked_in_ticket(p["cust"], p)
    first = spin(p["cust"], p, ticket).json()
    assert first["duplicate"] is False and first["prize"]["kind"] == "points" and first["points"] == 30 and first["prize_index"] == 0
    again = spin(p["cust"], p, ticket).json()
    assert again["duplicate"] is True and again["prize"]["name"] == "+20 điểm" and again["points"] == 30
    with Session(p["app"].state.engine) as db:
        assert db.scalar(select(func.count()).select_from(SpinResult)) == 1
        assert db.scalar(select(func.count()).select_from(PointLedger).where(PointLedger.reason == "wheel")) == 1
    assert p["cust"].get(v(p, "/my/game")).json()["tickets"] == []


def test_concurrent_spins_of_one_ticket_produce_one_result(p, monkeypatch):
    set_wheel(p, [{"name": "+20 điểm", "kind": "points", "value": 20, "weight_bp": 10000}, {"name": "Chúc may mắn", "kind": "nothing", "weight_bp": 0}])
    ticket = checked_in_ticket(p["cust"], p)
    with ThreadPoolExecutor(5) as pool:
        results = list(pool.map(lambda _: spin(p["cust"], p, ticket), range(5)))
    assert all(r.status_code == 200 for r in results)
    assert sum(1 for r in results if r.json()["duplicate"] is False) == 1
    with Session(p["app"].state.engine) as db:
        assert db.scalar(select(func.count()).select_from(SpinResult)) == 1
        assert db.scalar(select(func.count()).select_from(PointLedger).where(PointLedger.reason == "wheel")) == 1


def test_expired_ticket_cannot_be_spun(p):
    ticket = checked_in_ticket(p["cust"], p)
    p["clock"].advance(hours=15)  # qua nửa đêm giờ VN: hết hạn trong ngày
    relogin_staff(p)
    client = relogin(p)
    assert spin(client, p, ticket).status_code == 409
    assert client.get(v(p, "/my/game")).json()["tickets"] == []
    configure(p, spin_expiry_days=3)
    p["clock"].advance(days=1)
    client = relogin(p)
    assert checkin(client, p).json()["ticket_id"]  # vé mới của ngày hôm sau


def test_ticket_expiry_days_keeps_older_tickets_valid(p):
    configure(p, spin_expiry_days=3)
    old_ticket = checked_in_ticket(p["cust"], p)
    p["clock"].advance(days=2)
    client = relogin(p)
    assert spin(client, p, old_ticket).status_code == 200


def test_prize_selection_follows_the_configured_weights(p, monkeypatch):
    set_wheel(p, [{"name": "A", "kind": "points", "value": 1, "weight_bp": 5000}, {"name": "B", "kind": "points", "value": 2, "weight_bp": 3000},
                  {"name": "Chúc may mắn", "kind": "nothing", "weight_bp": 2000}])
    configure(p, min_daily_prizes=0, max_daily_prizes=50)
    picks = []
    for roll in (0, 4999, 5000, 7999, 8000, 9999):
        monkeypatch.setattr(game_api.secrets, "randbelow", lambda n, roll=roll: roll)
        client = register(p["app"], "quan-a", f"09{roll:08d}")
        picks.append(spin(client, p, checked_in_ticket(client, p)).json()["prize"]["name"])
    assert picks == ["A", "A", "B", "B", "Chúc may mắn", "Chúc may mắn"]


def test_real_randomness_roughly_matches_the_odds(p):
    set_wheel(p, [{"name": "Thưởng", "kind": "points", "value": 1, "weight_bp": 4000}, {"name": "Chúc may mắn", "kind": "nothing", "weight_bp": 6000}])
    configure(p, min_daily_prizes=0, max_daily_prizes=50, expected_daily_checkins=1000)
    wins, total = 0, 100  # 100 lượt × 40% < mức tối đa 50 thưởng/ngày nên giới hạn không làm lệch phép thử
    with Session(p["app"].state.engine) as db:
        db.query(WheelDailyPlan).delete()
        db.commit()
    for n in range(total):
        client = register(p["app"], "quan-a", f"08{n:08d}", ip=f"203.0.113.{n % 200 + 1}")
        result = spin(client, p, checked_in_ticket(client, p)).json()
        wins += result["prize"]["kind"] == "points"
    assert 0.40 * total - 6 * (total * 0.24) ** 0.5 < wins < 0.40 * total + 6 * (total * 0.24) ** 0.5  # ±6σ quanh 40%


# ---------- thưởng đảm bảo mỗi ngày ----------

def spin_many(p, count, prefix="07"):
    results = []
    for n in range(count):
        client = register(p["app"], "quan-a", f"{prefix}{n:08d}", ip=f"203.0.113.{n % 200 + 1}")
        results.append(spin(client, p, checked_in_ticket(client, p)).json())
    return results


def test_guaranteed_prizes_are_given_even_when_the_natural_odds_are_zero(p):
    set_wheel(p, [{"name": "Thưởng", "kind": "points", "value": 5, "weight_bp": 0}, {"name": "Chúc may mắn", "kind": "nothing", "weight_bp": 10000}])
    configure(p, min_daily_prizes=2, max_daily_prizes=2, expected_daily_checkins=6)
    results = spin_many(p, 8)
    won = [i for i, r in enumerate(results, start=1) if r["prize"]["kind"] == "points"]
    assert len(won) == 2 and all(1 <= i <= 6 for i in won)  # đúng 2 lượt trúng, đều nằm trong 6 lượt dự kiến
    with Session(p["app"].state.engine) as db:
        plan = db.scalar(select(WheelDailyPlan))
        assert sorted(plan.guaranteed) == won and (plan.prizes_given, plan.guaranteed_given, plan.spin_count) == (2, 2, 8)
        forced = sorted(db.scalars(select(SpinResult.spin_index).where(SpinResult.forced.is_(True))))
        assert forced == won
    stats = p["owner"].get(v(p, "/game-stats")).json()
    assert stats["plan"]["guaranteed_given"] == 2 and stats["plan"]["guaranteed_total"] == 2 and stats["plan"]["spins"] == 8
    assert p["staff"].get(v(p, "/game-stats")).status_code == 403


def test_daily_cap_is_never_exceeded_and_leaves_room_for_the_guarantee(p):
    set_wheel(p, [{"name": "Thưởng", "kind": "points", "value": 5, "weight_bp": 10000}, {"name": "Chúc may mắn", "kind": "nothing", "weight_bp": 0}])
    configure(p, min_daily_prizes=1, max_daily_prizes=2, expected_daily_checkins=5)
    results = spin_many(p, 10)
    assert sum(r["prize"]["kind"] == "points" for r in results) == 2  # đúng mức tối đa dù tỷ lệ tự nhiên là 100%
    with Session(p["app"].state.engine) as db:
        plan = db.scalar(select(WheelDailyPlan))
        assert plan.prizes_given == 2 and plan.guaranteed_given == 1


def test_guarantee_is_kept_when_natural_wins_would_have_used_the_cap(p):
    set_wheel(p, [{"name": "Thưởng", "kind": "points", "value": 5, "weight_bp": 10000}, {"name": "Chúc may mắn", "kind": "nothing", "weight_bp": 0}])
    configure(p, min_daily_prizes=2, max_daily_prizes=2, expected_daily_checkins=4)
    results = spin_many(p, 6)
    assert sum(r["prize"]["kind"] == "points" for r in results) == 2


def test_each_day_gets_its_own_plan(p):
    set_wheel(p, [{"name": "Thưởng", "kind": "points", "value": 5, "weight_bp": 0}, {"name": "Chúc may mắn", "kind": "nothing", "weight_bp": 10000}])
    configure(p, min_daily_prizes=1, max_daily_prizes=1, expected_daily_checkins=3)
    spin_many(p, 3, "06")
    p["clock"].advance(days=1)
    relogin_staff(p)
    configure(p, min_daily_prizes=1, max_daily_prizes=1, expected_daily_checkins=3)
    spin_many(p, 3, "05")
    with Session(p["app"].state.engine) as db:
        plans = db.scalars(select(WheelDailyPlan).order_by(WheelDailyPlan.day)).all()
        assert [pl.day for pl in plans] == ["2026-11-22", "2026-11-23"] and [pl.prizes_given for pl in plans] == [1, 1]


def test_stock_runs_out_and_never_goes_negative(p, monkeypatch):
    set_wheel(p, [{"name": "Giảm 10.000₫", "kind": "discount_vnd", "value": 10000, "weight_bp": 10000, "stock": 2},
                  {"name": "Chúc may mắn", "kind": "nothing", "weight_bp": 0}])
    configure(p, min_daily_prizes=0, max_daily_prizes=50)
    results = spin_many(p, 5)
    assert sum(r["prize"]["kind"] == "discount_vnd" for r in results) == 2
    with Session(p["app"].state.engine) as db:
        assert db.scalar(select(WheelPrize.stock_remaining).where(WheelPrize.kind == "discount_vnd", WheelPrize.status == "ACTIVE")) == 0
        assert db.scalar(select(func.count()).select_from(Voucher)) == 2


def test_forced_prize_falls_back_to_nothing_when_all_real_stock_is_gone(p):
    set_wheel(p, [{"name": "Giảm 10.000₫", "kind": "discount_vnd", "value": 10000, "weight_bp": 10000, "stock": 1},
                  {"name": "Chúc may mắn", "kind": "nothing", "weight_bp": 0}])
    configure(p, min_daily_prizes=2, max_daily_prizes=2, expected_daily_checkins=3)
    results = spin_many(p, 4)
    assert sum(r["prize"]["kind"] == "discount_vnd" for r in results) == 1  # không thể bù quá tồn kho
    stats = p["owner"].get(v(p, "/game-stats")).json()["plan"]
    assert stats["guaranteed_total"] == 2 and stats["guaranteed_given"] == 1  # thống kê cho chủ quán thấy cam kết chưa đủ


def test_concurrent_spins_by_many_customers_respect_the_cap(p):
    set_wheel(p, [{"name": "Thưởng", "kind": "points", "value": 5, "weight_bp": 10000}, {"name": "Chúc may mắn", "kind": "nothing", "weight_bp": 0}])
    configure(p, min_daily_prizes=0, max_daily_prizes=2, expected_daily_checkins=50)
    customers = [register(p["app"], "quan-a", f"04{n:08d}", ip=f"203.0.113.{n + 1}") for n in range(6)]
    tickets = [checked_in_ticket(c, p) for c in customers]
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(lambda pair: spin(pair[0], p, pair[1]).json(), zip(customers, tickets)))
    assert sum(r["prize"]["kind"] == "points" for r in results) == 2
    with Session(p["app"].state.engine) as db:
        plan = db.scalar(select(WheelDailyPlan))
        assert plan.spin_count == 6 and sorted(db.scalars(select(SpinResult.spin_index))) == [1, 2, 3, 4, 5, 6]


def test_results_snapshot_the_odds_and_changing_odds_does_not_rewrite_history(p, monkeypatch):
    monkeypatch.setattr(game_api.secrets, "randbelow", lambda n: 0)
    first = spin(p["cust"], p, checked_in_ticket(p["cust"], p)).json()
    set_wheel(p, [{"name": "Mới", "kind": "points", "value": 7, "weight_bp": 9000}, {"name": "Chúc may mắn", "kind": "nothing", "weight_bp": 1000}])
    with Session(p["app"].state.engine) as db:
        result = db.scalar(select(SpinResult))
        assert (result.prize_name, result.odds_bp) == (first["prize"]["name"], 4000)
        assert "wheel_changed" in [r.action for r in db.scalars(select(AuditLog))]


# ---------- voucher ----------

_table_counter = iter(range(1, 1000))


def make_session_for(p, customer_phone="0901111111", rate=60000):
    table = p["owner"].post(v(p, "/tables"), json={"name": f"Bàn {next(_table_counter)}", "hourly_rate": rate}).json()
    session = p["staff"].post(v(p, f"/tables/{table['id']}/open"), json={}).json()
    with Session(p["app"].state.engine) as db:
        cid = db.scalar(select(User.id).where(User.login == customer_phone, User.venue_id == p["a"]))
    assert p["staff"].patch(v(p, f"/sessions/{session['id']}/customer"), json={"customer_id": cid}).status_code == 200
    return session["id"]


def win_voucher(p, client, kind="discount_vnd", value=10000, valid_days=30):
    set_wheel(p, [{"name": "Voucher", "kind": kind, "value": value, "weight_bp": 10000, "voucher_valid_days": valid_days},
                  {"name": "Chúc may mắn", "kind": "nothing", "weight_bp": 0}])
    configure(p, min_daily_prizes=0, max_daily_prizes=50)
    result = spin(client, p, checked_in_ticket(client, p)).json()
    assert result["voucher"]["code"]
    with Session(p["app"].state.engine) as db:
        return db.scalar(select(Voucher.id).where(Voucher.code == result["voucher"]["code"]))


def test_voucher_is_listed_previewed_and_applied_once_at_checkout(p):
    voucher_id = win_voucher(p, p["cust"], "discount_vnd", 10000)
    state = p["cust"].get(v(p, "/my/game")).json()
    assert [x["value"] for x in state["vouchers"]] == [10000]
    session_id = make_session_for(p)
    p["clock"].advance(minutes=60)
    quote = p["staff"].get(v(p, f"/sessions/{session_id}/quote")).json()
    assert [x["id"] for x in quote["available_vouchers"]] == [voucher_id] and quote["voucher_discount"] == 0
    preview = p["staff"].get(v(p, f"/sessions/{session_id}/quote?voucher_id={voucher_id}")).json()
    assert preview["voucher_discount"] == 10000 and preview["amount_vnd"] == 50000
    paid = p["staff"].post(v(p, f"/sessions/{session_id}/checkout"), json={"payment_method": "cash", "voucher_id": voucher_id}).json()
    assert paid["voucher_discount"] == 10000 and paid["amount_vnd"] == 50000 and paid["amount_due"] == 50000
    assert p["staff"].get(v(p, "/revenue/today")).json()["total_vnd"] == 50000  # doanh thu tính sau giảm giá
    invoice = p["staff"].get(v(p, f"/sessions/{session_id}/invoice")).json()
    assert invoice["voucher_discount"] == 10000 and invoice["total"] == 50000
    assert p["cust"].get(v(p, "/my/game")).json()["vouchers"] == []
    # Dùng lại ở phiên khác: bị chặn.
    other = make_session_for(p, rate=60000)
    assert p["staff"].post(v(p, f"/sessions/{other}/checkout"), json={"payment_method": "cash", "voucher_id": voucher_id}).status_code == 409
    with Session(p["app"].state.engine) as db:
        assert db.get(Voucher, voucher_id).status == "USED" and db.get(Voucher, voucher_id).used_session_id == session_id


def test_free_minutes_voucher_only_discounts_table_time(p):
    voucher_id = win_voucher(p, p["cust"], "free_minutes", 30)
    session_id = make_session_for(p, rate=60000)
    product = p["owner"].post(v(p, "/products"), json={"name": "Nước", "price": 10000}).json()
    p["staff"].post(v(p, f"/sessions/{session_id}/items"), json={"product_id": product["id"], "quantity": 2})
    p["clock"].advance(minutes=20)  # tiền giờ 20.000 < 30 phút miễn phí (30.000): chỉ trừ tối đa tiền giờ
    paid = p["staff"].post(v(p, f"/sessions/{session_id}/checkout"), json={"payment_method": "cash", "voucher_id": voucher_id}).json()
    assert paid["table_amount"] == 20000 and paid["items_amount"] == 20000 and paid["voucher_discount"] == 20000 and paid["amount_vnd"] == 20000


def test_discount_voucher_is_capped_at_the_bill(p):
    voucher_id = win_voucher(p, p["cust"], "discount_vnd", 500000)
    session_id = make_session_for(p)
    p["clock"].advance(minutes=30)
    paid = p["staff"].post(v(p, f"/sessions/{session_id}/checkout"), json={"payment_method": "cash", "voucher_id": voucher_id}).json()
    assert paid["voucher_discount"] == 30000 and paid["amount_vnd"] == 0 and paid["amount_due"] == 0


def test_voucher_rules_owner_expiry_and_customer_link(p):
    voucher_id = win_voucher(p, p["cust"], "discount_vnd", 10000, valid_days=2)
    stranger = register(p["app"], "quan-a", "0907070707")
    stranger_session = make_session_for(p, "0907070707")
    assert p["staff"].post(v(p, f"/sessions/{stranger_session}/checkout"), json={"payment_method": "cash", "voucher_id": voucher_id}).status_code == 400
    table = p["owner"].post(v(p, "/tables"), json={"name": "Bàn lẻ", "hourly_rate": 60000}).json()
    anonymous = p["staff"].post(v(p, f"/tables/{table['id']}/open"), json={}).json()["id"]
    assert p["staff"].post(v(p, f"/sessions/{anonymous}/checkout"), json={"payment_method": "cash", "voucher_id": voucher_id}).status_code == 400
    assert p["staff"].post(v(p, f"/sessions/{anonymous}/checkout"), json={"payment_method": "cash", "voucher_id": 99999}).status_code == 404
    assert p["staff"].get(v(p, f"/sessions/{anonymous}/quote")).json()["available_vouchers"] == []
    p["clock"].advance(days=3)
    relogin_staff(p)
    mine = make_session_for(p)
    assert p["staff"].get(v(p, f"/sessions/{mine}/quote")).json()["available_vouchers"] == []  # đã hết hạn
    assert p["staff"].post(v(p, f"/sessions/{mine}/checkout"), json={"payment_method": "cash", "voucher_id": voucher_id}).status_code == 409
    assert p["owner_b"].post(v(p, f"/sessions/{mine}/checkout", "b"), json={"payment_method": "cash", "voucher_id": voucher_id}).status_code == 404


def test_voucher_stacks_with_a_deposit(p):
    voucher_id = win_voucher(p, p["cust"], "discount_vnd", 20000)
    table = p["owner"].post(v(p, "/tables"), json={"name": "Bàn cọc", "hourly_rate": 60000}).json()
    start = (START + timedelta(minutes=40)).isoformat().replace("+00:00", "Z")
    booking = p["cust"].post(v(p, "/my/bookings"), json={"table_id": table["id"], "start_at": start, "duration_minutes": 60}).json()
    p["cust"].post(v(p, f"/my/bookings/{booking['id']}/deposit/mock-pay"))
    p["clock"].advance(minutes=30)
    session_id = p["staff"].post(v(p, f"/bookings/{booking['id']}/check-in")).json()["session_id"]
    p["clock"].advance(minutes=60)  # tiền giờ 60.000
    paid = p["staff"].post(v(p, f"/sessions/{session_id}/checkout"), json={"payment_method": "cash", "voucher_id": voucher_id}).json()
    assert paid["voucher_discount"] == 20000 and paid["amount_vnd"] == 40000 and paid["deposit_applied"] == 40000 and paid["amount_due"] == 0


# ---------- điểm / thống kê ----------

def test_points_ledger_is_idempotent_and_wheel_points_accumulate(p, monkeypatch):
    set_wheel(p, [{"name": "+20 điểm", "kind": "points", "value": 20, "weight_bp": 10000}, {"name": "Chúc may mắn", "kind": "nothing", "weight_bp": 0}])
    configure(p, min_daily_prizes=0, max_daily_prizes=50)
    client = register(p["app"], "quan-a", "0909090909")
    with Session(p["app"].state.engine) as db:
        cid = db.scalar(select(User.id).where(User.login == "0909090909"))
        assert game_api  # sổ điểm: cùng (reason, ref) không cộng hai lần
    spin(client, p, checked_in_ticket(client, p))
    state = client.get(v(p, "/my/game")).json()
    assert state["points"] == 30 and [e["delta"] for e in state["ledger"]] == [20, 10]
    with Session(p["app"].state.engine) as db:
        game = db.get(CustomerGame, (p["a"], cid))
        assert game.points == db.scalar(select(func.sum(PointLedger.delta)).where(PointLedger.customer_id == cid))


def test_owner_stats_list_recent_spins_and_checkins(p, monkeypatch):
    monkeypatch.setattr(game_api.secrets, "randbelow", lambda n: 0)
    spin(p["cust"], p, checked_in_ticket(p["cust"], p))
    stats = p["owner"].get(v(p, "/game-stats")).json()
    assert stats["checkins_today"] == 1 and stats["plan"]["spins"] == 1 and stats["recent"][0]["customer"] == "Khách 1111"
    assert p["owner_b"].get(v(p, "/game-stats", "b")).json()["checkins_today"] == 0
    assert p["owner_b"].get(v(p, "/game-stats", "a")).status_code == 404
