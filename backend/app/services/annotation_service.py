from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import status
from loguru import logger
from sqlalchemy import Select, delete, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import safe_exception_context
from app.models.annotation import Annotation
from app.models.named_query import NamedQuery
from app.schemas.annotation import AnnotationColor, AnnotationCreate
from app.schemas.datetime import ensure_utc

_ANNOTATION_TTL_DAYS = 90


@dataclass(frozen=True, slots=True)
class AnnotationFilters:
    author: str | None = None
    author_prefix: str | None = None
    color: AnnotationColor | None = None
    row_identity: str | None = None
    column_key: str | None = None
    annotation_set: str | None = None
    include_expired: bool = False


@dataclass(frozen=True, slots=True)
class AnnotationDeleteFilters:
    author: str | None = None
    author_prefix: str | None = None
    color: AnnotationColor | None = None
    annotation_set: str | None = None

    def has_any_filter(self) -> bool:
        return (
            _has_text(self.author)
            or _has_text(self.author_prefix)
            or self.color is not None
            or _has_text(self.annotation_set)
        )


class AnnotationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    async def create(self, query_id: int, payload: AnnotationCreate) -> Annotation:
        query = self._get_query_or_raise(query_id)
        now = _utcnow()
        annotation = self._build_annotation(query=query, payload=payload, now=now)
        self.session.add(annotation)
        try:
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            logger.warning(
                "Annotation create failed: query_id={} context={}",
                query_id,
                safe_exception_context(exc),
            )
            raise
        logger.info(
            "Annotation created: query_id={} annotation_id={} author={} color={}",
            query_id,
            annotation.id,
            annotation.author,
            annotation.color,
        )
        if _fingerprints_are_empty(annotation):
            logger.info(
                "Annotation created without fingerprints: query_id={} annotation_id={}",
                query_id,
                annotation.id,
            )
        return annotation

    async def create_batch(
        self,
        query_id: int,
        payloads: list[AnnotationCreate],
    ) -> list[Annotation]:
        query = self._get_query_or_raise(query_id)
        now = _utcnow()
        annotations = [
            self._build_annotation(query=query, payload=payload, now=now) for payload in payloads
        ]
        self.session.add_all(annotations)
        try:
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            logger.warning(
                "Annotation batch create failed: query_id={} context={}",
                query_id,
                safe_exception_context(exc),
            )
            raise
        logger.info(
            "Annotations batch created: query_id={} count={}",
            query_id,
            len(annotations),
        )
        return annotations

    async def list(self, query_id: int, filters: AnnotationFilters) -> list[Annotation]:
        self._get_query_or_raise(query_id)
        stmt: Select[tuple[Annotation]] = select(Annotation).where(Annotation.query_id == query_id)
        stmt = _apply_common_filters(stmt, filters)
        if not filters.include_expired:
            now = _utcnow()
            stmt = stmt.where(or_(Annotation.expires_at.is_(None), Annotation.expires_at >= now))
        stmt = stmt.order_by(Annotation.created_at.asc(), Annotation.id.asc())
        annotations = list(self.session.scalars(stmt))
        logger.info("Annotations listed: query_id={} count={}", query_id, len(annotations))
        return annotations

    async def delete(self, query_id: int, annotation_id: int) -> None:
        annotation = self.session.get(Annotation, annotation_id)
        if annotation is None or annotation.query_id != query_id:
            raise NotFoundError(
                "annotation not found",
                code="ANNOTATION_NOT_FOUND",
                detail={"query_id": query_id, "annotation_id": annotation_id},
            )
        self.session.delete(annotation)
        self.session.commit()
        logger.info("Annotation deleted: query_id={} annotation_id={}", query_id, annotation_id)

    async def delete_by_filter(
        self,
        query_id: int,
        filters: AnnotationDeleteFilters,
    ) -> int:
        self._get_query_or_raise(query_id)
        if not filters.has_any_filter():
            raise ValidationError(
                "at least one annotation delete filter is required",
                code="ANNOTATION_CLEAR_REQUIRES_FILTER",
                http_status=status.HTTP_400_BAD_REQUEST,
                detail={"allowed_filters": ["author", "author_prefix", "color", "annotation_set"]},
            )

        stmt = delete(Annotation).where(Annotation.query_id == query_id)
        if _has_text(filters.author):
            stmt = stmt.where(Annotation.author == filters.author)
        if _has_text(filters.author_prefix):
            author_prefix = filters.author_prefix
            assert author_prefix is not None
            logger.info(
                "Clearing annotations by author_prefix: query_id={} author_prefix={}",
                query_id,
                author_prefix,
            )
            stmt = stmt.where(_author_startswith(author_prefix))
        if filters.color is not None:
            stmt = stmt.where(Annotation.color == filters.color.value)
        if _has_text(filters.annotation_set):
            stmt = stmt.where(Annotation.annotation_set == filters.annotation_set)

        result = self.session.execute(stmt)
        self.session.commit()
        deleted = int(result.rowcount or 0)
        logger.info("Annotations deleted by filter: query_id={} count={}", query_id, deleted)
        return deleted

    def compute_expires_at(self, query: NamedQuery, now: datetime) -> datetime:
        default_expiration = ensure_utc(now) + timedelta(days=_ANNOTATION_TTL_DAYS)
        if query.expires_at is None:
            return default_expiration
        return min(ensure_utc(query.expires_at), default_expiration)

    def _build_annotation(
        self,
        *,
        query: NamedQuery,
        payload: AnnotationCreate,
        now: datetime,
    ) -> Annotation:
        return Annotation(
            query_id=query.id,
            row_identity=payload.row_identity,
            column_key=payload.column_key,
            author=payload.author,
            color=payload.color.value,
            title=payload.title,
            text=payload.text,
            severity=payload.severity.value if payload.severity is not None else None,
            annotation_set=payload.annotation_set,
            sql_fingerprint=payload.sql_fingerprint,
            schema_fingerprint=payload.schema_fingerprint,
            result_fingerprint=payload.result_fingerprint,
            created_at=now,
            expires_at=self.compute_expires_at(query, now),
        )

    def _get_query_or_raise(self, query_id: int) -> NamedQuery:
        query = self.session.get(NamedQuery, query_id)
        if query is None:
            raise NotFoundError(
                "Named query not found.",
                code="QUERY_NOT_FOUND",
                detail={"query_id": query_id},
            )
        return query


