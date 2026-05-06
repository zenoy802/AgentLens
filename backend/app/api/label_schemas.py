from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.label import LabelSchemaPayload, LabelSchemaRead
from app.services.label_schema_service import label_schema_service

router = APIRouter(prefix="/queries/{query_id}", tags=["label-schema"])


@router.get("/label-schema", response_model=LabelSchemaRead)
def get_label_schema(
    query_id: int,
    db: Annotated[Session, Depends(get_db_session)],
) -> LabelSchemaRead:
    return label_schema_service.get(db, query_id)


@router.put("/label-schema", response_model=LabelSchemaRead)
def put_label_schema(
    query_id: int,
    payload: LabelSchemaPayload,
    db: Annotated[Session, Depends(get_db_session)],
) -> LabelSchemaRead:
    return label_schema_service.put(db, query_id, payload)
