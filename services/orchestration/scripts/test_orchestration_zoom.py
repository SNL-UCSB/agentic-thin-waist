"""
End-to-end smoke test: join a Zoom meeting via the orchestration service.

The orchestrator parses the intent, selects the run_zoom_workflow from the
browser workflow library, spins up an ephemeral substrate worker with a
headless Chromium session, joins the meeting for `wait_seconds`, captures
traffic on veth2, and uploads the pcap + qtrace to telemetry.

Usage (from repo root):
    python3 services/orchestration/scripts/test_orchestration_zoom.py

Override defaults via env vars:
    ORCH_URL            Orchestration base URL  (default: http://localhost:8005)
    TELEMETRY_URL       Telemetry base URL       (default: http://localhost:8004)
    ORCH_CONTAINER      Container name for log streaming (default: orchestration)
    POLL_INTERVAL_SECONDS   (default: 5)
    TIMEOUT_SECONDS         (default: 600)

    # Meeting parameters (can be overridden per-run):
    ZOOM_MEETING_ID     (default: 89481474264)
    ZOOM_PASSCODE       (default: 138555)
    ZOOM_DISPLAY_NAME   (default: Henry)
    ZOOM_WAIT_SECONDS   (default: 60)
"""

import json
import os
import subprocess
import sys
import threading
import time

try:
    import requests
except ImportError:
    print("requests not installed. Run: pip install requests")
    sys.exit(1)

ORCH_URL      = os.getenv("ORCH_URL",      "http://localhost:8005").rstrip("/")
TELEMETRY_URL = os.getenv("TELEMETRY_URL", "http://localhost:8004").rstrip("/")
ORCH_CONTAINER = os.getenv("ORCH_CONTAINER", "orchestration")
POLL_INTERVAL  = float(os.getenv("POLL_INTERVAL_SECONDS", "5"))
TIMEOUT_SECONDS = float(os.getenv("TIMEOUT_SECONDS", "600"))

# Meeting parameters
MEETING_ID    = os.getenv("ZOOM_MEETING_ID",    "89481474264")
PASSCODE      = os.getenv("ZOOM_PASSCODE",      "138555")
DISPLAY_NAME  = os.getenv("ZOOM_DISPLAY_NAME",  "Henry")
WAIT_SECONDS  = int(os.getenv("ZOOM_WAIT_SECONDS", "60"))

TERMINAL_STATUSES = {"complete", "failed", "partial"}

# Natural-language intent — the orchestrator will parse this and map it to
# run_zoom_workflow with the parameters above.
CAPACITY_MBPS = int(os.getenv("ZOOM_CAPACITY_MBPS", "20"))

INTENT = (
    f"Join Zoom meeting ID {MEETING_ID} with passcode {PASSCODE}, "
    f"display name {DISPLAY_NAME!r}, stay for {WAIT_SECONDS} seconds. "
    f"Use a {CAPACITY_MBPS} Mbps bottleneck with 20 ms latency, 1 trial."
)


# ---------------------------------------------------------------------------
# Log streaming helpers (same pattern as test_orchestration_manager.py)
# ---------------------------------------------------------------------------

