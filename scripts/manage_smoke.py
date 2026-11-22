"""Smoke test HTTP thật cho phòng quản lý: chạy uvicorn trên cổng tự chọn với DB tạm, đi qua luồng chính của
admin → chủ quán → nhân viên → khách (đặt bàn, cọc giả lập, check-in, vòng quay) → báo cáo. Chạy sau khi đổi luồng tích hợp.

Ví dụ:  .venv/Scripts/python scripts/manage_smoke.py
Thoát mã khác 0 nếu bất kỳ bước nào sai. Không đụng vào data/manage.db.
"""
import http.cookiejar
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.manage_create_admin import create_admin  # noqa: E402

ADMIN_PASSWORD = "Smoke-Admin-2026!"
STEPS = []


class Client:
    def __init__(self, base: str):
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = ""

    def call(self, method: str, path: str, body=None, expect: int | tuple = (200, 201)):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        if method != "GET" and self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with self.opener.open(request, timeout=20) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as err:
            status, raw = err.code, err.read()
        allowed = (expect,) if isinstance(expect, int) else expect
        if status not in allowed:
            raise AssertionError(f"{method} {path} -> {status}, mong đợi {allowed}: {raw[:300]!r}")
        try:
            return json.loads(raw) if raw else None
        except ValueError:
            return raw.decode("utf-8", "replace")

    def login(self, login: str, password: str, slug: str | None = None):
        user = self.call("POST", "/api/auth/login", {"login": login, "password": password, "venue_slug": slug})
        self.csrf = user["csrf_token"]
        return user


def step(name: str):
    STEPS.append(name)
    print(f"  ✓ {name}")


