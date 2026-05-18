"""Stream a finished qtrace JSONL from substrate to telemetry as an artifact.

Mirrors :mod:`telemetry_capture_pull` but for the queue-occupancy trace
produced by the substrate worker's ``/qtrace`` endpoint. Traces are small
(seconds of JSONL records), so we fetch them in one shot rather than chunked.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)


def stream_qtrace_to_telemetry(
    *,
    worker_base_url: str,
    qtrace_id: str,
    telemetry_base_url: str,
    result_id: str,
    trace_filename: str,
    download_token: str | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """GET JSONL from substrate, POST multipart to telemetry /artifacts."""
    base_w = worker_base_url.rstrip("/")
    base_t = telemetry_base_url.rstrip("/")
    tmo = timeout or float(os.getenv("ORCH_PCAP_DOWNLOAD_TIMEOUT_SECONDS", "600"))

    token = download_token
    if token is None:
        token = (os.getenv("CAPTURE_DOWNLOAD_TOKEN") or "").strip() or None

    headers_get: dict[str, str] = {}
    if token:
        headers_get["X-Capture-Download-Token"] = token

    try:
        resp = requests.get(
            f"{base_w}/qtrace/{qtrace_id}/trace",
            headers=headers_get,
            timeout=tmo,
        )
    except Exception as exc:
        logger.warning("QTrace download failed: %s", exc, exc_info=True)
        return {"status": "error", "detail": str(exc), "phase": "download"}

    if resp.status_code != 200:
        return {
            "status": "error",
            "detail": (resp.text or "")[:2000],
            "http_status": resp.status_code,
            "phase": "download",
        }

    files = {
        "file": (
            trace_filename,
            resp.content,
            "application/x-ndjson",
        ),
    }
    data = {"result_id": result_id, "artifact_type": "queue_trace"}
    try:
        post_resp = requests.post(
            f"{base_t}/artifacts", data=data, files=files, timeout=tmo
        )
    except Exception as exc:
        logger.warning("QTrace upload to telemetry failed: %s", exc, exc_info=True)
        return {"status": "error", "detail": str(exc), "phase": "upload"}

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
