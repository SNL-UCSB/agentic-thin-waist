"""Unit tests for the local CTP source mode (ORCH_CTP_SOURCE=local_list).

Tests cover:
- Default service mode still delegates to the CTP service.
- .txt list: plain name selection, download/upload paths constructed correctly.
- .json list: filtering by ctp_capacity_range when mean_mbps is present.
- Range fallback: returns None (no CTP) when no match and fallback is disabled;
  returns a candidate from the full list when fallback is enabled.
- Missing list file or empty list returns None.
- Selection modes: first (default) and random.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.engine import orchestration_manager as om


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_txt(tmp_path: pathlib.Path, names: list[str]) -> pathlib.Path:
    p = tmp_path / "ctps.txt"
    p.write_text("\n".join(names))
    return p


def _write_json(tmp_path: pathlib.Path, entries: list[dict]) -> pathlib.Path:
    p = tmp_path / "ctps.json"
    p.write_text(json.dumps(entries))
    return p


def _make_pcaps(root: pathlib.Path, name: str) -> None:
    """Create placeholder download/upload pcap files."""
    (root / "download").mkdir(parents=True, exist_ok=True)
    (root / "upload").mkdir(parents=True, exist_ok=True)
    (root / "download" / f"{name}.pcap").write_bytes(b"")
    (root / "upload" / f"{name}.pcap").write_bytes(b"")


# ---------------------------------------------------------------------------
# service mode (default) — no change to existing behavior
# ---------------------------------------------------------------------------


def test_select_ctp_service_mode_calls_ctp_service(monkeypatch):
    """Default ORCH_CTP_SOURCE=service must call the CTP service as before."""
    monkeypatch.setenv("ORCH_CTP_SOURCE", "service")
    seen = {}

    class FakeClients:
        def __init__(self, ctp_service_url=None):
            pass

        def select_ctps(self, payload):
            seen["called"] = True
            return {"ctps": [{"ctp_id": "svc-ctp-1", "intensity": {"mean_mbps": 5.0}}]}

    monkeypatch.setattr(om, "DownstreamClients", FakeClients)
    result = om._select_ctp({"lower_value": 4.0, "higher_value": 7.0}, "exp-svc")
    assert seen.get("called"), "Expected CTP service to be queried"
    assert result is not None
    assert result["ctp_id"] == "svc-ctp-1"


def test_select_ctp_default_is_service_mode(monkeypatch):
    """Unset ORCH_CTP_SOURCE must use service mode."""
    monkeypatch.delenv("ORCH_CTP_SOURCE", raising=False)
    seen = {}

    class FakeClients:
        def __init__(self, ctp_service_url=None):
            pass

        def select_ctps(self, payload):
            seen["called"] = True
            return {"ctps": []}

    monkeypatch.setattr(om, "DownstreamClients", FakeClients)
    om._select_ctp(None, "exp-default")
    assert seen.get("called"), "Expected CTP service to be queried by default"


# ---------------------------------------------------------------------------
# _load_local_ctp_candidates
# ---------------------------------------------------------------------------


def test_load_candidates_txt(tmp_path):
    list_path = _write_txt(tmp_path, ["ctp_a", "ctp_b", "ctp_c"])
    candidates = om._load_local_ctp_candidates(str(list_path))
    assert len(candidates) == 3
    assert candidates[0] == {"name": "ctp_a", "mean_mbps": None}
    assert candidates[2] == {"name": "ctp_c", "mean_mbps": None}


def test_load_candidates_json_with_intensity(tmp_path):
    entries = [
        {"name": "ctp_x", "mean_mbps": 3.5},
        {"name": "ctp_y", "mean_mbps": 8.0},
    ]
    list_path = _write_json(tmp_path, entries)
    candidates = om._load_local_ctp_candidates(str(list_path))
    assert len(candidates) == 2
    assert candidates[0]["name"] == "ctp_x"
    assert candidates[0]["mean_mbps"] == pytest.approx(3.5)


def test_load_candidates_json_without_intensity(tmp_path):
    entries = [{"name": "ctp_plain"}]
    list_path = _write_json(tmp_path, entries)
    candidates = om._load_local_ctp_candidates(str(list_path))
    assert candidates[0]["mean_mbps"] is None


def test_load_candidates_missing_file():
    candidates = om._load_local_ctp_candidates("/nonexistent/path/ctps.txt")
    assert candidates == []


def test_load_candidates_empty_txt(tmp_path):
    p = tmp_path / "ctps.txt"
    p.write_text("  \n\n")
    assert om._load_local_ctp_candidates(str(p)) == []


# ---------------------------------------------------------------------------
# _select_local_ctp — basic selection
# ---------------------------------------------------------------------------


def test_select_local_ctp_txt_returns_correct_paths(tmp_path, monkeypatch):
    name = "cluster0_tree1_profile1"
    _make_pcaps(tmp_path, name)
    list_path = _write_txt(tmp_path, [name])

    monkeypatch.setenv("ORCH_CTP_SOURCE", "local_list")
    monkeypatch.setenv("ORCH_LOCAL_CTP_ROOT", str(tmp_path))
    monkeypatch.setenv("ORCH_LOCAL_CTP_LIST", str(list_path))

    result = om._select_local_ctp(None, "exp-txt")
    assert result is not None
    assert result["ctp_id"] == name
    assert result["download_pcap"] == str(tmp_path / "download" / f"{name}.pcap")
    assert result["upload_pcap"] == str(tmp_path / "upload" / f"{name}.pcap")
    assert result["source"] == "local_list"


def test_select_ctp_dispatches_to_local(tmp_path, monkeypatch):
    """_select_ctp must route to local mode when ORCH_CTP_SOURCE=local_list."""
    name = "ctp_local"
    _make_pcaps(tmp_path, name)
    list_path = _write_txt(tmp_path, [name])

    monkeypatch.setenv("ORCH_CTP_SOURCE", "local_list")
    monkeypatch.setenv("ORCH_LOCAL_CTP_ROOT", str(tmp_path))
    monkeypatch.setenv("ORCH_LOCAL_CTP_LIST", str(list_path))

    result = om._select_ctp(None, "exp-dispatch")
    assert result is not None
    assert result["source"] == "local_list"


# ---------------------------------------------------------------------------
# Range filtering
# ---------------------------------------------------------------------------


def test_select_local_ctp_filters_by_range(tmp_path, monkeypatch):
    entries = [
        {"name": "low_ctp", "mean_mbps": 2.0},
        {"name": "mid_ctp", "mean_mbps": 6.0},
        {"name": "high_ctp", "mean_mbps": 20.0},
    ]
    for e in entries:
        _make_pcaps(tmp_path, e["name"])
    list_path = _write_json(tmp_path, entries)

    monkeypatch.setenv("ORCH_LOCAL_CTP_ROOT", str(tmp_path))
    monkeypatch.setenv("ORCH_LOCAL_CTP_LIST", str(list_path))
    monkeypatch.delenv("ORCH_LOCAL_CTP_ALLOW_RANGE_FALLBACK", raising=False)

    result = om._select_local_ctp({"lower_value": 5.0, "higher_value": 10.0}, "exp-range")
    assert result is not None
    assert result["ctp_id"] == "mid_ctp"


def test_select_local_ctp_no_range_match_returns_none(tmp_path, monkeypatch):
    entries = [{"name": "far_ctp", "mean_mbps": 50.0}]
    _make_pcaps(tmp_path, "far_ctp")
    list_path = _write_json(tmp_path, entries)

    monkeypatch.setenv("ORCH_LOCAL_CTP_ROOT", str(tmp_path))
    monkeypatch.setenv("ORCH_LOCAL_CTP_LIST", str(list_path))
    monkeypatch.setenv("ORCH_LOCAL_CTP_ALLOW_RANGE_FALLBACK", "false")

    result = om._select_local_ctp({"lower_value": 1.0, "higher_value": 10.0}, "exp-no-match")
    assert result is None


def test_select_local_ctp_no_range_match_with_fallback(tmp_path, monkeypatch):
    entries = [{"name": "far_ctp", "mean_mbps": 50.0}]
    _make_pcaps(tmp_path, "far_ctp")
    list_path = _write_json(tmp_path, entries)

    monkeypatch.setenv("ORCH_LOCAL_CTP_ROOT", str(tmp_path))
    monkeypatch.setenv("ORCH_LOCAL_CTP_LIST", str(list_path))
    monkeypatch.setenv("ORCH_LOCAL_CTP_ALLOW_RANGE_FALLBACK", "true")

    result = om._select_local_ctp({"lower_value": 1.0, "higher_value": 10.0}, "exp-fallback")
    assert result is not None
    assert result["ctp_id"] == "far_ctp"


def test_select_local_ctp_no_mean_mbps_always_matches(tmp_path, monkeypatch):
    """Entries without mean_mbps must always pass the range filter."""
    _make_pcaps(tmp_path, "unnamed_ctp")
    list_path = _write_txt(tmp_path, ["unnamed_ctp"])

    monkeypatch.setenv("ORCH_LOCAL_CTP_ROOT", str(tmp_path))
    monkeypatch.setenv("ORCH_LOCAL_CTP_LIST", str(list_path))

    result = om._select_local_ctp({"lower_value": 1.0, "higher_value": 2.0}, "exp-no-mbps")
    assert result is not None
    assert result["ctp_id"] == "unnamed_ctp"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_select_local_ctp_missing_root(monkeypatch, tmp_path):
    monkeypatch.setenv("ORCH_LOCAL_CTP_ROOT", "")
    monkeypatch.setenv("ORCH_LOCAL_CTP_LIST", str(tmp_path / "ctps.txt"))
    assert om._select_local_ctp(None, "exp-no-root") is None


def test_select_local_ctp_missing_list(monkeypatch, tmp_path):
    monkeypatch.setenv("ORCH_LOCAL_CTP_ROOT", str(tmp_path))
    monkeypatch.setenv("ORCH_LOCAL_CTP_LIST", "")
    assert om._select_local_ctp(None, "exp-no-list") is None


def test_select_local_ctp_empty_list(monkeypatch, tmp_path):
    p = tmp_path / "ctps.txt"
    p.write_text("")
    monkeypatch.setenv("ORCH_LOCAL_CTP_ROOT", str(tmp_path))
    monkeypatch.setenv("ORCH_LOCAL_CTP_LIST", str(p))
    assert om._select_local_ctp(None, "exp-empty-list") is None


def test_select_local_ctp_random_selection(tmp_path, monkeypatch):
    names = [f"ctp_{i}" for i in range(5)]
    for n in names:
        _make_pcaps(tmp_path, n)
    list_path = _write_txt(tmp_path, names)

    monkeypatch.setenv("ORCH_LOCAL_CTP_ROOT", str(tmp_path))
    monkeypatch.setenv("ORCH_LOCAL_CTP_LIST", str(list_path))
    monkeypatch.setenv("ORCH_LOCAL_CTP_SELECTION", "random")

    results = {om._select_local_ctp(None, f"exp-{i}")["ctp_id"] for i in range(30)}
    assert len(results) > 1, "random selection should return different entries over many calls"


def test_select_local_ctp_first_selection_is_deterministic(tmp_path, monkeypatch):
    names = ["ctp_alpha", "ctp_beta", "ctp_gamma"]
    for n in names:
        _make_pcaps(tmp_path, n)
    list_path = _write_txt(tmp_path, names)

    monkeypatch.setenv("ORCH_LOCAL_CTP_ROOT", str(tmp_path))
    monkeypatch.setenv("ORCH_LOCAL_CTP_LIST", str(list_path))
    monkeypatch.setenv("ORCH_LOCAL_CTP_SELECTION", "first")

    results = {om._select_local_ctp(None, f"exp-{i}")["ctp_id"] for i in range(5)}
    assert results == {"ctp_alpha"}
