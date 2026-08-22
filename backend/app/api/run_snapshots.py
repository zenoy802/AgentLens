from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.core.snapshot_jobs import SnapshotJobRunner, get_snapshot_job_runner
from app.db.session import get_db_session
from app.schemas.run_snapshot import (
    RunSnapshotCreate,
    RunSnapshotListResponse,
    RunSnapshotRead,
    RunSnapshotRowsResponse,
    RunSnapshotStatusRead,
)
from app.services.snapshot_service import SnapshotService

router = APIRouter(prefix="/run-snapshots", tags=["run-snapshots"])


def get_snapshot_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> SnapshotService:
    return SnapshotService(session)


@router.post(
    "",
    response_model=RunSnapshotRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_run_snapshot(
    payload: RunSnapshotCreate,
    service: Annotated[SnapshotService, Depends(get_snapshot_service)],
    job_runner: Annotated[SnapshotJobRunner, Depends(get_snapshot_job_runner)],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", min_length=1, max_length=200),
    ] = None,
) -> RunSnapshotRead:
    result = service.create(payload, idempotency_key=idempotency_key)
    if result.snapshot.status == "building":
        job_runner.submit(result.snapshot.id)
    return service.to_read(result.snapshot, include_manifest=False)


@router.get("", response_model=RunSnapshotListResponse)
def list_run_snapshots(
    service: Annotated[SnapshotService, Depends(get_snapshot_service)],
    status_filter: Annotated[
        Literal["building", "ready", "failed", "corrupted", "deleted"] | None,
        Query(alias="status"),
    ] = None,
    trace_contract_id: str | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> RunSnapshotListResponse:
    return service.list(
        status=status_filter,
        trace_contract_id=trace_contract_id,
        cursor=cursor,
        limit=limit,
    )


@router.get("/{snapshot_id}", response_model=RunSnapshotRead)
def get_run_snapshot(
    snapshot_id: str,
    service: Annotated[SnapshotService, Depends(get_snapshot_service)],
) -> RunSnapshotRead:
    return service.to_read(service.get(snapshot_id), include_manifest=True)


@router.get("/{snapshot_id}/status", response_model=RunSnapshotStatusRead)
def get_run_snapshot_status(
    snapshot_id: str,
    service: Annotated[SnapshotService, Depends(get_snapshot_service)],
) -> RunSnapshotStatusRead:
    return service.to_status_read(service.get(snapshot_id))


@router.get("/{snapshot_id}/rows", response_model=RunSnapshotRowsResponse)
def get_run_snapshot_rows(
    snapshot_id: str,
    service: Annotated[SnapshotService, Depends(get_snapshot_service)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> RunSnapshotRowsResponse:
    return service.read_rows(service.get(snapshot_id), cursor=cursor, limit=limit)
