from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.api.execute import get_query_service
from app.db.session import get_db_session
from app.schemas.trace_contract import (
    TraceContractCreate,
    TraceContractListResponse,
    TraceContractRead,
    TraceContractValidateRequest,
    TraceContractValidationResult,
)
from app.services.query_service import QueryService
from app.services.trace_contract_service import TraceContractService

router = APIRouter(prefix="/trace-contracts", tags=["trace-contracts"])


def get_trace_contract_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> TraceContractService:
    return TraceContractService(session)


@router.post(
    "/validate",
    response_model=TraceContractValidationResult,
)
def validate_trace_contract(
    payload: TraceContractValidateRequest,
    service: Annotated[TraceContractService, Depends(get_trace_contract_service)],
    query_service: Annotated[QueryService, Depends(get_query_service)],
) -> TraceContractValidationResult:
    query = query_service.get(payload.named_query_id)
    timeout = min(query.connection.default_timeout, 30)
    outcome = query_service.execute_readonly(
        query,
        timeout=timeout,
        row_limit=payload.sample_limit,
    )
    return service.validate_rows(
        payload.definition,
        outcome.execution_result.rows,
        query_id=query.id,
        row_identities=outcome.row_identities,
    )


@router.post(
    "",
    response_model=TraceContractRead,
    status_code=status.HTTP_201_CREATED,
)
def create_trace_contract(
    payload: TraceContractCreate,
    service: Annotated[TraceContractService, Depends(get_trace_contract_service)],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", min_length=1, max_length=200),
    ] = None,
) -> TraceContractRead:
    contract = service.create(payload, idempotency_key=idempotency_key)
    return service.to_read(contract)


@router.get("", response_model=TraceContractListResponse)
def list_trace_contracts(
    service: Annotated[TraceContractService, Depends(get_trace_contract_service)],
    named_query_id: int | None = None,
    include_archived: bool = False,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> TraceContractListResponse:
    return service.list(
        named_query_id=named_query_id,
        include_archived=include_archived,
        cursor=cursor,
        limit=limit,
    )


@router.get("/{contract_id}", response_model=TraceContractRead)
def get_trace_contract(
    contract_id: str,
    service: Annotated[TraceContractService, Depends(get_trace_contract_service)],
) -> TraceContractRead:
    return service.to_read(service.get(contract_id))
