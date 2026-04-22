"""
End-to-end smoke test: submit a parallel ping campaign to the orchestrator.

Usage (from repo root):
    python3 services/orchestration/scripts/test_orchestration_parallel_ping.py

Optional overrides:
    ORCH_URL=http://localhost:8005
    ORCH_CONTAINER=orchestration
    MAX_PARALLEL_WORKERS=8
    POLL_INTERVAL_SECONDS=3
    TIMEOUT_SECONDS=1800
"""

from __future__ import annotations

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

ORCH_URL = os.getenv("ORCH_URL", "http://localhost:8005").rstrip("/")
ORCH_CONTAINER = os.getenv("ORCH_CONTAINER", "orchestration")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL_SECONDS", "3"))
TIMEOUT_SECONDS = float(os.getenv("TIMEOUT_SECONDS", "1800"))
MAX_PARALLEL_WORKERS = int(os.getenv("MAX_PARALLEL_WORKERS", "8"))
CONNECTIVITY_BACKEND = os.getenv("CONNECTIVITY_BACKEND", "local_docker").strip().lower()

INTENT = "Run 4 ping experiments to 8.8.8.8 at 10 Mbps with 20ms RTT, 20 Mbps with 30ms RTT, 30 Mbps with 40ms RTT, and 40 Mbps with 50ms RTT latency for each capacity with a ctp between 4 and 5 Mbps for each"

TERMINAL_STATUSES = {"complete", "failed", "partial"}


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
        print(f"  [{prefix}] WARNING: docker not found; cannot stream logs")
    except Exception as exc:
        print(f"  [{prefix}] log stream error: {exc}")


def _watch_ephemeral_workers(stop_event: threading.Event) -> None:
    active: dict[str, threading.Thread] = {}
    try:
        proc = subprocess.Popen(
            [
                "docker",
                "events",
                "--filter",
                "event=start",
                "--filter",
                "type=container",
                "--format",
                "{{.Actor.Attributes.name}}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
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
            name = line.strip()
            if not name.startswith("worker-"):
                continue
            if name in active and active[name].is_alive():
                continue
            print(
                f"\n  [watch] worker started: {name} - attaching log stream\n",
                flush=True,
            )
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
        print("  [watch] WARNING: docker not found; cannot watch worker events")
    except Exception as exc:
        print(f"  [watch] event watcher error: {exc}")


def banner(msg: str) -> None:
    print(f"\n{'=' * 62}")
    print(f"  {msg}")
    print(f"{'=' * 62}")


def section(msg: str) -> None:
    print(f"\n{'-' * 60}")
    print(f"  {msg}")
    print(f"{'-' * 60}")


def check_health() -> bool:
    banner("Pre-flight: checking orchestration service health")
    try:
        r = requests.get(f"{ORCH_URL}/health", timeout=5)
        r.raise_for_status()
        print(f"  OK: {ORCH_URL}/health")
        return True
    except Exception as exc:
        print(f"  FAILED health check: {exc}")
        return False


def submit_intent(max_parallel_workers: int) -> str:
    banner("Step 1: Submitting parallel ping intent")
    payload = {
        "intent": INTENT,
        "context": {"application": "ping"},
        "preferences": {
            "max_parallel_workers": max_parallel_workers,
            "use_examples": True,
        },
    }
    print(f"  POST {ORCH_URL}/intent")
    print(f"  max_parallel_workers: {max_parallel_workers}")
    print(f"  intent: {INTENT!r}")

    r = requests.post(f"{ORCH_URL}/intent", json=payload, timeout=20)
    r.raise_for_status()
    data = r.json()
    orch_id = data["orchestration_id"]
    print(f"\n  Accepted orchestration_id={orch_id} status={data.get('status')}")
    return orch_id


def poll_until_done(orch_id: str) -> dict:
    banner(f"Step 2: Polling orchestration {orch_id}")
    deadline = time.time() + TIMEOUT_SECONDS
    last_status = None
    iteration = 0
    data: dict = {}

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

        status = data.get("status", "unknown")
        if status != last_status:
            ts = time.strftime("%H:%M:%S")
            print(f"  [{ts}] status: {last_status!r} -> {status!r}")
            last_status = status

        if iteration % max(1, int(15 / POLL_INTERVAL)) == 0:
            progress = data.get("detailed_progress") or {}
            stage_flags = progress.get("stage_flags") or {}
            active_stages = [k for k, v in stage_flags.items() if v]
            ts = time.strftime("%H:%M:%S")
            print(
                f"  [{ts}] heartbeat status={status} active_stages={active_stages or ['(none)']}"
            )

        if status in TERMINAL_STATUSES:
            return data

        time.sleep(POLL_INTERVAL)

    print(f"\n  Timed out after {TIMEOUT_SECONDS}s")
    return data


def print_results(orch_id: str) -> None:
    section(f"Step 3: Result summary for {orch_id}")
    try:
        r = requests.get(f"{ORCH_URL}/orchestration/{orch_id}/results", timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        print(f"  Could not fetch results: {exc}")
        return

    results = data.get("results", [])
    ok = sum(1 for item in results if item.get("status") == "success")
    failed = len(results) - ok
    print(f"  total={len(results)} success={ok} failed={failed}")

    for item in results[:10]:
        exp_id = item.get("experiment_id", "?")
        status = item.get("status", "?")
        cap = item.get("run", {}).get("requested", {}).get("download_mbps", "?")
        print(f"  - {exp_id}: status={status} download_mbps={cap}")
    if len(results) > 10:
        print(f"  ... truncated {len(results) - 10} more entries")


def print_reasoning(orch_id: str) -> None:
    section(f"Step 4: Parsed-intent reasoning for {orch_id}")
    try:
        r = requests.get(f"{ORCH_URL}/orchestration/{orch_id}/reasoning", timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        print(f"  Could not fetch reasoning: {exc}")
        return

    steps = data.get("reasoning_steps", [])
    if not steps:
        print("  No reasoning steps found")
        return
    for step in steps:
        action = step.get("action", "unknown")
        reasoning = (step.get("reasoning") or "").strip()
        short = reasoning[:220] + ("..." if len(reasoning) > 220 else "")
        print(f"  - {action}: {short}")


def main() -> None:
    banner("Orchestration Manager - Parallel Ping Campaign")
    print(f"  target={ORCH_URL}")
    print(f"  container={ORCH_CONTAINER}")
    print(f"  max_parallel_workers={MAX_PARALLEL_WORKERS}")
    print(f"  connectivity_backend={CONNECTIVITY_BACKEND}")

    if not check_health():
        print("\nRun the service first, e.g. docker compose up orchestration")
        sys.exit(1)

    try:
        orch_id = submit_intent(MAX_PARALLEL_WORKERS)
    except Exception as exc:
        print(f"\nFailed to submit intent: {exc}")
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

    banner(f"Done - final status: {final_status}")
    if final_status == "complete":
        print("  SUCCESS")
        sys.exit(0)
    print(f"  FAILED status={final_status} error={final_data.get('error')}")
    sys.exit(1)


if __name__ == "__main__":
    main()
