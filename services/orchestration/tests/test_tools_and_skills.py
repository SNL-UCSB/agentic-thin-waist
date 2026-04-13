"""Tests for Step 9-10 OpenClaw declarations and execution."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_tools_lists_openclaw_declarations():
    resp = client.get("/tools")
    assert resp.status_code == 200
    data = resp.json()
    names = [t["name"] for t in data["tools"]]
    assert "run_experiment" in names
    assert "query_results" in names
    assert "validate_ctp" in names
    assert "get_available_applications" in names
    assert "get_available_cc_algorithms" in names
    assert "list_experiments" in names


def test_get_skills_lists_supported_skill_definitions():
    resp = client.get("/skills")
    assert resp.status_code == 200
    data = resp.json()
    names = [s["name"] for s in data["skills"]]
    assert "parameter_sweep" in names
    assert "application_comparison" in names
    assert "baseline_establishment" in names
    assert "network_characterization" in names
    assert "replicate_study" in names


def test_execute_parameter_sweep_skill():
    resp = client.post(
        "/skills/parameter_sweep/execute",
        json={
            "applications": ["youtube", "zoom"],
            "capacity_values": [25],
            "latency_values": [20, 80, 150],
            "num_trials": 1,
        },
    )
    assert resp.status_code == 200
    out = resp.json()
    exps = out["generated_experiments"]
    # generator produces product(capacities, latencies, cc_algorithms) = 1×3×1 = 3
    assert len(exps) == 3
    latencies = sorted({e["latency_ms"] for e in exps})
    assert latencies == [20.0, 80.0, 150.0]
