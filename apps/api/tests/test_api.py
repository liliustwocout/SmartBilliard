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
                        zones_config=str(tmp_path / "zones.json"),
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
    assert data["model_status"]["person"]["loaded"] is False
    assert data["model_status"]["cue"]["validated"] is False


def test_startup_adds_latest_event_index_to_existing_database_without_losing_data(tmp_path):
    import sqlite3

    path = tmp_path / "existing.db"
    settings = Settings(database_url=f"sqlite:///{path}", zones_config=str(tmp_path / "zones.json"))
    with TestClient(create_app(settings, Clock()), base_url="http://127.0.0.1") as client:
        observe(client)
    with sqlite3.connect(path) as db:
        before = db.execute("SELECT count(*) FROM detection_events").fetchone()[0]
        db.execute("DROP INDEX ix_detection_events_latest")
    for _ in range(2):
        with TestClient(create_app(settings, Clock()), base_url="http://127.0.0.1") as client:
            assert client.get("/api/dashboard").status_code == 200
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT count(*) FROM detection_events").fetchone()[0] == before
            plan = db.execute("EXPLAIN QUERY PLAN SELECT id FROM detection_events ORDER BY timestamp DESC, id DESC LIMIT 30").fetchall()
            assert any("ix_detection_events_latest" in row[3] for row in plan)


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


def test_calibration_api_endpoints(client, tmp_path):
    client, _ = client

    # Test GET preview
    resp_preview = client.get("/api/calibration/preview")
    assert resp_preview.status_code == 200
    assert resp_preview.headers["content-type"] == "image/jpeg"
    assert len(resp_preview.content) > 1000

    # Test GET zones
    resp_get = client.get("/api/calibration/zones")
    assert resp_get.status_code == 200
    data = resp_get.json()
    assert "config" in data
    assert "tables" in data["config"]

    # Test POST valid zones
    valid_payload = {
        "camera_id": "cam-test-api",
        "calibration_status": "CALIBRATED",
        "coordinate_system": "normalized_xy_0_1",
        "tables": [
            {
                "table_id": 1,
                "enabled": True,
                "play_polygon": [[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]],
                "standing_polygon": [[0.05, 0.05], [0.35, 0.05], [0.35, 0.35], [0.05, 0.35]],
            }
        ],
    }
    resp_post = client.post("/api/calibration/zones", json=valid_payload)
    assert resp_post.status_code == 200
    assert resp_post.json()["message"] == "Đã lưu cấu hình ROI thành công"
    assert (tmp_path / "zones.json").is_file()

    # Test POST invalid zones (self-intersecting)
    invalid_payload = {
        "camera_id": "cam-test-api",
        "calibration_status": "CALIBRATED",
        "coordinate_system": "normalized_xy_0_1",
        "tables": [
            {
                "table_id": 1,
                "enabled": True,
                "play_polygon": [[0.1, 0.1], [0.4, 0.4], [0.4, 0.1], [0.1, 0.4]],
                "standing_polygon": [[0.05, 0.05], [0.35, 0.05], [0.35, 0.35], [0.05, 0.35]],
            }
        ],
    }
    resp_post_invalid = client.post("/api/calibration/zones", json=invalid_payload)
    assert resp_post_invalid.status_code == 422


