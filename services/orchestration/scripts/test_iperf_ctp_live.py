"""
Live smoke test: CTP select → worker fetch → iperf3 run.

Run from repo root:
    PYTHONPATH=services/orchestration python3 services/orchestration/scripts/test_iperf_ctp_live.py

What it does:
    1. Query the local CTP service for a transformed CTP
    2. Create an ephemeral substrate worker via local_docker backend
    3. POST /ctp/fetch on the worker (HTTP export-ZIP flow)
    4. POST /run with an iperf3 workflow
    5. Destroy the worker
"""

import json
import os
import sys
import time

# Allow running from repo root or services/orchestration/
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from app.engine.connectivity import ConnectivityManager
from app.engine.executor import DownstreamClients
from app.engine.orchestration_manager import _select_ctp, _ctp_pointer_for_worker

CTP_SERVICE_URL = os.getenv("CTP_SERVICE_URL", "http://localhost:8001")
# Workers are launched by Docker on the host; orchestrator reaches them via localhost
os.environ.setdefault("SUBSTRATE_WORKER_HOST", "localhost")
os.environ.setdefault("CTP_SERVICE_GLOBAL", CTP_SERVICE_URL)
os.environ.setdefault("ORCH_CTP_POINTER_MODE", "export")

IPERF_WORKFLOW = {
    "specification": "iperf3-smoke",
    "states": [
        {
            "checks": [],
            "actions": [
                # iperf3 server is at 172.16.3.1 inside the worker's upstream namespace
                {"type": "iperf", "params": {"host": "8.8.8.8", "duration_seconds": 5}}
            ],
            "end_state": "done",
        }
    ],
}


def banner(msg: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")


def main() -> None:
    # ------------------------------------------------------------------ #
    # 1. Select a transformed CTP from the CTP service                    #
    # ------------------------------------------------------------------ #
    banner("Step 1: Select transformed CTP")
    ctp = _select_ctp(capacity_mbps=10.0, experiment_id="smoke-iperf")
    if ctp:
        print(f"  ctp_id       : {ctp.get('ctp_id')}")
        print(f"  download_pcap: {ctp.get('download_pcap')}")
        print(f"  intensity    : {ctp.get('intensity', {}).get('mean_mbps')} Mbps")
        ctp_pointer = _ctp_pointer_for_worker(ctp)
        print(f"  pointer      : {ctp_pointer}")
    else:
        print("  No transformed CTP found — will run without background traffic")
        ctp_pointer = None

    # ------------------------------------------------------------------ #
    # 2. Create an ephemeral substrate worker                              #
    # ------------------------------------------------------------------ #
    banner("Step 2: Create ephemeral substrate worker")
    mgr = ConnectivityManager()
    print(f"  Backend: {mgr.backend_name}")

    try:
        worker = mgr.create_worker(
            {
                "image": "agentic-thin-waist-substrate-worker",
                "network": "agentic-thin-waist_agentic-network",
                "ctp_dir": os.getenv("CTP_DIR", "/tmp/atw-ctp"),
                "capture_dir": os.getenv("CAPTURE_DIR", "/tmp/atw-captures"),
            }
        )
    except Exception as exc:
        print(f"  FAILED to create worker: {exc}")
        sys.exit(1)

    print(f"  worker_id : {worker.worker_id}")
    print(f"  endpoint  : {worker.endpoint}")
    print(f"  container : {worker.container_id[:12] if worker.container_id else 'n/a'}")
    print("  Waiting 5s for container setup...")
    time.sleep(5)

    try:
        # ---------------------------------------------------------------- #
        # 3. Fetch CTP PCAPs onto the worker                               #
        # ---------------------------------------------------------------- #
        banner("Step 3: POST /ctp/fetch on worker")
        if ctp_pointer:
            client = DownstreamClients(substrate_worker_url=worker.endpoint)
            try:
                fetch_result = client.fetch_ctp_substrate({"ctp_pointer": ctp_pointer})
                print(f"  name          : {fetch_result.get('name')}")
                print(f"  download_path : {fetch_result.get('download_path')}")
                print(f"  upload_path   : {fetch_result.get('upload_path')}")
                print(f"  fetched       : {fetch_result.get('fetched')}")
            except Exception as exc:
                print(f"  CTP fetch failed (continuing without CTP): {exc}")
        else:
            print("  Skipped (no CTP selected)")

        # ---------------------------------------------------------------- #
        # 4. Run iperf3 experiment                                          #
        # ---------------------------------------------------------------- #
        banner("Step 4: POST /run (iperf3 @ 10 Mbps)")
        result = mgr.run_experiment(
            worker_id=worker.worker_id,
            workflow=IPERF_WORKFLOW,
            download_mbps=10.0,
            upload_mbps=5.0,
            latency_ms=20.0,
            runtime="shell",
        )
        print("  SUCCESS")
        print(json.dumps(result, indent=2, default=str))

    except Exception as exc:
        print(f"  FAILED: {exc}")

    finally:
        # ---------------------------------------------------------------- #
        # 5. Destroy worker                                                 #
        # ---------------------------------------------------------------- #
        banner("Step 5: Destroy worker")
        try:
            mgr.destroy_worker(worker.worker_id)
            print(f"  Destroyed {worker.worker_id}")
        except Exception as exc:
            print(f"  Destroy failed: {exc}")


if __name__ == "__main__":
    main()
