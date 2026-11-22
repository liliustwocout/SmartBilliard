import os
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.manage_api.config import ManageSettings
from apps.manage_api.main import create_app
from apps.manage_api.models import Venue
from scripts.manage_backup import backup_database, verify_backup

NOW = datetime(2026, 11, 22, 10, 0, 0)


@pytest.fixture
def live(tmp_path):
    path = tmp_path / "manage.db"
    app = create_app(ManageSettings(database_url=f"sqlite:///{path}"))
    with TestClient(app, base_url="http://127.0.0.1"):
        with Session(app.state.engine) as db:
            db.add(Venue(name="Quán sao lưu", slug="sao-luu", created_at=NOW))
            db.commit()
        yield app, path


def test_backup_of_a_running_database_is_complete_and_valid(live, tmp_path):
    _, path = live
    copy = backup_database(path, tmp_path / "backups", now=NOW)
    assert copy.name == "manage-20261122-100000.db" and copy != path
    assert verify_backup(copy) >= 5
    with closing(sqlite3.connect(copy)) as db:
        assert db.execute("SELECT name FROM venues").fetchall() == [("Quán sao lưu",)]


def test_backup_never_touches_or_deletes_the_source(live, tmp_path):
    _, path = live
    before = path.stat().st_size
    backup_database(path, tmp_path / "b", keep=1)
    backup_database(path, tmp_path / "b", keep=1, now=NOW + timedelta(seconds=5))
    assert path.exists() and path.stat().st_size == before


def test_same_second_backups_do_not_overwrite_each_other(live, tmp_path):
    _, path = live
    first = backup_database(path, tmp_path / "b", now=NOW)
    second = backup_database(path, tmp_path / "b", now=NOW)
    assert first != second and first.exists() and second.exists() and second.name.endswith("-1.db")


def test_rotation_keeps_only_the_newest(live, tmp_path):
    _, path = live
    out = tmp_path / "b"
    made = []
    for n in range(4):
        made.append(backup_database(path, out, keep=2, now=NOW + timedelta(minutes=n)))
        os.utime(made[-1], (made[-1].stat().st_atime, NOW.timestamp() + n * 60))  # mtime tăng dần để thứ tự xác định
    remaining = sorted(p.name for p in out.glob("manage-*.db"))
    assert remaining == [made[2].name, made[3].name]


def test_backup_is_consistent_while_writes_happen(live, tmp_path):
    app, path = live
    stop = threading.Event()

    def writer():
        n = 0
        while not stop.is_set():
            with Session(app.state.engine) as db:
                db.add(Venue(name=f"V{n}", slug=f"v-{n}", created_at=NOW))
                db.commit()
            n += 1

    thread = threading.Thread(target=writer)
    thread.start()
    try:
        copies = [backup_database(path, tmp_path / "b", keep=10, now=NOW + timedelta(seconds=i)) for i in range(3)]
    finally:
        stop.set()
        thread.join()
    for copy in copies:
        assert verify_backup(copy) >= 5


def test_invalid_inputs_fail_loudly(tmp_path):
    with pytest.raises(FileNotFoundError):
        backup_database(tmp_path / "khong-co.db", tmp_path / "b")
    path = tmp_path / "x.db"
    path.write_bytes(b"")  # tệp SQLite rỗng hợp lệ
    with pytest.raises(ValueError):
        backup_database(path, tmp_path / "b", keep=0)


def test_corrupt_copy_is_detected(tmp_path):
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"day khong phai la sqlite" * 100)
    with pytest.raises(sqlite3.DatabaseError):
        verify_backup(bad)
