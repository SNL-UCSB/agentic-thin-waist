"""Tests for POST /intent and status/results/reasoning endpoints (Step 8)."""

import os
import time
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app

# Ensure ClaudeClient can be instantiated in tests (no real API calls; parse is mocked)
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-tests")

client = TestClient(app)

SAMPLE_PARSED = {
    "applications": ["zoom"],
    "capacities": [25],
    "latencies": [50],
    "cc_algorithms": ["cubic"],
    "num_trials": 1,
    "reasoning": "test reasoning",
}


def test_post_intent_returns_202_with_orchestration_id():
    """POST /intent returns 202 and includes orchestration_id."""
    with patch("app.api.intent.IntentParser") as MockParser:
        MockParser.return_value.parse.return_value = SAMPLE_PARSED.copy()
        resp = client.post(
            "/intent",
            json={"intent": "Compare Zoom under 25 Mbps"},
        )
    assert resp.status_code == 202
    data = resp.json()
    assert "orchestration_id" in data
    assert data["orchestration_id"].startswith("orch-")
    assert data["status"] == "pending"
    assert data["intent"] == "Compare Zoom under 25 Mbps"
    assert data["generated_experiments"] == 0


def test_get_orchestration_status_returns_progress():
    """GET /orchestration/{id} returns status and experiments after completion."""
    with patch("app.api.intent.IntentParser") as MockParser:
        MockParser.return_value.parse.return_value = SAMPLE_PARSED.copy()
        resp = client.post(
            "/intent",
            json={"intent": "Compare Zoom under 25 Mbps"},
        )
    assert resp.status_code == 202
    orch_id = resp.json()["orchestration_id"]

    # Poll until complete (background task runs after response)
    for _ in range(20):
        status_resp = client.get(f"/orchestration/{orch_id}")
        assert status_resp.status_code == 200
        if status_resp.json()["status"] == "complete":
            break
        time.sleep(0.1)
    else:
        pytest.fail("Orchestration did not complete within 2 seconds")

    data = status_resp.json()
    assert data["orchestration_id"] == orch_id
    assert data["status"] == "complete"
    assert "generated_experiments" in data
    assert len(data["generated_experiments"]) >= 1
    assert "detailed_progress" in data
    assert "iteration_phase_flags" in data["detailed_progress"]


def test_get_orchestration_results_after_completion():
    """GET /orchestration/{id}/results returns results after completion."""
    with patch("app.api.intent.IntentParser") as MockParser:
        MockParser.return_value.parse.return_value = SAMPLE_PARSED.copy()
        resp = client.post(
            "/intent",
            json={"intent": "Compare Zoom under 25 Mbps"},
        )
    assert resp.status_code == 202
    orch_id = resp.json()["orchestration_id"]

    for _ in range(20):
        results_resp = client.get(f"/orchestration/{orch_id}/results")
        assert results_resp.status_code == 200
        if results_resp.json()["status"] == "complete":
            break
        time.sleep(0.1)
    else:
        pytest.fail("Orchestration did not complete within 2 seconds")

    data = results_resp.json()
    assert data["orchestration_id"] == orch_id
    assert data["status"] == "complete"
    assert "results" in data
    # Step 8 stubs dispatch so results list may be empty
    assert isinstance(data["results"], list)


def test_get_orchestration_404_when_unknown():
    """GET /orchestration/{id} returns 404 for unknown id."""
    resp = client.get("/orchestration/orch-nonexistent")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_get_results_404_when_unknown():
    """GET /orchestration/{id}/results returns 404 for unknown id."""
    resp = client.get("/orchestration/orch-nonexistent/results")
    assert resp.status_code == 404


def test_get_reasoning_returns_steps():
    """GET /orchestration/{id}/reasoning returns reasoning_steps."""
    with patch("app.api.intent.IntentParser") as MockParser:
        MockParser.return_value.parse.return_value = SAMPLE_PARSED.copy()
        resp = client.post(
            "/intent",
            json={"intent": "Compare Zoom under 25 Mbps"},
        )
    orch_id = resp.json()["orchestration_id"]
    # Wait for completion
    for _ in range(20):
        if client.get(f"/orchestration/{orch_id}").json()["status"] == "complete":
            break
        time.sleep(0.1)

    reasoning_resp = client.get(f"/orchestration/{orch_id}/reasoning")
    assert reasoning_resp.status_code == 200
    data = reasoning_resp.json()
    assert data["orchestration_id"] == orch_id
    assert "reasoning_steps" in data
    assert isinstance(data["reasoning_steps"], list)
