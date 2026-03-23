"""Background worker entrypoints and shared Procrastinate app wiring."""

from __future__ import annotations

from functools import lru_cache

import procrastinate

from api.config import APIConfig
from api.utils.init.init_queue import build_psycopg_conninfo


@lru_cache(maxsize=1)
def get_queue_app() -> procrastinate.App:
    """Build the shared Procrastinate app on first use."""

    connector = procrastinate.PsycopgConnector(conninfo=build_psycopg_conninfo())
    config = APIConfig()
    return procrastinate.App(
        connector=connector,
        import_paths=["api.worker.queue.app"],
        worker_defaults={
            "queues": ["workflows"],
            "concurrency": config.queue_worker_concurrency,
        },
    )


__all__ = ["get_queue_app"]
