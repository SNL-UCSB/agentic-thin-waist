"""
Individual receive-only Zoom receiver for ONE room slot.

One OS process = one (ROOM_INDEX, SLOT_INDEX) = serial walk of that slot's CTP shard.
Each CTP is submitted as a single /intent (max_parallel_workers=1), polled until done,
then logged. Multiple processes run independently — no synchronization across slots or
rooms. This is the "individual" execution model from the plan.

Sharding formula (R = ROOM_INDEX, S = SLOT_INDEX, both 1-based):
    g           = (R - 1) + (S - 1) * NUM_ROOMS
    total       = NUM_ROOMS * SLOTS_PER_ROOM
    my_ctps     = master[g :: total]

Phase 1 (SLOTS_PER_ROOM=1):
    room1 slot1 → master[0::5]   (~1999 CTPs from 9994-line list)
    room2 slot1 → master[1::5]
    …

Key differences from batch sweep (sweep_rooms_receive.py):
  - 1 CTP per /intent (not 10 in ctp_list fan-out)
  - ctp_name context override (not a shared CTP_LIST_FILE rewrite)
  - Receive-only (fake_media=False), display name Henry
  - 30 s hold (ZOOM_WAIT_SECONDS default 30, not 60)
  - Intended to use per-room orchestrators 8016-8020

Key differences from async_room_worker.py:
  - Uses SLOT_INDEX / SLOTS_PER_ROOM naming (not WORKER_INDEX / WORKERS_PER_ROOM)
  - Default orchestrator is 8015+ROOM_INDEX (8016-8020, shared with batch sweep)
  - Default master list is master_cosine_10000_10mbps.txt (full 9994-CTP corpus)
  - ZOOM_WAIT_SECONDS defaults to 30 seconds
  - Resume log named room{R}_slot{S}.jsonl

Env-var overrides:
    ROOM_INDEX           1-based room number (default 1)
    SLOT_INDEX           1-based slot number within this room (default 1)
    NUM_ROOMS            total rooms (default 5)
    SLOTS_PER_ROOM       total slots per room (default 1); increase when scaling
    ROOMS_ENV_FILE       path to rooms.env (default: alongside broadcast_room.py)
    MASTER_CTP_LIST      master CTP list file
                         (default: .../master_cosine_10000_10mbps.txt)
    ORCH_URL             orchestrator base URL
                         (default: http://localhost:<8015+ROOM_INDEX>)
    ZOOM_DISPLAY_NAME    display name shown in Zoom (default: Henry)
    ZOOM_WAIT_SECONDS    seconds to stay in meeting (default: 30)
    ZOOM_CAPACITY_MBPS   bottleneck capacity (default: 10)
    ZOOM_LATENCY_MS      one-way latency (default: 10)
    ZOOM_QDISC           queuing discipline (default: pfifo)
    SWEEP_LIMIT          max CTPs this invocation, 0 = no limit (default: 0)
    SWEEP_LOG            JSONL progress/resume file
                         (default: ./logs/room{R}_slot{S}.jsonl)
    POLL_INTERVAL_SECONDS (default: 10)
    TIMEOUT_SECONDS      per-experiment wall clock (default: 600)
"""

import json
import os
import pathlib
import random
import sys
import time

try:
    import requests
except ImportError:
    print("requests not installed.  Run: pip install requests")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Load rooms.env (meeting IDs + passcodes)
# ---------------------------------------------------------------------------

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
_SCRIPTS_DIR = _SCRIPT_DIR.parent / "services" / "orchestration" / "scripts"

_DEFAULT_ROOMS_ENV  = _SCRIPTS_DIR / "rooms.env"
_DEFAULT_MASTER     = _SCRIPTS_DIR / "master_cosine_10000_10mbps.txt"

