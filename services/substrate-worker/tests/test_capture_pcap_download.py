"""Tests for GET /capture/{id}/pcap (orchestrator pull path)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

with patch(
    "subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")
):
    from substrate.main import app
    import substrate.main as main_module

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_global_state():
    main_module.CURRENT_BOTTLENECK_STATE = None
    main_module.CURRENT_INTERFACES = None
    main_module.ACTIVE_CAPTURES = {}
    main_module.ACTIVE_REPLAYS = {}
    yield
    main_module.CURRENT_BOTTLENECK_STATE = None
    main_module.CURRENT_INTERFACES = None
    main_module.ACTIVE_CAPTURES = {}
    main_module.ACTIVE_REPLAYS = {}


def test_download_pcap_404_unknown_id():
    r = client.get("/capture/nonexistent-id/pcap")
    assert r.status_code == 404


def test_download_pcap_409_while_running(tmp_path):
    pcap = tmp_path / "run.pcap"
    pcap.write_bytes(b"pcap")
    proc = MagicMock()
    proc.poll.return_value = None
    cid = "test-cap-1"
    main_module.ACTIVE_CAPTURES[cid] = {
        "capture_id": cid,
        "pcap_path": str(pcap),
        "interface": "eth0",
        "capture_filter": "",
        "process": proc,
        "start_time": "2020-01-01T00:00:00",
    }
    r = client.get(f"/capture/{cid}/pcap")
    assert r.status_code == 409


def test_download_pcap_200_when_finished(tmp_path):
    pcap = tmp_path / "done.pcap"
    body = b"\xd4\xc3\xb2\xa1pcap"
    pcap.write_bytes(body)
    proc = MagicMock()
    proc.poll.return_value = 0
    cid = "test-cap-2"
    main_module.ACTIVE_CAPTURES[cid] = {
        "capture_id": cid,
        "pcap_path": str(pcap),
        "interface": "eth0",
        "capture_filter": "",
        "process": proc,
        "start_time": "2020-01-01T00:00:00",
    }
    r = client.get(f"/capture/{cid}/pcap")
    assert r.status_code == 200
    assert r.content == body


def test_download_pcap_401_when_token_required(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_DOWNLOAD_TOKEN", "expected-secret")
    pcap = tmp_path / "t.pcap"
    pcap.write_bytes(b"x")
    proc = MagicMock()
    proc.poll.return_value = 0
    cid = "test-cap-3"
    main_module.ACTIVE_CAPTURES[cid] = {
        "capture_id": cid,
        "pcap_path": str(pcap),
        "interface": "eth0",
        "capture_filter": "",
        "process": proc,
        "start_time": "2020-01-01T00:00:00",
    }
    assert client.get(f"/capture/{cid}/pcap").status_code == 401
    r = client.get(
        f"/capture/{cid}/pcap",
        headers={"X-Capture-Download-Token": "expected-secret"},
    )
    assert r.status_code == 200
    assert r.content == b"x"
