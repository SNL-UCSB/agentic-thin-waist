"""
main.py — FastAPI application entry point for the CTP Service.

Startup sequence
~~~~~~~~~~~~~~~~
1. :func:`configure_logging` sets up structured logging at the configured level.
2. The ``lifespan`` context manager opens the PostgreSQL connection pool and
   applies the schema on startup, then closes the pool on shutdown.
3. The :class:`fastapi.FastAPI` app is configured with the API router and
   CORS middleware.

Running
~~~~~~~
.. code-block:: bash

    # Development
    uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

    # Production (via Docker)
    gunicorn -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8001 --workers 4 app.main:app

Environment variables
~~~~~~~~~~~~~~~~~~~~~
All settings are read from environment variables prefixed ``CTP_``.
See :mod:`app.config` for the full list.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings
from app.database.postgres import Database
from app.utils.logging import configure_logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level database singleton
# ---------------------------------------------------------------------------

_db: Database | None = None


def get_db() -> Database:
    """Return the process-level :class:`~app.database.postgres.Database` instance.

    Raises:
        RuntimeError: If the application has not started yet.
    """
    if _db is None:
        raise RuntimeError(
            "Database not initialised. " "Ensure the FastAPI app lifespan has completed startup."
        )
    return _db


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Manage the lifecycle of shared resources.

    Opens the PostgreSQL connection pool on startup and closes it on shutdown.
    This ensures connections are properly released when the process exits.
    """
    global _db  # noqa: PLW0603
    cfg = get_settings()

    # Configure logging as early as possible
    configure_logging(level=cfg.log_level, json_format=False)

    logger.info(
        "CTP Service starting on %s:%d (log_level=%s)",
        cfg.host,
        cfg.port,
        cfg.log_level,
    )

    # Initialise database
    _db = Database(
        database_url=cfg.database_url,
        pool_min=cfg.db_pool_min,
        pool_max=cfg.db_pool_max,
    )
    try:
        _db.initialize()
        logger.info("PostgreSQL connection pool ready.")
    except Exception as exc:
        logger.error("Failed to connect to PostgreSQL: %s", exc)
        # Continue startup — health check will report degraded status

    yield  # Application is running

    # Shutdown
    if _db is not None:
        _db.close()
        logger.info("PostgreSQL connection pool closed.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured :class:`fastapi.FastAPI` instance.
    """
    cfg = get_settings()

    application = FastAPI(
        title="CTP Service",
        description=(
            "Cross-Traffic Profile (CTP) Service — the Representation Plane of the "
            "Agentic Thin Waist architecture.  Transforms passive packet traces into "
            "reusable, composable representations of dynamic congestion pressure."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS — allow the Experiment Controller and research clients
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    application.include_router(router)

    return application


# ---------------------------------------------------------------------------
# Application instance
# ---------------------------------------------------------------------------

app = create_app()


# ---------------------------------------------------------------------------
# CLI entry point (python -m app.main or direct execution)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    cfg = get_settings()
    configure_logging(level=cfg.log_level)
    uvicorn.run(
        "app.main:app",
        host=cfg.host,
        port=cfg.port,
        reload=False,
        log_config=None,  # Use our custom logging configuration
    )
