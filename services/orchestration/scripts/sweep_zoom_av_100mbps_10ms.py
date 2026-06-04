"""
Serial Zoom AV sweep across every CTP in ORCH_LOCAL_CTP_LIST.

For each CTP the script:
  1. Writes a single-entry version of the CTP list file so the orchestrator
     always selects exactly that CTP (relies on ORCH_LOCAL_CTP_SELECTION=first).
  2. Submits a Zoom AV intent and polls until the experiment completes.
  3. Appends a result record to a JSONL progress log.

The original CTP list file is restored unconditionally on exit (even on Ctrl-C).
On restart the script reads the progress log and skips already-finished CTPs.

Usage (from repo root):
    python3 services/orchestration/scripts/sweep_zoom_av_all_ctps.py

Key env-var overrides:
    ZOOM_MEETING_ID        (default: 89597290818)
    ZOOM_PASSCODE          (default: 046582)
    ZOOM_DISPLAY_NAME      (default: Henry)
    ZOOM_WAIT_SECONDS      (default: 60)
    ZOOM_CAPACITY_MBPS     (default: 6)
    ZOOM_LATENCY_MS        (default: 100)
    ZOOM_QDISC             (default: pfifo)

    CTP_LIST_FILE          Path to the CTP names file that the orchestration
                           container reads (must be the same path as
                           ORCH_LOCAL_CTP_LIST inside the container).
                           Default: /mnt/md0/haarika/ctps.txt

    SWEEP_LIMIT            Max number of CTPs to run in this invocation
                           (0 = no limit, default: 0)

    SWEEP_LOG              JSONL file for progress / resume
                           Default: ./sweep_zoom_av_10ms_progress.jsonl

    ORCH_URL               (default: http://localhost:8005)
    TELEMETRY_URL          (default: http://localhost:8004)
    POLL_INTERVAL_SECONDS  (default: 10)
    TIMEOUT_SECONDS        (default: 600)
"""

import json
import os
import pathlib
import signal
import sys
import time

try:
    import requests
except ImportError:
    print("requests not installed. Run: pip install requests")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ORCH_URL      = os.getenv("ORCH_URL",      "http://localhost:8005").rstrip("/")
TELEMETRY_URL = os.getenv("TELEMETRY_URL", "http://localhost:8004").rstrip("/")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL_SECONDS", "10"))
TIMEOUT       = float(os.getenv("TIMEOUT_SECONDS", "600"))

MEETING_ID   = os.getenv("ZOOM_MEETING_ID",   "83908205391")
PASSCODE     = os.getenv("ZOOM_PASSCODE",     "971104")
DISPLAY_NAME = os.getenv("ZOOM_DISPLAY_NAME", "Henry")
WAIT_SECONDS = int(os.getenv("ZOOM_WAIT_SECONDS", "60"))
CAPACITY     = int(os.getenv("ZOOM_CAPACITY_MBPS", "100"))
LATENCY      = int(os.getenv("ZOOM_LATENCY_MS",    "10"))
QDISC        = os.getenv("ZOOM_QDISC",             "pfifo")

CTP_LIST_FILE = os.getenv("CTP_LIST_FILE", "/mnt/md0/haarika/ctps_sweep_100mbps_10ms.txt")
SWEEP_LIMIT   = int(os.getenv("SWEEP_LIMIT", "0"))          # 0 = no limit
SWEEP_LOG     = os.getenv("SWEEP_LOG", "./sweep_zoom_av_100mbps_10ms_progress.jsonl")

