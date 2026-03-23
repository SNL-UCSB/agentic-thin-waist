"""Primary FastAPI entrypoint for the NetGent API package."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
import uvicorn

from .config import APIConfig
from .routers import health_router, workflow_router
from .utils.init_db import init_db
from .utils.init_s3 import init_s3_bucket


def create_app() -> FastAPI:
    config = APIConfig()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        s3_bucket_name = (
            os.getenv("NETGENT_S3_BUCKET_NAME")
            or os.getenv("S3_BUCKET_NAME")
            or "netgent"
        ).strip()
        engine = init_db()
        s3_client = init_s3_bucket(s3_bucket_name)
        app.state.db_engine = engine
        app.state.s3_client = s3_client
        app.state.s3_bucket_name = s3_bucket_name
        try:
            yield
        finally:
            close = getattr(s3_client, "close", None)
            if callable(close):
                close()
            engine.dispose()

    app = FastAPI(
        title=config.title,
        version=config.version,
        description=config.description,
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(workflow_router)
    return app


app = create_app()


def main() -> None:
    config = APIConfig()
    uvicorn.run(
        "api.main:app",
        host=config.host,
        port=config.port,
    )


if __name__ == "__main__":
    main()
