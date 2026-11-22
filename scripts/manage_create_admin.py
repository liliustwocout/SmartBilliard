"""Tạo tài khoản admin nền tảng đầu tiên cho phòng quản lý.

Mật khẩu lấy từ biến môi trường MANAGE_ADMIN_PASSWORD hoặc nhập khi chạy (không nhận qua tham số dòng lệnh).
Ví dụ:  .venv/Scripts/python scripts/manage_create_admin.py --login admin@example.com --name "Quản trị"
"""
import argparse
import getpass
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from apps.manage_api.auth import audit  # noqa: E402
from apps.manage_api.config import ManageSettings  # noqa: E402
from apps.manage_api.models import Base, User  # noqa: E402
from apps.manage_api.security import hash_password, password_problem  # noqa: E402


def create_admin(database_url: str, login: str, name: str, password: str, must_change: bool = False) -> int:
    problem = password_problem(password)
    if problem:
        raise ValueError(problem)
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    login = login.strip().lower()
    with Session(engine) as db:
        if db.scalar(select(User).where(User.login == login, User.role != "customer")):
            raise ValueError("Tên đăng nhập đã tồn tại.")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        user = User(role="platform_admin", login=login, display_name=name, password_hash=hash_password(password),
                    venue_id=None, must_change_password=must_change, created_at=now)
        db.add(user)
        db.flush()
        audit(db, now, "admin_created", actor=user, target=login, detail={"via": "script"})
        db.commit()
        return user.id


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # console Windows mặc định cp1252 không in được tiếng Việt
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--login", required=True)
    parser.add_argument("--name", default="Quản trị viên")
    parser.add_argument("--must-change-password", action="store_true")
    args = parser.parse_args()
    password = os.environ.get("MANAGE_ADMIN_PASSWORD") or getpass.getpass("Mật khẩu admin: ")
    try:
        user_id = create_admin(ManageSettings.from_env().database_url, args.login, args.name, password, args.must_change_password)
    except ValueError as err:
        sys.exit(f"Lỗi: {err}")
    print(f"Đã tạo admin #{user_id} ({args.login.strip().lower()}).")


if __name__ == "__main__":
    main()
