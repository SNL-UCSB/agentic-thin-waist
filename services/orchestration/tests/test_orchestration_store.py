"""Persistence for orchestration runs (SQLite + Telemetry HTTP)."""

from __future__ import annotations

from unittest.mock import MagicMock

import app.engine.orchestration_store as store
from app.engine.orchestration_store import (
    delete_orchestration,
    load_orchestration,
    save_orchestration,
)
from app.models.schemas import OrchestrationStatus


def test_save_load_sqlite_roundtrip(monkeypatch, tmp_path):
    monkeypatch.delenv("TELEMETRY_SERVICE_URL", raising=False)
    monkeypatch.setenv("ORCH_SQLITE_PATH", str(tmp_path / "o.db"))
    rec = {
        "orchestration_id": "orch-abc",
        "intent": "test intent",
        "status": OrchestrationStatus.generating,
        "experiments": [{"experiment_id": "e1"}],
        "reasoning_steps": [],
        "results": [],
    }
    save_orchestration(rec)
    loaded = load_orchestration("orch-abc")
    assert loaded is not None
    assert loaded["orchestration_id"] == "orch-abc"
    assert loaded["intent"] == "test intent"
    assert loaded["status"] == OrchestrationStatus.generating
    assert loaded["experiments"][0]["experiment_id"] == "e1"


def test_load_missing_returns_none(monkeypatch, tmp_path):
    monkeypatch.delenv("TELEMETRY_SERVICE_URL", raising=False)
    monkeypatch.setenv("ORCH_SQLITE_PATH", str(tmp_path / "empty.db"))
    assert load_orchestration("orch-ghost") is None


def test_delete_orchestration_sqlite(monkeypatch, tmp_path):
    monkeypatch.delenv("TELEMETRY_SERVICE_URL", raising=False)
    monkeypatch.setenv("ORCH_SQLITE_PATH", str(tmp_path / "d.db"))
    save_orchestration(
        {
            "orchestration_id": "orch-xxx",
            "intent": "x",
            "status": OrchestrationStatus.pending,
            "experiments": [],
            "reasoning_steps": [],
            "results": [],
        }
    )
    delete_orchestration("orch-xxx")
    assert load_orchestration("orch-xxx") is None


def test_save_load_telemetry_http(monkeypatch):
    monkeypatch.setenv("TELEMETRY_SERVICE_URL", "http://telemetry:8004")

    def mock_put(url, json=None, timeout=None):
        assert "orch-t1" in str(url)
        assert json is not None and json["intent"] == "nl"
        r = MagicMock()
        r.status_code = 200
        r.raise_for_status = lambda: None
        return r

    def mock_get(url, timeout=None):
        assert "orch-t1" in str(url)
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {
            "orchestration_id": "orch-t1",
            "intent": "nl",
            "status": "complete",
            "experiments": [],
            "reasoning_steps": [],
            "results": [],
        }
        r.raise_for_status = lambda: None
        return r

    monkeypatch.setattr(store.httpx, "put", mock_put)
    monkeypatch.setattr(store.httpx, "get", mock_get)

    rec = {
        "orchestration_id": "orch-t1",
        "intent": "nl",
        "status": OrchestrationStatus.pending,
        "experiments": [],
        "reasoning_steps": [],
        "results": [],
    }
    save_orchestration(rec)
    loaded = load_orchestration("orch-t1")
    assert loaded is not None
    assert loaded["status"] == OrchestrationStatus.complete


def test_load_telemetry_404_returns_none(monkeypatch):
    monkeypatch.setenv("TELEMETRY_SERVICE_URL", "http://telemetry:8004")

    def mock_get(url, timeout=None):
        r = MagicMock()
        r.status_code = 404
        return r

    monkeypatch.setattr(store.httpx, "get", mock_get)
    assert load_orchestration("missing") is None


def test_put_orchestration_alias_matches_save(monkeypatch, tmp_path):
    from app.engine.telemetry_sync import put_orchestration

    monkeypatch.delenv("TELEMETRY_SERVICE_URL", raising=False)
    monkeypatch.setenv("ORCH_SQLITE_PATH", str(tmp_path / "alias.db"))
    put_orchestration(
        {
            "orchestration_id": "orch-z",
            "intent": "i",
            "status": OrchestrationStatus.pending,
            "experiments": [],
            "reasoning_steps": [],
            "results": [],
        }
    )
    assert load_orchestration("orch-z") is not None