def _apply_common_filters(
    stmt: Select[tuple[Annotation]],
    filters: AnnotationFilters,
) -> Select[tuple[Annotation]]:
    if _has_text(filters.author):
        stmt = stmt.where(Annotation.author == filters.author)
    if _has_text(filters.author_prefix):
        author_prefix = filters.author_prefix
        assert author_prefix is not None
        stmt = stmt.where(_author_startswith(author_prefix))
    if filters.color is not None:
        stmt = stmt.where(Annotation.color == filters.color.value)
    if filters.row_identity is not None:
        stmt = stmt.where(Annotation.row_identity == filters.row_identity)
    if filters.column_key is not None:
        if filters.column_key == "":
            stmt = stmt.where(Annotation.column_key.is_(None))
        else:
            stmt = stmt.where(Annotation.column_key == filters.column_key)
    if _has_text(filters.annotation_set):
        stmt = stmt.where(Annotation.annotation_set == filters.annotation_set)
    return stmt


def _has_text(value: str | None) -> bool:
    return value is not None and value != ""


def _author_startswith(prefix: str) -> ColumnElement[bool]:
    return Annotation.author.startswith(prefix, autoescape=True)


def _fingerprints_are_empty(annotation: Annotation) -> bool:
    return (
        annotation.sql_fingerprint is None
        and annotation.schema_fingerprint is None
        and annotation.result_fingerprint is None
    )


def _utcnow() -> datetime:
    return datetime.now(UTC)