_load_rooms_env(os.getenv("ROOMS_ENV_FILE", str(_DEFAULT_ROOMS_ENV)))

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOM_INDEX     = int(os.getenv("ROOM_INDEX",     "1"))
SLOT_INDEX     = int(os.getenv("SLOT_INDEX",     "1"))
NUM_ROOMS      = int(os.getenv("NUM_ROOMS",      "5"))
SLOTS_PER_ROOM = int(os.getenv("SLOTS_PER_ROOM", "1"))

MEETING_ID = os.getenv(f"ROOM{ROOM_INDEX}_MEETING_ID", "")
PASSCODE   = os.getenv(f"ROOM{ROOM_INDEX}_PASSCODE",   "")

ORCH_URL       = os.getenv("ORCH_URL", f"http://localhost:{8015 + ROOM_INDEX}").rstrip("/")
POLL_INTERVAL  = float(os.getenv("POLL_INTERVAL_SECONDS", "10"))
TIMEOUT        = float(os.getenv("TIMEOUT_SECONDS", "600"))
# Longer per-request poll timeout + jitter so N receivers sharing one
# orchestrator don't hammer it in lockstep (and a transient slow response
# isn't an instant failure).
POLL_HTTP_TIMEOUT = float(os.getenv("POLL_HTTP_TIMEOUT_SECONDS", "30"))
POLL_JITTER       = float(os.getenv("POLL_JITTER", "0.4"))  # +/- fraction of POLL_INTERVAL


def _jittered(interval: float) -> float:
    if POLL_JITTER <= 0:
        return interval
    return max(0.5, interval * (1.0 + random.uniform(-POLL_JITTER, POLL_JITTER)))

DISPLAY_NAME = os.getenv("ZOOM_DISPLAY_NAME", "Henry")
WAIT_SECONDS = int(os.getenv("ZOOM_WAIT_SECONDS", "30"))   # 30 s (not 60)
CAPACITY     = float(os.getenv("ZOOM_CAPACITY_MBPS", "10"))
LATENCY      = int(os.getenv("ZOOM_LATENCY_MS",    "10"))
QDISC        = os.getenv("ZOOM_QDISC", "pfifo")

MASTER_CTP_LIST = os.getenv("MASTER_CTP_LIST", str(_DEFAULT_MASTER))
SWEEP_LIMIT     = int(os.getenv("SWEEP_LIMIT", "0"))
SWEEP_LOG       = os.getenv(
    "SWEEP_LOG",
    str(_SCRIPT_DIR / "logs" / f"room{ROOM_INDEX}_slot{SLOT_INDEX}.jsonl"),
)

