"""
Long-lived Zoom broadcaster for ONE room.

Joins the room ONCE (no rejoin) and streams the looping fake WAV audio + MJPEG
video for a very long time (wait_seconds, default 1,000,000 s). The broadcaster
talks DIRECTLY to a dedicated, persistent substrate worker's POST /run, so it
bypasses the orchestration pipeline entirely (no CTP, no capture, no teardown).
The worker must be started with a huge BROWSERLESS_SESSION_TIMEOUT_MS so
browserless does not kill the session mid-broadcast.

Network shaping is effectively "off": a very high capacity and 0 ms latency are
applied just so the worker's shaped browser path is configured.

Run one room (rooms.env is read for ROOM<i>_MEETING_ID / ROOM<i>_PASSCODE):
    ROOM_INDEX=1 python3 services/orchestration/scripts/broadcast_room.py

Key env-var overrides:
    ROOM_INDEX           1-based room number (default 1)
    ROOMS_ENV_FILE       Path to rooms.env (default: alongside this script)
    BROADCASTER_URL      Worker /run base URL (default http://localhost:<8100+ROOM_INDEX>)
    ZOOM_DISPLAY_NAME    (default: Broadcaster<ROOM_INDEX>)
    ZOOM_WAIT_SECONDS    Broadcast duration in seconds (default: 1000000)
    BCAST_CAPACITY_MBPS  (default: 1000)   high capacity ~= unshaped
    BCAST_LATENCY_MS     (default: 0)
    WORKFLOW_FILE        AV workflow JSON (default: config/workflows/run_zoom_av_workflow.json)
"""

import json
import os
import pathlib
import sys

try:
    import requests
except ImportError:
    print("requests not installed. Run: pip install requests")
    sys.exit(1)


def _load_rooms_env(path: str) -> None:
    p = pathlib.Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


_SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent.parent  # services/orchestration/scripts -> repo
_load_rooms_env(os.getenv("ROOMS_ENV_FILE", str(_SCRIPT_DIR / "rooms.env")))

ROOM_INDEX = int(os.getenv("ROOM_INDEX", "1"))
MEETING_ID = os.getenv(f"ROOM{ROOM_INDEX}_MEETING_ID", "")
PASSCODE = os.getenv(f"ROOM{ROOM_INDEX}_PASSCODE", "")

BROADCASTER_URL = os.getenv(
    "BROADCASTER_URL", f"http://localhost:{8100 + ROOM_INDEX}"
).rstrip("/")
DISPLAY_NAME = os.getenv("ZOOM_DISPLAY_NAME", f"Broadcaster{ROOM_INDEX}")
WAIT_SECONDS = int(os.getenv("ZOOM_WAIT_SECONDS", "1000000"))
CAPACITY = float(os.getenv("BCAST_CAPACITY_MBPS", "1000"))
LATENCY = float(os.getenv("BCAST_LATENCY_MS", "0"))

DEFAULT_WF = (
    _REPO_ROOT
    / "services/orchestration/app/config/workflows/run_zoom_av_workflow.json"
)
WORKFLOW_FILE = os.getenv("WORKFLOW_FILE", str(DEFAULT_WF))


def load_workflow() -> dict:
    wf = json.loads(pathlib.Path(WORKFLOW_FILE).read_text())
    wf.pop("id", None)  # substrate /run schema rejects unknown top-level keys
    return wf


def main() -> None:
    if not MEETING_ID or not PASSCODE:
        print(
            f"[bcast] ROOM{ROOM_INDEX}_MEETING_ID / ROOM{ROOM_INDEX}_PASSCODE not set. "
            f"Check rooms.env or ROOM_INDEX."
        )
        sys.exit(1)

    try:
        h = requests.get(f"{BROADCASTER_URL}/health", timeout=10)
        h.raise_for_status()
        print(f"[bcast] Broadcaster worker {BROADCASTER_URL} healthy")
    except Exception as exc:
        print(f"[bcast] Cannot reach broadcaster worker at {BROADCASTER_URL}: {exc}")
        sys.exit(1)

    payload = {
        "workflow": load_workflow(),
        "runtime": "browser",
        "parameters": {
            "meeting_id": MEETING_ID,
            "passcode": PASSCODE,
            "display_name": DISPLAY_NAME,
            "wait_seconds": str(WAIT_SECONDS),
        },
        # High capacity / no latency: just configures the shaped browser path.
        "download_mbps": CAPACITY,
        "upload_mbps": CAPACITY,
        "latency_ms": LATENCY,
        "qdisc": "pfifo",
        "verify_shaping": False,
        "cca": "cubic",
        "cca_namespace": "ns1",
    }

    print(
        f"[bcast] Room {ROOM_INDEX}  meeting={MEETING_ID}  "
        f"display={DISPLAY_NAME!r}  wait={WAIT_SECONDS}s  -> POST {BROADCASTER_URL}/run"
    )
    print("[bcast] This call blocks for the full broadcast duration. Run it backgrounded.")
    # The /run call blocks for the entire broadcast; give requests an effectively
    # unbounded read timeout (connect timeout stays short).
    try:
        r = requests.post(
            f"{BROADCASTER_URL}/run",
            json=payload,
            timeout=(30, WAIT_SECONDS + 600),
        )
        print(f"[bcast] /run returned HTTP {r.status_code}: {r.text[:500]}")
    except requests.exceptions.ReadTimeout:
        print("[bcast] /run read-timeout reached (broadcast duration elapsed).")
    except Exception as exc:
        print(f"[bcast] /run error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
