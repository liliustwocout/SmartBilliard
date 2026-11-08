from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.billing import quote
from apps.api.config import Settings
from apps.api.main import create_app
from apps.api.models import PlaySession, Table
from services.vision.decision import DecisionConfig


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 8, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def tick(self, seconds=1):
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def runtime(tmp_path):
    clock = Clock()
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}",
                        decision=DecisionConfig(presence_seconds=3))
    return settings, clock


@pytest.fixture
def client(runtime):
    settings, clock = runtime
    with TestClient(create_app(settings, clock), base_url="http://127.0.0.1") as client:
        yield client, clock


def observe(client, table_id=1, **kwargs):
    payload = {"event_id": str(uuid4()), "table_id": table_id, "present": True,
               "confidence": .9, **kwargs}
    response = client.post("/api/simulations/observations", json=payload)
    assert response.status_code == 200, response.text
    return response.json(), payload


def open_table(client, table_id=1):
    response = client.post(f"/api/tables/{table_id}/open")
    assert response.status_code == 200, response.text
    return response.json()


def test_initial_dashboard_has_no_fabricated_sessions(client):
    client, _ = client
    data = client.get("/api/dashboard").json()
    assert len(data["tables"]) == 4 and data["active_count"] == 0
    assert data["revenue_vnd"] == 0 and data["mode"] == "SIMULATED"
    assert data["camera_ready"] is False and data["cue_detector_ready"] is False


def test_simulation_to_staff_confirmation_checkout_and_history(client):
    client, clock = client
    for _ in range(4):
        result, _ = observe(client)
        clock.tick()
    assert result["state"] == "NEEDS_CONFIRMATION"
    assert result["session_id"] is None
    session = open_table(client)
    assert session["trigger_source"] == "STAFF_CONFIRMATION"
    assert session["evidence_source"] == "SIMULATED"
    clock.tick(61)
    checkout = client.post(f"/api/sessions/{session['id']}/checkout").json()
    assert checkout["total_amount"] == 2000 and checkout["billable_minutes"] == 2
    assert checkout["status"] == "PAID" and checkout["ended_at"].endswith("+00:00")
    assert client.get("/api/sessions").json()[0]["id"] == session["id"]
    assert client.get("/api/dashboard").json()["revenue_vnd"] == 2000


def test_duplicate_does_not_accumulate_time_or_create_sessions(client):
    client, clock = client
    result, payload = observe(client)
    clock.tick(20)
    replay = client.post("/api/simulations/observations", json=payload).json()
    assert replay["duplicate"] and replay["state"] == result["state"]
    assert client.get("/api/sessions").json() == []
    payload["confidence"] = .8
    assert client.post("/api/simulations/observations", json=payload).status_code == 409
    assert len(client.get("/api/dashboard").json()["events"]) == 1


def test_automatic_simulated_opening_is_labeled_and_idempotent(runtime):
    settings, clock = runtime
    with TestClient(create_app(replace(settings, auto_open=True), clock), base_url="http://127.0.0.1") as client:
        for _ in range(6):
            result, _ = observe(client)
            clock.tick()
        assert result["state"] == "ACTIVE"
        sessions = client.get("/api/sessions").json()
        assert len(sessions) == 1 and sessions[0]["trigger_source"] == "SIMULATED"


def test_cue_policy_cannot_auto_open_with_fabricated_confidence(runtime):
    settings, clock = runtime
    settings = replace(settings, auto_open=True,
                       decision=DecisionConfig(policy="PERSON_AND_CUE", presence_seconds=2))
    with TestClient(create_app(settings, clock), base_url="http://127.0.0.1") as client:
        for _ in range(4):
            result, _ = observe(client, cue_confidence=1)
            clock.tick()
        assert result["reason"] == "CUE_NOT_READY" and not result["session_id"]


def test_missing_person_does_not_end_active_session(client):
    client, clock = client
    session = open_table(client)
    clock.tick(300)
    observe(client, present=False, confidence=0)
    assert client.get(f"/api/sessions/{session['id']}/quote").json()["status"] == "ACTIVE"


def test_checkout_replay_does_not_close_a_new_session(client):
    client, clock = client
    old = open_table(client)
    clock.tick(61)
    paid = client.post(f"/api/sessions/{old['id']}/checkout").json()
    new = open_table(client)
    assert new["id"] != old["id"]
    clock.tick(120)
    assert client.post(f"/api/sessions/{old['id']}/checkout").json() == paid
    assert client.get("/api/dashboard").json()["active_count"] == 1


