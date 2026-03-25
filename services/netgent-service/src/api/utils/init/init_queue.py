"""Procrastinate queue connection string and schema bootstrap."""

from __future__ import annotations

import os
from urllib.parse import quote_plus

import procrastinate
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from .init_db import (
    DEFAULT_DB_HOST,
    DEFAULT_DB_NAME,
    DEFAULT_DB_PASSWORD,
    DEFAULT_DB_PORT,
    DEFAULT_DB_USER,
)


def build_psycopg_conninfo() -> str:
    """Libpq-style DSN for Procrastinate / psycopg (user/password URL-encoded)."""

    host = os.getenv("DB_HOST", DEFAULT_DB_HOST)
    name = os.getenv("DB_NAME", DEFAULT_DB_NAME)
    port = os.getenv("DB_PORT", DEFAULT_DB_PORT)
    user = quote_plus(os.getenv("DB_USER", DEFAULT_DB_USER))
    password = quote_plus(os.getenv("DB_PASSWORD", DEFAULT_DB_PASSWORD))
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


async def init_queue(queue_app: procrastinate.App, engine: Engine) -> None:
    """Ensure Procrastinate tables exist. Call only inside ``async with queue_app.open_async():``."""

    insp = sa.inspect(engine)
    if not insp.has_table("procrastinate_jobs"):
        await queue_app.schema_manager.apply_schema_async()
