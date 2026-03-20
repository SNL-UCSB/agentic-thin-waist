"""Health routes for the NetGent API."""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="healthy",
    )
