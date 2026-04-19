import time
from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter, Request
from loguru import logger
from pydantic import BaseModel

from app.db.session import metadata_database_is_ready

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: str
    version: str
    metadata_db: str
    uptime_seconds: int


def get_app_version() -> str:
    try:
        return version("AgentLens-backend")
    except PackageNotFoundError:
        return "0.1.0"


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    started_at = getattr(request.app.state, "started_at", time.monotonic())
    uptime_seconds = max(int(time.monotonic() - started_at), 0)
    metadata_db_status = "ok"
    service_status = "ok"

    try:
        if not metadata_database_is_ready():
            metadata_db_status = "error"
            service_status = "degraded"
    except Exception as exc:
        logger.exception("Metadata DB health check failed: {}", exc)
        metadata_db_status = "error"
        service_status = "degraded"

    return HealthResponse(
        status=service_status,
        version=get_app_version(),
        metadata_db=metadata_db_status,
        uptime_seconds=uptime_seconds,
    )
