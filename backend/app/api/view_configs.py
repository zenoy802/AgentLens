from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.view_config import ViewConfigPayload, ViewConfigRead
from app.services.view_config_service import view_config_service

router = APIRouter(prefix="/queries/{query_id}", tags=["view-config"])


@router.get("/view-config", response_model=ViewConfigRead)
def get_view_config(
    query_id: int,
    db: Annotated[Session, Depends(get_db_session)],
) -> ViewConfigRead:
    return view_config_service.get(db, query_id)


@router.put("/view-config", response_model=ViewConfigRead)
def put_view_config(
    query_id: int,
    payload: ViewConfigPayload,
    db: Annotated[Session, Depends(get_db_session)],
) -> ViewConfigRead:
    return view_config_service.put(db, query_id, payload)
