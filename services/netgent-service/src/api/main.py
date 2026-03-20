"""Primary FastAPI entrypoint for the NetGent API package."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
import uvicorn

from .config import APIConfig
from .routers import health_router, workflow_router
from .utils.init_db import init_db


def create_app() -> FastAPI:
    config = APIConfig()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = init_db()
        app.state.db_engine = engine
        try:
            yield
        finally:
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
