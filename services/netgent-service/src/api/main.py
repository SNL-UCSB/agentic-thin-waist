"""Primary FastAPI entrypoint for the NetGent API package."""

from __future__ import annotations

from fastapi import FastAPI
import uvicorn
from .config import APIConfig
from .routers import health_router, workflow_router


def create_app() -> FastAPI:
    config = APIConfig()
    app = FastAPI(
        title=config.title,
        version=config.version,
        description=config.description,
    )
    app.include_router(health_router)
    app.include_router(workflow_router)
    return app


app = create_app()


def main() -> None:
    config = APIConfig()
    uvicorn.run(app, host=config.host, port=config.port, reload=False)


if __name__ == "__main__":
    main()