def test_manual_and_simulation_races_keep_one_session_per_table(client):
    client, _ = client
    with ThreadPoolExecutor(max_workers=6) as pool:
        ids = list(pool.map(lambda _: open_table(client)["id"], range(12)))
    assert len(set(ids)) == 1
    assert len(client.get("/api/sessions").json()) == 1


def test_database_also_enforces_single_active_session(client):
    client, clock = client
    open_table(client)
    with Session(client.app.state.engine) as db:
        db.add(PlaySession(id=str(uuid4()), table_id=1, started_at=clock(), status="ACTIVE",
                           hourly_rate_snapshot=60000, trigger_source="STAFF"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_rate_snapshot_is_preserved_when_table_rate_changes(client):
    client, clock = client
    session = open_table(client)
    with Session(client.app.state.engine) as db:
        table = db.get(Table, 1)
        table.hourly_rate = 120000
        db.commit()
    clock.tick(60)
    result = client.post(f"/api/sessions/{session['id']}/checkout").json()
    assert result["total_amount"] == 1000 and result["hourly_rate_snapshot"] == 60000


def test_restart_preserves_session_and_decision_memory(runtime):
    settings, clock = runtime
    with TestClient(create_app(settings, clock), base_url="http://127.0.0.1") as first:
        active = open_table(first)
        observe(first, 2)
    clock.tick()
    with TestClient(create_app(settings, clock), base_url="http://127.0.0.1") as second:
        assert open_table(second)["id"] == active["id"]
        observe(second, 2)
        clock.tick()
        observe(second, 2)
        clock.tick()
        result, _ = observe(second, 2)
        assert result["state"] == "NEEDS_CONFIRMATION"


def test_multiple_tables_and_websocket_publish_full_snapshot(client):
    client, _ = client
    with client.websocket_connect("ws://127.0.0.1/ws") as socket:
        assert socket.receive_json()["active_count"] == 0
        for table_id in range(1, 5):
            open_table(client, table_id)
        for _ in range(10):
            data = socket.receive_json()
            if data["active_count"] == 4:
                break
        assert data["active_count"] == 4
        assert all(table["session"] for table in data["tables"])


def test_disabled_simulation_and_local_origin_guards(runtime):
    settings, clock = runtime
    with TestClient(create_app(replace(settings, simulation_enabled=False), clock), base_url="http://127.0.0.1") as client:
        assert client.post("/api/simulations/observations", json={"event_id": str(uuid4()), "table_id": 1}).status_code == 403
        assert client.post("/api/tables/1/open", headers={"Origin": "https://untrusted.example"}).status_code == 403
        assert client.get("/api/health", headers={"Host": "untrusted.example"}).status_code == 400
        assert client.post("/api/tables/1/open", headers={"Origin": "http://127.0.0.1:5173"}).status_code == 200


def test_input_validation_and_missing_resources(client):
    client, _ = client
    for payload in ({"event_id": "bad", "table_id": 1},
                    {"event_id": str(uuid4()), "table_id": 1, "confidence": 1.1},
                    {"event_id": str(uuid4()), "table_id": 1, "timestamp": "2000-01-01"}):
        assert client.post("/api/simulations/observations", json=payload).status_code == 422
    assert client.post("/api/tables/999/open").status_code == 404
    assert client.post("/api/sessions/missing/checkout").status_code == 404
    assert client.get("/api/sessions?limit=501").status_code == 422


def test_cooldown_and_ambiguous_input_cannot_open(client):
    client, clock = client
    for _ in range(4):
        result, _ = observe(client, ambiguous=True)
        clock.tick()
    assert result["state"] == "EMPTY"
    session = open_table(client)
    client.post(f"/api/sessions/{session['id']}/checkout")
    result, _ = observe(client)
    assert result["reason"] == "COOLDOWN" and result["session_id"] is None


@pytest.mark.parametrize(("microseconds", "minutes", "amount"), [
    (0, 0, 0), (1, 1, 1000), (60_000_000, 1, 1000),
    (60_000_001, 2, 2000), (3_600_000_000, 60, 60000),
])
def test_integer_billing_boundaries(microseconds, minutes, amount):
    start = datetime(2026, 11, 8, tzinfo=timezone.utc)
    result = quote(start, start + timedelta(microseconds=microseconds), 60000)
    assert result["billable_minutes"] == minutes and result["amount_vnd"] == amount


def test_dong_rounding_free_rate_and_timezone_conversion():
    start = datetime(2026, 11, 8, tzinfo=timezone.utc)
    end = (start + timedelta(seconds=1)).astimezone(timezone(timedelta(hours=7)))
    assert quote(start, end, 1001)["amount_vnd"] == 17
    assert quote(start, end, 0)["amount_vnd"] == 0
