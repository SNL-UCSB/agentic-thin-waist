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

# Allow running from repo root or services/orchestration/
sys.path.insert(0, "/app")

# When running inside a Docker container, use host.docker.internal to reach
# host-mapped ports on ephemeral workers.
os.environ.setdefault("SUBSTRATE_WORKER_HOST", "host.docker.internal")

from app.engine.connectivity import ConnectivityManager

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
        info = mgr.create_worker({
            "image": "agentic-thin-waist-substrate-worker",
            "network": "agentic-thin-waist_agentic-network",
            "ctp_dir": "/Users/eugenevuong/Documents/UCSB/agentic-thin-waist/ctp",
            "capture_dir": "/Users/eugenevuong/Documents/UCSB/agentic-thin-waist/captures",
        })
        print(f"  worker_id : {info.worker_id}")
        print(f"  endpoint  : {info.endpoint}")
        print(f"  container : {info.container_id[:12] if info.container_id else 'n/a'}")
    except Exception as exc:
        print(f"  FAILED: {exc}")
        sys.exit(1)

    # Give the container a moment to start
    print("  Waiting 3s for container to be ready...")
    time.sleep(3)

    # 2. Run experiment
    print("\n--- run_experiment() -> POST /run ---")
    try:
        result = mgr.run_experiment(
            worker_id=info.worker_id,
            workflow=MINIMAL_WORKFLOW,
            download_mbps=10.0,
            upload_mbps=5.0,
            latency_ms=0.0,
            runtime="shell",
        )
        print("  SUCCESS")
        print(json.dumps(result, indent=2, default=str))
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
