"""
End-to-end smoke test: submit an iperf3 intent to the orchestrator and
follow the pipeline live — including server-side print statements streamed
directly from the orchestration container logs.

Usage (from repo root):
    python3 services/orchestration/scripts/test_orchestration_manager.py

    # Custom orchestrator URL or container name:
    ORCH_URL=http://localhost:8005 python3 services/orchestration/scripts/test_orchestration_manager.py
    ORCH_CONTAINER=orchestration python3 services/orchestration/scripts/test_orchestration_manager.py

What happens:
    1. POST /intent  → orchestrator submits iperf3 experiment intent
    2. Stream orchestration container logs live (server-side print statements)
    3. Poll /orchestration/{id} every 3 s until complete/failed
    4. Fetch and print /results and /reasoning at the end
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

ORCH_URL = os.getenv("ORCH_URL", "http://localhost:8005").rstrip("/")
ORCH_CONTAINER = os.getenv("ORCH_CONTAINER", "orchestration")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL_SECONDS", "3"))
TIMEOUT_SECONDS = float(os.getenv("TIMEOUT_SECONDS", "300"))

INTENT = (
    "Run ping experiments to 8.8.8.8 at 10 Mbps bottleneck capacity "
    "with 20 ms RTT latency for each capacity, 1 trial"
)

TERMINAL_STATUSES = {"complete", "failed", "partial"}


def _stream_container_logs(
    container: str, stop_event: threading.Event, prefix: str = "container"
) -> None:
    """Background thread: stream Docker container logs with a labeled prefix."""
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
    """Background thread: watch docker events for new worker-* containers and
    auto-attach a log-streaming thread to each one."""
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
                f"\n  [watch] Ephemeral worker started: {name} — attaching log stream\n",
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
        print("  [watch] WARNING: docker not found — cannot watch worker events")
    except Exception as exc:
        print(f"  [watch] event watcher error: {exc}")


def banner(msg: str) -> None:
    width = 62
    print(f"\n{'='*width}")
    print(f"  {msg}")
    print(f"{'='*width}")


def section(msg: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {msg}")
    print(f"{'─'*60}")


def fmt_stage_flags(flags: dict) -> str:
    """Return only the True flags as a compact string."""
    true_flags = [k for k, v in flags.items() if v]
    return ", ".join(true_flags) if true_flags else "(none yet)"


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
    banner("Step 1: Submitting iperf3 intent")
    payload = {
        "intent": INTENT,
        "context": {"application": "iperf3"},
        "preferences": {
            "max_parallel_workers": 1,
            "use_examples": True,
        },
    }
    print(f"  POST {ORCH_URL}/intent")
    print(f"  intent: {INTENT!r}")

    r = requests.post(f"{ORCH_URL}/intent", json=payload, timeout=15)
    r.raise_for_status()
    data = r.json()

    orch_id = data["orchestration_id"]
    print(f"\n  ✓ Accepted — orchestration_id: {orch_id}")
    print(f"  initial status: {data['status']}")
    return orch_id


def poll_until_done(orch_id: str) -> dict:
    banner(f"Step 2: Polling {orch_id}")
    print(f"  Will poll every {POLL_INTERVAL}s (timeout={TIMEOUT_SECONDS}s)\n")

    deadline = time.time() + TIMEOUT_SECONDS
    last_status = None
    last_stage_flags: dict = {}
    iteration = 0

    while time.time() < deadline:
        iteration += 1
        try:
            r = requests.get(f"{ORCH_URL}/orchestration/{orch_id}", timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            print(f"  [{iteration:>3}] Poll error: {exc}")
            time.sleep(POLL_INTERVAL)
            continue

        status = data.get("status", "unknown")
        error = data.get("error")
        stage_flags = (data.get("detailed_progress") or {}).get("stage_flags", {})
        iter_flags = (data.get("detailed_progress") or {}).get(
            "iteration_phase_flags", {}
        )

        # Print status changes
        if status != last_status:
            ts = time.strftime("%H:%M:%S")
            print(f"  [{ts}] status changed: {last_status!r} → {status!r}")
            last_status = status

        # Print newly-flipped stage flags
        new_flags = {
            k: v for k, v in stage_flags.items() if v and not last_stage_flags.get(k)
        }
        if new_flags:
            ts = time.strftime("%H:%M:%S")
            for flag in new_flags:
                print(f"  [{ts}]   ✓ stage: {flag}")
            last_stage_flags = dict(stage_flags)

        # Always print a heartbeat line every ~15 s
        if iteration % max(1, int(15 / POLL_INTERVAL)) == 0:
            ts = time.strftime("%H:%M:%S")
            active_stages = fmt_stage_flags(stage_flags)
            active_iters = fmt_stage_flags(iter_flags)
            print(
                f"  [{ts}] heartbeat — status={status}  "
                f"stages=[{active_stages}]  iter=[{active_iters}]"
            )

        if status in TERMINAL_STATUSES:
            if error:
                print(f"\n  ✗ Finished with error: {error}")
            return data

        time.sleep(POLL_INTERVAL)

    print(f"\n  ✗ Timed out after {TIMEOUT_SECONDS}s waiting for terminal status")
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
        exp_id = res.get("experiment_id", "?")
        status = res.get("status", "?")
        error = res.get("error", "")
        run = res.get("run", {})
        ctp = res.get("ctp_selected") or {}
        print(f"\n  result[{i}]  exp_id={exp_id}  status={status}")
        if error:
            print(f"    error: {error}")
        if ctp:
            print(
                f"    ctp_id={ctp.get('ctp_id')}  intensity={ctp.get('intensity', {}).get('mean_mbps')} Mbps"
            )
        if run and isinstance(run, dict):
            if "error" in run:
                print(f"    run error: {run['error']}")
            else:
                print(f"    run keys: {list(run.keys())}")

        # Capture / replay summary
        capture_status = res.get("capture_status") or {}
        capture_state = capture_status.get("status", "not_reported")
        pcap_path = res.get("pcap_path") or capture_status.get("pcap_path", "")
        replay_r = res.get("replay") or {}
        replay_state = replay_r.get(
            "replay_id", replay_r.get("skipped", replay_r.get("error", "not_reported"))
        )
        print(f"    capture: {capture_state}  replay: {replay_state}")
        _verify_pcap(pcap_path, exp_id)


def _verify_pcap(pcap_path: str, exp_id: str) -> None:
    """Check whether the pcap file reported by the worker actually exists."""
    import os
    from pathlib import Path

    if not pcap_path:
        print(f"    pcap: NOT recorded (pcap_path empty)")
        return

    print(f"    pcap_path: {pcap_path}")

    # 1. Direct path check (works when the capture dir is a shared host mount)
    if Path(pcap_path).exists():
        size = Path(pcap_path).stat().st_size
        print(f"    pcap: ✓ EXISTS on host  size={size} bytes")
        return

    # 2. Check via NETREPLICA_CAPTURE_DIR env override
    capture_dir = os.getenv("NETREPLICA_CAPTURE_DIR")
    if capture_dir:
        candidate = Path(capture_dir) / f"{exp_id}.pcap"
        if candidate.exists():
            size = candidate.stat().st_size
            print(f"    pcap: ✓ EXISTS at {candidate}  size={size} bytes")
            return

    # 3. Try docker exec into the worker container (best-effort)
    worker_container = None
    try:
        import subprocess

        out = subprocess.check_output(
            ["docker", "ps", "--filter", f"name=worker-", "--format", "{{.Names}}"],
            text=True,
            timeout=5,
        )
        names = [n.strip() for n in out.splitlines() if n.strip()]
        if names:
            worker_container = names[0]
    except Exception:
        pass

    if worker_container:
        try:
            import subprocess

            result = subprocess.run(
                ["docker", "exec", worker_container, "ls", "-lh", pcap_path],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                print(f"    pcap: ✓ EXISTS in worker container '{worker_container}'")
                print(f"           {result.stdout.strip()}")
            else:
                print(
                    f"    pcap: ✗ NOT FOUND in worker container '{worker_container}': {result.stderr.strip()}"
                )
        except Exception as exc:
            print(f"    pcap: could not check via docker exec: {exc}")
        return

    print(
        f"    pcap: path reported but not accessible from this host (worker already destroyed or path not mounted)"
    )


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
            short = reasoning[:200] + ("…" if len(reasoning) > 200 else "")
            print(f"    reasoning: {short}")
        output = step.get("output", {})
        if isinstance(output, dict):
            summary_keys = ["status", "total_experiments", "successful", "failed"]
            summary = {k: output.get(k) for k in summary_keys if k in output}
            if summary:
                print(f"    summary: {summary}")


def main() -> None:
    banner("Orchestration Manager — iperf3 Intent Test")
    print(f"  Target:    {ORCH_URL}")
    print(f"  Container: {ORCH_CONTAINER}  (server-side logs streamed below)")

    if not check_health():
        print("\n  Make sure the orchestration service is running:")
        print("    docker compose up orchestration")
        sys.exit(1)

    try:
        orch_id = submit_intent()
    except Exception as exc:
        print(f"\n  ✗ Failed to submit intent: {exc}")
        sys.exit(1)

    # Start log streams:
    #   [orch]         — orchestration container (intent parsing, dispatch steps)
    #   [worker/...]   — ephemeral worker-XXXX containers (auto-attached on start)
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
    print(f"  [orch]       = orchestration service (intent parse, dispatch, CTP)")
    print(f"  [worker/...] = ephemeral substrate worker (shape, run, capture)\n")
    orch_log_thread.start()
    worker_watch_thread.start()

    try:
        final_data = poll_until_done(orch_id)
    finally:
        # Give log streams a moment to flush trailing lines, then stop them.
        time.sleep(1)
        stop_logs.set()
        orch_log_thread.join(timeout=3)
        worker_watch_thread.join(timeout=3)

    final_status = final_data.get("status", "unknown")

    print_results(orch_id)
    print_reasoning(orch_id)

    banner(f"Done — final status: {final_status}")
    if final_status == "complete":
        print("  ✓ Experiment succeeded")
        sys.exit(0)
    else:
        print("  ✗ Experiment did not complete successfully")
        error = final_data.get("error")
        if error:
            print(f"  error: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
