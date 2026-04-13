"""Tests for POST /intent and status/results/reasoning endpoints."""

import os

from fastapi.testclient import TestClient

from app.main import app

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-tests")

client = TestClient(app)


def test_get_orchestration_404_when_unknown():
    """GET /orchestration/{id} returns 404 for unknown id."""
    resp = client.get("/orchestration/orch-nonexistent")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_get_results_404_when_unknown():
    """GET /orchestration/{id}/results returns 404 for unknown id."""
    resp = client.get("/orchestration/orch-nonexistent/results")
    assert resp.status_code == 404
