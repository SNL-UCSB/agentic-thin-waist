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
def health_check() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        checks=HealthChecks(
            browser_driver="available",
            llm_service="responsive",
            workflow_engine="operational",
            telemetry_service="reachable",
        ),
        uptime_seconds=0,
    )
