"""Sao lưu cơ sở dữ liệu SQLite của phòng quản lý (an toàn khi máy chủ đang chạy).

Dùng API sao lưu của SQLite (nhất quán ngay cả khi có ghi đồng thời), kiểm tra toàn vẹn bản sao, giữ N bản mới nhất.
Khôi phục: DỪNG máy chủ, rồi chép bản sao lưu đè lên `data/manage.db` (xem README). Không bao giờ xoá DB gốc.

Ví dụ:  .venv/Scripts/python scripts/manage_backup.py --keep 14
"""
import argparse
import sqlite3
from contextlib import closing
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.engine import make_url  # noqa: E402

PREFIX = "manage-"


def verify_backup(path: Path) -> int:
    """Trả về số bảng nếu bản sao toàn vẹn; ném lỗi nếu hỏng."""
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as db:  # đóng hẳn để Windows cho phép xoá/xoay vòng tệp
        result = db.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"Bản sao lưu không toàn vẹn: {result}")
        return db.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]


def backup_database(db_path: Path, out_dir: Path, keep: int = 14, now: datetime | None = None) -> Path:
    if not db_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy cơ sở dữ liệu: {db_path}")
    if keep < 1:
        raise ValueError("--keep phải >= 1")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    target = out_dir / f"{PREFIX}{stamp}.db"
    suffix = 1
    while target.exists():  # hai lần sao lưu trong cùng một giây: không ghi đè
        target = out_dir / f"{PREFIX}{stamp}-{suffix}.db"
        suffix += 1
    source = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    try:
        verify_backup(target)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    for old in sorted(out_dir.glob(f"{PREFIX}*.db"), key=lambda p: p.stat().st_mtime, reverse=True)[keep:]:
        old.unlink()
    return target


def main() -> None:
    from apps.manage_api.config import ROOT, ManageSettings

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, help="Đường dẫn tệp .db (mặc định lấy từ MANAGE_DATABASE_URL)")
    parser.add_argument("--out", type=Path, help="Thư mục lưu bản sao (mặc định data/backups cạnh DB)")
    parser.add_argument("--keep", type=int, default=14, help="Số bản sao mới nhất được giữ lại")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    db_path = args.db
    if db_path is None:
        database = make_url(ManageSettings.from_env().database_url).database
        if not database or database == ":memory:":
            sys.exit("Lỗi: cơ sở dữ liệu trong bộ nhớ không sao lưu được.")
        db_path = Path(database) if Path(database).is_absolute() else ROOT / database
    try:
        target = backup_database(db_path, args.out or db_path.parent / "backups", args.keep)
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as err:
        sys.exit(f"Lỗi: {err}")
    print(f"Đã sao lưu: {target} ({target.stat().st_size // 1024} KB, toàn vẹn: OK)")


if __name__ == "__main__":
    main()
