"""Local configuration helpers for the NetGent API package."""

from __future__ import annotations

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

class APIConfig(BaseSettings):
    title: str = "NetGent Service"
    version: str = "0.1.0"
    description: str = "Dummy NetGent controller implementation based on the service README."
    host: str = Field(default="0.0.0.0", validation_alias="NETGENT_HOST")
    port: int = Field(default=8003, validation_alias="NETGENT_PORT")
    timeout_default: int = Field(default=120, validation_alias="NETGENT_TIMEOUT_DEFAULT")
    browserless_ws_endpoint: str = Field(
        default="ws://browserless:3000/chromium/playwright",
        validation_alias="BROWSERLESS_WS_ENDPOINT",
    )
    browser_pool_size: int = Field(default=5, validation_alias="BROWSER_POOL_SIZE")

    model_config = SettingsConfigDict(
        extra="ignore",
    )