def test_camera_event_ingestion_and_provenance(client):
    client, clock = client
    eid = str(uuid4())

    payload = {
        "event_id": eid,
        "table_id": 1,
        "present": True,
        "confidence": 0.88,
        "ambiguous": False,
        "source": "CAMERA",
        "track_ids": [101],
        "people_count": 1,
    }

    # 1. Ingest camera event
    resp = client.post("/api/ingestion/events", json=payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["duplicate"] is False
    assert res_data["source"] == "CAMERA"

    # 2. Replay with identical payload -> idempotent
    resp_replay = client.post("/api/ingestion/events", json=payload)
    assert resp_replay.status_code == 200
    assert resp_replay.json()["duplicate"] is True

    # 3. Conflicting payload with same event_id -> 409 Conflict
    conflict_payload = dict(payload)
    conflict_payload["confidence"] = 0.50
    resp_conflict = client.post("/api/ingestion/events", json=conflict_payload)
    assert resp_conflict.status_code == 409

    # 4. Check events list in dashboard shows CAMERA provenance
    dash = client.get("/api/dashboard").json()
    latest_event = next(e for e in dash["events"] if e["id"] == eid)
    assert latest_event["source"] == "CAMERA"


def test_camera_controls_status_and_lifecycle(client):
    client, _ = client
    resp_status = client.get("/api/camera/status")
    assert resp_status.status_code == 200
    status_data = resp_status.json()
    assert "status" in status_data
    assert "running" in status_data
    assert status_data["models"]["person"]["loaded"] is False
    assert status_data["models"]["cue"]["validated"] is False

    # Stop camera
    resp_stop = client.post("/api/camera/stop")
    assert resp_stop.status_code == 200
    assert resp_stop.json()["status"] == "STOPPED"


def test_camera_frame_endpoint(client):
    client, _ = client
    resp = client.get("/api/camera/frame")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert len(resp.content) > 500
    assert resp.content.startswith(b"\xff\xd8")


def test_two_table_pos_unbilled_play_alert_and_backdate_open(tmp_path):
    clock = Clock()
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'pos2.db'}",
        table_count=2,
        decision=DecisionConfig(
            policy="POSE_AND_CUE",
            presence_seconds=3,
            max_observation_gap_seconds=10,
            absence_grace_seconds=6,
            playing_hold_grace_seconds=25,
            unbilled_alert_seconds=300,
        ),
    )
    with TestClient(create_app(settings, clock), base_url="http://127.0.0.1") as client:
        dash = client.get("/api/dashboard").json()
        assert len(dash["tables"]) == 2
        assert dash["unbilled_alerts"] == []

        # Spectator standing around table 2 does NOT trigger playing or alert
        for _ in range(10):
            observe(client, table_id=2, activity_state="NOT_PLAYING")
            clock.tick(1)
        dash = client.get("/api/dashboard").json()
        assert dash["tables"][1]["ai_activity"] == "NOT_PLAYING"
        assert dash["tables"][1]["unbilled_alert"] is False

        # Player actively plays on table 1 for > 5 minutes (305s) without POS open
        for _ in range(62):
            res, _ = observe(client, table_id=1, activity_state="PLAYING")
            clock.tick(5)

        assert res["unbilled_alert"] is True
        assert res["reason"] == "UNBILLED_PLAY_OVER_5M"

        dash = client.get("/api/dashboard").json()
        t1 = dash["tables"][0]
        assert t1["ai_activity"] == "PLAYING"
        assert t1["unbilled_alert"] is True
        assert t1["unbilled_playing_seconds"] >= 300
        assert len(dash["unbilled_alerts"]) == 1

        # Open table backdated to AI start time -> clears alert and records session duration
        opened = client.post("/api/tables/1/open?backdate_to_ai=true").json()
        assert opened["status"] == "ACTIVE"
        assert opened["billable_minutes"] >= 5
        dash_after = client.get("/api/dashboard").json()
        assert dash_after["unbilled_alerts"] == []
        assert dash_after["tables"][0]["unbilled_alert"] is False


