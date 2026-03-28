"""Health routes for the NetGent API."""

from __future__ import annotations

from fastapi import APIRouter, status

from ..schemas import HealthResponse

router = APIRouter(tags=["health"])


# Always Return Healthy Status with Status Code 200
@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="healthy",
    )
