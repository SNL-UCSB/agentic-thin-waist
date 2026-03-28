"""Primary FastAPI entrypoint for the NetGent API package."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from .config import APIConfig
from .routers import health_router, workflow_router
from .utils.init.init_db import init_db
from .utils.init.init_queue import init_queue
from .utils.init.init_s3 import init_s3_bucket
from .worker import get_queue_app


def create_app() -> FastAPI:
    config = APIConfig()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        s3_bucket_name = (
            os.getenv("NETGENT_S3_BUCKET_NAME")
            or os.getenv("S3_BUCKET_NAME")
            or "netgent"
        ).strip()
        queue_app = get_queue_app()
        engine = init_db()
        s3_client = init_s3_bucket(s3_bucket_name)
        app.state.db_engine = engine
        app.state.s3_client = s3_client
        app.state.s3_bucket_name = s3_bucket_name
        async with queue_app.open_async():
            await init_queue(queue_app, engine)
            app.state.queue_app = queue_app
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
