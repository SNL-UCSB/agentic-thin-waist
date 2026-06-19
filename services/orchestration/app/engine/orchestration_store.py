"""Persistent orchestration lifecycle via the Telemetry Service (PostgreSQL)."""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from typing import Any

import httpx

from app.models.schemas import OrchestrationStatus

logger = logging.getLogger(__name__)


def _classify_http_error(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.ConnectError):
        return "connect_error"
    if isinstance(exc, httpx.ReadError):
        return "read_error"
    return type(exc).__name__


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


def _load_retries() -> int:
    try:
        return max(1, int(os.getenv("ORCH_LOAD_RETRIES", "3")))
    except ValueError:
        return 3


def _retry_sleep(attempt: int) -> None:
    time.sleep(min(4.0, 0.5 * (2 ** max(0, attempt - 1))) + random.uniform(0, 0.5))


async def _retry_sleep_async(attempt: int) -> None:
    await asyncio.sleep(
        min(4.0, 0.5 * (2 ** max(0, attempt - 1))) + random.uniform(0, 0.5)
    )


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
        started = time.monotonic()
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
            if isinstance(exc, httpx.HTTPError):
                logger.warning(
                    "Telemetry save failed for %s (attempt=%d/%d kind=%s elapsed=%.2fs): %s",
                    oid,
                    attempt,
                    attempts,
                    _classify_http_error(exc),
                    time.monotonic() - started,
                    str(exc),
                )
            else:
                logger.warning(
                    "Telemetry save failed for %s (attempt=%d/%d elapsed=%.2fs): %s",
                    oid,
                    attempt,
                    attempts,
                    time.monotonic() - started,
                    str(exc),
                )
            if attempt < attempts:
                time.sleep(min(8.0, 1.0 * (2 ** (attempt - 1))) + random.uniform(0, 1.0))
    if last_exc is not None:
        raise last_exc


def load_orchestration(orch_id: str) -> dict[str, Any] | None:
    """Load orchestration state from Telemetry GET /orchestrations/{id}."""
    started = time.monotonic()
    try:
        resp = httpx.get(
            f"{_telemetry_base()}/orchestrations/{orch_id}",
            timeout=_timeout(),
        )
    except httpx.HTTPError as exc:
        logger.warning(
            "Failed to reach telemetry service for %s (kind=%s elapsed=%.2fs): %s",
            orch_id,
            _classify_http_error(exc),
            time.monotonic() - started,
            str(exc),
        )
        return None

    if resp.status_code == 200:
        return _parse_loaded(resp.json())
    if resp.status_code == 404:
        logger.warning(
            "Telemetry lookup 404 for %s (elapsed=%.2fs)",
            orch_id,
            time.monotonic() - started,
        )
        return None
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Telemetry returned %d for %s (elapsed=%.2fs): %s",
            resp.status_code,
            orch_id,
            time.monotonic() - started,
            str(exc),
        )
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
    attempts = _save_retries()
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=_timeout()) as client:
                resp = await client.put(
                    f"{_telemetry_base()}/orchestrations/{oid}",
                    json=payload,
                )
            resp.raise_for_status()
            return
        except httpx.HTTPError as exc:
            last_exc = exc
            logger.warning(
                "Async telemetry save failed for %s (attempt=%d/%d kind=%s elapsed=%.2fs): %s",
                oid,
                attempt,
                attempts,
                _classify_http_error(exc),
                time.monotonic() - started,
                str(exc),
            )
            if attempt < attempts:
                await _retry_sleep_async(attempt)
        except Exception as exc:  # noqa: BLE001 - preserve prior broad retry behavior
            last_exc = exc
            logger.warning(
                "Async telemetry save failed for %s (attempt=%d/%d elapsed=%.2fs): %s",
                oid,
                attempt,
                attempts,
                time.monotonic() - started,
                str(exc),
            )
            if attempt < attempts:
                await _retry_sleep_async(attempt)
    if last_exc is not None:
        raise last_exc


async def load_orchestration_async(orch_id: str) -> dict[str, Any] | None:
    """Async load via Telemetry GET /orchestrations/{id} (non-blocking)."""
    attempts = _load_retries()
    for attempt in range(1, attempts + 1):
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=_timeout()) as client:
                resp = await client.get(
                    f"{_telemetry_base()}/orchestrations/{orch_id}",
                )
        except httpx.HTTPError as exc:
            logger.warning(
                "Failed to reach telemetry service for %s (attempt=%d/%d kind=%s elapsed=%.2fs): %s",
                orch_id,
                attempt,
                attempts,
                _classify_http_error(exc),
                time.monotonic() - started,
                str(exc),
            )
            if attempt < attempts:
                await _retry_sleep_async(attempt)
                continue
            return None

        if resp.status_code == 200:
            return _parse_loaded(resp.json())
        if resp.status_code == 404:
            logger.warning(
                "Telemetry lookup 404 for %s (attempt=%d/%d elapsed=%.2fs)",
                orch_id,
                attempt,
                attempts,
                time.monotonic() - started,
            )
            if attempt < attempts:
                await _retry_sleep_async(attempt)
                continue
            return None
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Telemetry returned %d for %s (attempt=%d/%d elapsed=%.2fs): %s",
                resp.status_code,
                orch_id,
                attempt,
                attempts,
                time.monotonic() - started,
                str(exc),
            )
            if attempt < attempts:
                await _retry_sleep_async(attempt)
                continue
            return None
        return _parse_loaded(resp.json())
    return None


def delete_orchestration(orch_id: str) -> None:
    """Delete orchestration record (tests / admin only)."""
    try:
        httpx.delete(
            f"{_telemetry_base()}/orchestrations/{orch_id}",
            timeout=_timeout(),
        )
    except httpx.HTTPError:
        pass
