"""Pytest defaults for orchestration tests (no live CTP by default)."""

import pytest

import app.engine.orchestration_store as orch_store


@pytest.fixture(autouse=True)
def orchestration_test_env(monkeypatch, tmp_path):
    """CTP off; orchestration state in isolated SQLite (not home dir or Telemetry)."""
    orch_store._force_sqlite_store = False
    monkeypatch.setenv("ORCH_ENABLE_CTP_VALIDATION", "0")
    monkeypatch.setenv("ORCH_CTP_SERVICE_PREFLIGHT", "0")
    monkeypatch.setenv("ORCH_NETGENT_EXECUTION_ENABLED", "0")
    monkeypatch.delenv("TELEMETRY_SERVICE_URL", raising=False)
    monkeypatch.setenv("ORCH_SQLITE_PATH", str(tmp_path / "orchestrations.db"))
