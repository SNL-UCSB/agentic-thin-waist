"""Pytest defaults for orchestration tests."""

import pytest


@pytest.fixture(autouse=True)
def orchestration_test_env(monkeypatch):
    """CTP off; orchestration state via Telemetry Service."""
    monkeypatch.setenv("ORCH_ENABLE_CTP_VALIDATION", "0")
    monkeypatch.setenv("ORCH_CTP_SERVICE_PREFLIGHT", "0")
    monkeypatch.setenv("ORCH_NETGENT_EXECUTION_ENABLED", "0")
    monkeypatch.setenv("TELEMETRY_SERVICE_URL", "http://telemetry-service:8004")
