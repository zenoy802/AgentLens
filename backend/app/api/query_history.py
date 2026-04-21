from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.misc import QueryHistory
from app.schemas.common import Pagination
from app.schemas.query_history import QueryHistoryListResponse, QueryHistoryRead

router = APIRouter(prefix="/query-history", tags=["query-history"])


@router.get("", response_model=QueryHistoryListResponse)
def list_query_history(
    session: Annotated[Session, Depends(get_db_session)],
    connection_id: int | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
    limit: Annotated[int | None, Query(ge=1, le=500)] = None,
) -> QueryHistoryListResponse:
    effective_page_size = limit or page_size
    filters = []
    if connection_id is not None:
        filters.append(QueryHistory.connection_id == connection_id)

    count_stmt: Select[tuple[int]] = select(func.count()).select_from(QueryHistory).where(*filters)
    total_records = session.scalar(count_stmt) or 0
    total_pages = max((total_records + effective_page_size - 1) // effective_page_size, 1)

    stmt: Select[tuple[QueryHistory]] = (
        select(QueryHistory)
        .where(*filters)
        .order_by(QueryHistory.executed_at.desc(), QueryHistory.id.desc())
        .offset((page - 1) * effective_page_size)
        .limit(effective_page_size)
    )
    items = session.scalars(stmt).all()
    return QueryHistoryListResponse(
        items=[QueryHistoryRead.model_validate(item) for item in items],
        pagination=Pagination(
            page=page,
            page_size=effective_page_size,
            total=total_records,
            total_pages=total_pages,
        ),
    )