def stop(server: subprocess.Popen) -> None:
    """Dừng máy chủ và mọi tiến trình con (launcher của venv trên Windows tạo thêm một tiến trình con giữ tệp DB)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(server.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_url = f"sqlite:///{Path(tmp, 'smoke.db').as_posix()}"
        create_admin(db_url, "admin@smoke.test", "Quản trị smoke", ADMIN_PASSWORD)
        env = {**os.environ, "MANAGE_DATABASE_URL": db_url, "MANAGE_API_PORT": str(port)}
        server = subprocess.Popen([sys.executable, "-m", "uvicorn", "apps.manage_api.main:create_app", "--factory", "--host", "127.0.0.1",
                                   "--port", str(port)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(60):
                try:
                    urllib.request.urlopen(base + "/api/health", timeout=1).read()
                    break
                except OSError:
                    time.sleep(0.25)
            else:
                raise AssertionError("Máy chủ không khởi động được")
            run(base)
        finally:
            stop(server)
    print(f"Smoke phòng quản lý: {len(STEPS)} bước đạt.")
    return 0


def run(base: str) -> None:
    assert Client(base).call("GET", "/api/health")["app"] == "manage"
    step("health trả đúng ứng dụng quản lý")

    admin = Client(base)
    admin.login("admin@smoke.test", ADMIN_PASSWORD)
    created = admin.call("POST", "/api/admin/venues", {"name": "Bi-a Smoke", "owner": {"login": "chu@smoke.test", "display_name": "Chủ smoke"}})
    vid, slug = created["venue"]["id"], created["venue"]["slug"]
    step("admin tạo quán và nhận mật khẩu tạm của chủ quán")

    owner = Client(base)
    user = owner.login("chu@smoke.test", created["owner_temp_password"])
    assert user["must_change_password"] is True
    owner.call("POST", "/api/auth/change-password", {"current_password": created["owner_temp_password"], "new_password": "Chu-Quan-2026-OK"})
    owner.login("chu@smoke.test", "Chu-Quan-2026-OK")
    step("chủ quán đổi mật khẩu tạm bắt buộc")

    v = f"/api/venues/{vid}"
    table = owner.call("POST", f"{v}/tables", {"name": "Bàn 1", "hourly_rate": 60000})
    product = owner.call("POST", f"{v}/products", {"name": "Nước suối", "price": 10000})
    owner.call("PUT", f"{v}/networks", {"networks": [{"cidr": "127.0.0.1", "label": "Máy smoke"}]})
    settings = owner.call("GET", f"{v}/game-settings")
    owner.call("PUT", f"{v}/game-settings", {**settings, "min_daily_prizes": 1, "max_daily_prizes": 2})
    owner.call("PUT", f"{v}/wheel", {"prizes": [{"name": "+20 điểm", "kind": "points", "value": 20, "weight_bp": 5000},
                                                 {"name": "Chúc may mắn", "kind": "nothing", "weight_bp": 5000}]})
    staff_created = owner.call("POST", f"{v}/staff", {"login": "nv@smoke.test", "display_name": "Nhân viên smoke"})
    step("chủ quán dựng bàn, menu, mạng wifi, vòng quay và nhân viên")

    staff = Client(base)
    staff.login("nv@smoke.test", staff_created["temp_password"])
    staff.call("POST", "/api/auth/change-password", {"current_password": staff_created["temp_password"], "new_password": "Nhan-Vien-2026-OK"})
    staff.login("nv@smoke.test", "Nhan-Vien-2026-OK")
    staff.call("POST", f"{v}/tables", {"name": "X", "hourly_rate": 1}, expect=403)
    step("nhân viên không đổi được bàn/giá (backend chặn)")

    session = staff.call("POST", f"{v}/tables/{table['id']}/open", {})
    staff.call("POST", f"{v}/tables/{table['id']}/open", {}, expect=409)
    staff.call("POST", f"{v}/sessions/{session['id']}/items", {"product_id": product["id"], "quantity": 2})
    paid = staff.call("POST", f"{v}/sessions/{session['id']}/checkout", {"payment_method": "cash"})
    assert paid["status"] == "PAID" and paid["items_amount"] == 20000 and paid["amount_vnd"] == paid["table_amount"] + 20000
    assert staff.call("POST", f"{v}/sessions/{session['id']}/checkout", {"payment_method": "cash"})["duplicate"] is True
    invoice = staff.call("GET", f"{v}/sessions/{session['id']}/invoice")
    assert invoice["total"] == paid["amount_vnd"]
    step("mở bàn, gọi món, thu tiền idempotent, hoá đơn khớp")

    customer = Client(base)
    customer.call("POST", "/api/auth/register", {"venue_slug": slug, "display_name": "Khách smoke", "phone": "0912345678", "password": "Khach-Smoke-2026"})
    me = customer.call("GET", "/api/auth/me")
    customer.csrf = me["csrf_token"]
    customer.call("GET", f"{v}/tables", expect=403)
    step("khách tự đăng ký và không vào được khu vận hành")

    start = (datetime.now(timezone.utc) + timedelta(hours=3)).replace(minute=0, second=0, microsecond=0)
    booking = customer.call("POST", f"{v}/my/bookings", {"table_id": table["id"], "start_at": start.isoformat().replace("+00:00", "Z"), "duration_minutes": 60})
    assert booking["status"] == "PENDING" and booking["deposit"]["is_mock"] is True
    confirmed = customer.call("POST", f"{v}/my/bookings/{booking['id']}/deposit/mock-pay", {})
    assert confirmed["status"] == "CONFIRMED"
    customer.call("POST", f"{v}/my/bookings", {"table_id": table["id"], "start_at": start.isoformat().replace("+00:00", "Z"), "duration_minutes": 30}, expect=409)
    step("đặt bàn, cọc giả lập xác nhận, đặt trùng giờ bị chặn")

    checkin = customer.call("POST", f"{v}/my/checkin", {"code": None})
    assert checkin["points_added"] == 10 and checkin["ticket_id"]
    assert customer.call("POST", f"{v}/my/checkin", {"code": None})["already_checked_in"] is True
    spin = customer.call("POST", f"{v}/my/spins/{checkin['ticket_id']}/spin", {})
    assert spin["duplicate"] is False and spin["prize"]["kind"] in ("points", "nothing")
    assert customer.call("POST", f"{v}/my/spins/{checkin['ticket_id']}/spin", {})["duplicate"] is True
    step("check-in qua IP quán, quay thưởng một lần cho mỗi vé")

    today = datetime.now().astimezone().date().isoformat()
    report = owner.call("GET", f"{v}/reports/revenue?date_from={(datetime.now().astimezone().date() - timedelta(days=1)).isoformat()}&date_to={today}")
    assert report["totals"]["revenue"] == paid["amount_vnd"] and report["totals"]["sessions"] == 1
    staff.call("GET", f"{v}/reports/revenue", expect=403)
    csv_text = owner.call("GET", f"{v}/reports/export.csv?date_from={today}&date_to={today}")
    assert "Tổng hoá đơn" in csv_text
    assert staff.call("GET", f"{v}/revenue/today")["total_vnd"] == paid["amount_vnd"]
    step("báo cáo khớp hoá đơn, nhân viên chỉ xem doanh thu hôm nay, xuất CSV")

    audit = admin.call("GET", "/api/admin/audit?limit=200")
    actions = {row["action"] for row in audit}
    assert {"venue_created", "session_paid", "checkin", "wheel_spin", "booking_created", "report_exported"} <= actions
    step("nhật ký audit ghi đủ các thao tác chính")


if __name__ == "__main__":
    sys.exit(main())
