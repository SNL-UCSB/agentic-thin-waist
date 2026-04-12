"""
Quick smoke test for ConnectivityManager.run_experiment().

Usage (inside the orchestration container or with the stack running):
    python scripts/test_connectivity_run_experiment.py

What it does:
    1. create_worker()  — spin up a fresh substrate-worker Docker container
    2. run_experiment() — POST /run with a minimal shell workflow (ping)
    3. destroy_worker() — clean up
"""

import json
import os
import sys
import time

import httpx

# Allow running from repo root or services/orchestration/
sys.path.insert(0, "/app")

# When running inside a Docker container, use host.docker.internal to reach
# host-mapped ports on ephemeral workers.
os.environ.setdefault("SUBSTRATE_WORKER_HOST", "host.docker.internal")

from app.engine.connectivity import ConnectivityManager


def _wait_for_health(endpoint: str, timeout: int = 90, interval: int = 3) -> bool:
    """Poll the worker /health endpoint until it responds OK or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{endpoint}/health", timeout=5)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# Minimal workflow: a single shell ping action
# ---------------------------------------------------------------------------
MINIMAL_WORKFLOW = {
    "specification": "smoke-test",
    "states": [
        {
            "checks": [],
            "actions": [
                {
                    "type": "ping",
                    "params": {"host": "8.8.8.8", "count": 3},
                }
            ],
            "end_state": "done",
        }
    ],
}


def main() -> None:
    mgr = ConnectivityManager()
    print(f"Backend: {mgr.backend_name}")

    # 1. Create worker
    print("\n--- create_worker() ---")
    try:
        info = mgr.create_worker(
            {
                "image": "agentic-thin-waist-substrate-worker",
                "network": "agentic-thin-waist_agentic-network",
                "ctp_dir": "/Users/eugenevuong/Documents/UCSB/agentic-thin-waist/ctp",
                "capture_dir": "/Users/eugenevuong/Documents/UCSB/agentic-thin-waist/captures",
            }
        )
        print(f"  worker_id : {info.worker_id}")
        print(f"  endpoint  : {info.endpoint}")
        print(f"  container : {info.container_id[:12] if info.container_id else 'n/a'}")
    except Exception as exc:
        print(f"  FAILED: {exc}")
        sys.exit(1)

    print("  Waiting for worker health check...")
    if _wait_for_health(info.endpoint):
        print("  Worker is healthy!")
    else:
        print("  WARNING: Worker health check timed out, trying anyway...")

    # 2. Run experiment + push to telemetry
    print("\n--- run_experiment() -> POST /run + POST /results ---")
    try:
        result = mgr.run_experiment(
            worker_id=info.worker_id,
            workflow=MINIMAL_WORKFLOW,
            download_mbps=10.0,
            upload_mbps=5.0,
            latency_ms=0.0,
            runtime="shell",
            experiment_id="smoke-test-connectivity-001",
            application="ping",
            telemetry_url="http://telemetry-service:8004",
        )
        print("  shaping           :", result["shaping"].get("status"))
        print("  congestion        :", result["congestion"].get("current_algorithm"))
        print(
            "  workflow status   :",
            result["workflow_result"].get("status"),
        )
        print(
            "  telemetry response:",
            json.dumps(result["telemetry"], indent=2, default=str),
        )
    except Exception as exc:
        print(f"  FAILED: {exc}")
    finally:
        # 3. Destroy worker
        print("\n--- destroy_worker() ---")
        try:
            mgr.destroy_worker(info.worker_id)
            print("  Destroyed successfully")
        except Exception as exc:
            print(f"  destroy FAILED: {exc}")


if __name__ == "__main__":
    main()
