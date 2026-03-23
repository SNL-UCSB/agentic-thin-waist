"""Pipeline, lifecycle, and edge-case tests for ``executor`` (Step 12 integration)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.engine.executor import DownstreamClients, ExecutionManager, ToolRouter


def _spec(eid: str = "exp-a") -> dict:
    return {
        "experiment_id": eid,
        "capacity_mbps": 10.0,
        "latency_ms": 40.0,
        "application": "youtube",
        "duration_seconds": 60,
        "num_trials": 1,
        "aqm_policy": "fq_codel",
    }


def test_run_experiments_empty_specs_returns_zero_summary():
    m = ExecutionManager(clients=DownstreamClients())
    out = m.run_experiments([], enable_ctp_validation=False)
    assert out["experiment_results"] == []
    assert out["summary"] == {
        "total_experiments": 0,
        "successful": 0,
        "failed": 0,
    }


def test_run_experiments_includes_ctp_validation_when_enabled():
    clients = DownstreamClients()
    clients.validate_ctp_spec = MagicMock(
        return_value={"valid": True, "matches": [], "warnings": []}
    )
    clients.run_experiment = MagicMock(
        return_value={"experiment_id": "exp-a", "status": "pending", "spec": {}}
    )
    clients.shape_substrate = MagicMock(return_value={"status": "shaped"})
    clients.capture_substrate = MagicMock(
        return_value={"capture_id": "c1", "status": "started"}
    )
    clients.get_capture = MagicMock(
        return_value={"capture_id": "c1", "status": "finished"}
    )
    clients.get_experiment = MagicMock(
        return_value={"experiment_id": "exp-a", "status": "completed"}
    )
    clients.query_results = MagicMock(return_value={"results": []})
    clients.patch_experiment = MagicMock(return_value={})

    m = ExecutionManager(clients=clients)
    out = m.run_experiments([_spec("exp-a")], enable_ctp_validation=True)
    assert out["summary"]["successful"] == 1
    item = out["experiment_results"][0]
    assert "ctp_validation" in item
    assert item["ctp_validation"]["valid"] is True
    clients.validate_ctp_spec.assert_called_once()


def test_run_experiments_shape_failure_still_records_dispatch_error_and_patches_failed():
    clients = DownstreamClients()
    clients.run_experiment = MagicMock(
        return_value={"experiment_id": "exp-b", "status": "pending", "spec": {}}
    )
    clients.shape_substrate = MagicMock(side_effect=RuntimeError("no tc"))
    clients.patch_experiment = MagicMock(return_value={})

    m = ExecutionManager(clients=clients)
    out = m.run_experiments([_spec("exp-b")], enable_ctp_validation=False)
    assert out["summary"]["failed"] == 1
    item = out["experiment_results"][0]
    assert item["status"] == "failed"
    assert "no tc" in item["error"]
    clients.patch_experiment.assert_called()
    fail_call = [
        c
        for c in clients.patch_experiment.call_args_list
        if c[0][0] == "exp-b" and c[0][1].get("status") == "failed"
    ]
    assert fail_call


def test_run_experiments_run_experiment_failure_skips_shape_and_capture():
    clients = DownstreamClients()
    clients.run_experiment = MagicMock(
        side_effect=ConnectionError("experiment api down")
    )
    clients.shape_substrate = MagicMock()
    clients.capture_substrate = MagicMock()
    clients.patch_experiment = MagicMock()

    m = ExecutionManager(clients=clients)
    out = m.run_experiments([_spec("exp-c")], enable_ctp_validation=False)
    assert out["summary"]["failed"] == 1
    clients.shape_substrate.assert_not_called()
    clients.capture_substrate.assert_not_called()


def test_run_experiments_partial_failure_continues_to_next_spec():
    clients = DownstreamClients()
    clients.run_experiment = MagicMock(
        side_effect=[
            ConnectionError("first"),
            {"experiment_id": "exp-ok", "status": "pending", "spec": {}},
        ]
    )
    clients.shape_substrate = MagicMock(return_value={"ok": True})
    clients.capture_substrate = MagicMock(
        return_value={"capture_id": "c2", "status": "started"}
    )
    clients.get_capture = MagicMock(
        return_value={"capture_id": "c2", "status": "finished"}
    )
    clients.get_experiment = MagicMock(
        return_value={"experiment_id": "exp-ok", "status": "completed"}
    )
    clients.query_results = MagicMock(return_value={"results": []})
    clients.patch_experiment = MagicMock(return_value={})

    m = ExecutionManager(clients=clients)
    out = m.run_experiments(
        [_spec("exp-fail"), _spec("exp-ok")],
        enable_ctp_validation=False,
    )
    assert out["summary"]["total_experiments"] == 2
    assert out["summary"]["successful"] == 1
    assert out["summary"]["failed"] == 1


def test_run_experiments_missing_capture_id_marks_capture_status():
    clients = DownstreamClients()
    clients.run_experiment = MagicMock(
        return_value={"experiment_id": "exp-d", "status": "pending"}
    )
    clients.shape_substrate = MagicMock(return_value={})
    clients.capture_substrate = MagicMock(return_value={"status": "started"})
    clients.get_experiment = MagicMock(return_value={"status": "pending"})
    clients.query_results = MagicMock(return_value={"results": []})
    clients.patch_experiment = MagicMock(return_value={})

    m = ExecutionManager(clients=clients)
    out = m.run_experiments([_spec("exp-d")], enable_ctp_validation=False)
    assert out["summary"]["successful"] == 1
    assert (
        out["experiment_results"][0]["capture_status"]["status"] == "missing_capture_id"
    )


def test_tool_router_validate_ctp_surfaces_http_error():
    clients = DownstreamClients()
    clients.validate_ctp_spec = MagicMock(side_effect=OSError("timeout"))
    router = ToolRouter(clients=clients)
    out = router.handle_tool_call("validate_ctp", {"capacity_mbps": 10.0})
    assert out["valid"] is False
    assert any("ctp_validate_failed" in w for w in out["warnings"])


def test_downstream_clients_list_experiments_returns_payload():
    clients = DownstreamClients()
    clients.list_experiments = MagicMock(return_value=[{"experiment_id": "x"}])  # type: ignore[method-assign]
    assert clients.list_experiments() == [{"experiment_id": "x"}]


def test_execution_manager_poll_experiment_disabled_uses_dispatch_status(monkeypatch):
    clients = DownstreamClients()
    clients.run_experiment = MagicMock(
        return_value={"experiment_id": "exp-p", "status": "pending", "spec": {}}
    )
    clients.shape_substrate = MagicMock(return_value={})
    clients.capture_substrate = MagicMock(
        return_value={"capture_id": "c", "status": "finished"}
    )
    clients.get_capture = MagicMock(return_value={"status": "finished"})
    clients.query_results = MagicMock(return_value={"results": []})
    clients.patch_experiment = MagicMock(return_value={})
    clients.get_experiment = MagicMock(return_value={"status": "completed"})
    monkeypatch.setenv("ORCH_POLL_EXPERIMENT_STATUS", "0")

    m = ExecutionManager(clients=clients)
    out = m.run_experiments([_spec("exp-p")], enable_ctp_validation=False)
    assert out["summary"]["successful"] == 1
    assert out["experiment_results"][0]["experiment_status"]["status"] == "pending"
    clients.get_experiment.assert_not_called()