def test_web_video_upload_automation_and_dataset_extract(tmp_path):
    import cv2
    import numpy as np

    clock = Clock()
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'video_web.db'}", table_count=2)

    # Create a small synthetic 2-second MP4 clip in memory/disk to upload
    src_mp4 = tmp_path / "client_clip.mp4"
    writer = cv2.VideoWriter(str(src_mp4), cv2.VideoWriter_fourcc(*"mp4v"), 6.0, (320, 240))
    for i in range(12):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.rectangle(frame, (15 + i * 10, 40), (75 + i * 10, 120), (60, 190, 90), -1)
        writer.write(frame)
    writer.release()
    mp4_bytes = src_mp4.read_bytes()

    with TestClient(create_app(settings, clock), base_url="http://127.0.0.1") as client:
        # 1. Reject empty or unsupported upload
        assert client.post("/api/videos/upload?filename=bad.txt", content=b"hello").status_code == 400
        assert client.post("/api/videos/upload?filename=empty.mp4", content=b"").status_code == 400

        # 2. Upload MP4 -> auto-activates CameraRunner + runs fast-forward evaluation
        up = client.post(
            "/api/videos/upload?filename=match_test.mp4&auto_start=true&auto_evaluate=true",
            content=mp4_bytes,
        )
        assert up.status_code == 200, up.text
        up_data = up.json()
        assert up_data["filename"] == "match_test.mp4"
        assert up_data["size_bytes"] == len(mp4_bytes)
        assert up_data["live_started"] is True
        assert up_data["evaluation"]["processed_frames"] >= 10

        # 3. Video list shows active video
        listing = client.get("/api/videos").json()
        assert any(v["filename"] == "match_test.mp4" and v["active"] for v in listing["videos"])

        # 4. Calibration preview renders frame from uploaded video
        preview = client.get("/api/calibration/preview")
        assert preview.status_code == 200 and preview.content.startswith(b"\xff\xd8")

        # 5. Extract training dataset frames from uploaded video via web endpoint
        ext = client.post("/api/videos/extract-dataset", json={"filename": "match_test.mp4", "interval": 0.5})
        assert ext.status_code == 200, ext.text
        assert ext.json()["total_images"] >= 2

        # 6. 1-click generate demo video + activate + evaluate
        demo = client.post("/api/videos/generate-demo", json={"duration_seconds": 2.5})
        assert demo.status_code == 200, demo.text
        demo_data = demo.json()
        assert demo_data["filename"] == "demo_auto.mp4"
        assert demo_data["live_started"] is True
        assert demo_data["evaluation"]["processed_frames"] >= 10

        # 7. Switch back to match_test.mp4 & stop cleanly
        act = client.post("/api/videos/activate", json={"filename": "match_test.mp4"})
        assert act.status_code == 200 and act.json()["success"] is True
        del_demo = client.post("/api/videos/delete", json={"filename": "demo_auto.mp4"})
        assert del_demo.status_code == 200
        assert del_demo.json() == {"deleted": True, "filename": "demo_auto.mp4", "stopped_live": False}

        del_active = client.post("/api/videos/delete", json={"filename": "match_test.mp4"})
        assert del_active.status_code == 200
        assert del_active.json() == {"deleted": True, "filename": "match_test.mp4", "stopped_live": True}
        assert client.get("/api/camera/status").json()["running"] is False
        assert client.get("/api/videos").json()["videos"] == []
        assert client.post("/api/videos/delete", json={"filename": "match_test.mp4"}).status_code == 404
        assert client.post("/api/videos/delete", json={"filename": "../secret.mp4"}).status_code == 404





def test_ai_pauses_for_tables_with_open_session_and_resumes_after_checkout(client):
    client, clock = client
    app_runner = client.app.state.runner
    assert app_runner.paused_tables == frozenset()

    session = open_table(client, 1)
    assert app_runner.paused_tables == frozenset({1})
    tables = {t["id"]: t for t in client.get("/api/tables").json()}
    assert tables[1]["ai_paused"] is True and tables[2]["ai_paused"] is False
    assert client.get("/api/camera/status").json()["paused_tables"] == [1]

    open_table(client, 2)
    assert app_runner.paused_tables == frozenset({1, 2})

    clock.tick(60)
    assert client.post(f"/api/sessions/{session['id']}/checkout").status_code == 200
    assert app_runner.paused_tables == frozenset({2})
    assert {t["id"]: t["ai_paused"] for t in client.get("/api/tables").json()}[1] is False


def test_auto_open_pauses_ai_for_that_table(runtime):
    settings, clock = runtime
    with TestClient(create_app(replace(settings, auto_open=True), clock), base_url="http://127.0.0.1") as client:
        for _ in range(6):
            observe(client)
            clock.tick()
        assert client.app.state.runner.paused_tables == frozenset({1})


