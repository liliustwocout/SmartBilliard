"""Send clearly labeled synthetic observations; does not read a camera."""
import argparse
import json
import time
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description="SIMULATED observations, not camera detection")
    parser.add_argument("--table", type=int, choices=range(1, 9), default=1)
    parser.add_argument("--seconds", type=int, default=12)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    if not 1 <= args.seconds <= 600:
        parser.error("--seconds must be 1..600")
    deadline = time.monotonic() + args.seconds
    print("SIMULATED ONLY — no camera input", flush=True)
    try:
        while time.monotonic() < deadline:
            payload = {"event_id": str(uuid4()), "table_id": args.table,
                       "present": True, "confidence": .9, "ambiguous": False}
            request = Request(args.url + "/api/simulations/observations",
                              data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=5) as response:
                print(response.read().decode(), flush=True)
            time.sleep(.9)
    except KeyboardInterrupt:
        print("Stopped. Active sessions are NOT closed.")


if __name__ == "__main__":
    main()
