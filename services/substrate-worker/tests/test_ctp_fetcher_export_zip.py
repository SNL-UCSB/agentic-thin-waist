"""Tests for CTP /export ZIP download (remote CTP service → worker over HTTP)."""

from __future__ import annotations

import io
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from substrate.ctp_fetcher import fetch_ctp


def _make_export_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("download/bg-dl.pcap", b"\xa1\xb2\xc3\xd4fake-dl-pcap")
        zf.writestr("upload/bg-dl.pcap", b"\xa1\xb2\xc3\xd4fake-ul-pcap")
    return buf.getvalue()


@pytest.fixture()
def export_zip_server():
    """Serve GET …/export as a ZIP on localhost (simulates global CTP)."""
    payload = _make_export_zip_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.rstrip("/").endswith("/export"):
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(len(payload)))
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
    base = f"http://{host}:{port}"
    try:
        yield base
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_fetch_ctp_export_zip_extracts_download_and_upload(
    tmp_path: Path, export_zip_server: str
):
    url = f"{export_zip_server}/ctps/ctp-transform-test/export"
    result = fetch_ctp(url, str(tmp_path))

    assert result["name"] == "bg-dl"
    assert Path(result["download_path"]).read_bytes().startswith(b"\xa1\xb2")
    assert Path(result["upload_path"]).read_bytes().startswith(b"\xa1\xb2")
    assert result["fetched"] is True
    assert (tmp_path / "download" / "bg-dl.pcap").is_file()
    assert (tmp_path / "upload" / "bg-dl.pcap").is_file()


def test_fetch_ctp_export_zip_accepts_downlink_uplink_folders(
    tmp_path: Path, export_zip_server: str
):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("downlink/x.pcap", b"dl")
        zf.writestr("uplink/x.pcap", b"ul")

    payload = buf.getvalue()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address
    try:
        url = f"http://{host}:{port}/ctps/foo/export"
        result = fetch_ctp(url, str(tmp_path))
        assert result["name"] == "x"
        assert Path(result["download_path"]).read_text() == "dl"
        assert Path(result["upload_path"]).read_text() == "ul"
    finally:
        server.shutdown()
