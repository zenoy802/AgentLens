from __future__ import annotations

import io
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.executor_registry import get_executor_service
from app.db.session import get_db_session
from app.schemas.export import ExportRequest
from app.services.export_service import ExportService
from app.services.query_executor import ExecutorService

router = APIRouter(prefix="/queries", tags=["export"])

_MEDIA_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def get_export_service(
    executor_service: Annotated[ExecutorService, Depends(get_executor_service)],
) -> ExportService:
    return ExportService(executor_service)


@router.post(
    "/{query_id}/export",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Exported query result file.",
            "content": {
                "text/csv": {},
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {},
            },
        }
    },
)
def export_query(
    query_id: int,
    payload: ExportRequest,
    db: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ExportService, Depends(get_export_service)],
) -> StreamingResponse:
    file_bytes, filename = service.export(
        db,
        query_id=query_id,
        format=payload.format,
        include_labels=payload.include_labels,
        json_serialization=payload.json_serialization,
    )
    encoded_filename = quote(filename, safe="")
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type=_MEDIA_TYPES[payload.format],
        headers=headers,
    )
