"""Telemetry-facing entry point for orchestration persistence (compatibility).

Historically this module only ``PUT`` orchestration state when
``TELEMETRY_SERVICE_URL`` was set, and no-oped otherwise. The canonical
implementation is now :mod:`app.engine.orchestration_store`, which always
persists: to the Telemetry Service (PostgreSQL) when configured, or to a
local SQLite file otherwise.

Keep importing ``put_orchestration`` from here if you prefer the old name; it
is an alias for :func:`~app.engine.orchestration_store.save_orchestration`.
"""

from __future__ import annotations

from app.engine.orchestration_store import save_orchestration

put_orchestration = save_orchestration

__all__ = ["put_orchestration"]
