import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.manage_api.config import ManageSettings
from apps.manage_api.main import create_app
from apps.manage_api.models import Base as ManageBase

PACKAGE = Path(__file__).resolve().parents[1]


def make_settings(tmp_path, name="manage.db"):
    return ManageSettings(database_url=f"sqlite:///{tmp_path / name}")


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(make_settings(tmp_path)), base_url="http://127.0.0.1") as c:
        yield c


def test_health_uses_own_database(client, tmp_path):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["app"] == "manage"
    assert (tmp_path / "manage.db").exists()


def test_rejects_unknown_host_and_foreign_origin(client, tmp_path):
    with TestClient(create_app(make_settings(tmp_path, "h.db")), base_url="http://evil.example") as bad:
        assert bad.get("/api/health").status_code == 400
    assert client.post("/api/health", headers={"origin": "http://evil.example"}).status_code == 403


def test_default_database_is_not_the_demo_one():
    assert ManageSettings().database_url.endswith("manage.db")
    with pytest.raises(ValueError):
        ManageSettings(database_url="sqlite:///./data/smartbilliard.db")


def test_settings_validation():
    with pytest.raises(ValueError):
        ManageSettings(database_url="postgresql://x/y")
    with pytest.raises(ValueError):
        ManageSettings(api_port=0)
    with pytest.raises(Exception):
        ManageSettings(timezone="Mars/Base")


def test_ports_differ_from_demo():
    s = ManageSettings()
    assert (s.api_port, s.web_port) == (8100, 5174)
    assert "http://127.0.0.1:5174" in s.allowed_origins
    assert "http://127.0.0.1:5173" not in s.allowed_origins


def test_metadata_is_separate_from_demo():
    from apps.api.models import Base as DemoBase
    assert ManageBase is not DemoBase
    assert ManageBase.metadata is not DemoBase.metadata


def test_manage_code_never_imports_demo_code():
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        if "tests" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(n == "apps.api" or n.startswith("apps.api.") for n in names):
                offenders.append(str(path))
    assert not offenders, offenders
