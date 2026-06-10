"""Persistent orchestration lifecycle via the Telemetry Service (PostgreSQL)."""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Any

import httpx

from app.models.schemas import OrchestrationStatus

logger = logging.getLogger(__name__)


def _telemetry_base() -> str:
    return os.getenv("TELEMETRY_SERVICE_URL", "http://telemetry-service:8004").rstrip(
        "/"
    )


def _timeout() -> float:
    return float(os.getenv("ORCH_HTTP_TIMEOUT_SECONDS", "20"))


def _serialize_status(status: Any) -> str:
    if isinstance(status, OrchestrationStatus):
        return status.value
    if hasattr(status, "value"):
        return str(status.value)
    return str(status)


def _serialize_orch(orch: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-serializable copy with enums converted to strings."""
    out: dict[str, Any] = {}
    for k, v in orch.items():
        if k == "status":
            out[k] = _serialize_status(v)
        else:
            out[k] = v
    return out


def _parse_loaded(data: dict[str, Any]) -> dict[str, Any]:
    """Restore OrchestrationStatus enum from the persisted dict."""
    out = dict(data)
    s = out.get("status", "pending")
    try:
        out["status"] = OrchestrationStatus(s)
    except ValueError:
        out["status"] = OrchestrationStatus.pending
    return out


def _save_retries() -> int:
    try:
        return max(1, int(os.getenv("ORCH_SAVE_RETRIES", "4")))
    except ValueError:
        return 4


def save_orchestration(orch: dict[str, Any]) -> None:
    """Upsert full orchestration state via Telemetry PUT /orchestrations/{id}.

    Retries on transient failures (timeouts / 5xx) with exponential backoff so a
    momentary telemetry slowdown during a synchronized burst does not drop the
    orchestration record.
    """
    oid = orch.get("orchestration_id")
    if not oid:
        raise ValueError("orchestration_id is required")
    payload = _serialize_orch(orch)
    attempts = _save_retries()
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            resp = httpx.put(
                f"{_telemetry_base()}/orchestrations/{oid}",
                json=payload,
                timeout=_timeout(),
            )
            resp.raise_for_status()
            return
        except Exception as exc:  # noqa: BLE001 - retry on any transient error
            last_exc = exc
            if attempt < attempts:
                time.sleep(min(8.0, 1.0 * (2 ** (attempt - 1))) + random.uniform(0, 1.0))
    if last_exc is not None:
        raise last_exc


def load_orchestration(orch_id: str) -> dict[str, Any] | None:
    """Load orchestration state from Telemetry GET /orchestrations/{id}."""
    try:
        resp = httpx.get(
            f"{_telemetry_base()}/orchestrations/{orch_id}",
            timeout=_timeout(),
        )
    except httpx.HTTPError:
        logger.warning("Failed to reach telemetry service for %s", orch_id)
        return None

    if resp.status_code == 200:
        return _parse_loaded(resp.json())
    if resp.status_code == 404:
        return None
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError:
        logger.warning("Telemetry returned %d for %s", resp.status_code, orch_id)
        return None
    return _parse_loaded(resp.json())


# --- Async variants ---------------------------------------------------------
# The FastAPI request handlers (submit_intent, get_status, ...) run on the
# single event loop. Calling the sync httpx helpers above from those handlers
# blocks the loop for the full telemetry round-trip, which under load freezes
# every concurrent poll on that orchestrator. The async variants below let the
# handlers ``await`` telemetry I/O so the loop stays free to serve other
# workers' requests while one call is in flight.


async def save_orchestration_async(orch: dict[str, Any]) -> None:
    """Async upsert via Telemetry PUT /orchestrations/{id} (non-blocking)."""
    oid = orch.get("orchestration_id")
    if not oid:
        raise ValueError("orchestration_id is required")
    payload = _serialize_orch(orch)
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await client.put(
            f"{_telemetry_base()}/orchestrations/{oid}",
            json=payload,
        )
    resp.raise_for_status()


async def load_orchestration_async(orch_id: str) -> dict[str, Any] | None:
    """Async load via Telemetry GET /orchestrations/{id} (non-blocking)."""
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            resp = await client.get(
                f"{_telemetry_base()}/orchestrations/{orch_id}",
            )
    except httpx.HTTPError:
        logger.warning("Failed to reach telemetry service for %s", orch_id)
        return None

    if resp.status_code == 200:
        return _parse_loaded(resp.json())
    if resp.status_code == 404:
        return None
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError:
        logger.warning("Telemetry returned %d for %s", resp.status_code, orch_id)
        return None
    return _parse_loaded(resp.json())


def delete_orchestration(orch_id: str) -> None:
    """Delete orchestration record (tests / admin only)."""
    try:
        httpx.delete(
            f"{_telemetry_base()}/orchestrations/{orch_id}",
            timeout=_timeout(),
        )
    except httpx.HTTPError:
        pass
