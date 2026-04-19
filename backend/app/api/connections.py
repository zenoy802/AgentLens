from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.connection import (
    ConnectionCreate,
    ConnectionListResponse,
    ConnectionRead,
    ConnectionTestResponse,
    ConnectionUpdate,
)
from app.services.connection_service import ConnectionService

router = APIRouter(prefix="/connections", tags=["connections"])


def get_connection_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> ConnectionService:
    return ConnectionService(session)


@router.get("", response_model=ConnectionListResponse)
def list_connections(
    service: Annotated[ConnectionService, Depends(get_connection_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ConnectionListResponse:
    return service.list_connections(page=page, page_size=page_size)


@router.post("", response_model=ConnectionRead, status_code=status.HTTP_201_CREATED)
def create_connection(
    payload: ConnectionCreate,
    service: Annotated[ConnectionService, Depends(get_connection_service)],
) -> ConnectionRead:
    return service.create_connection(payload)


@router.get("/{connection_id}", response_model=ConnectionRead)
def get_connection(
    connection_id: int,
    service: Annotated[ConnectionService, Depends(get_connection_service)],
) -> ConnectionRead:
    return service.get_connection(connection_id)


@router.patch("/{connection_id}", response_model=ConnectionRead)
def update_connection(
    connection_id: int,
    payload: ConnectionUpdate,
    service: Annotated[ConnectionService, Depends(get_connection_service)],
) -> ConnectionRead:
    return service.update_connection(connection_id, payload)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    connection_id: int,
    service: Annotated[ConnectionService, Depends(get_connection_service)],
) -> Response:
    service.delete_connection(connection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{connection_id}/test", response_model=ConnectionTestResponse)
def test_connection(
    connection_id: int,
    service: Annotated[ConnectionService, Depends(get_connection_service)],
) -> ConnectionTestResponse:
    return service.test_connection(connection_id)
