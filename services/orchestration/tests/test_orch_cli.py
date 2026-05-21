"""Unit tests for the orch CLI (services/orchestration/scripts/orch_cli.py).

The CLI is a stdlib-only urllib wrapper around the orchestration REST API
(issue #145). Tests mock ``urllib.request.urlopen`` so they exercise the
CLI's request-shaping, response-parsing, and exit-code conventions without
needing a running service.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest


def _load_cli_module() -> types.ModuleType:
    """Load orch_cli.py by path so the test runs regardless of CWD / pythonpath.

    The CLI deliberately lives outside the ``app`` package (it's a standalone
    user-facing tool), so we can't rely on the orchestration test harness's
    ``app.*`` import path.
    """
    here = Path(__file__).resolve().parent
    cli_path = here.parent / "scripts" / "orch_cli.py"
    spec = importlib.util.spec_from_file_location("orch_cli_under_test", cli_path)
    assert spec and spec.loader, f"cannot locate {cli_path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


cli = _load_cli_module()


class _FakeResponse:
    """Minimal stand-in for the object returned by urllib.request.urlopen()."""

    def __init__(self, body: dict | str, status: int = 200) -> None:
        if isinstance(body, dict):
            payload = json.dumps(body).encode("utf-8")
        else:
            payload = body.encode("utf-8")
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


@pytest.fixture
def capture_request(monkeypatch):
    """Capture the urllib.request.Request the CLI built and feed back a mock response.

    Yields a dict that gets populated on each call so tests can assert on the
    request method, URL, headers, and body.
    """
    seen: dict = {}

    def _factory(response_body, status=200):
        def _urlopen(req, timeout=None):
            seen["method"] = req.get_method()
            seen["url"] = req.full_url
            seen["headers"] = {k.lower(): v for k, v in req.header_items()}
            seen["body"] = req.data.decode("utf-8") if req.data else None
            return _FakeResponse(response_body, status=status)

        monkeypatch.setattr(cli.urllib.request, "urlopen", _urlopen)

    return seen, _factory


def test_intent_posts_text_and_prints_orchestration_id(capsys, capture_request):
    seen, install = capture_request
    install({"orchestration_id": "orch-abc123", "status": "pending"})

    rc = cli.main(["intent", "Run iperf3 under cubic and bbr"])

    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out == ["orch-abc123"]
    assert seen["method"] == "POST"
    assert seen["url"].endswith("/intent")
    assert seen["headers"]["content-type"] == "application/json"
    body = json.loads(seen["body"])
    assert body == {
        "intent": "Run iperf3 under cubic and bbr",
        "context": {},
        "preferences": {},
    }


def test_intent_propagates_http_error(capsys, capture_request):
    _, install = capture_request
    install({"detail": "missing intent"}, status=400)

    rc = cli.main(["intent", ""])

    assert rc == 1
    err = capsys.readouterr().err
    assert "HTTP 400" in err


def test_get_id_prints_one_experiment_id_per_line(capsys, capture_request):
    seen, install = capture_request
    install(
        {
            "orchestration_id": "orch-abc",
            "status": "complete",
            "generated_experiments": [
                {"experiment_id": "exp-1", "cc_algorithm": "cubic"},
                {"experiment_id": "exp-2", "cc_algorithm": "bbr"},
            ],
        }
    )

    rc = cli.main(["get_id", "orch-abc"])

    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out == ["exp-1", "exp-2"]
    assert seen["method"] == "GET"
    assert seen["url"].endswith("/orchestration/orch-abc")


def test_get_id_returns_404_when_orchestration_missing(capsys, capture_request):
    _, install = capture_request
    install({"detail": "Orchestration not found"}, status=404)

    rc = cli.main(["get_id", "orch-missing"])

    assert rc == 1
    err = capsys.readouterr().err
    assert "orch-missing" in err


def test_status_polls_until_terminal_and_returns_zero_on_complete(capsys, monkeypatch):
    """Status loops until the API returns a terminal status, then exits 0 (complete) or 1 (failed)."""
    # Three calls: pending → executing → complete.
    responses = [
        {"status": "pending", "generated_experiments": []},
        {
            "status": "executing",
            "generated_experiments": [{"experiment_id": "exp-1"}],
        },
        {
            "status": "complete",
            "generated_experiments": [{"experiment_id": "exp-1"}],
        },
    ]
    iter_responses = iter(responses)

    def _urlopen(req, timeout=None):
        return _FakeResponse(next(iter_responses), status=200)

    monkeypatch.setattr(cli.urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr(cli.time, "sleep", lambda _s: None)

    rc = cli.main(["status", "orch-abc"])

    assert rc == 0
    out_lines = capsys.readouterr().out.strip().splitlines()
    # We collapse duplicate summaries, so we expect three distinct lines
    # because each status changes between polls.
    assert len(out_lines) == 3
    assert "status=pending" in out_lines[0]
    assert "status=executing" in out_lines[1]
    assert "status=complete" in out_lines[2]


def test_status_returns_nonzero_on_failure(capsys, monkeypatch):
    def _urlopen(req, timeout=None):
        return _FakeResponse(
            {"status": "failed", "error": "boom", "generated_experiments": []},
            status=200,
        )

    monkeypatch.setattr(cli.urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr(cli.time, "sleep", lambda _s: None)

    rc = cli.main(["status", "orch-x"])
    assert rc == 1


def test_debug_renders_status_experiments_and_results(capsys, monkeypatch):
    """Debug fans out to /orchestration, /results, and /reasoning."""
    responses = {
        "/orchestration/orch-abc": {
            "orchestration_id": "orch-abc",
            "status": "complete",
            "error": None,
            "generated_experiments": [
                {
                    "experiment_id": "exp-1",
                    "cc_algorithm": "cubic",
                    "capacity_mbps": 5.0,
                    "latency_ms": 50.0,
                    "aqm_policy": "pfifo",
                    "num_trials": 1,
                }
            ],
            "lifecycle_stages": [
                {
                    "stage": "received_intent",
                    "timestamp": "2026-05-21T01:00:00Z",
                    "experiment_id": None,
                }
            ],
            "detailed_progress": {"stage_flags": {"received_intent": True}},
        },
        "/orchestration/orch-abc/results": {
            "results": [
                {
                    "experiment_id": "exp-1",
                    "status": "success",
                    "run": {
                        "congestion": {"current_algorithm": "cubic"},
                        "workflow_result": {"congestion_observed": {"cubic": 35}},
                    },
                }
            ]
        },
        "/orchestration/orch-abc/reasoning": {
            "reasoning_steps": [{"summary": "parsed intent"}, "done"]
        },
    }

    def _urlopen(req, timeout=None):
        path = req.full_url.split("8005", 1)[-1]  # everything after base URL host
        return _FakeResponse(responses[path], status=200)

    monkeypatch.setattr(cli.urllib.request, "urlopen", _urlopen)

    rc = cli.main(["debug", "orch-abc"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "=== orchestration orch-abc ===" in out
    assert "status      : complete" in out
    assert "experiments : 1 generated" in out
    assert "exp-1" in out
    assert "cc_set=cubic observed={'cubic': 35}" in out
    assert "reasoning (2 steps)" in out
    assert "parsed intent" in out


def test_url_override_via_flag(capsys, capture_request):
    _, install = capture_request
    install({"orchestration_id": "orch-xyz"})

    rc = cli.main(["--url", "http://custom:9999", "intent", "hi"])

    assert rc == 0


def test_url_override_via_env(monkeypatch, capsys, capture_request):
    seen, install = capture_request
    install({"orchestration_id": "orch-env"})

    monkeypatch.setenv("ORCH_URL", "http://from-env:1234")
    # Re-build parser to re-read env var default.
    rc = cli.main(["intent", "hi"])

    assert rc == 0
    assert seen["url"].startswith("http://from-env:1234")
