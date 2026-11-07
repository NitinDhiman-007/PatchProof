"""Health and system status endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter

from app.core.config import get_settings
from app.database.database import check_db_health
from app.models.schemas import HealthResponse, SystemStatusResponse
from app.services.repository_service import count_repositories

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, summary="Basic health check")
def get_health() -> HealthResponse:
    """Return application health status."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=settings.VERSION,
        timestamp=datetime.now(UTC),
    )


@router.get("/status", response_model=SystemStatusResponse, summary="Detailed system status")
def get_status() -> SystemStatusResponse:
    """Return system operational status, database connectivity, and configuration details."""
    settings = get_settings()
    db_ok = check_db_health()
    db_status = "connected" if db_ok else "disconnected"
    bharatcode_configured = bool(settings.BHARATCODE_API_KEY.strip())
    repo_count = count_repositories() if db_ok else 0

    return SystemStatusResponse(
        status="operational" if db_ok else "degraded",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        database=db_status,
        bharatcode_configured=bharatcode_configured,
        repositories_count=repo_count,
        timestamp=datetime.now(UTC),
    )
