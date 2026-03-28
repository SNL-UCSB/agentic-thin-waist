"""Local configuration helpers for the NetGent API package."""

from __future__ import annotations

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class APIConfig(BaseSettings):
    title: str = "NetGent Service"
    version: str = "0.1.0"
    description: str = (
        "Dummy NetGent controller implementation based on the service README."
    )
    host: str = Field(default="0.0.0.0", validation_alias="NETGENT_HOST")
    port: int = Field(default=8003, validation_alias="NETGENT_PORT")
    timeout_default: int = Field(default=30, validation_alias="NETGENT_TIMEOUT_DEFAULT")
    browserless_ws_endpoint: str = Field(
        default="ws://substrate-worker:3000/chromium/playwright",
        validation_alias="BROWSERLESS_WS_ENDPOINT",
    )
    browser_pool_size: int = Field(default=5, validation_alias="BROWSER_POOL_SIZE")
    # Max workflow jobs executed in parallel by the Procrastinate worker (per process).
    queue_worker_concurrency: int = Field(
        default=1,
        ge=1,
        validation_alias="NETGENT_QUEUE_CONCURRENCY",
    )

    model_config = SettingsConfigDict(
        extra="ignore",
    )
