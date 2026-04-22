from __future__ import annotations

import time
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.health import get_app_version
from app.core.config import get_settings
from app.db.session import get_db_session
from app.services.cleanup_service import CleanupReport, CleanupService

router = APIRouter(prefix="/admin", tags=["admin"])


class CleanupRequest(BaseModel):
    dry_run: bool = False


class SchedulerJobRead(BaseModel):
    id: str
    name: str
    trigger: str
    next_run_time: datetime | None


class AdminInfoResponse(BaseModel):
    version: str
    data_dir: str
    db_path: str
    uptime_seconds: int
    scheduler_jobs: list[SchedulerJobRead]


@router.post("/cleanup", response_model=CleanupReport)
def run_cleanup(
    payload: CleanupRequest,
    session: Annotated[Session, Depends(get_db_session)],
) -> CleanupReport:
    return CleanupService().run(session, dry_run=payload.dry_run)


@router.get("/info", response_model=AdminInfoResponse)
def get_admin_info(request: Request) -> AdminInfoResponse:
    settings = get_settings()
    started_at = getattr(request.app.state, "started_at", time.monotonic())
    scheduler = getattr(request.app.state, "scheduler", None)

    return AdminInfoResponse(
        version=get_app_version(),
        data_dir=str(settings.data_dir),
        db_path=str(settings.metadata_db_path),
        uptime_seconds=_uptime_seconds(started_at),
        scheduler_jobs=_scheduler_jobs(scheduler),
    )


def _uptime_seconds(started_at: object) -> int:
    if isinstance(started_at, int | float):
        return max(int(time.monotonic() - started_at), 0)
    return 0


def _scheduler_jobs(scheduler: Any) -> list[SchedulerJobRead]:
    if scheduler is None:
        return []

    jobs = scheduler.get_jobs()
    return [
        SchedulerJobRead(
            id=str(job.id),
            name=str(job.name),
            trigger=str(job.trigger),
            next_run_time=getattr(job, "next_run_time", None),
        )
        for job in jobs
    ]
