from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status
from loguru import logger
from sqlalchemy.orm import Session

from app.api.ws import annotation_broadcaster
from app.core.logging import safe_exception_context
from app.db.session import get_db_session
from app.schemas.annotation import (
    AnnotationBatchCreate,
    AnnotationColor,
    AnnotationCreate,
    AnnotationDeleteResponse,
    AnnotationOut,
)
from app.services.annotation_service import (
    AnnotationDeleteFilters,
    AnnotationFilters,
    AnnotationService,
)

router = APIRouter(prefix="/queries/{query_id}", tags=["annotations"])


@router.post(
    "/annotations",
    response_model=AnnotationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_annotation(
    query_id: int,
    payload: AnnotationCreate,
    db: Annotated[Session, Depends(get_db_session)],
) -> AnnotationOut:
    _log_agent_bridge_annotation_call(query_id, payload.author)
    annotation = await AnnotationService(db).create(query_id, payload)
    output = AnnotationOut.model_validate(annotation)
    await _safe_broadcast(
        query_id,
        {
            "type": "annotation.created",
            "query_id": query_id,
            "data": output.model_dump(mode="json"),
            "timestamp": _timestamp(),
        },
    )
    return output


@router.post(
    "/annotations/batch",
    response_model=list[AnnotationOut],
    status_code=status.HTTP_201_CREATED,
)
async def create_annotations_batch(
    query_id: int,
    payload: AnnotationBatchCreate,
    db: Annotated[Session, Depends(get_db_session)],
) -> list[AnnotationOut]:
    for item in payload.annotations:
        _log_agent_bridge_annotation_call(query_id, item.author)
    annotations = await AnnotationService(db).create_batch(query_id, payload.annotations)
    outputs = [AnnotationOut.model_validate(annotation) for annotation in annotations]
    await _safe_broadcast(
        query_id,
        {
            "type": "annotation.batch_created",
            "query_id": query_id,
            "data": [output.model_dump(mode="json") for output in outputs],
            "timestamp": _timestamp(),
        },
    )
    return outputs


@router.get("/annotations", response_model=list[AnnotationOut])
async def list_annotations(
    query_id: int,
    db: Annotated[Session, Depends(get_db_session)],
    author: Annotated[str | None, Query(max_length=64)] = None,
    author_prefix: Annotated[str | None, Query(max_length=64)] = None,
    color: AnnotationColor | None = None,
    row_identity: Annotated[str | None, Query(max_length=256)] = None,
    column_key: Annotated[str | None, Query(max_length=128)] = None,
    annotation_set: Annotated[str | None, Query(max_length=128)] = None,
    include_expired: bool = False,
) -> list[AnnotationOut]:
    annotations = await AnnotationService(db).list(
        query_id,
        AnnotationFilters(
            author=author,
            author_prefix=author_prefix,
            color=color,
            row_identity=row_identity,
            column_key=column_key,
            annotation_set=annotation_set,
            include_expired=include_expired,
        ),
    )
    return [AnnotationOut.model_validate(annotation) for annotation in annotations]


@router.delete("/annotations/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_annotation(
    query_id: int,
    annotation_id: int,
    db: Annotated[Session, Depends(get_db_session)],
) -> Response:
    await AnnotationService(db).delete(query_id, annotation_id)
    await _safe_broadcast(
        query_id,
        {
            "type": "annotation.deleted",
            "query_id": query_id,
            "data": {"id": annotation_id},
            "timestamp": _timestamp(),
        },
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/annotations", response_model=AnnotationDeleteResponse)
async def delete_annotations(
    query_id: int,
    db: Annotated[Session, Depends(get_db_session)],
    author: Annotated[str | None, Query(max_length=64)] = None,
    author_prefix: Annotated[str | None, Query(max_length=64)] = None,
    color: AnnotationColor | None = None,
    annotation_set: Annotated[str | None, Query(max_length=128)] = None,
) -> AnnotationDeleteResponse:
    filters = AnnotationDeleteFilters(
        author=author,
        author_prefix=author_prefix,
        color=color,
        annotation_set=annotation_set,
    )
    deleted_count = await AnnotationService(db).delete_by_filter(query_id, filters)
    filter_payload: dict[str, Any] = {
        "author": author,
        "author_prefix": author_prefix,
        "color": color.value if color is not None else None,
        "annotation_set": annotation_set,
    }
    await _safe_broadcast(
        query_id,
        {
            "type": "annotations.deleted",
            "query_id": query_id,
            "data": {
                "deleted_count": deleted_count,
                "filters": {
                    key: value for key, value in filter_payload.items() if value is not None
                },
            },
            "timestamp": _timestamp(),
        },
    )
    return AnnotationDeleteResponse(deleted_count=deleted_count)


async def _safe_broadcast(query_id: int, message: dict[str, Any]) -> None:
    try:
        await annotation_broadcaster.broadcast(query_id, message)
    except Exception as exc:  # pragma: no cover - broadcaster is defensive per client
        logger.warning(
            "Annotation broadcast failed: query_id={} context={}",
            query_id,
            safe_exception_context(exc),
        )


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _log_agent_bridge_annotation_call(query_id: int, author: str) -> None:
    if author.startswith("agent:"):
        logger.info(
            "Agent Bridge annotation API call: query_id={} author={}",
            query_id,
            author,
        )
