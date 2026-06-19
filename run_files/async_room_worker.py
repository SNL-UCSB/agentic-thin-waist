"""
Async, INDIVIDUAL receive-only Zoom worker for ONE room (one worker = one process).

Unlike sweep_rooms_receive.py (which fans a single /intent into a synchronized
batch of N receivers that fire together on a minute boundary), this is the
"individual" style of sweep_zoom_av_10ms.py: a single worker that walks its OWN
shard of the master CTP list ONE CTP AT A TIME, submitting a single-experiment
/intent for each and polling until it finishes. Many of these run in parallel
(10 per room) but each is independent — they do NOT run together as a batch.

Key differences vs the existing 10 ms batch sweep (which keeps running too):
  * Network params: 10 Mbps / 100 ms latency (vs 10 ms) — a separate dataset.
  * Receive-only (fake_media=False): no camera/mic, never broadcasts.
  * Per-experiment ``ctp_name`` override (NOT a shared list file) so 50 workers
    never clobber each other's CTP selection.

Sharding (no overlap, full 5000 coverage at 100 ms):
    global index g = (ROOM_INDEX-1)*WORKERS_PER_ROOM + (WORKER_INDEX-1)
    total workers  T = NUM_ROOMS * WORKERS_PER_ROOM
    this worker handles  master[g :: T]

Resume: each worker keeps its own JSONL log and skips CTPs already complete.

Env-var overrides:
    ROOM_INDEX           1-based room number (selects ROOM<i>_MEETING_ID/PASSCODE)
    WORKER_INDEX         1-based worker number within the room (1..WORKERS_PER_ROOM)
    WORKERS_PER_ROOM     workers per room (default 10)
    NUM_ROOMS            rooms in use (default 5)
    ROOMS_ENV_FILE       path to rooms.env (default: ../services/orchestration/scripts/rooms.env)
    MASTER_CTP_LIST      master CTP list file (default: the 5000 cosine list)
    ORCH_URL             orchestrator base URL (default http://localhost:<8015+ROOM_INDEX>)
    ZOOM_DISPLAY_NAME    (default: AsyncR<ROOM>W<WORKER>)
    ZOOM_WAIT_SECONDS    (default 60)
    ZOOM_CAPACITY_MBPS   (default 10)
    ZOOM_LATENCY_MS      (default 100)
    ZOOM_QDISC           (default pfifo)
    SWEEP_LIMIT          max CTPs this invocation (0 = no limit)
    SWEEP_LOG            JSONL progress/resume (default: ./logs/room<r>_worker<w>.jsonl)
    POLL_INTERVAL_SECONDS (default 10)
    TIMEOUT_SECONDS      per-experiment wall clock (default 900)
"""

import json
import os
import pathlib
import sys
import time

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
_DEFAULT_ROOMS_ENV = _SCRIPT_DIR.parent / "services/orchestration/scripts/rooms.env"
_DEFAULT_MASTER = _SCRIPT_DIR.parent / "services/orchestration/scripts/master_cosine_5000.txt"
_load_rooms_env(os.getenv("ROOMS_ENV_FILE", str(_DEFAULT_ROOMS_ENV)))

ROOM_INDEX = int(os.getenv("ROOM_INDEX", "1"))
WORKER_INDEX = int(os.getenv("WORKER_INDEX", "1"))
WORKERS_PER_ROOM = int(os.getenv("WORKERS_PER_ROOM", "10"))
NUM_ROOMS = int(os.getenv("NUM_ROOMS", "5"))

MEETING_ID = os.getenv(f"ROOM{ROOM_INDEX}_MEETING_ID", "")
PASSCODE = os.getenv(f"ROOM{ROOM_INDEX}_PASSCODE", "")

# Async sweep uses the IDLE orchestrators 8021-8025 (the room6-10 orchestrator
# processes, whose broadcasters never joined) so it never contends with the
# batch sweep's web servers on 8016-8020. Meeting IDs travel in the intent, so
# orchestrator "8020+R" cheerfully drives room R's meeting.
ORCH_URL = os.getenv("ORCH_URL", f"http://localhost:{8020 + ROOM_INDEX}").rstrip("/")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL_SECONDS", "10"))
TIMEOUT = float(os.getenv("TIMEOUT_SECONDS", "900"))