def test_restart_restores_paused_tables_from_active_sessions(runtime):
    settings, clock = runtime
    with TestClient(create_app(settings, clock), base_url="http://127.0.0.1") as first:
        open_table(first, 1)
    with TestClient(create_app(settings, clock), base_url="http://127.0.0.1") as second:
        assert second.app.state.runner.paused_tables == frozenset({1})


def test_threshold_edit_applies_immediately_persists_and_resets(runtime):
    settings, clock = runtime
    with TestClient(create_app(settings, clock), base_url="http://127.0.0.1") as client:
        view = client.get("/api/settings").json()
        assert view["decision"]["presence_seconds"] == 3 and view["overridden"] == []
        res = client.post("/api/settings", json={"decision": {"presence_seconds": 20, "cooldown_seconds": 5}})
        assert res.status_code == 200, res.text
        assert res.json()["decision"]["presence_seconds"] == 20 and res.json()["overridden"] == ["decision"]
        assert client.get("/api/dashboard").json()["decision_config"]["presence_seconds"] == 20
    # Same database dir -> override survives a restart
    with TestClient(create_app(settings, clock), base_url="http://127.0.0.1") as client:
        assert client.get("/api/settings").json()["decision"]["cooldown_seconds"] == 5
        res = client.post("/api/settings/reset")
        assert res.json()["decision"]["presence_seconds"] == 3 and res.json()["overridden"] == []
    with TestClient(create_app(settings, clock), base_url="http://127.0.0.1") as client:
        assert client.get("/api/settings").json()["decision"]["presence_seconds"] == 3


def test_invalid_thresholds_are_rejected_without_changing_anything(client):
    client, _ = client
    before = client.get("/api/settings").json()["decision"]
    for bad in ({"confidence_enter": .4, "confidence_exit": .6}, {"presence_seconds": 0},
                {"cooldown_seconds": 99999}, {"nope": 1}):
        assert client.post("/api/settings", json={"decision": bad}).status_code == 422
    assert client.get("/api/settings").json()["decision"] == before
    assert client.get("/api/settings").json()["overridden"] == []


def test_auto_open_requires_explicit_confirmation(client):
    client, _ = client
    assert client.post("/api/settings", json={"auto_open": True}).status_code == 422
    assert client.get("/api/dashboard").json()["auto_open_enabled"] is False
    res = client.post("/api/settings", json={"auto_open": True, "confirm_auto_open": True})
    assert res.status_code == 200 and res.json()["auto_open"] is True
    assert client.get("/api/dashboard").json()["auto_open_enabled"] is True
    assert client.post("/api/settings", json={"auto_open": False}).json()["auto_open"] is False


def test_camera_source_edit_masks_credentials_and_keeps_runner_stopped(client):
    client, _ = client
    res = client.post("/api/settings", json={"camera_source": "rtsp://admin:secret@10.0.0.5/stream"})
    assert res.status_code == 200
    assert "secret" not in res.text and "admin:***" in res.json()["camera_source"]
    assert client.get("/api/camera/status").json()["running"] is False
    assert client.post("/api/settings", json={"camera_source": ""}).status_code == 422


def test_table_rate_edit_does_not_change_open_session_price(client):
    client, clock = client
    session = open_table(client, 1)
    assert client.post("/api/tables/1/rate", json={"hourly_rate": 90000}).status_code == 200
    tables = {t["id"]: t for t in client.get("/api/tables").json()}
    assert tables[1]["hourly_rate"] == 90000 and tables[1]["session"]["hourly_rate_snapshot"] == 60000
    assert tables[2]["hourly_rate"] == 60000
    for bad in (-1, 10_000_001):
        assert client.post("/api/tables/1/rate", json={"hourly_rate": bad}).status_code == 422
    assert client.post("/api/tables/99/rate", json={"hourly_rate": 1}).status_code == 404
    assert session["hourly_rate_snapshot"] == 60000


