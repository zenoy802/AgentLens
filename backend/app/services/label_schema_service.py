from __future__ import annotations

from loguru import logger
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.models.label import LabelRecord, LabelSchema
from app.models.named_query import NamedQuery
from app.schemas.label import (
    LabelField,
    LabelSchemaPayload,
    LabelSchemaRead,
    MultiSelectField,
    SingleSelectField,
    label_fields_adapter,
)


class LabelSchemaService:
    def get(self, db: Session, query_id: int) -> LabelSchemaRead:
        query = self._get_query_or_raise(db, query_id)
        label_schema = self._get_or_create_label_schema(db, query)
        return self._to_read_model(label_schema, cascade_deleted_records=0)

    def put(
        self,
        db: Session,
        query_id: int,
        payload: LabelSchemaPayload,
    ) -> LabelSchemaRead:
        query = self._get_query_or_raise(db, query_id)
        label_schema = self._get_or_create_label_schema(db, query)
        old_fields = self._load_fields(label_schema)
        new_fields = label_fields_adapter.validate_python(payload.fields)
        self._validate_fields(new_fields)

        old_keys = {field.key for field in old_fields}
        new_keys = {field.key for field in new_fields}
        removed_keys = old_keys - new_keys

        cascade_deleted_records = 0
        if removed_keys:
            cascade_deleted_records = self._count_removed_records(db, query_id, removed_keys)
            db.execute(
                delete(LabelRecord).where(
                    LabelRecord.query_id == query_id,
                    LabelRecord.field_key.in_(removed_keys),
                )
            )

        label_schema.fields = label_fields_adapter.dump_json(new_fields).decode()
        db.commit()
        db.refresh(label_schema)
        return self._to_read_model(
            label_schema,
            cascade_deleted_records=cascade_deleted_records,
        )

    @staticmethod
    def _get_query_or_raise(db: Session, query_id: int) -> NamedQuery:
        query = db.get(NamedQuery, query_id)
        if query is None:
            raise NotFoundError(
                "query not found",
                code="NOT_FOUND",
                detail={"query_id": query_id},
            )
        return query

    @staticmethod
    def _get_or_create_label_schema(db: Session, query: NamedQuery) -> LabelSchema:
        stmt = select(LabelSchema).where(LabelSchema.query_id == query.id)
        label_schema = db.scalars(stmt).first()
        if label_schema is not None:
            return label_schema

        label_schema = LabelSchema(query_id=query.id, fields="[]")
        db.add(label_schema)
        db.commit()
        db.refresh(label_schema)
        return label_schema

    @staticmethod
    def _load_fields(label_schema: LabelSchema) -> list[LabelField]:
        try:
            return label_fields_adapter.validate_json(label_schema.fields or "[]")
        except (PydanticValidationError, ValueError) as exc:
            logger.warning(
                "Invalid label_schema.fields for query {}: {}",
                label_schema.query_id,
                exc,
            )
            return []

    @staticmethod
    def _validate_fields(fields: list[LabelField]) -> None:
        seen_keys: set[str] = set()
        for field in fields:
            if field.key in seen_keys:
                raise ValidationError(
                    code="LABEL_SCHEMA_DUPLICATE_FIELD_KEY",
                    message="Label field keys must be unique within a schema.",
                    detail={"field_key": field.key},
                )
            seen_keys.add(field.key)

            if not isinstance(field, (SingleSelectField, MultiSelectField)):
                continue

            if not field.options:
                raise ValidationError(
                    code="LABEL_SCHEMA_OPTIONS_REQUIRED",
                    message="single_select and multi_select fields require at least one option.",
                    detail={"field_key": field.key},
                )

            seen_option_values: set[str] = set()
            for option in field.options:
                if option.value in seen_option_values:
                    raise ValidationError(
                        code="LABEL_SCHEMA_DUPLICATE_OPTION_VALUE",
                        message="Option values must be unique within a label field.",
                        detail={"field_key": field.key, "option_value": option.value},
                    )
                seen_option_values.add(option.value)

    @staticmethod
    def _count_removed_records(
        db: Session,
        query_id: int,
        removed_keys: set[str],
    ) -> int:
        return int(
            db.scalar(
                select(func.count())
                .select_from(LabelRecord)
                .where(
                    LabelRecord.query_id == query_id,
                    LabelRecord.field_key.in_(removed_keys),
                )
            )
            or 0
        )

    def _to_read_model(
        self,
        label_schema: LabelSchema,
        *,
        cascade_deleted_records: int,
    ) -> LabelSchemaRead:
        return LabelSchemaRead(
            query_id=label_schema.query_id,
            fields=self._load_fields(label_schema),
            updated_at=label_schema.updated_at,
            cascade_deleted_records=cascade_deleted_records,
        )


label_schema_service = LabelSchemaService()
