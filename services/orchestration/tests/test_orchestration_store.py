"""Persistence for orchestration runs via Telemetry HTTP."""

from __future__ import annotations

from unittest.mock import MagicMock

import app.engine.orchestration_store as store
from app.engine.orchestration_store import (
    delete_orchestration,
    load_orchestration,
    save_orchestration,
)
from app.models.schemas import OrchestrationStatus


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


def test_save_requires_orchestration_id():
    import pytest

    with pytest.raises(ValueError, match="orchestration_id is required"):
        save_orchestration({"intent": "missing id"})


def test_delete_orchestration(monkeypatch):
    monkeypatch.setenv("TELEMETRY_SERVICE_URL", "http://telemetry:8004")
    deleted_ids = []

    def mock_delete(url, timeout=None):
        deleted_ids.append(url)
        r = MagicMock()
        r.status_code = 200
        return r

    monkeypatch.setattr(store.httpx, "delete", mock_delete)
    delete_orchestration("orch-del")
    assert any("orch-del" in str(u) for u in deleted_ids)


def test_serialize_status_enum():
    payload = store._serialize_orch(
        {
            "orchestration_id": "o1",
            "status": OrchestrationStatus.generating,
        }
    )
    assert payload["status"] == "generating"


def test_parse_loaded_restores_enum():
    data = store._parse_loaded({"status": "complete"})
    assert data["status"] == OrchestrationStatus.complete


def test_parse_loaded_invalid_status_defaults_to_pending():
    data = store._parse_loaded({"status": "bogus_status"})
    assert data["status"] == OrchestrationStatus.pending