TERMINAL_STATUSES = {"complete", "failed", "partial"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_all_ctps(path: str) -> list[str]:
    return [
        line.strip()
        for line in pathlib.Path(path).read_text().splitlines()
        if line.strip()
    ]


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
            done.add(rec["ctp_name"])
        except Exception:
            pass
    return done


def append_log(log_path: str, record: dict) -> None:
    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\n")


def pin_ctp(list_file: str, ctp_name: str) -> None:
    """Overwrite the CTP list file with a single entry."""
    pathlib.Path(list_file).write_text(ctp_name + "\n")


def restore_ctp_list(list_file: str, original: str) -> None:
    """Restore the CTP list file to its original content."""
    pathlib.Path(list_file).write_text(original)
    print(f"\n[sweep] CTP list file restored → {list_file}")


def build_intent(ctp_name: str) -> str:
    return (
        f"Join Zoom meeting ID {MEETING_ID} with passcode {PASSCODE}, "
        f"display name {DISPLAY_NAME!r}, stay for {WAIT_SECONDS} seconds, "
        f"streaming WAV audio as the microphone and MJPEG video as the camera. "
        f"Use a {CAPACITY} Mbps bottleneck with {LATENCY} ms latency, "
        f"{QDISC} AQM policy, 1 trial."
    )


def submit_intent(ctp_name: str) -> str:
    payload = {
        "intent": build_intent(ctp_name),
        "context":     {"application": "zoom"},
        "preferences": {"max_parallel_workers": 1, "use_examples": True},
        "workflow_id":     "run_zoom_av_workflow",
        "workflow_source": "library",
    }
    r = requests.post(f"{ORCH_URL}/intent", json=payload, timeout=20)
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
            print(f"    [poll] {orch_id}  status: {last_status!r} → {status!r}")
            last_status = status
        if status in TERMINAL_STATUSES:
            return data
        time.sleep(POLL_INTERVAL)
    print(f"    [poll] TIMEOUT after {TIMEOUT}s")
    return {"status": "timeout"}


def fetch_result_summary(orch_id: str) -> dict:
    try:
        r = requests.get(f"{ORCH_URL}/orchestration/{orch_id}/results", timeout=15)
        r.raise_for_status()
        results = r.json().get("results", [])
        if results:
            res = results[0]
            ctp = res.get("ctp_selected") or {}
            cap = res.get("capture_status") or {}
            return {
                "experiment_id": res.get("experiment_id"),
                "status":        res.get("status"),
                "ctp_id":        ctp.get("ctp_id"),
                "pcap_path":     res.get("pcap_path") or cap.get("pcap_path", ""),
                "capture":       cap.get("status", "?"),
            }
    except Exception as exc:
        return {"error": str(exc)}
    return {}

# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------

def main() -> None:
    # --- pre-flight ---
    try:
        r = requests.get(f"{ORCH_URL}/health", timeout=5)
        r.raise_for_status()
        print(f"[sweep] Orchestration service at {ORCH_URL} is healthy")
    except Exception as exc:
        print(f"[sweep] Cannot reach {ORCH_URL}/health: {exc}")
        sys.exit(1)

    list_path = pathlib.Path(CTP_LIST_FILE)
    if not list_path.exists():
        print(f"[sweep] CTP list file not found: {CTP_LIST_FILE}")
        sys.exit(1)

    original_content = list_path.read_text()
    all_ctps = load_all_ctps(CTP_LIST_FILE)
    done     = load_done(SWEEP_LOG)

    pending = [c for c in all_ctps if c not in done]
    if SWEEP_LIMIT > 0:
        pending = pending[:SWEEP_LIMIT]

    print(f"\n[sweep] CTP list:   {CTP_LIST_FILE}  ({len(all_ctps)} total)")
    print(f"[sweep] Already done: {len(done)}")
    print(f"[sweep] To run now:   {len(pending)}")
    print(f"[sweep] Parameters:   {CAPACITY} Mbps  {LATENCY} ms  {QDISC}")
    print(f"[sweep] Progress log: {SWEEP_LOG}")
    if SWEEP_LIMIT > 0:
        print(f"[sweep] Limit:        {SWEEP_LIMIT} CTPs this run")
    print()

    if not pending:
        print("[sweep] Nothing to do — all CTPs already complete.")
        return

    # Restore file on Ctrl-C or any exit
    def _cleanup(*_):
        restore_ctp_list(CTP_LIST_FILE, original_content)
        sys.exit(0)

    signal.signal(signal.SIGINT,  _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    succeeded = 0
    failed    = 0
    sweep_start = time.time()

    try:
        for idx, ctp_name in enumerate(pending, 1):
            t0 = time.time()
            eta_msg = ""
            if idx > 1:
                elapsed = t0 - sweep_start
                avg_per = elapsed / (idx - 1)
                remaining = (len(pending) - idx + 1) * avg_per
                h, rem = divmod(int(remaining), 3600)
                m = rem // 60
                eta_msg = f"  ETA ~{h}h{m:02d}m remaining"

            print(
                f"\n{'='*62}\n"
                f"[sweep] CTP {idx}/{len(pending)}: {ctp_name}{eta_msg}\n"
                f"{'='*62}"
            )

            # Pin this CTP
            pin_ctp(CTP_LIST_FILE, ctp_name)

            try:
                orch_id = submit_intent(ctp_name)
                print(f"    [sweep] Submitted → orch_id={orch_id}")
            except Exception as exc:
                print(f"    [sweep] Submit FAILED: {exc}")
                record = {
                    "ctp_name":   ctp_name,
                    "status":     "submit_failed",
                    "error":      str(exc),
                    "timestamp":  time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                append_log(SWEEP_LOG, record)
                failed += 1
                continue

            final = poll_until_done(orch_id)
            summary = fetch_result_summary(orch_id)
            elapsed_s = round(time.time() - t0, 1)

            status = final.get("status", "unknown")
            record = {
                "ctp_name":      ctp_name,
                "orch_id":       orch_id,
                "status":        status,
                "experiment_id": summary.get("experiment_id", ""),
                "pcap_path":     summary.get("pcap_path", ""),
                "capture":       summary.get("capture", ""),
                "elapsed_s":     elapsed_s,
                "timestamp":     time.strftime("%Y-%m-%dT%H:%M:%S"),
                "error":         final.get("error", ""),
            }
            append_log(SWEEP_LOG, record)

            if status == "complete":
                succeeded += 1
                print(
                    f"    [sweep] ✓ complete  "
                    f"exp={summary.get('experiment_id','')}  "
                    f"pcap={summary.get('pcap_path','')}  "
                    f"({elapsed_s}s)"
                )
            else:
                failed += 1
                print(f"    [sweep] ✗ {status}  error={final.get('error','')}")

    finally:
        restore_ctp_list(CTP_LIST_FILE, original_content)

    total_elapsed = time.time() - sweep_start
    h, rem = divmod(int(total_elapsed), 3600)
    m = rem // 60
    print(
        f"\n{'='*62}\n"
        f"[sweep] Done — {succeeded} succeeded  {failed} failed  "
        f"(wall time {h}h{m:02d}m)\n"
        f"[sweep] Progress log: {SWEEP_LOG}\n"
        f"{'='*62}"
    )


if __name__ == "__main__":
    main()
