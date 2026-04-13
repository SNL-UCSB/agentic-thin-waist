"""Stream a finished capture PCAP from substrate to telemetry (no local file copy)."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Iterator

import httpx
import requests

logger = logging.getLogger(__name__)


def _multipart_pcap_chunks(
    *,
    boundary: str,
    result_id: str,
    artifact_type: str,
    filename: str,
    pcap_chunk_iter: Iterator[bytes],
) -> Iterator[bytes]:
    """Yield multipart chunks while streaming the file payload."""
    crlf = b"\r\n"
    bnd = f"--{boundary}".encode("ascii")

    yield bnd + crlf
    yield (
        b'Content-Disposition: form-data; name="result_id"'
        + crlf
        + crlf
        + result_id.encode("utf-8")
        + crlf
    )
    yield bnd + crlf
    yield (
        b'Content-Disposition: form-data; name="artifact_type"'
        + crlf
        + crlf
        + artifact_type.encode("ascii")
        + crlf
    )
    yield bnd + crlf
    fn = filename.replace("\\", "\\\\").replace('"', '\\"')
    yield (
        f'Content-Disposition: form-data; name="file"; filename="{fn}"'.encode("utf-8")
        + crlf
        + b"Content-Type: application/vnd.tcpdump.pcap"
        + crlf
        + crlf
    )
    for chunk in pcap_chunk_iter:
        if chunk:
            yield chunk
    yield crlf + bnd + b"--" + crlf


def stream_capture_pcap_to_telemetry(
    *,
    worker_base_url: str,
    capture_id: str,
    telemetry_base_url: str,
    result_id: str,
    pcap_filename: str,
    download_token: str | None = None,
    download_timeout: float | None = None,
) -> dict[str, Any]:
    """GET PCAP from substrate (streaming) and POST multipart to telemetry /artifacts."""
    base_w = worker_base_url.rstrip("/")
    base_t = telemetry_base_url.rstrip("/")
    timeout = download_timeout or float(
        os.getenv("ORCH_PCAP_DOWNLOAD_TIMEOUT_SECONDS", "600")
    )
    token = download_token
    if token is None:
        token = (os.getenv("CAPTURE_DOWNLOAD_TOKEN") or "").strip() or None

    headers_get: dict[str, str] = {}
    if token:
        headers_get["X-Capture-Download-Token"] = token

    url_get = f"{base_w}/capture/{capture_id}/pcap"
    boundary = f"orchPcap{uuid.uuid4().hex}"

    try:
        with httpx.stream(
            "GET",
            url_get,
            headers=headers_get,
            timeout=timeout,
        ) as response:
            if response.status_code != 200:
                detail = ""
                try:
                    detail = response.text[:2000]
                except Exception:
                    pass
                return {
                    "status": "error",
                    "detail": detail or f"HTTP {response.status_code}",
                    "http_status": response.status_code,
                    "phase": "download",
                }

            chunk_iter = response.iter_bytes(chunk_size=65536)

            def body_iter() -> Iterator[bytes]:
                yield from _multipart_pcap_chunks(
                    boundary=boundary,
                    result_id=result_id,
                    artifact_type="pcap",
                    filename=pcap_filename,
                    pcap_chunk_iter=chunk_iter,
                )

            post_resp = requests.post(
                f"{base_t}/artifacts",
                data=body_iter(),
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
                timeout=timeout,
            )
    except Exception as exc:
        logger.warning("PCAP stream to telemetry failed: %s", exc, exc_info=True)
        return {"status": "error", "detail": str(exc), "phase": "unknown"}

    if post_resp.status_code != 201:
        return {
            "status": "error",
            "detail": (post_resp.text or "")[:2000],
            "http_status": post_resp.status_code,
            "phase": "upload",
        }
    try:
        body = post_resp.json()
    except Exception:
        body = {}
    return {"status": "stored", **body}
