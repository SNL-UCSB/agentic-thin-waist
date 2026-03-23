"""Tests for Step-12 execution manager in executor.py."""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from app.engine.executor import DownstreamClients, ExecutionManager


def _sample_spec(experiment_id: str = "youtube-20mbps-50ms-cubic-001") -> dict:
    return {
        "experiment_id": experiment_id,
        "capacity_mbps": 20.0,
        "latency_ms": 50.0,
        "loss_rate": 0.0,
        "application": "youtube",
        "duration_seconds": 60,
        "num_trials": 1,
        "cc_algorithm": "cubic",
        "aqm_policy": "fq_codel",
        "ctp_cluster": "ctp_low_background",
        "reasoning": "unit-test",
    }


def test_execution_manager_run_experiments_aggregates_single_success(monkeypatch):
    clients = DownstreamClients()
    clients.capture_substrate = MagicMock(
        return_value={"capture_id": "cap-1", "status": "started", "pcap_path": "/tmp/e1.pcap"}
    )
    clients.shape_substrate = MagicMock(return_value={"status": "shaped"})
    clients.run_experiment = MagicMock(
        side_effect=lambda payload: {
            "experiment_id": payload["experiment_id"],
            "status": "pending",
            "spec": payload,
        }
    )
    clients.get_capture = MagicMock(
        return_value={"capture_id": "cap-1", "status": "finished", "exit_code": 0, "pcap_path": "/tmp/e1.pcap"}
    )
    clients.get_experiment = MagicMock(
        return_value={"experiment_id": "e1", "status": "completed"}
    )
    clients.query_results = MagicMock(return_value={"results": [{"ok": True}]})
    clients.patch_experiment = MagicMock(return_value={"status": "complete"})

    monkeypatch.setenv("ORCH_POLL_EXPERIMENT_STATUS", "1")
    manager = ExecutionManager(clients=clients)
    out = manager.run_experiments([_sample_spec("e1")], enable_ctp_validation=False)

    assert out["summary"]["total_experiments"] == 1
    assert out["summary"]["successful"] == 1
    assert out["summary"]["failed"] == 0
    result = out["experiment_results"][0]
    assert result["experiment_id"] == "e1"
    assert result["status"] == "success"
    assert result["dispatch"]["experiment"]["spec"]["experiment_id"] == "e1"
    assert result["capture_status"]["status"] == "finished"
    assert result["capture_status"]["exit_code"] == 0
    assert result["dispatch"]["pipeline"] == ["experiment_api", "shape", "capture"]


@pytest.mark.skipif(
    not os.getenv("RUN_REAL_STACK_TESTS"),
    reason="Set RUN_REAL_STACK_TESTS=1 to run real stack executor test",
)
def test_execution_manager_real_stack_generates_pcap(monkeypatch):
    # Preconditions: substrate-worker (:8002) and experiment-api (:8006) must be running.
    assert requests.get("http://localhost:8002/health", timeout=5).status_code == 200
    assert requests.get("http://localhost:8006/health", timeout=5).status_code == 200

    monkeypatch.setenv("EXPERIMENT_API_URL", "http://localhost:8006")
    monkeypatch.setenv("SUBSTRATE_WORKER_URL", "http://localhost:8002")
    monkeypatch.setenv("ORCH_CAPTURE_DURATION_SECONDS", "8")
    monkeypatch.setenv("ORCH_CAPTURE_TIMEOUT_SECONDS", "60")
    # Experiment API keeps status pending in this implementation; skip long polling.
    monkeypatch.setenv("ORCH_POLL_EXPERIMENT_STATUS", "0")

    manager = ExecutionManager()
    unique = str(int(time.time()))
    experiment_id = f"youtube-20.19mbps-50ms-cubic-real-{unique}"
    out = manager.run_experiments([_sample_spec(experiment_id)], enable_ctp_validation=False)
    print("real-stack execution output:")
    print(out)

    assert out["summary"]["successful"] == 1
    item = out["experiment_results"][0]
    assert item["status"] == "success"
    assert item["dispatch"]["experiment"]["spec"]["experiment_id"] == experiment_id
    assert item["capture_status"]["status"] == "finished"
    assert item["capture_status"]["exit_code"] == 0
    assert item["capture_status"]["pcap_path"].endswith(".pcap")

    # Validate file appears in host capture directory (bind mount used in this setup).
    capture_dir = Path(
        "/home/haarika/imp_files/thinwaist/agentic-thin-waist/netreplica/config/captures"
    )
    assert (capture_dir / f"{experiment_id}.pcap").exists()

