"""Pytest defaults for orchestration tests."""

from __future__ import annotations

import copy
import re
from unittest.mock import MagicMock

import pytest

import app.engine.orchestration_store as orch_store

# In-process stand-in for Telemetry PUT/GET/DELETE so unit tests do not need a real service.
_ORCH_STORE: dict[str, dict] = {}


def _orch_id_from_url(url: str) -> str | None:
    m = re.search(r"/orchestrations/([^/?#]+)", str(url))
    return m.group(1) if m else None


def _telemetry_put(url, json=None, timeout=None, **kwargs):
    oid = _orch_id_from_url(url)
    if oid is not None and json is not None:
        _ORCH_STORE[oid] = copy.deepcopy(json)
    r = MagicMock()
    r.status_code = 200
    r.raise_for_status = lambda: None
    return r


def _telemetry_get(url, timeout=None, **kwargs):
    r = MagicMock()
    oid = _orch_id_from_url(url)
    if oid is None or oid not in _ORCH_STORE:
        r.status_code = 404
        return r
    r.status_code = 200
    r.json = lambda: copy.deepcopy(_ORCH_STORE[oid])
    r.raise_for_status = lambda: None
    return r


def _telemetry_delete(url, timeout=None, **kwargs):
    oid = _orch_id_from_url(url)
    if oid is not None:
        _ORCH_STORE.pop(oid, None)
    r = MagicMock()
    r.status_code = 200
    return r


@pytest.fixture(autouse=True)
def orchestration_test_env(monkeypatch):
    """CTP off; orchestration state via in-memory Telemetry HTTP shim."""
    _ORCH_STORE.clear()
    monkeypatch.setenv("ORCH_ENABLE_CTP_VALIDATION", "0")
    monkeypatch.setenv("ORCH_CTP_SERVICE_PREFLIGHT", "0")
    monkeypatch.setenv("ORCH_NETGENT_EXECUTION_ENABLED", "0")
    monkeypatch.setenv("TELEMETRY_SERVICE_URL", "http://telemetry-service:8004")
    monkeypatch.setattr(orch_store.httpx, "put", _telemetry_put)
    monkeypatch.setattr(orch_store.httpx, "get", _telemetry_get)
    monkeypatch.setattr(orch_store.httpx, "delete", _telemetry_delete)
