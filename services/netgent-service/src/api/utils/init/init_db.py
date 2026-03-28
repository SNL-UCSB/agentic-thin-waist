"""Database initialization helpers for the NetGent API package."""

from __future__ import annotations

import os
from typing import Final

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from ...models import Base

DEFAULT_DB_HOST: Final[str] = "postgres"
DEFAULT_DB_NAME: Final[str] = "telemetry"
DEFAULT_DB_PORT: Final[str] = "5432"
DEFAULT_DB_USER: Final[str] = "admin"
DEFAULT_DB_PASSWORD: Final[str] = "admin123"


def build_database_url() -> str:
    """Build a PostgreSQL URL from environment-backed database settings."""

    host = os.getenv("DB_HOST", DEFAULT_DB_HOST)
    name = os.getenv("DB_NAME", DEFAULT_DB_NAME)
    port = os.getenv("DB_PORT", DEFAULT_DB_PORT)
    user = os.getenv("DB_USER", DEFAULT_DB_USER)
    password = os.getenv("DB_PASSWORD", DEFAULT_DB_PASSWORD)
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


def create_engine(database_url: str | None = None, *, echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine for the configured PostgreSQL database."""

    resolved_database_url = database_url or build_database_url()
    engine_kwargs: dict[str, object] = {
        "echo": echo,
        "future": True,
        "pool_pre_ping": True,
    }
    return sa.create_engine(resolved_database_url, **engine_kwargs)


def create_session_factory(
    database_url: str | None = None,
    *,
    echo: bool = False,
) -> sessionmaker:
    """Create a session factory bound to the configured engine."""

    engine = create_engine(database_url, echo=echo)
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def init_db(database_url: str | None = None, *, echo: bool = False) -> Engine:
    """Create any missing ORM tables defined in ``models.py`` and return the engine."""

    engine = create_engine(database_url, echo=echo)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    return engine


def main() -> None:
    """Initialize the configured database when run as a module/script."""

    engine = init_db()
    print(f"Initialized NetGent schema on {engine.url.render_as_string()}")


if __name__ == "__main__":
    main()