DISPLAY_NAME = os.getenv("ZOOM_DISPLAY_NAME", f"AsyncR{ROOM_INDEX}W{WORKER_INDEX}")
WAIT_SECONDS = int(os.getenv("ZOOM_WAIT_SECONDS", "60"))
CAPACITY = int(os.getenv("ZOOM_CAPACITY_MBPS", "10"))
LATENCY = int(os.getenv("ZOOM_LATENCY_MS", "100"))
QDISC = os.getenv("ZOOM_QDISC", "pfifo")

MASTER_CTP_LIST = os.getenv("MASTER_CTP_LIST", str(_DEFAULT_MASTER))
SWEEP_LIMIT = int(os.getenv("SWEEP_LIMIT", "0"))
SWEEP_LOG = os.getenv(
    "SWEEP_LOG",
    str(_SCRIPT_DIR / "logs" / f"room{ROOM_INDEX}_worker{WORKER_INDEX}.jsonl"),
)

TERMINAL_STATUSES = {"complete", "failed", "partial"}


def build_master() -> list[str]:
    p = pathlib.Path(MASTER_CTP_LIST)
    if not p.exists():
        print(f"[w{ROOM_INDEX}.{WORKER_INDEX}] master list not found: {MASTER_CTP_LIST}")
        sys.exit(1)
    return [ln.strip() for ln in p.read_text().splitlines() if ln.strip()]


def load_done(log_path: str) -> set[str]:
    done: set[str] = set()
    p = pathlib.Path(log_path)
    if not p.exists():
        return done
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            if rec.get("status") == "complete":
                done.add(rec["ctp_name"])
        except Exception:
            pass
    return done


def append_log(log_path: str, record: dict) -> None:
    pathlib.Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\n")


def build_intent() -> str:
    return (
        f"Join Zoom meeting ID {MEETING_ID} with passcode {PASSCODE}, "
        f"display name {DISPLAY_NAME!r}, as a receive-only participant: connect "
        f"computer audio to receive sound but stay muted and do NOT start video. "
        f"Stay for {WAIT_SECONDS} seconds. "
        f"Use a {CAPACITY} Mbps bottleneck with {LATENCY} ms latency, "
        f"{QDISC} AQM policy, 1 trial."
    )


def submit(ctp_name: str) -> str:
    payload = {
        "intent": build_intent(),
        "context": {
            "application": "zoom",
            # Per-experiment CTP pin (no shared list file) — safe for many
            # concurrent workers hitting the same orchestrator.
            "ctp_name": ctp_name,
            "capacities": [CAPACITY],
            "latencies": [LATENCY],
            "aqm_policy": QDISC,
            "duration_seconds": WAIT_SECONDS,
            # Receive-only: no fake camera/mic, never broadcasts.
            "fake_media": False,
        },
        "preferences": {"max_parallel_workers": 1, "use_examples": True},
        "workflow_id": "run_zoom_receive_workflow",
        "workflow_source": "library",
    }
    last_exc = None
    for attempt in range(3):
        try:
            r = requests.post(f"{ORCH_URL}/intent", json=payload, timeout=60)
            r.raise_for_status()
            return r.json()["orchestration_id"]
        except Exception as exc:
            last_exc = exc
            time.sleep(5 * (attempt + 1))
    raise last_exc


