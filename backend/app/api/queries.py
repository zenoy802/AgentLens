from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.execute import build_execution_result_response, get_query_service
from app.schemas.execution import ExecutionResult, QueryExecuteRequest
from app.schemas.query import (
    NamedQueryCreate,
    NamedQueryListResponse,
    NamedQueryPromote,
    NamedQueryRead,
    NamedQueryUpdate,
)
from app.services.query_service import QueryService

router = APIRouter(prefix="/queries", tags=["queries"])


@router.get("", response_model=NamedQueryListResponse)
def list_queries(
    service: Annotated[QueryService, Depends(get_query_service)],
    connection_id: int | None = None,
    is_named: bool | None = None,
    search: str | None = None,
    include_expired: bool = False,
    order_by: Literal["created_at", "last_executed_at"] = "created_at",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> NamedQueryListResponse:
    return service.list_queries(
        connection_id=connection_id,
        is_named=is_named,
        search=search,
        include_expired=include_expired,
        order_by=order_by,
        page=page,
        page_size=page_size,
    )


@router.get("/{query_id}", response_model=NamedQueryRead)
def get_query(
    query_id: int,
    service: Annotated[QueryService, Depends(get_query_service)],
) -> NamedQueryRead:
    return service.build_read(service.get(query_id))


@router.post(
    "",
    response_model=NamedQueryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_query(
    payload: NamedQueryCreate,
    service: Annotated[QueryService, Depends(get_query_service)],
) -> NamedQueryRead:
    return service.build_read(service.create_named_query(payload))


@router.patch("/{query_id}", response_model=NamedQueryRead)
def update_query(
    query_id: int,
    payload: NamedQueryUpdate,
    service: Annotated[QueryService, Depends(get_query_service)],
) -> NamedQueryRead:
    return service.build_read(service.update(query_id, payload))


@router.delete("/{query_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_query(
    query_id: int,
    service: Annotated[QueryService, Depends(get_query_service)],
) -> Response:
    service.delete(query_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{query_id}/promote", response_model=NamedQueryRead)
def promote_query(
    query_id: int,
    payload: NamedQueryPromote,
    service: Annotated[QueryService, Depends(get_query_service)],
) -> NamedQueryRead:
    return service.build_read(service.promote(query_id, payload))


@router.post(
    "/{query_id}/execute",
    response_model=ExecutionResult,
)
def execute_query(
    query_id: int,
    service: Annotated[QueryService, Depends(get_query_service)],
    payload: QueryExecuteRequest | None = None,
) -> ExecutionResult:
    active_payload = payload or QueryExecuteRequest()
    query = service.get(query_id)
    connection = query.connection
    timeout = (
        active_payload.timeout if active_payload.timeout is not None else connection.default_timeout
    )
    row_limit = (
        active_payload.row_limit
        if active_payload.row_limit is not None
        else connection.default_row_limit
    )
    outcome = service.execute_and_record(query, timeout=timeout, row_limit=row_limit)
    return build_execution_result_response(
        query=query,
        outcome=outcome,
        is_temporary=not query.is_named,
    )
