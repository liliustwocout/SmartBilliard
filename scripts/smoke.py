"""Real-process HTTP/WebSocket smoke check using an isolated temporary database."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8001"


def api(path, body=None):
    request = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                      headers={"Content-Type": "application/json"} if body is not None else {})
    with urlopen(request, timeout=3) as response:
        return json.load(response)


def main():
    assert (ROOT / "apps/web/dist/index.html").exists(), "Build web first: cd apps/web; npm run build"
    # Avoid accidentally testing or writing to an existing service on the smoke-test port.
    try:
        api("/api/health")
    except (URLError, TimeoutError):
        pass
    else:
        raise RuntimeError("Port 8001 already has a service. Stop it or use another test environment.")
    with tempfile.TemporaryDirectory(prefix="smartbilliard-smoke-") as folder:
        temporary = Path(folder)
        config = temporary / "decision.toml"
        config.write_text('presence_seconds = 0.3\nmax_observation_gap_seconds = 2.5\n', encoding="utf-8")
        environment = {**os.environ, "DATABASE_URL": f"sqlite:///{temporary / 'smoke.db'}",
                       "DECISION_CONFIG": str(config), "SIMULATION_ENABLED": "true",
                       "AUTO_OPEN_ENABLED": "false", "TABLE_COUNT": "4", "HOURLY_RATE_VND": "60000"}
        with (temporary / "server.log").open("w+", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, "-m", "uvicorn", "apps.api.main:app",
                                        "--host", "127.0.0.1", "--port", "8001"], cwd=ROOT,
                                       env=environment, stdout=log, stderr=log,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                deadline = time.monotonic() + 15
                while True:
                    try:
                        assert api("/api/health")["phase"] == 2
                        break
                    except (URLError, TimeoutError):
                        if time.monotonic() > deadline or process.poll() is not None:
                            raise RuntimeError("API failed to start")
                        time.sleep(.1)
                with urlopen(BASE, timeout=3) as response:
                    assert b'<div id="root">' in response.read()
                with connect("ws://127.0.0.1:8001/ws", open_timeout=3) as socket:
                    assert json.loads(socket.recv(timeout=3))["active_count"] == 0
                    for _ in range(5):
                        result = api("/api/simulations/observations", {
                            "event_id": str(uuid4()), "table_id": 1, "present": True, "confidence": .9})
                        time.sleep(.1)
                    assert result["state"] == "NEEDS_CONFIRMATION" and not result["session_id"]
                    session = api("/api/tables/1/open", {})
                    assert session["evidence_source"] == "SIMULATED"
                    assert api("/api/tables/1/open", {})["id"] == session["id"]
                    for _ in range(15):
                        frame = json.loads(socket.recv(timeout=3))
                        if frame["active_count"] == 1:
                            break
                    assert frame["tables"][0]["session"]["id"] == session["id"]
                    assert api(f"/api/sessions/{session['id']}/quote")["hourly_rate_snapshot"] == 60000
                    # Exercise the CLI publisher as well as direct HTTP ingestion.
                    cli = subprocess.run([sys.executable, "scripts/simulate.py", "--table", "2",
                                          "--seconds", "1", "--url", BASE], cwd=ROOT,
                                         capture_output=True, text=True, timeout=10)
                    assert cli.returncode == 0 and "SIMULATED" in cli.stdout, cli.stderr
                    paid = api(f"/api/sessions/{session['id']}/checkout", {})
                    assert paid["status"] == "PAID" and isinstance(paid["total_amount"], int)
                    assert api(f"/api/sessions/{session['id']}/checkout", {}) == paid
                    assert api("/api/sessions")[0]["id"] == session["id"]
                    assert api("/api/dashboard")["revenue_vnd"] == paid["total_amount"]
                print("PASS: static web, real HTTP/WS, simulated FSM, CLI, confirmation, billing, history, idempotency.")
                print("No camera inference or AI accuracy was tested.")
            except Exception:
                log.flush()
                log.seek(0)
                print(log.read(), file=sys.stderr)
                raise
            finally:
                if os.name == "nt" and process.poll() is None:
                    # Windows venv launches a child interpreter; terminate the owned tree.
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   capture_output=True, check=True)
                elif process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    main()
