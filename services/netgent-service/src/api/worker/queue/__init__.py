"""Procrastinate job queue for NetGent workflow execution."""

from __future__ import annotations

from api.worker import get_queue_app

from .app import run_netgent

__all__ = ["get_queue_app", "run_netgent"]
