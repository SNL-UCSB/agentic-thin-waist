"""Integration: orchestrator builds /export URL; substrate fetcher loads ZIP over HTTP.

Simulates orchestration and substrate on different hosts: the only link is an HTTP
URL (no shared filesystem).  A local HTTP server stands in for the global CTP service.
"""

from __future__ import annotations

import io
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

# Repo layout: tests/integration/ → workspace root is parents[2]
_WORKSPACE = Path(__file__).resolve().parents[2]
_SUBSTRATE_SRC = _WORKSPACE / "services" / "substrate-worker" / "src"
if str(_SUBSTRATE_SRC) not in sys.path:
    sys.path.insert(0, str(_SUBSTRATE_SRC))

from substrate.ctp_fetcher import fetch_ctp  # noqa: E402

from app.engine.orchestration_manager import (  # noqa: E402
    global_ctp_export_pointer,
    _ctp_pointer_for_worker,
)


def test_global_ctp_export_pointer_matches_ctp_service_url_pattern(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CTP_SERVICE_GLOBAL", "http://ctp-global.example:8001")
    ptr = global_ctp_export_pointer(
        "ctp-transform-ctp-ctp_samples-169.231.135.128_29-w0019-6mbps"
    )
    assert ptr == (
        "http://ctp-global.example:8001/ctps/"
        "ctp-transform-ctp-ctp_samples-169.231.135.128_29-w0019-6mbps/export"
    )


def test_ctp_pointer_for_worker_export_vs_local_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CTP_SERVICE_GLOBAL", "http://ctp:8001")
    ctp = {
        "ctp_id": "ctp-transform-foo",
        "download_pcap": "/mnt/global/downlink/foo.pcap",
    }
    monkeypatch.setenv("ORCH_CTP_POINTER_MODE", "export")
    assert (
        _ctp_pointer_for_worker(ctp) == "http://ctp:8001/ctps/ctp-transform-foo/export"
    )

    monkeypatch.setenv("ORCH_CTP_POINTER_MODE", "local_path")
    assert _ctp_pointer_for_worker(ctp) == "/mnt/global/downlink/foo.pcap"


def test_end_to_end_export_url_fetched_like_remote_ctp_service(tmp_path: Path) -> None:
    """Worker-side fetch from URL only (orchestrator would pass this string)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("download/replay.pcap", b"pcap-download-bytes")
        zf.writestr("upload/replay.pcap", b"pcap-upload-bytes")
    payload = buf.getvalue()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.rstrip("/").endswith("/export"):
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_error(404)

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        url = f"http://{host}:{port}/ctps/ctp-transform-demo/export"
        result = fetch_ctp(url, str(tmp_path))
        assert result["name"] == "replay"
        assert Path(result["download_path"]).read_bytes() == b"pcap-download-bytes"
        assert Path(result["upload_path"]).read_bytes() == b"pcap-upload-bytes"
    finally:
        server.shutdown()
        thread.join(timeout=5)
