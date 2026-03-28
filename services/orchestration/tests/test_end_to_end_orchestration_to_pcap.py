"""E2E orchestration workflow tests.

These tests invoke the **real production orchestration code** (workflow runner,
preflight, per-iteration dispatch, lifecycle, aggregation) through the public
HTTP entrypoint (``POST /intent``).  External services are mocked at the
``DownstreamClients`` boundary so the tests run without a live stack.
CTP PCAP resolution is mocked via ``resolve_ctp`` (file-based).

Branch coverage
~~~~~~~~~~~~~~~
1. Happy path — everything ready, one full iteration succeeds
2. CTP corpus missing — no PCAPs on disk for the requested cluster
3. Unsupported application — NetGent rejects, orchestration fails early
4. Worker unavailable — preflight failure
5. Iteration failure — a downstream call fails mid-iteration
6. Telemetry save failure — execution completes but telemetry persistence fails

Run:
    pytest services/orchestration/tests/test_end_to_end_orchestration_to_pcap.py -v
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.engine.executor import DownstreamClients
from app.engine.ctp_resolver import CtpResolution
from app.engine.experiment_lifecycle import OrchestrationStage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INTENT_TEXT = "Run one YouTube experiment at 20 Mbps and 50 ms latency"

_PARSED_INTENT = {
    "applications": ["youtube"],
    "capacities": [20.0],
    "latencies": [50],
    "cc_algorithms": ["cubic"],
    "aqm_policy": "fq_codel",
    "ctp_cluster": "cluster0",
    "duration_seconds": 60,
    "num_trials": 1,
    "clarification_needed": [],
    "design_type": ["isolated"],
    "reasoning": "Single YouTube experiment for E2E test.",
}


def _make_ready_ctp_resolution(cluster: str = "cluster0") -> CtpResolution:
    """A CtpResolution that reports ready with a plausible replay path."""
    dl_pcap = Path(f"/fake/ctp/ctp_100_cluster_6M/{cluster}_tree9_profile869.pcap")
    ul_pcap = Path(
        f"/fake/ctp/ctp_100_cluster_incoming_6M/{cluster}_tree2_profile861.pcap"
    )
    res = CtpResolution(cluster=cluster, download_pcap=dl_pcap, upload_pcap=ul_pcap)
    # Override ready check since the path doesn't exist on disk in test
    res.__class__ = type(
        "_TestCtp", (CtpResolution,), {"ready": property(lambda self: True)}
    )
    return res


def _make_missing_ctp_resolution(cluster: str = "cluster99") -> CtpResolution:
    """A CtpResolution where no PCAPs were found."""
    return CtpResolution(cluster=cluster, download_pcap=None, upload_pcap=None)


def _post_intent(client: TestClient, intent: str = _INTENT_TEXT) -> dict[str, Any]:
    resp = client.post(
        "/intent",
        json={"intent": intent, "preferences": {"run_immediately": True}},
    )
    assert resp.status_code == 202
    return resp.json()


def _poll_until_done(
    client: TestClient, orch_id: str, max_seconds: int = 10
) -> dict[str, Any]:
    for _ in range(max_seconds * 10):
        resp = client.get(f"/orchestration/{orch_id}")
        assert resp.status_code == 200
        payload = resp.json()
        if payload["status"] in ("complete", "failed", "partial"):
            return payload
        time.sleep(0.1)
    raise AssertionError(
        f"Orchestration {orch_id} did not finish within {max_seconds}s"
    )


def _get_results(client: TestClient, orch_id: str) -> dict[str, Any]:
    resp = client.get(f"/orchestration/{orch_id}/results")
    assert resp.status_code == 200
    return resp.json()


def _make_happy_clients() -> MagicMock:
    """Return a mock DownstreamClients where every call succeeds."""
    clients = MagicMock(spec=DownstreamClients)

    # NetGent
    clients.get_available_workflows.return_value = {
        "applications": [
            {"application": "youtube", "notes": ""},
            {"application": "zoom", "notes": ""},
        ],
    }
    clients.generate_workflow.return_value = {
        "workflow_id": "wf-001",
        "status": "pending",
    }
    clients.get_workflow_status.return_value = {
        "workflow_id": "wf-001",
        "status": "completed",
    }
    clients.get_workflow_result.return_value = {
        "workflow_id": "wf-001",
        "status": "completed",
    }

    # Substrate
    clients.get_substrate_health.return_value = {
        "status": "ok",
        "root_privileges": True,
        "tc_available": True,
        "tshark_available": True,
        "tcpreplay_available": True,
        "qdisc_support": True,
        "interfaces": ["veth1", "veth2"],
    }
    clients.shape_substrate.return_value = {
        "status": "shaped",
        "bottleneck_state": {
            "download_mbps": 20.0,
            "upload_mbps": 20.0,
            "latency_ms": 50.0,
        },
        "applied_commands": [],
    }
    clients.capture_substrate.return_value = {
        "capture_id": "cap-001",
        "status": "started",
        "pcap_path": "/tmp/test.pcap",
    }
    clients.get_capture.return_value = {
        "capture_id": "cap-001",
        "status": "finished",
        "pcap_path": "/tmp/test.pcap",
        "exit_code": 0,
    }
    clients.stop_capture.return_value = {"capture_id": "cap-001", "status": "stopped"}
    clients.replay_substrate.return_value = {
        "replay_id": "rep-001",
        "status": "started",
    }
    clients.get_replay.return_value = {"replay_id": "rep-001", "status": "finished"}
    clients.stop_replay.return_value = {"replay_id": "rep-001", "status": "stopped"}
    clients.get_substrate_state.return_value = {
        "status": "ok",
        "bottleneck_state": {
            "download_mbps": 20.0,
            "upload_mbps": 20.0,
            "latency_ms": 50.0,
        },
    }

    # Experiment API
    clients.run_experiment.side_effect = lambda p: {
        "experiment_id": p["experiment_id"],
        "status": "pending",
        "spec": p,
    }
    clients.patch_experiment.return_value = {"status": "complete"}
    clients.get_experiment.return_value = {"experiment_id": "e1", "status": "completed"}

    # Telemetry
    clients.query_results.return_value = {"results": []}
    clients.post_result.return_value = {
        "result_id": "res-001",
        "experiment_id": "e1",
        "status": "stored",
    }

    return clients


def _stage_names(payload: dict[str, Any]) -> list[str]:
    """Extract the list of stage names from an orchestration status/results payload."""
    return [s["stage"] for s in payload.get("lifecycle_stages", [])]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


def test_happy_path(client, monkeypatch):
    """Everything ready: one full iteration, complete lifecycle, UI-friendly result."""
    mock_clients = _make_happy_clients()
    ready_ctp = _make_ready_ctp_resolution()

    with patch("app.api.intent.IntentParser") as mock_parser_cls, patch(
        "app.engine.orchestration_workflow.DownstreamClients", return_value=mock_clients
    ), patch(
        "app.engine.orchestration_workflow.resolve_ctp", return_value=ready_ctp
    ), patch(
        "app.api.intent.DownstreamClients", return_value=mock_clients
    ):
        mock_parser_cls.return_value.parse.return_value = _PARSED_INTENT

        body = _post_intent(client)
        orch_id = body["orchestration_id"]
        status = _poll_until_done(client, orch_id)

    assert status["status"] == "complete"

    results = _get_results(client, orch_id)
    assert results["status"] == "complete"

    stages = _stage_names(results)
    assert OrchestrationStage.RECEIVED_INTENT.value in stages
    assert OrchestrationStage.GENERATED_EXPERIMENT_SPEC.value in stages
    assert OrchestrationStage.CHECKING_CTP_REPLAY_READINESS.value in stages
    assert OrchestrationStage.CTP_REPLAY_READY.value in stages
    assert OrchestrationStage.APPLICATION_SUPPORTED.value in stages
    assert OrchestrationStage.WORKER_AVAILABLE.value in stages
    assert OrchestrationStage.STARTING_ITERATION.value in stages
    assert OrchestrationStage.CONFIGURING_BOTTLENECK.value in stages
    assert OrchestrationStage.CAPTURE_IN_PROGRESS.value in stages
    assert OrchestrationStage.NETGENT_EXECUTION_SKIPPED.value in stages
    assert OrchestrationStage.SAVING_TO_TELEMETRY.value in stages
    assert OrchestrationStage.TELEMETRY_SAVE_COMPLETE.value in stages
    assert OrchestrationStage.ITERATION_SUCCEEDED.value in stages
    assert OrchestrationStage.EXPERIMENT_SUCCEEDED.value in stages

    # Preflight passed
    preflight = results.get("preflight", {})
    assert preflight["passed"] is True

    # Iteration results
    iter_results = results.get("results", [])
    assert len(iter_results) >= 1
    assert iter_results[0]["status"] == "success"
    assert "capture" in iter_results[0]
    assert "telemetry" in iter_results[0]
    assert "shape" in iter_results[0]
    assert "ctp_resolution" in iter_results[0]
    assert iter_results[0].get("netgent_execution_enabled") is False
    assert iter_results[0]["netgent"]["status"] == "netgent_execution_skipped"

    # Replay payload used the resolved CTP file path
    replay_call = mock_clients.replay_substrate.call_args
    assert (
        "ctp_100_cluster_6M/cluster0_tree9_profile869" in replay_call[0][0]["ctp_file"]
    )

    # Downstream calls happened in order
    mock_clients.get_available_workflows.assert_called_once()
    mock_clients.get_substrate_health.assert_called_once()
    mock_clients.shape_substrate.assert_called_once()
    mock_clients.capture_substrate.assert_called_once()
    mock_clients.replay_substrate.assert_called_once()
    mock_clients.generate_workflow.assert_not_called()
    mock_clients.post_result.assert_called_once()
    mock_clients.run_experiment.assert_called_once()


# ---------------------------------------------------------------------------
# 2. CTP corpus missing — no PCAPs on disk for the cluster
# ---------------------------------------------------------------------------


def test_ctp_corpus_missing(client, monkeypatch):
    """No PCAP files exist for the requested CTP cluster; preflight fails."""
    mock_clients = _make_happy_clients()
    missing_ctp = _make_missing_ctp_resolution("cluster99")

    with patch("app.api.intent.IntentParser") as mock_parser_cls, patch(
        "app.engine.orchestration_workflow.DownstreamClients", return_value=mock_clients
    ), patch(
        "app.engine.orchestration_workflow.resolve_ctp", return_value=missing_ctp
    ), patch(
        "app.api.intent.DownstreamClients", return_value=mock_clients
    ):
        mock_parser_cls.return_value.parse.return_value = _PARSED_INTENT

        body = _post_intent(client)
        orch_id = body["orchestration_id"]
        status = _poll_until_done(client, orch_id)

    assert status["status"] == "failed"

    results = _get_results(client, orch_id)
    preflight = results.get("preflight", {})
    assert preflight["passed"] is False
    assert "no PCAP" in (preflight.get("failure_reason") or "")


# ---------------------------------------------------------------------------
# 3. Unsupported application — rejected by orchestration
# ---------------------------------------------------------------------------


def test_unsupported_application(client, monkeypatch):
    """NetGent does not support the requested application; experiment rejected early."""
    mock_clients = _make_happy_clients()
    mock_clients.get_available_workflows.return_value = {
        "applications": [{"application": "zoom", "notes": ""}],
    }
    ready_ctp = _make_ready_ctp_resolution()

    with patch("app.api.intent.IntentParser") as mock_parser_cls, patch(
        "app.engine.orchestration_workflow.DownstreamClients", return_value=mock_clients
    ), patch(
        "app.engine.orchestration_workflow.resolve_ctp", return_value=ready_ctp
    ), patch(
        "app.api.intent.DownstreamClients", return_value=mock_clients
    ):
        mock_parser_cls.return_value.parse.return_value = _PARSED_INTENT

        body = _post_intent(client)
        orch_id = body["orchestration_id"]
        status = _poll_until_done(client, orch_id)

    assert status["status"] == "failed"

    stages = _stage_names(status)
    assert OrchestrationStage.APPLICATION_UNSUPPORTED.value in stages

    # No iterations should have run
    results = _get_results(client, orch_id)
    iter_results = results.get("results", [])
    assert len(iter_results) == 0

    # Preflight failed
    preflight = results.get("preflight", {})
    assert preflight["passed"] is False
    assert "youtube" in (preflight.get("failure_reason") or "")


# ---------------------------------------------------------------------------
# 4. Worker unavailable — preflight failure
# ---------------------------------------------------------------------------


def test_worker_unavailable(client, monkeypatch):
    """Substrate worker reports degraded health; orchestration fails at preflight."""
    mock_clients = _make_happy_clients()
    mock_clients.get_substrate_health.return_value = {
        "status": "degraded",
        "root_privileges": False,
        "tc_available": False,
        "tshark_available": False,
        "tcpreplay_available": False,
        "qdisc_support": False,
        "interfaces": [],
    }
    ready_ctp = _make_ready_ctp_resolution()

    with patch("app.api.intent.IntentParser") as mock_parser_cls, patch(
        "app.engine.orchestration_workflow.DownstreamClients", return_value=mock_clients
    ), patch(
        "app.engine.orchestration_workflow.resolve_ctp", return_value=ready_ctp
    ), patch(
        "app.api.intent.DownstreamClients", return_value=mock_clients
    ):
        mock_parser_cls.return_value.parse.return_value = _PARSED_INTENT

        body = _post_intent(client)
        orch_id = body["orchestration_id"]
        status = _poll_until_done(client, orch_id)

    assert status["status"] == "failed"

    stages = _stage_names(status)
    assert OrchestrationStage.WORKER_UNAVAILABLE.value in stages

    results = _get_results(client, orch_id)
    assert results.get("preflight", {})["passed"] is False


# ---------------------------------------------------------------------------
# 5. Iteration failure — shape raises mid-iteration
# ---------------------------------------------------------------------------


def test_iteration_failure(client, monkeypatch):
    """A downstream call fails during iteration; lifecycle records the failure."""
    mock_clients = _make_happy_clients()
    mock_clients.shape_substrate.side_effect = RuntimeError("tc qdisc: No such device")
    ready_ctp = _make_ready_ctp_resolution()

    with patch("app.api.intent.IntentParser") as mock_parser_cls, patch(
        "app.engine.orchestration_workflow.DownstreamClients", return_value=mock_clients
    ), patch(
        "app.engine.orchestration_workflow.resolve_ctp", return_value=ready_ctp
    ), patch(
        "app.api.intent.DownstreamClients", return_value=mock_clients
    ):
        mock_parser_cls.return_value.parse.return_value = _PARSED_INTENT

        body = _post_intent(client)
        orch_id = body["orchestration_id"]
        status = _poll_until_done(client, orch_id)

    assert status["status"] == "failed"

    stages = _stage_names(status)
    assert OrchestrationStage.ITERATION_FAILED.value in stages
    assert OrchestrationStage.EXPERIMENT_FAILED.value in stages

    results = _get_results(client, orch_id)
    iter_results = results.get("results", [])
    assert len(iter_results) == 1
    assert iter_results[0]["status"] == "failed"
    assert "tc qdisc" in iter_results[0].get("error", "")


# ---------------------------------------------------------------------------
# 6. Telemetry save failure — execution succeeds but telemetry fails
# ---------------------------------------------------------------------------


def test_telemetry_save_failure(client, monkeypatch):
    """Iteration itself completes but telemetry POST /results fails; surfaced clearly."""
    mock_clients = _make_happy_clients()
    mock_clients.post_result.return_value = {
        "error": "telemetry_service_unavailable",
        "stored": False,
    }
    ready_ctp = _make_ready_ctp_resolution()

    with patch("app.api.intent.IntentParser") as mock_parser_cls, patch(
        "app.engine.orchestration_workflow.DownstreamClients", return_value=mock_clients
    ), patch(
        "app.engine.orchestration_workflow.resolve_ctp", return_value=ready_ctp
    ), patch(
        "app.api.intent.DownstreamClients", return_value=mock_clients
    ):
        mock_parser_cls.return_value.parse.return_value = _PARSED_INTENT

        body = _post_intent(client)
        orch_id = body["orchestration_id"]
        status = _poll_until_done(client, orch_id)

    # Iteration still succeeds overall (telemetry failure is non-fatal)
    assert status["status"] == "complete"

    stages = _stage_names(status)
    assert OrchestrationStage.TELEMETRY_SAVE_FAILED.value in stages
    assert OrchestrationStage.ITERATION_SUCCEEDED.value in stages

    results = _get_results(client, orch_id)
    iter_results = results.get("results", [])
    assert len(iter_results) == 1
    assert iter_results[0]["telemetry_saved"] is False


def test_netgent_live_execution_when_enabled(client, monkeypatch):
    """With ORCH_NETGENT_EXECUTION_ENABLED=1, NetGent generate/status/result are invoked."""
    monkeypatch.setenv("ORCH_NETGENT_EXECUTION_ENABLED", "1")
    mock_clients = _make_happy_clients()
    ready_ctp = _make_ready_ctp_resolution()

    with patch("app.api.intent.IntentParser") as mock_parser_cls, patch(
        "app.engine.orchestration_workflow.DownstreamClients", return_value=mock_clients
    ), patch(
        "app.engine.orchestration_workflow.resolve_ctp", return_value=ready_ctp
    ), patch(
        "app.api.intent.DownstreamClients", return_value=mock_clients
    ):
        mock_parser_cls.return_value.parse.return_value = _PARSED_INTENT

        body = _post_intent(client)
        orch_id = body["orchestration_id"]
        _poll_until_done(client, orch_id)

    results = _get_results(client, orch_id)
    stages = _stage_names(results)
    assert OrchestrationStage.RUNNING_NETGENT_WORKFLOW.value in stages
    assert OrchestrationStage.NETGENT_WORKFLOW_COMPLETE.value in stages
    assert OrchestrationStage.NETGENT_EXECUTION_SKIPPED.value not in stages
    mock_clients.generate_workflow.assert_called_once()
    iter_results = results.get("results", [])
    assert iter_results[0].get("netgent_execution_enabled") is True


# ---------------------------------------------------------------------------
# Optional: real-stack integration (opt-in)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.getenv("RUN_REAL_STACK_TESTS"),
    reason="Set RUN_REAL_STACK_TESTS=1 to run real stack integration test",
)
def test_real_stack_happy_path():
    """Smoke test against a live local stack (all services running)."""
    import requests

    orch_base = os.getenv("ORCH_BASE_URL", "http://localhost:8005")
    unique_capacity = round(20 + ((time.time() % 1000) / 1000.0), 3)
    intent = f"Run one YouTube experiment at {unique_capacity} Mbps and 50 ms latency"

    resp = requests.post(
        f"{orch_base}/intent",
        json={"intent": intent, "preferences": {"run_immediately": True}},
        timeout=30,
    )
    assert resp.status_code == 202
    orch_id = resp.json()["orchestration_id"]

    final = None
    for _ in range(120):
        status_resp = requests.get(f"{orch_base}/orchestration/{orch_id}", timeout=10)
        assert status_resp.status_code == 200
        payload = status_resp.json()
        if payload["status"] in ("complete", "failed", "partial"):
            final = payload
            break
        time.sleep(1)
    assert final is not None, "Timed out waiting for orchestration"
    assert final["status"] == "complete"
