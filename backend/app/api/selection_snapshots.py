from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.selection_snapshot import SelectionSnapshotCreate, SelectionSnapshotOut
from app.services.selection_snapshot_service import SelectionSnapshotService

router = APIRouter(tags=["selection-snapshots"])


@router.post(
    "/queries/{query_id}/selection-snapshots",
    response_model=SelectionSnapshotOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_selection_snapshot(
    query_id: int,
    payload: SelectionSnapshotCreate,
    db: Annotated[Session, Depends(get_db_session)],
) -> SelectionSnapshotOut:
    service = SelectionSnapshotService(db)
    snapshot = await service.create(query_id, payload)
    return service.to_read_model(snapshot)


@router.get("/selections/{selection_id}", response_model=SelectionSnapshotOut)
async def get_selection_snapshot(
    selection_id: str,
    db: Annotated[Session, Depends(get_db_session)],
) -> SelectionSnapshotOut:
    service = SelectionSnapshotService(db)
    snapshot = await service.get(selection_id)
    return service.to_read_model(snapshot)


@router.delete("/selections/{selection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_selection_snapshot(
    selection_id: str,
    db: Annotated[Session, Depends(get_db_session)],
) -> Response:
    await SelectionSnapshotService(db).delete(selection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