TERMINAL_STATUSES = {"complete", "failed", "partial"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_master() -> list[str]:
    p = pathlib.Path(MASTER_CTP_LIST)
    if not p.exists():
        print(f"[r{ROOM_INDEX}s{SLOT_INDEX}] master list not found: {MASTER_CTP_LIST}")
        sys.exit(1)
    return [ln.strip() for ln in p.read_text().splitlines() if ln.strip()]


def _load_done() -> set[str]:
    done: set[str] = set()
    p = pathlib.Path(SWEEP_LOG)
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


def _append_log(record: dict) -> None:
    pathlib.Path(SWEEP_LOG).parent.mkdir(parents=True, exist_ok=True)
    with open(SWEEP_LOG, "a") as fh:
        fh.write(json.dumps(record) + "\n")


def build_intent() -> str:
    """NL intent in the style of sweep_zoom_av_10ms.py, adapted for receive-only."""
    return (
        f"Join Zoom meeting ID {MEETING_ID} with passcode {PASSCODE}, "
        f"display name {DISPLAY_NAME!r}, as a receive-only participant: connect "
        f"computer audio to receive sound but stay muted and do NOT start video. "
        f"Stay for {WAIT_SECONDS} seconds. "
        f"Use a {CAPACITY} Mbps bottleneck with {LATENCY} ms latency, "
        f"{QDISC} AQM policy, 1 trial."
    )


def _submit(ctp_name: str) -> str:
    payload = {
        "intent": build_intent(),
        "context": {
            "application": "zoom",
            "applications": ["zoom"],
            "application_type": "browser",
            "ctp_name": ctp_name,      # per-CTP pin; no shared list file needed
            "capacities":       [CAPACITY],
            "latencies":        [LATENCY],
            "cc_algorithms":    ["cubic"],
            "aqm_policy":       QDISC,
            "duration_seconds": WAIT_SECONDS,
            "fake_media":       False,  # receive-only: no camera/mic
            "workflow_parameters": {
                "meeting_id": MEETING_ID,
                "passcode": PASSCODE,
                "display_name": DISPLAY_NAME,
                "wait_seconds": WAIT_SECONDS,
            },
        },
        "preferences": {
            "max_parallel_workers": 1,
            "use_examples": True,
            "bypass_llm": True,
        },
        "workflow_id":     "run_zoom_receive_workflow",
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
    raise last_exc  # type: ignore[misc]


def _poll(orch_id: str) -> dict:
    deadline = time.time() + TIMEOUT
    last = None
    while time.time() < deadline:
        try:
            r = requests.get(
                f"{ORCH_URL}/orchestration/{orch_id}", timeout=POLL_HTTP_TIMEOUT
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            print(f"    [poll] error: {exc}")
            time.sleep(_jittered(POLL_INTERVAL))
            continue
        status = data.get("status", "unknown")
        if status != last:
            print(f"    [r{ROOM_INDEX}s{SLOT_INDEX}] {orch_id} {last!r} -> {status!r}")
            last = status
        if status in TERMINAL_STATUSES:
            return data
        time.sleep(_jittered(POLL_INTERVAL))
    print(f"    [r{ROOM_INDEX}s{SLOT_INDEX}] TIMEOUT after {TIMEOUT}s")
    return {"status": "timeout"}


def _fetch_summary(orch_id: str) -> dict:
    try:
        r = requests.get(
            f"{ORCH_URL}/orchestration/{orch_id}/results", timeout=POLL_HTTP_TIMEOUT
        )
        r.raise_for_status()
        results = r.json().get("results", []) or []
        if results:
            res = results[0]
            cap = res.get("capture_status") or {}
            return {
                "experiment_id": res.get("experiment_id", ""),
                "status":        res.get("status"),
                "pcap_path":     res.get("pcap_path") or cap.get("pcap_path", ""),
                "capture":       cap.get("status", ""),
            }
    except Exception as exc:
        return {"error": str(exc)}
    return {}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not MEETING_ID or not PASSCODE:
        print(
            f"[r{ROOM_INDEX}s{SLOT_INDEX}] ROOM{ROOM_INDEX}_MEETING_ID / "
            f"ROOM{ROOM_INDEX}_PASSCODE not set.  Check rooms.env."
        )
        sys.exit(1)

    # Preflight: wait for orchestrator to be healthy (it may be warming up)
    healthy = False
    for attempt in range(12):  # up to ~2 min
        try:
            requests.get(f"{ORCH_URL}/health", timeout=10).raise_for_status()
            healthy = True
            break
        except Exception as exc:
            if attempt == 0:
                print(f"[r{ROOM_INDEX}s{SLOT_INDEX}] waiting for {ORCH_URL} … ({exc})")
            time.sleep(10)
    if not healthy:
        print(f"[r{ROOM_INDEX}s{SLOT_INDEX}] {ORCH_URL} unreachable after retries; exiting")
        sys.exit(1)

    # Compute this slot's shard
    master = _load_master()
    total  = NUM_ROOMS * SLOTS_PER_ROOM
    g      = (ROOM_INDEX - 1) + (SLOT_INDEX - 1) * NUM_ROOMS
    my_ctps = master[g::total]

    done    = _load_done()
    pending = [c for c in my_ctps if c not in done]
    if SWEEP_LIMIT > 0:
        pending = pending[:SWEEP_LIMIT]

    print(
        f"[r{ROOM_INDEX}s{SLOT_INDEX}] room={MEETING_ID}  orch={ORCH_URL}\n"
        f"[r{ROOM_INDEX}s{SLOT_INDEX}] shard={len(my_ctps)} done={len(done)} "
        f"pending={len(pending)}  params={CAPACITY}Mbps/{LATENCY}ms/{QDISC}  "
        f"wait={WAIT_SECONDS}s"
    )
    if not pending:
        print(f"[r{ROOM_INDEX}s{SLOT_INDEX}] nothing to do — all CTPs complete.")
        return

    ok = bad = 0
    sweep_start = time.time()

    for idx, ctp in enumerate(pending, 1):
        t0 = time.time()

        # ETA estimate
        if idx > 1:
            elapsed  = t0 - sweep_start
            avg      = elapsed / (idx - 1)
            rem_s    = (len(pending) - idx + 1) * avg
            h, r     = divmod(int(rem_s), 3600)
            m        = r // 60
            eta_msg  = f"  ETA ~{h}h{m:02d}m"
        else:
            eta_msg = ""

        print(
            f"\n{'='*60}\n"
            f"[r{ROOM_INDEX}s{SLOT_INDEX}] CTP {idx}/{len(pending)}: {ctp}{eta_msg}\n"
            f"{'='*60}"
        )

        try:
            orch_id = _submit(ctp)
            print(f"    [r{ROOM_INDEX}s{SLOT_INDEX}] submitted → {orch_id}")
        except Exception as exc:
            print(f"    [r{ROOM_INDEX}s{SLOT_INDEX}] submit FAILED: {exc}")
            _append_log({
                "ctp_name":  ctp,
                "room":      ROOM_INDEX,
                "slot":      SLOT_INDEX,
                "status":    "submit_failed",
                "error":     str(exc),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            bad += 1
            continue

        final   = _poll(orch_id)
        summary = _fetch_summary(orch_id)
        status  = summary.get("status") or final.get("status", "unknown")
        is_ok   = status in ("complete", "success")

        _append_log({
            "ctp_name":      ctp,
            "room":          ROOM_INDEX,
            "slot":          SLOT_INDEX,
            "orch_id":       orch_id,
            "status":        "complete" if is_ok else (status or "failed"),
            "experiment_id": summary.get("experiment_id", ""),
            "pcap_path":     summary.get("pcap_path", ""),
            "capture":       summary.get("capture", ""),
            "elapsed_s":     round(time.time() - t0, 1),
            "timestamp":     time.strftime("%Y-%m-%dT%H:%M:%S"),
            "error":         final.get("error", ""),
        })

        if is_ok:
            ok += 1
            print(
                f"    [r{ROOM_INDEX}s{SLOT_INDEX}] ✓ complete  "
                f"exp={summary.get('experiment_id','')}  "
                f"pcap={bool(summary.get('pcap_path'))}  "
                f"({round(time.time()-t0,1)}s)"
            )
        else:
            bad += 1
            print(f"    [r{ROOM_INDEX}s{SLOT_INDEX}] ✗ {status}  error={final.get('error','')}")

        if idx % 10 == 0 or idx == len(pending):
            print(f"[r{ROOM_INDEX}s{SLOT_INDEX}] progress {idx}/{len(pending)} ok={ok} bad={bad}")

    total_s = time.time() - sweep_start
    h, rem  = divmod(int(total_s), 3600)
    m       = rem // 60
    print(
        f"\n{'='*60}\n"
        f"[r{ROOM_INDEX}s{SLOT_INDEX}] DONE — {ok} succeeded  {bad} failed  "
        f"(wall {h}h{m:02d}m)\n"
        f"[r{ROOM_INDEX}s{SLOT_INDEX}] log: {SWEEP_LOG}\n"
        f"{'='*60}"
    )


if __name__ == "__main__":
    main()