def poll_until_done(orch_id: str) -> dict:
    deadline = time.time() + TIMEOUT
    last = None
    while time.time() < deadline:
        try:
            r = requests.get(f"{ORCH_URL}/orchestration/{orch_id}", timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            print(f"    [poll] error: {exc}")
            time.sleep(POLL_INTERVAL)
            continue
        status = data.get("status", "unknown")
        if status != last:
            print(f"    [w{ROOM_INDEX}.{WORKER_INDEX}] {orch_id} {last!r} -> {status!r}")
            last = status
        if status in TERMINAL_STATUSES:
            return data
        time.sleep(POLL_INTERVAL)
    return {"status": "timeout"}


def fetch_summary(orch_id: str) -> dict:
    try:
        r = requests.get(f"{ORCH_URL}/orchestration/{orch_id}/results", timeout=15)
        r.raise_for_status()
        results = r.json().get("results", []) or []
        if results:
            res = results[0]
            cap = res.get("capture_status") or {}
            return {
                "experiment_id": res.get("experiment_id", ""),
                "status": res.get("status"),
                "pcap_path": res.get("pcap_path") or cap.get("pcap_path", ""),
                "capture": cap.get("status", ""),
            }
    except Exception as exc:
        return {"error": str(exc)}
    return {}


def main() -> None:
    if not MEETING_ID or not PASSCODE:
        print(f"[w{ROOM_INDEX}.{WORKER_INDEX}] ROOM{ROOM_INDEX} creds missing in rooms.env")
        sys.exit(1)

    # The shared orchestrator can be momentarily busy (dispatching the batch
    # sweep + other async workers), so retry the health gate rather than exiting
    # on the first slow response.
    healthy = False
    for attempt in range(20):  # ~20 x (10s timeout + 5s sleep) up to ~5 min
        try:
            requests.get(f"{ORCH_URL}/health", timeout=10).raise_for_status()
            healthy = True
            break
        except Exception as exc:
            if attempt == 0:
                print(f"[w{ROOM_INDEX}.{WORKER_INDEX}] {ORCH_URL} busy, retrying… ({exc})")
            time.sleep(5)
    if not healthy:
        print(f"[w{ROOM_INDEX}.{WORKER_INDEX}] {ORCH_URL} never became reachable; giving up")
        sys.exit(1)

    master = build_master()
    total_workers = NUM_ROOMS * WORKERS_PER_ROOM
    g = (ROOM_INDEX - 1) * WORKERS_PER_ROOM + (WORKER_INDEX - 1)
    my_ctps = master[g::total_workers]

    done = load_done(SWEEP_LOG)
    pending = [c for c in my_ctps if c not in done]
    if SWEEP_LIMIT > 0:
        pending = pending[:SWEEP_LIMIT]

    print(
        f"[w{ROOM_INDEX}.{WORKER_INDEX}] room={MEETING_ID} orch={ORCH_URL} "
        f"shard={len(my_ctps)} done={len(done)} pending={len(pending)} "
        f"params={CAPACITY}Mbps/{LATENCY}ms/{QDISC}"
    )
    if not pending:
        print(f"[w{ROOM_INDEX}.{WORKER_INDEX}] nothing to do.")
        return

    ok = bad = 0
    for idx, ctp in enumerate(pending, 1):
        t0 = time.time()
        try:
            orch_id = submit(ctp)
        except Exception as exc:
            append_log(SWEEP_LOG, {
                "ctp_name": ctp, "room": ROOM_INDEX, "worker": WORKER_INDEX,
                "status": "submit_failed", "error": str(exc),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            bad += 1
            continue
        final = poll_until_done(orch_id)
        summary = fetch_summary(orch_id)
        status = summary.get("status") or final.get("status", "unknown")
        is_ok = status in ("complete", "success")
        append_log(SWEEP_LOG, {
            "ctp_name": ctp, "room": ROOM_INDEX, "worker": WORKER_INDEX,
            "orch_id": orch_id,
            "status": "complete" if is_ok else (status or "failed"),
            "experiment_id": summary.get("experiment_id", ""),
            "pcap_path": summary.get("pcap_path", ""),
            "elapsed_s": round(time.time() - t0, 1),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "error": final.get("error", ""),
        })
        if is_ok:
            ok += 1
        else:
            bad += 1
        if idx % 10 == 0 or idx == len(pending):
            print(f"[w{ROOM_INDEX}.{WORKER_INDEX}] {idx}/{len(pending)} ok={ok} bad={bad}")

    print(f"[w{ROOM_INDEX}.{WORKER_INDEX}] DONE ok={ok} bad={bad}")


if __name__ == "__main__":
    main()
