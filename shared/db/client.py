from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row


class DatabaseClient:
    def __init__(self) -> None:
        self.client: psycopg.Connection | None = None
        self.database_url: str | None = None
        self.connect_timeout: int = 5

    def init_app(self, app: Any | None = None) -> None:
        config = getattr(app, "config", {}) if app is not None else {}
        self.database_url = (
            self._get_config_value(config, "DATABASE_URL")
            or self._get_config_value(config, "SQLALCHEMY_DATABASE_URI")
            or self._build_database_url(config)
        )
        self.connect_timeout = int(
            self._get_config_value(
                config,
                "DB_CONNECTION_TIMEOUT_SECONDS",
                os.environ.get("DB_CONNECTION_TIMEOUT_SECONDS", "5"),
            )
        )
        self.connect()

    def connect(self) -> psycopg.Connection:
        if not self.database_url:
            self.database_url = self._build_database_url({})

        if self.client is not None and not self.client.closed:
            return self.client

        self.client = psycopg.connect(
            self.database_url,
            connect_timeout=self.connect_timeout,
            row_factory=dict_row,
        )
        return self.client

    def close(self) -> None:
        if self.client is not None and not self.client.closed:
            self.client.close()
        self.client = None

    def execute(
        self, query: str, params: Sequence[Any] | Mapping[str, Any] | None = None
    ) -> int:
        with self.cursor() as cur:
            cur.execute(query, params)
            return cur.rowcount

    def fetch_one(
        self, query: str, params: Sequence[Any] | Mapping[str, Any] | None = None
    ) -> dict[str, Any] | None:
        with self.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
        return dict(row) if row is not None else None

    def fetch_all(
        self, query: str, params: Sequence[Any] | Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        with self.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return [dict(row) for row in rows]

    @contextmanager
    def cursor(self) -> Iterator[psycopg.Cursor[dict[str, Any]]]:
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _build_database_url(self, config: Mapping[str, Any]) -> str:
        host = self._get_config_value(config, "DB_HOST", "localhost")
        name = self._get_config_value(config, "DB_NAME", "")
        port = self._get_config_value(config, "DB_PORT", "5432")
        user = self._get_config_value(config, "DB_USER", "postgres")
        password = self._get_config_value(config, "DB_PASSWORD", "")
        return f"postgresql://{user}:{password}@{host}:{port}/{name}"

    @staticmethod
    def _get_config_value(
        config: Mapping[str, Any], key: str, default: str | None = None
    ) -> str | None:
        value = config.get(key)
        if value is not None:
            return str(value)
        env_value = os.environ.get(key)
        if env_value is not None:
            return env_value
        return default