def _stream_container_logs(
    container: str, stop_event: threading.Event, prefix: str = "container"
) -> None:
    try:
        proc = subprocess.Popen(
            ["docker", "logs", "--follow", "--tail", "0", container],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        while not stop_event.is_set():
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            print(f"  [{prefix}] {line}", end="", flush=True)
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
    except FileNotFoundError:
        print(f"  [{prefix}] WARNING: docker not found — cannot stream logs")
    except Exception as exc:
        print(f"  [{prefix}] log stream error: {exc}")


def _watch_ephemeral_workers(stop_event: threading.Event) -> None:
    active: dict[str, threading.Thread] = {}
    try:
        proc = subprocess.Popen(
            ["docker", "events", "--filter", "event=start",
             "--filter", "type=container", "--format", "{{.Actor.Attributes.name}}"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )
        assert proc.stdout is not None
        while not stop_event.is_set():
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            name = line.strip()
            if not name.startswith("worker-"):
                continue
            if name in active and active[name].is_alive():
                continue
            print(f"\n  [watch] Ephemeral worker started: {name} — attaching log stream\n", flush=True)
            t = threading.Thread(
                target=_stream_container_logs,
                args=(name, stop_event, f"worker/{name[:14]}"),
                daemon=True,
            )
            t.start()
            active[name] = t
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
    except FileNotFoundError:
        print("  [watch] WARNING: docker not found — cannot watch worker events")
    except Exception as exc:
        print(f"  [watch] event watcher error: {exc}")


# ---------------------------------------------------------------------------
# Banner helpers
# ---------------------------------------------------------------------------

def banner(msg: str) -> None:
    width = 62
    print(f"\n{'='*width}\n  {msg}\n{'='*width}")


def section(msg: str) -> None:
    print(f"\n{'─'*60}\n  {msg}\n{'─'*60}")


# ---------------------------------------------------------------------------
# Orchestration steps
# ---------------------------------------------------------------------------

def check_health() -> bool:
    banner("Pre-flight: checking orchestration service health")
    try:
        r = requests.get(f"{ORCH_URL}/health", timeout=5)
        r.raise_for_status()
        print(f"  ✓ Orchestration service at {ORCH_URL} is healthy")
        return True
    except Exception as exc:
        print(f"  ✗ Cannot reach {ORCH_URL}/health: {exc}")
        return False


def submit_intent() -> str:
    banner("Step 1: Submitting Zoom intent")
    payload = {
        "intent": INTENT,
        "context": {
            "application": "zoom",
        },
        "preferences": {
            "max_parallel_workers": 1,
            "use_examples": True,
        },
        # Pin the workflow so the LLM doesn't have to guess; it also ensures
        # the correct parameter schema is applied.
        "workflow_id": "run_zoom_workflow",
        "workflow_source": "library",
    }
    print(f"  POST {ORCH_URL}/intent")
    print(f"  intent:       {INTENT!r}")
    print(f"  meeting_id:   {MEETING_ID}")
    print(f"  passcode:     {PASSCODE}")
    print(f"  display_name: {DISPLAY_NAME}")
    print(f"  wait_seconds: {WAIT_SECONDS}")

    r = requests.post(f"{ORCH_URL}/intent", json=payload, timeout=15)
    r.raise_for_status()
    data = r.json()
    orch_id = data["orchestration_id"]
    print(f"\n  ✓ Accepted — orchestration_id: {orch_id}")
    print(f"  initial status: {data['status']}")
    return orch_id


def poll_until_done(orch_id: str) -> dict:
    banner(f"Step 2: Polling {orch_id}")
    print(f"  polling every {POLL_INTERVAL}s  (timeout={TIMEOUT_SECONDS}s)\n")

    deadline     = time.time() + TIMEOUT_SECONDS
    last_status  = None
    last_flags: dict = {}
    iteration    = 0

    while time.time() < deadline:
        iteration += 1
        try:
            r = requests.get(f"{ORCH_URL}/orchestration/{orch_id}", timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            print(f"  [{iteration:>3}] poll error: {exc}")
            time.sleep(POLL_INTERVAL)
            continue

        status      = data.get("status", "unknown")
        error       = data.get("error")
        stage_flags = (data.get("detailed_progress") or {}).get("stage_flags", {})

        if status != last_status:
            ts = time.strftime("%H:%M:%S")
            print(f"  [{ts}] status changed: {last_status!r} → {status!r}")
            last_status = status

        new_flags = {k: v for k, v in stage_flags.items() if v and not last_flags.get(k)}
        if new_flags:
            ts = time.strftime("%H:%M:%S")
            for flag in new_flags:
                print(f"  [{ts}]   ✓ stage: {flag}")
            last_flags = dict(stage_flags)

        if iteration % max(1, int(30 / POLL_INTERVAL)) == 0:
            ts = time.strftime("%H:%M:%S")
            true_flags = [k for k, v in stage_flags.items() if v]
            print(f"  [{ts}] heartbeat — status={status}  stages={true_flags or '(none yet)'}")

        if status in TERMINAL_STATUSES:
            if error:
                print(f"\n  ✗ Finished with error: {error}")
            return data

        time.sleep(POLL_INTERVAL)

    print(f"\n  ✗ Timed out after {TIMEOUT_SECONDS}s")
    return data


def print_results(orch_id: str) -> None:
    section(f"Step 3: Results for {orch_id}")
    try:
        r = requests.get(f"{ORCH_URL}/orchestration/{orch_id}/results", timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        print(f"  Could not fetch results: {exc}")
        return

    results = data.get("results", [])
    print(f"  Total result entries: {len(results)}")

    for i, res in enumerate(results):
        exp_id  = res.get("experiment_id", "?")
        status  = res.get("status", "?")
        error   = res.get("error", "")
        run     = res.get("run", {})
        ctp     = res.get("ctp_selected") or {}

        print(f"\n  result[{i}]  exp_id={exp_id}  status={status}")
        if error:
            print(f"    error: {error}")
        if ctp:
            print(f"    ctp_id={ctp.get('ctp_id')}  intensity={ctp.get('intensity', {}).get('mean_mbps')} Mbps")
        if run and isinstance(run, dict):
            if "error" in run:
                print(f"    run error: {run['error']}")
            else:
                print(f"    run keys: {list(run.keys())}")

        capture_status = res.get("capture_status") or {}
        capture_state  = capture_status.get("status", "not_reported")
        pcap_path      = res.get("pcap_path") or capture_status.get("pcap_path", "")
        replay_r       = res.get("replay") or {}
        replay_state   = replay_r.get("replay_id", replay_r.get("skipped", replay_r.get("error", "not_reported")))
        print(f"    capture: {capture_state}  replay: {replay_state}")

        _verify_telemetry_artifacts(exp_id, pcap_path)


def _verify_telemetry_artifacts(exp_id: str, pcap_path: str) -> None:
    """Check both pcap and queue_trace artifacts in telemetry."""
    print(f"    pcap_path (worker-side): {pcap_path or '(empty)'}")

    try:
        r = requests.get(
            f"{TELEMETRY_URL}/results",
            params={"experiment_id": exp_id, "limit": 1},
            timeout=10,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            print(f"    ✗ No result row in telemetry for exp_id={exp_id}")
            return

        result_id = results[0]["result_id"]
        ar = requests.get(f"{TELEMETRY_URL}/results/{result_id}/artifacts", timeout=10)
        ar.raise_for_status()
        artifacts      = ar.json().get("artifacts", [])
        pcap_arts      = [a for a in artifacts if a.get("artifact_type") == "pcap"]
        qtrace_arts    = [a for a in artifacts if a.get("artifact_type") == "queue_trace"]

        if pcap_arts:
            a = pcap_arts[0]
            print(
                f"    pcap:    ✓ STORED in telemetry  "
                f"artifact_id={a['artifact_id']}  "
                f"size={a['size_bytes']} bytes  "
                f"file={a['filename']}"
            )
        else:
            print(f"    pcap:    ✗ NOT in telemetry (upload failed or capture failed)")

        if qtrace_arts:
            qt = qtrace_arts[0]
            print(
                f"    qtrace:  ✓ STORED in telemetry  "
                f"size={qt['size_bytes']} bytes  "
                f"file={qt['filename']}"
            )
        else:
            print(f"    qtrace:  ✗ NOT in telemetry")

    except Exception as exc:
        print(f"    could not query telemetry: {exc}")


def print_reasoning(orch_id: str) -> None:
    section(f"Step 4: Reasoning steps for {orch_id}")
    try:
        r = requests.get(f"{ORCH_URL}/orchestration/{orch_id}/reasoning", timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        print(f"  Could not fetch reasoning: {exc}")
        return

    steps = data.get("reasoning_steps", [])
    print(f"  Total reasoning steps: {len(steps)}")
    for step in steps:
        print(f"\n  step={step.get('step')}  action={step.get('action')}")
        reasoning = step.get("reasoning", "")
        if reasoning:
            short = reasoning[:300] + ("…" if len(reasoning) > 300 else "")
            print(f"    reasoning: {short}")
        output = step.get("output", {})
        if isinstance(output, dict):
            summary = {k: output.get(k) for k in ["status", "total_experiments", "successful", "failed"] if k in output}
            if summary:
                print(f"    summary: {summary}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    banner("Orchestration — Zoom Meeting Join Test")
    print(f"  Target:       {ORCH_URL}")
    print(f"  Container:    {ORCH_CONTAINER}")
    print(f"  Meeting ID:   {MEETING_ID}")
    print(f"  Passcode:     {PASSCODE}")
    print(f"  Display name: {DISPLAY_NAME}")
    print(f"  Wait:         {WAIT_SECONDS}s")

    if not check_health():
        print("\n  Make sure the stack is running: docker compose up -d")
        sys.exit(1)

    try:
        orch_id = submit_intent()
    except Exception as exc:
        print(f"\n  ✗ Failed to submit intent: {exc}")
        sys.exit(1)

    stop_logs = threading.Event()
    orch_log_thread = threading.Thread(
        target=_stream_container_logs,
        args=(ORCH_CONTAINER, stop_logs, "orch"),
        daemon=True,
    )
    worker_watch_thread = threading.Thread(
        target=_watch_ephemeral_workers,
        args=(stop_logs,),
        daemon=True,
    )

    banner("Step 2: Live container logs + polling")
    print(f"  [orch]       = orchestration service")
    print(f"  [worker/...] = ephemeral substrate worker\n")
    orch_log_thread.start()
    worker_watch_thread.start()

    try:
        final_data = poll_until_done(orch_id)
    finally:
        time.sleep(1)
        stop_logs.set()
        orch_log_thread.join(timeout=3)
        worker_watch_thread.join(timeout=3)

    final_status = final_data.get("status", "unknown")

    print_results(orch_id)
    print_reasoning(orch_id)

    banner(f"Done — final status: {final_status}")
    if final_status == "complete":
        print("  ✓ Zoom experiment succeeded")
        sys.exit(0)
    else:
        print("  ✗ Zoom experiment did not complete successfully")
        error = final_data.get("error")
        if error:
            print(f"  error: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
