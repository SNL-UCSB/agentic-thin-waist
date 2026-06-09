"""
Receive-only Zoom sweep for ONE room, fanning out CTPs in parallel batches.

Design (minimal-code fan-out, no per-CTP list files):
  * The master CTP list is built once from ORCH_LOCAL_CTP_ROOT/download/*.pcap
    (intersected with upload/) and sharded across rooms:
        room i (1-based) handles  master[i-1 :: NUM_ROOMS]
    so the N rooms jointly cover every CTP with no overlap.
  * For each batch of BATCH_SIZE CTPs the script submits ONE /intent whose
    request.context carries an explicit ``ctp_list``. The orchestrator's
    experiment generator fans that single intent into len(batch) experiments,
    each pinned to a distinct CTP via ``ctp_name`` (resolved directly from
    ORCH_LOCAL_CTP_ROOT — no list file). ``max_parallel_workers`` is set to the
    batch size so the whole batch runs concurrently.
  * Each experiment joins the SAME room meeting receive-only (muted, no video),
    receiving the broadcaster's looping A/V under 10 Mbps / 10 ms shaping while
    its assigned CTP is replayed as background cross-traffic.
  * Progress is logged per-CTP to a JSONL file for resume.

Run one room (after `source rooms.env` or with rooms.env beside this script):
    ROOM_INDEX=1 python3 services/orchestration/scripts/sweep_rooms_receive.py

Key env-var overrides:
    ROOM_INDEX            1-based room number (selects ROOM<i>_MEETING_ID/PASSCODE)
    NUM_ROOMS            Total rooms the master list is sharded across (default: rooms.env)
    ROOMS_ENV_FILE       Path to rooms.env (default: alongside this script)
    BATCH_SIZE           CTPs (== parallel receivers) per /intent (default: 10)
    SWEEP_LIMIT          Max CTPs to run this invocation (0 = no limit)
    ZOOM_DISPLAY_NAME    (default: Receiver<ROOM_INDEX>)
    ZOOM_WAIT_SECONDS    (default: 60)
    ZOOM_CAPACITY_MBPS   (default: 10)
    ZOOM_LATENCY_MS      (default: 10)
    ZOOM_QDISC           (default: pfifo)
    CTP_ROOT             (default: /mnt/md0/haarika)  download/ + upload/ live here
    MASTER_CTP_LIST      Optional explicit master list file (one CTP name/line)
    SWEEP_LOG            JSONL progress/resume file (default: ./sweep_rooms_receive_room<i>.jsonl)
    ORCH_URL             (default: http://localhost:8016)  the rooms receiver orchestrator
    POLL_INTERVAL_SECONDS (default: 10)
    TIMEOUT_SECONDS      (default: 1800)  per-batch wall clock
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
        key, val = key.strip(), val.strip()
        # Don't clobber values already set in the real environment.
        os.environ.setdefault(key, val)


_SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
_load_rooms_env(os.getenv("ROOMS_ENV_FILE", str(_SCRIPT_DIR / "rooms.env")))

ROOM_INDEX = int(os.getenv("ROOM_INDEX", "1"))
NUM_ROOMS = int(os.getenv("NUM_ROOMS", "5"))

MEETING_ID = os.getenv(f"ROOM{ROOM_INDEX}_MEETING_ID", "")
PASSCODE = os.getenv(f"ROOM{ROOM_INDEX}_PASSCODE", "")

ORCH_URL = os.getenv("ORCH_URL", "http://localhost:8016").rstrip("/")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL_SECONDS", "10"))
TIMEOUT = float(os.getenv("TIMEOUT_SECONDS", "1800"))

DISPLAY_NAME = os.getenv("ZOOM_DISPLAY_NAME", f"Receiver{ROOM_INDEX}")
WAIT_SECONDS = int(os.getenv("ZOOM_WAIT_SECONDS", "60"))
CAPACITY = int(os.getenv("ZOOM_CAPACITY_MBPS", "10"))
LATENCY = int(os.getenv("ZOOM_LATENCY_MS", "10"))
QDISC = os.getenv("ZOOM_QDISC", "pfifo")

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))
SWEEP_LIMIT = int(os.getenv("SWEEP_LIMIT", "0"))
CTP_ROOT = os.getenv("CTP_ROOT", "/mnt/md0/haarika")
MASTER_CTP_LIST = os.getenv("MASTER_CTP_LIST", "")
SWEEP_LOG = os.getenv("SWEEP_LOG", f"./sweep_rooms_receive_room{ROOM_INDEX}.jsonl")

TERMINAL_STATUSES = {"complete", "failed", "partial"}


def build_master_ctps() -> list[str]:
    if MASTER_CTP_LIST and pathlib.Path(MASTER_CTP_LIST).exists():
        names = [
            ln.strip()
            for ln in pathlib.Path(MASTER_CTP_LIST).read_text().splitlines()
            if ln.strip()
        ]
        return sorted(set(names))
    dl = pathlib.Path(CTP_ROOT) / "download"
    ul = pathlib.Path(CTP_ROOT) / "upload"
    dl_names = {p.stem for p in dl.glob("*.pcap")}
    ul_names = {p.stem for p in ul.glob("*.pcap")}
    return sorted(dl_names & ul_names)


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


def submit_batch(ctps: list[str]) -> str:
    payload = {
        "intent": build_intent(),
        "context": {
            "application": "zoom",
            "ctp_list": ctps,
            "capacities": [CAPACITY],
            "latencies": [LATENCY],
            "aqm_policy": QDISC,
            "duration_seconds": WAIT_SECONDS,
            # Receive-only: no fake camera/mic on the worker, so receivers never
            # broadcast audio or video.
            "fake_media": False,
        },
        "preferences": {
            "max_parallel_workers": len(ctps),
            "use_examples": True,
        },
        "workflow_id": "run_zoom_receive_workflow",
        "workflow_source": "library",
    }
    r = requests.post(f"{ORCH_URL}/intent", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["orchestration_id"]


def poll_until_done(orch_id: str) -> dict:
    deadline = time.time() + TIMEOUT
    last_status = None
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
        if status != last_status:
            print(f"    [poll] {orch_id}  status: {last_status!r} -> {status!r}")
            last_status = status
        if status in TERMINAL_STATUSES:
            return data
        time.sleep(POLL_INTERVAL)
    print(f"    [poll] TIMEOUT after {TIMEOUT}s")
    return {"status": "timeout"}


def fetch_results(orch_id: str) -> list[dict]:
    try:
        r = requests.get(f"{ORCH_URL}/orchestration/{orch_id}/results", timeout=15)
        r.raise_for_status()
        return r.json().get("results", []) or []
    except Exception as exc:
        print(f"    [results] error: {exc}")
        return []


def main() -> None:
    if not MEETING_ID or not PASSCODE:
        print(
            f"[rooms] ROOM{ROOM_INDEX}_MEETING_ID / ROOM{ROOM_INDEX}_PASSCODE not set. "
            f"Check rooms.env or ROOM_INDEX."
        )
        sys.exit(1)

    try:
        r = requests.get(f"{ORCH_URL}/health", timeout=5)
        r.raise_for_status()
        print(f"[rooms] Orchestration service at {ORCH_URL} is healthy")
    except Exception as exc:
        print(f"[rooms] Cannot reach {ORCH_URL}/health: {exc}")
        sys.exit(1)

    master = build_master_ctps()
    if not master:
        print(f"[rooms] No CTPs found under {CTP_ROOT}/download and /upload")
        sys.exit(1)

    my_ctps = master[ROOM_INDEX - 1 :: NUM_ROOMS]
    done = load_done(SWEEP_LOG)
    pending = [c for c in my_ctps if c not in done]
    if SWEEP_LIMIT > 0:
        pending = pending[:SWEEP_LIMIT]

    print(f"\n[rooms] Room {ROOM_INDEX}/{NUM_ROOMS}  meeting={MEETING_ID}")
    print(f"[rooms] Master CTPs:  {len(master)}")
    print(f"[rooms] This room's shard: {len(my_ctps)}")
    print(f"[rooms] Already done: {len(done)}")
    print(f"[rooms] To run now:   {len(pending)}")
    print(f"[rooms] Batch size:   {BATCH_SIZE} (parallel receivers per /intent)")
    print(f"[rooms] Parameters:   {CAPACITY} Mbps  {LATENCY} ms  {QDISC}  wait={WAIT_SECONDS}s")
    print(f"[rooms] Progress log: {SWEEP_LOG}\n")

    if not pending:
        print("[rooms] Nothing to do — all CTPs for this room already complete.")
        return

    succeeded = failed = 0
    sweep_start = time.time()
    batches = [pending[i : i + BATCH_SIZE] for i in range(0, len(pending), BATCH_SIZE)]

    for bi, batch in enumerate(batches, 1):
        t0 = time.time()
        print(
            f"\n{'='*62}\n[rooms] Batch {bi}/{len(batches)}  "
            f"({len(batch)} CTPs): {batch[0]} ... {batch[-1]}\n{'='*62}"
        )
        try:
            orch_id = submit_batch(batch)
            print(f"    [rooms] Submitted -> orch_id={orch_id}")
        except Exception as exc:
            print(f"    [rooms] Submit FAILED: {exc}")
            for ctp in batch:
                append_log(
                    SWEEP_LOG,
                    {
                        "ctp_name": ctp,
                        "room": ROOM_INDEX,
                        "status": "submit_failed",
                        "error": str(exc),
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    },
                )
                failed += 1
            continue

        final = poll_until_done(orch_id)
        results = fetch_results(orch_id)
        elapsed_s = round(time.time() - t0, 1)

        # Map each experiment result back to its CTP id.
        by_ctp: dict[str, dict] = {}
        for res in results:
            ctp = (res.get("ctp_selected") or {}).get("ctp_id")
            if ctp:
                by_ctp[ctp] = res

        for ctp in batch:
            res = by_ctp.get(ctp, {})
            cap = res.get("capture_status") or {}
            status = res.get("status") or final.get("status", "unknown")
            ok = status == "success" or status == "complete"
            append_log(
                SWEEP_LOG,
                {
                    "ctp_name": ctp,
                    "room": ROOM_INDEX,
                    "orch_id": orch_id,
                    "status": "complete" if ok else (status or "failed"),
                    "experiment_id": res.get("experiment_id", ""),
                    "pcap_path": res.get("pcap_path") or cap.get("pcap_path", ""),
                    "capture": cap.get("status", ""),
                    "batch_elapsed_s": elapsed_s,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "error": res.get("error", final.get("error", "")),
                },
            )
            if ok:
                succeeded += 1
            else:
                failed += 1

        print(
            f"    [rooms] Batch done in {elapsed_s}s  "
            f"orch_status={final.get('status')}  "
            f"(running totals: {succeeded} ok / {failed} bad)"
        )

    total = time.time() - sweep_start
    h, rem = divmod(int(total), 3600)
    m = rem // 60
    print(
        f"\n{'='*62}\n[rooms] Room {ROOM_INDEX} done — "
        f"{succeeded} succeeded  {failed} failed  (wall {h}h{m:02d}m)\n"
        f"[rooms] Progress log: {SWEEP_LOG}\n{'='*62}"
    )


if __name__ == "__main__":
    main()