def test_multi_table_roi_calibration_snapshot_status_and_overlaps(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'roi_multi.db'}",
        table_count=4,
        zones_config=str(tmp_path / "zones.json"),
    )
    with TestClient(create_app(settings, Clock()), base_url="http://127.0.0.1") as client:
        multi_payload = {
            "camera_id": "cam-multi",
            "calibration_status": "CALIBRATED",
            "coordinate_system": "normalized_xy_0_1",
            "tables": [
                {
                    "table_id": 1,
                    "enabled": True,
                    "play_polygon": [[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]],
                    "standing_polygon": [[0.05, 0.05], [0.45, 0.05], [0.45, 0.4], [0.05, 0.4]],
                },
                {
                    "table_id": 2,
                    "enabled": True,
                    "play_polygon": [[0.42, 0.1], [0.62, 0.1], [0.62, 0.3], [0.42, 0.3]],
                    "standing_polygon": [[0.35, 0.05], [0.7, 0.05], [0.7, 0.4], [0.35, 0.4]],
                },
                {
                    "table_id": 3,
                    "enabled": False,
                    "play_polygon": [[0.72, 0.1], [0.9, 0.1], [0.9, 0.3], [0.72, 0.3]],
                    "standing_polygon": [[0.68, 0.05], [0.95, 0.05], [0.95, 0.4], [0.68, 0.4]],
                },
            ],
        }
        save_res = client.post("/api/calibration/zones", json=multi_payload)
        assert save_res.status_code == 200, save_res.text
        overlaps = save_res.json()["overlaps"]
        assert len(overlaps) == 1
        assert {overlaps[0]["table_a"], overlaps[0]["table_b"]} == {1, 2}

        dash_tables = {t["id"]: t for t in client.get("/api/dashboard").json()["tables"]}
        assert dash_tables[1]["roi_calibrated"] is True and dash_tables[1]["roi_enabled"] is True
        assert dash_tables[2]["roi_calibrated"] is True and dash_tables[2]["roi_enabled"] is True
        assert dash_tables[3]["roi_calibrated"] is True and dash_tables[3]["roi_enabled"] is False
        assert dash_tables[4]["roi_calibrated"] is False and dash_tables[4]["roi_enabled"] is False

        session = open_table(client, 1)
        remaining = {**multi_payload, "tables": multi_payload["tables"][1:]}
        assert client.post("/api/calibration/zones", json=remaining).status_code == 200
        assert client.get("/api/calibration/zones").json()["config"] == remaining
        dash_tables = {t["id"]: t for t in client.get("/api/dashboard").json()["tables"]}
        assert dash_tables[1]["roi_calibrated"] is False and dash_tables[1]["roi_enabled"] is False
        assert dash_tables[1]["session"]["id"] == session["id"]
        assert dash_tables[1]["session"]["status"] == "ACTIVE"

        empty = {**multi_payload, "tables": []}
        assert client.post("/api/calibration/zones", json=empty).status_code == 200
        assert client.get("/api/calibration/zones").json()["config"]["tables"] == []
        assert all(not t["roi_calibrated"] for t in client.get("/api/tables").json())


