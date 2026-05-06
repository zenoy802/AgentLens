from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.db.session import get_db_session
from app.schemas.label import (
    LabelBatchResult,
    LabelBatchUpsert,
    LabelRecordRead,
    LabelRecordUpsert,
    LabelRowsQuery,
    LabelsByRowResponse,
)
from app.services.label_service import label_service

MAX_LABEL_QUERY_ROW_IDENTITIES = 1000

router = APIRouter(prefix="/queries/{query_id}", tags=["labels"])


@router.get("/labels", response_model=LabelsByRowResponse)
def get_labels(
    query_id: int,
    db: Annotated[Session, Depends(get_db_session)],
    row_identities: Annotated[str | None, Query()] = None,
    row_identity: Annotated[list[str] | None, Query()] = None,
) -> LabelsByRowResponse:
    identities = _parse_row_identities(
        row_identities=row_identities,
        exact_row_identities=row_identity,
    )
    return LabelsByRowResponse(
        labels_by_row=label_service.get_labels_by_rows(db, query_id, identities)
    )


@router.post("/labels/query", response_model=LabelsByRowResponse)
def query_labels(
    query_id: int,
    payload: LabelRowsQuery,
    db: Annotated[Session, Depends(get_db_session)],
) -> LabelsByRowResponse:
    _validate_row_identity_count(payload.row_identities)
    return LabelsByRowResponse(
        labels_by_row=label_service.get_labels_by_rows(
            db,
            query_id,
            payload.row_identities,
        )
    )


@router.post("/labels", response_model=LabelRecordRead | None)
def upsert_label(
    query_id: int,
    payload: LabelRecordUpsert,
    db: Annotated[Session, Depends(get_db_session)],
) -> LabelRecordRead | None:
    record = label_service.upsert(
        db,
        query_id,
        payload.row_identity,
        payload.field_key,
        payload.value,
    )
    if record is None:
        return None
    return label_service.to_read_model(record)


@router.post("/labels/batch", response_model=LabelBatchResult)
def batch_upsert_labels(
    query_id: int,
    payload: LabelBatchUpsert,
    db: Annotated[Session, Depends(get_db_session)],
) -> LabelBatchResult:
    _validate_row_identity_count(payload.row_identities)
    return label_service.batch_upsert(
        db,
        query_id,
        payload.row_identities,
        payload.field_key,
        payload.value,
    )


@router.delete("/labels/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_label(
    query_id: int,
    record_id: int,
    db: Annotated[Session, Depends(get_db_session)],
) -> Response:
    label_service.delete_by_id(db, query_id, record_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _parse_row_identities(
    *,
    row_identities: str | None,
    exact_row_identities: list[str] | None,
) -> list[str]:
    identities: list[str] = []

    if row_identities is not None and row_identities != "":
        identities.extend(item.strip() for item in row_identities.split(",") if item.strip())

    if exact_row_identities is not None:
        identities.extend(item for item in exact_row_identities if item != "")

    _validate_row_identity_count(identities)
    return identities


def _validate_row_identity_count(row_identities: list[str]) -> None:
    if len(row_identities) > MAX_LABEL_QUERY_ROW_IDENTITIES:
        raise ValidationError(
            "row_identities is limited to 1000 items",
            code="LABEL_ROW_IDENTITIES_TOO_MANY",
            http_status=status.HTTP_400_BAD_REQUEST,
            detail={
                "max_items": MAX_LABEL_QUERY_ROW_IDENTITIES,
                "actual_items": len(row_identities),
            },
        )
