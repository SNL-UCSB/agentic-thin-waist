"""Tests for OpenClaw tool routing against downstream clients."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.engine.executor import DownstreamClients, ToolRouter


def test_tool_router_run_experiment_dispatches_shape_and_create():
    clients = DownstreamClients(
        experiment_api_url="http://example-exp:8000",
        ctp_service_url="http://example-ctp:8001",
        substrate_worker_url="http://example-sub:8002",
        telemetry_service_url="http://example-tel:8004",
    )
    call_order: list[str] = []

    def mark_run(*_args, **_kwargs):
        call_order.append("run_experiment")
        return {"status": "pending", "experiment_id": "e1"}

    def mark_shape(*_args, **_kwargs):
        call_order.append("shape")
        return {"status": "shaped"}

    def mark_capture(*_args, **_kwargs):
        call_order.append("capture")
        return {"status": "started", "pcap_path": "/tmp/e1.pcap"}

    clients.run_experiment = MagicMock(side_effect=mark_run)
    clients.shape_substrate = MagicMock(side_effect=mark_shape)
    clients.capture_substrate = MagicMock(side_effect=mark_capture)
    router = ToolRouter(clients=clients)

    out = router.handle_tool_call(
        "run_experiment",
        {
            "experiment_id": "e1",
            "capacity_mbps": 25,
            "latency_ms": 50,
            "application": "youtube",
            "duration_seconds": 60,
            "num_trials": 1,
            "aqm_policy": "fq_codel",
        },
    )
    assert out["status"] == "dispatched"
    assert out["pipeline"] == ["experiment_api", "shape", "capture"]
    assert call_order == ["run_experiment", "shape", "capture"]
    assert clients.run_experiment.called
    assert clients.shape_substrate.called
    assert clients.capture_substrate.called


def test_tool_router_run_experiment_requires_experiment_id():
    clients = DownstreamClients()
    clients.run_experiment = MagicMock()
    router = ToolRouter(clients=clients)
    try:
        router.handle_tool_call(
            "run_experiment",
            {
                "capacity_mbps": 25,
                "latency_ms": 50,
                "application": "youtube",
                "duration_seconds": 60,
                "num_trials": 1,
                "aqm_policy": "fq_codel",
            },
        )
    except ValueError as e:
        assert "experiment_id" in str(e).lower()
    else:
        raise AssertionError("expected ValueError for missing experiment_id")


def test_tool_router_validate_ctp_with_unknown_cluster():
    clients = DownstreamClients()
    clients.validate_ctp_spec = MagicMock(
        return_value={
            "valid": False,
            "ctp_cluster_id": "ctp_missing",
            "warnings": ["CTP not found: ctp_missing"],
            "matches": [],
        }
    )
    router = ToolRouter(clients=clients)
    out = router.handle_tool_call("validate_ctp", {"ctp_cluster": "ctp_missing"})
    assert out["valid"] is False
    assert "warnings" in out