def test_auto_roi_requires_real_frame_and_never_saves_proposals(tmp_path, monkeypatch):
    import base64
    import cv2
    import numpy as np

    zones_path = tmp_path / "zones.json"
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'auto_roi.db'}", zones_config=str(zones_path))
    payload = {"camera_id": "cam-test", "tables": []}
    with TestClient(create_app(settings, Clock()), base_url="http://127.0.0.1") as client:
        runner = client.app.state.runner
        assert client.post("/api/calibration/auto-detect", json=payload).status_code == 409
        assert not zones_path.exists()
        frame = np.full((400, 640, 3), 60, dtype=np.uint8)
        cv2.fillConvexPoly(frame, np.array([[100, 150], [500, 170], [480, 320], [80, 290]]), (190, 105, 25))
        with monkeypatch.context() as patch:
            patch.setattr(type(runner), "is_running", property(lambda _: True))
            patch.setattr(type(runner), "status", property(lambda _: "CONNECTED"))
            patch.setattr(runner, "get_latest_frame", lambda: None)
            assert client.post("/api/calibration/auto-detect", json=payload).status_code == 409
            patch.setattr(runner, "get_latest_frame", lambda: frame.copy())
            response = client.post("/api/calibration/auto-detect", json=payload)
            assert response.status_code == 200, response.text
            result = response.json()
            assert result["detected_count"] == 1 and result["updated_table_ids"] == [1]
            assert result["requires_review"] is True
            assert result["captured_at"].endswith("+00:00")
            assert base64.b64decode(result["preview_data_url"].split(",", 1)[1]).startswith(b"\xff\xd8")
            assert not zones_path.exists()
            assert client.get("/api/sessions").json() == []
            saved = client.post("/api/calibration/zones", json=result["config"])
            assert saved.status_code == 200, saved.text
            original_bytes = zones_path.read_bytes()
            again = client.post("/api/calibration/auto-detect", json=result["config"])
            assert again.status_code == 200
            assert zones_path.read_bytes() == original_bytes
            assert client.get("/api/calibration/zones").json()["config"] == result["config"]


def test_dashboard_snapshot_exposes_sanitized_camera_source(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'camera_source.db'}",
        camera_source="rtsp://user:secret@127.0.0.1:554/stream",
    )
    with TestClient(create_app(settings, Clock()), base_url="http://127.0.0.1") as client:
        snap = client.get("/api/dashboard").json()
        assert "camera_source" in snap
        assert "secret" not in snap["camera_source"]
        assert "***" in snap["camera_source"]
        assert "127.0.0.1:554/stream" in snap["camera_source"]

        updated = client.post("/api/settings", json={"camera_source": "demo_match.mp4"})
        assert updated.status_code == 200, updated.text
        assert client.get("/api/dashboard").json()["camera_source"] == "demo_match.mp4"

        reset = client.post("/api/settings/reset")
        assert reset.status_code == 200, reset.text
        restored = client.get("/api/dashboard").json()["camera_source"]
        assert "secret" not in restored and "127.0.0.1:554/stream" in restored


def test_staff_confirmation_preserves_camera_or_video_evidence_source(tmp_path):
    now = [datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)]
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'evidence.db'}",
        auto_open=False,
        decision=DecisionConfig(policy="SMART_STANCE", presence_seconds=2.0),
    )
    with TestClient(create_app(settings, lambda: now[0]), base_url="http://127.0.0.1") as client:
        for table_id, src in ((1, "CAMERA"), (2, "VIDEO")):
            for step in range(4):
                now[0] = now[0] + timedelta(seconds=1)
                res = client.post(
                    "/api/ingestion/events",
                    json={
                        "event_id": str(uuid4()),
                        "table_id": table_id,
                        "present": True,
                        "confidence": 0.9,
                        "activity_state": "PLAYING",
                        "source": src,
                    },
                )
                assert res.status_code == 200, res.text
            opened = client.post(f"/api/tables/{table_id}/open")
            assert opened.status_code == 200, opened.text
            data = opened.json()
            assert data["trigger_source"] == "STAFF_CONFIRMATION"
            assert data["evidence_source"] == src


def test_settings_accept_smart_stance_and_posture_pause_grace(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'smart_settings.db'}")
    with TestClient(create_app(settings, Clock()), base_url="http://127.0.0.1") as client:
        res = client.post(
            "/api/settings",
            json={"decision": {"policy": "SMART_STANCE", "posture_pause_grace_seconds": 7.5}},
        )
        assert res.status_code == 200, res.text
        decision = res.json()["decision"]
        assert decision["policy"] == "SMART_STANCE"
        assert decision["posture_pause_grace_seconds"] == pytest.approx(7.5)

        reset = client.post("/api/settings/reset")
        assert reset.status_code == 200, reset.text
        assert reset.json()["decision"] == res.json()["decision_defaults"]
