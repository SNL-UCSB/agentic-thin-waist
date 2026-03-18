"""
config.py — Centralised runtime configuration for the CTP Service.

All tunables are loaded from environment variables (prefixed ``CTP_``) or an
optional ``.env`` file in the working directory.  The singleton is cached via
:func:`get_settings` so each import pays the parse cost only once.

Environment variable examples
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: bash

    CTP_DATABASE_URL=postgresql://user:pass@db:5432/ctp_corpus
    CTP_WORKERS=8
    CTP_WINDOW_DURATION_SEC=30
    CTP_BURST_INTERVAL_MS=100
    CTP_INTERNAL_SUBNETS='["128.111","169.231","192.150.216"]'
    CTP_LOG_LEVEL=INFO
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the CTP Service.

    Every field can be overridden via the corresponding ``CTP_<FIELD>``
    environment variable.  Lists are accepted as JSON arrays or
    comma-separated strings.
    """

    model_config = SettingsConfigDict(
        env_prefix="CTP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Service
    # ------------------------------------------------------------------ #
    host: str = Field("0.0.0.0", description="Bind address for the FastAPI server.")
    port: int = Field(
        8001, ge=1, le=65535, description="TCP port for the FastAPI server."
    )
    log_level: str = Field(
        "INFO", description="Python logging level (DEBUG/INFO/WARNING/ERROR)."
    )

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    database_url: str = Field(
        "postgresql://ctp_user:ctp_pass@localhost:5432/ctp_corpus",
        description="psycopg2-compatible PostgreSQL connection URL.",
    )
    db_pool_min: int = Field(2, ge=1, description="Minimum DB connection pool size.")
    db_pool_max: int = Field(10, ge=1, description="Maximum DB connection pool size.")

    # ------------------------------------------------------------------ #
    # Pipeline — processing
    # ------------------------------------------------------------------ #
    workers: int = Field(
        4,
        ge=1,
        description="Default parallel worker count for multi-process pipeline stages.",
    )
    window_duration_sec: int = Field(
        30,
        ge=1,
        description=(
            "Duration of each time window produced by Step 2 (split by windows). "
            "A 15-minute capture with 30 s windows yields 30 window files."
        ),
    )
    burst_interval_ms: int = Field(
        100,
        ge=1,
        description=(
            "Bin width in milliseconds for timeseries construction (Step 3). "
            "With 30 s windows and 100 ms bins each timeseries has 300 samples."
        ),
    )
    start_offset_sec: int = Field(
        0,
        ge=0,
        description=(
            "Seconds of leading traffic to discard when building timeseries. "
            "Useful to skip transient warm-up traffic at the start of a capture."
        ),
    )
    pcap_batch_size: int = Field(
        30,
        ge=1,
        description="Max number of PCAP files joined per joincap invocation.",
    )
    top_prefix_len: int = Field(
        16,
        ge=1,
        le=32,
        description=(
            "Shortest prefix length in the hierarchy (gateway level). "
            "Tree is built from /32 leaves up to this level."
        ),
    )

    # ------------------------------------------------------------------ #
    # Network
    # ------------------------------------------------------------------ #
    internal_subnets: List[str] = Field(
        default=[
            "128.111",
            "169.231",
            "192.150.216",
            "192.150.217",
            "92.35.222",
            "199.120.153",
        ],
        description=(
            "IP prefix strings that identify *internal* (campus) hosts. "
            "A packet is classified as upload when its source IP starts with "
            "one of these prefixes; as download when its destination matches. "
            "Override for non-UCSB deployments via ``CTP_INTERNAL_SUBNETS``."
        ),
    )
    gateway_subnet: str = Field(
        "169.231.0.0/16",
        description="Top-level gateway subnet used as root of the prefix hierarchy.",
    )

    # ------------------------------------------------------------------ #
    # Validators
    # ------------------------------------------------------------------ #
    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}; got '{v}'")
        return upper

    # Derived property — not a settings field
    @property
    def bins_per_window(self) -> int:
        """Number of timeseries bins per window (window_duration_sec / burst_interval_ms)."""
        return int(self.window_duration_sec * 1000 // self.burst_interval_ms)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton :class:`Settings` instance.

    The result is cached after the first call so subsequent imports do not
    re-parse environment variables.  Call ``get_settings.cache_clear()`` in
    tests to force reloading.
    """
    return Settings()
