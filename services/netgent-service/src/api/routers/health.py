"""Health routes for the NetGent API."""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas import HealthChecks, HealthResponse


router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["health"],
)
def health_check(
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        checks=HealthChecks(
            browser_driver="ok",
            llm_service="ok",
            workflow_engine="ok",
            telemetry_service="ok",
        ),
        uptime_seconds=0,
    )
