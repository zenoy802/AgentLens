from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette import status

from app.core.errors import ValidationError
from app.db.session import get_session_factory, initialize_metadata_database
from app.models.annotation import Annotation
from app.models.connection import Connection
from app.models.named_query import NamedQuery
from app.schemas.annotation import AnnotationColor, AnnotationCreate, AnnotationSeverity
from app.services.annotation_service import (
    AnnotationDeleteFilters,
    AnnotationFilters,
    AnnotationService,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _create_query(session: Session, expires_at: datetime | None = None) -> int:
    connection = Connection(
        name="annotation-service-mysql",
        db_type="mysql",
        host="db.example.com",
        port=3306,
        database="agent_logs",
        username="reader",
        default_timeout=30,
        default_row_limit=10000,
    )
    session.add(connection)
    session.flush()
    query = NamedQuery(
        connection_id=connection.id,
        name=None,
        sql_text="SELECT * FROM traces",
        is_named=False,
        expires_at=expires_at.replace(tzinfo=None) if expires_at is not None else None,
    )
    session.add(query)
    session.commit()
    return query.id


def _annotation_create(
    *,
    row_identity: str,
    author: str,
    color: AnnotationColor,
    column_key: str | None = None,
    title: str | None = None,
    text: str | None = None,
    severity: AnnotationSeverity | None = None,
    annotation_set: str | None = None,
) -> AnnotationCreate:
    return AnnotationCreate(
        row_identity=row_identity,
        column_key=column_key,
        author=author,
        color=color,
        title=title,
        text=text,
        severity=severity,
        annotation_set=annotation_set,
        sql_fingerprint=None,
        schema_fingerprint=None,
        result_fingerprint=None,
    )


@pytest.mark.asyncio
async def test_create_annotation_uses_query_expiration_cap() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        query_expires_at = _now() + timedelta(days=1)
        query_id = _create_query(session, expires_at=query_expires_at)
        annotation = await AnnotationService(session).create(
            query_id,
            _annotation_create(
                row_identity="row-1",
                author="agent:codex",
                color=AnnotationColor.YELLOW,
                text="Potential issue",
            ),
        )

        assert annotation.id > 0
        assert annotation.row_identity == "row-1"
        assert annotation.expires_at is not None
        assert annotation.expires_at <= query_expires_at
    finally:
        session.close()


@pytest.mark.asyncio
async def test_create_batch_lists_and_deletes_by_author_prefix() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        query_id = _create_query(session)
        service = AnnotationService(session)
        annotations = await service.create_batch(
            query_id,
            [
                _annotation_create(
                    row_identity="row-1",
                    author="agent:claude-code",
                    color=AnnotationColor.RED,
                    annotation_set="set-1",
                ),
                _annotation_create(
                    row_identity="row-2",
                    author="human",
                    color=AnnotationColor.BLUE,
                    annotation_set="set-2",
                ),
            ],
        )
        assert [annotation.id for annotation in annotations] == [1, 2]

        agent_annotations = await service.list(
            query_id,
            AnnotationFilters(author_prefix="agent:"),
        )
        assert [annotation.row_identity for annotation in agent_annotations] == ["row-1"]

        deleted = await service.delete_by_filter(
            query_id,
            AnnotationDeleteFilters(author_prefix="agent:"),
        )
        assert deleted == 1

        remaining = session.scalar(
            select(func.count()).select_from(Annotation).where(Annotation.query_id == query_id)
        )
        assert remaining == 1
    finally:
        session.close()


@pytest.mark.asyncio
async def test_delete_by_filter_rejects_missing_or_empty_filters() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        query_id = _create_query(session)
        with pytest.raises(ValidationError) as exc_info:
            await AnnotationService(session).delete_by_filter(
                query_id,
                AnnotationDeleteFilters(author_prefix=""),
            )

        assert exc_info.value.http_status == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.code == "ANNOTATION_CLEAR_REQUIRES_FILTER"
    finally:
        session.close()
