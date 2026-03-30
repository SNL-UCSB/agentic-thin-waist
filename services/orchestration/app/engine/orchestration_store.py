"""Persistent orchestration lifecycle: Telemetry PostgreSQL (HTTP) or local SQLite."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from app.models.schemas import OrchestrationStatus

_sqlite_lock = threading.Lock()

# Set True after Telemetry returns 404/405 for PUT/GET /orchestrations/{id} (upstream
# telemetry often has no orchestration store route; use local SQLite instead).
_force_sqlite_store: bool = False


def _telemetry_base() -> str | None:
    u = os.getenv("TELEMETRY_SERVICE_URL", "").strip().rstrip("/")
    return u or None


def _sqlite_path() -> Path:
    raw = os.getenv("ORCH_SQLITE_PATH", "").strip()
    if raw:
        return Path(raw)
    return Path.home() / ".agentic_thin_waist" / "orchestrations.db"


def _ensure_sqlite_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orchestrations (
            orchestration_id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            updated_at REAL NOT NULL
        )
        """)
    conn.commit()


def _serialize_status(status: Any) -> str:
    if isinstance(status, OrchestrationStatus):
        return status.value
    if hasattr(status, "value"):
        return str(status.value)
    return str(status)


def _serialize_orch(orch: dict[str, Any]) -> dict[str, Any]:
    """JSON-serializable copy for Telemetry PUT / SQLite."""
    out: dict[str, Any] = {}
    for k, v in orch.items():
        if k == "status":
            out[k] = _serialize_status(v)
        else:
            out[k] = v
    return out


def _orch_to_json_str(orch: dict[str, Any]) -> str:
    return json.dumps(_serialize_orch(orch), default=str)


def _parse_loaded(data: dict[str, Any]) -> dict[str, Any]:
    """Restore OrchestrationStatus from persisted dict."""
    out = dict(data)
    s = out.get("status", "pending")
    try:
        out["status"] = OrchestrationStatus(s)
    except ValueError:
        out["status"] = OrchestrationStatus.pending
    return out


def _save_sqlite(orch: dict[str, Any]) -> None:
    path = _sqlite_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    oid = orch.get("orchestration_id")
    if not oid:
        raise ValueError("orchestration_id is required")
    blob = _orch_to_json_str(orch)
    now = time.time()
    with _sqlite_lock:
        conn = sqlite3.connect(str(path))
        try:
            _ensure_sqlite_schema(conn)
            conn.execute(
                """
                INSERT INTO orchestrations (orchestration_id, payload_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(orchestration_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (oid, blob, now),
            )
            conn.commit()
        finally:
            conn.close()


def save_orchestration(orch: dict[str, Any]) -> None:
    """Upsert full orchestration state (Telemetry or SQLite)."""
    global _force_sqlite_store
    base = _telemetry_base()
    if base and not _force_sqlite_store:
        oid = orch.get("orchestration_id")
        if not oid:
            raise ValueError("orchestration_id is required")
        payload = _serialize_orch(orch)
        timeout = float(os.getenv("ORCH_HTTP_TIMEOUT_SECONDS", "20"))
        try:
            resp = httpx.put(
                f"{base}/orchestrations/{oid}",
                json=payload,
                timeout=timeout,
            )
            if resp.status_code in (404, 405):
                _force_sqlite_store = True
                _save_sqlite(orch)
                return
            resp.raise_for_status()
            return
        except httpx.HTTPStatusError as e:
            if e.response is not None and e.response.status_code in (404, 405):
                _force_sqlite_store = True
                _save_sqlite(orch)
                return
            raise
        except httpx.HTTPError:
            _force_sqlite_store = True
            _save_sqlite(orch)
            return

    _save_sqlite(orch)


def _load_sqlite_only(orch_id: str) -> dict[str, Any] | None:
    path = _sqlite_path()
    if not path.exists():
        return None
    with _sqlite_lock:
        conn = sqlite3.connect(str(path))
        try:
            cur = conn.execute(
                "SELECT payload_json FROM orchestrations WHERE orchestration_id = ?",
                (orch_id,),
            )
            row = cur.fetchone()
        finally:
            conn.close()
    if not row:
        return None
    return _parse_loaded(json.loads(row[0]))


def load_orchestration(orch_id: str) -> dict[str, Any] | None:
    """Load orchestration state or None if missing."""
    global _force_sqlite_store
    base = _telemetry_base()
    if not base or _force_sqlite_store:
        return _load_sqlite_only(orch_id)

    timeout = float(os.getenv("ORCH_HTTP_TIMEOUT_SECONDS", "20"))
    try:
        resp = httpx.get(f"{base}/orchestrations/{orch_id}", timeout=timeout)
    except httpx.HTTPError:
        return None

    if resp.status_code == 200:
        return _parse_loaded(resp.json())
    if resp.status_code == 404:
        row = _load_sqlite_only(orch_id)
        if row is not None:
            _force_sqlite_store = True
        return row
    if resp.status_code == 405:
        _force_sqlite_store = True
        return _load_sqlite_only(orch_id)
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError:
        return None
    return _parse_loaded(resp.json())


def delete_orchestration(orch_id: str) -> None:
    """Remove record (tests / admin only)."""
    if _telemetry_base() and not _force_sqlite_store:
        return
    path = _sqlite_path()
    if not path.exists():
        return
    with _sqlite_lock:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                "DELETE FROM orchestrations WHERE orchestration_id = ?",
                (orch_id,),
            )
            conn.commit()
        finally:
            conn.close()
