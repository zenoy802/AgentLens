from __future__ import annotations

import json
from typing import Any

from fastapi import status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, NotFoundError, ValidationError
from app.models.label import LabelRecord
from app.schemas.label import (
    LabelBatchError,
    LabelBatchResult,
    LabelField,
    LabelRecordRead,
    LabelSchemaPayload,
    MultiSelectField,
    SingleSelectField,
    TextField,
)
from app.services.label_schema_service import label_schema_service

MAX_ROW_IDENTITY_LENGTH = 512
MAX_FIELD_KEY_LENGTH = 200


class LabelService:
    def get_schema(self, db: Session, query_id: int) -> LabelSchemaPayload:
        schema = label_schema_service.get(db, query_id)
        return LabelSchemaPayload(fields=schema.fields)

    def get_labels_by_rows(
        self,
        db: Session,
        query_id: int,
        row_identities: list[str],
    ) -> dict[str, dict[str, Any]]:
        if not row_identities:
            return {}

        stmt = select(LabelRecord).where(
            LabelRecord.query_id == query_id,
            LabelRecord.row_identity.in_(row_identities),
        )
        result: dict[str, dict[str, Any]] = {}
        for rec in db.scalars(stmt):
            parsed_value: Any = json.loads(rec.value)
            result.setdefault(rec.row_identity, {})[rec.field_key] = parsed_value
        return result

    def upsert(
        self,
        db: Session,
        query_id: int,
        row_identity: str,
        field_key: str,
        value: Any | None,
    ) -> LabelRecord | None:
        schema = self.get_schema(db, query_id)
        return self._upsert_with_schema(
            db,
            query_id=query_id,
            row_identity=row_identity,
            field_key=field_key,
            value=value,
            schema=schema,
        )

    def batch_upsert(
        self,
        db: Session,
        query_id: int,
        row_identities: list[str],
        field_key: str,
        value: Any | None,
    ) -> LabelBatchResult:
        schema = self.get_schema(db, query_id)
        affected = 0
        errors: list[LabelBatchError] = []

        for row_identity in row_identities:
            try:
                self._upsert_with_schema(
                    db,
                    query_id=query_id,
                    row_identity=row_identity,
                    field_key=field_key,
                    value=value,
                    schema=schema,
                )
                affected += 1
            except AppError as exc:
                errors.append(
                    LabelBatchError(
                        row_identity=row_identity,
                        code=exc.code,
                        message=exc.message,
                        detail=exc.detail,
                    )
                )

        return LabelBatchResult(
            affected=affected,
            skipped=len(errors),
            errors=errors,
        )

    def delete_by_id(self, db: Session, query_id: int, record_id: int) -> None:
        record = db.get(LabelRecord, record_id)
        if record is None or record.query_id != query_id:
            raise NotFoundError(
                "label record not found",
                code="LABEL_RECORD_NOT_FOUND",
                detail={"query_id": query_id, "record_id": record_id},
            )

        db.delete(record)
        db.commit()

    def to_read_model(self, record: LabelRecord) -> LabelRecordRead:
        parsed_value: Any = json.loads(record.value)
        return LabelRecordRead(
            record_id=record.id,
            query_id=record.query_id,
            row_identity=record.row_identity,
            field_key=record.field_key,
            value=parsed_value,
            updated_at=record.updated_at,
        )

    def _upsert_with_schema(
        self,
        db: Session,
        *,
        query_id: int,
        row_identity: str,
        field_key: str,
        value: Any | None,
        schema: LabelSchemaPayload,
    ) -> LabelRecord | None:
        self._validate_identity(row_identity=row_identity, field_key=field_key)
        field = self._find_field(schema, field_key)
        self._validate_value(field, value)

        if value is None:
            db.execute(
                delete(LabelRecord).where(
                    LabelRecord.query_id == query_id,
                    LabelRecord.row_identity == row_identity,
                    LabelRecord.field_key == field_key,
                )
            )
            db.commit()
            return None

        stored = json.dumps(value, ensure_ascii=False)
        stmt = select(LabelRecord).where(
            LabelRecord.query_id == query_id,
            LabelRecord.row_identity == row_identity,
            LabelRecord.field_key == field_key,
        )
        record = db.scalars(stmt).first()
        if record is None:
            record = LabelRecord(
                query_id=query_id,
                row_identity=row_identity,
                field_key=field_key,
                value=stored,
            )
            db.add(record)
        else:
            record.value = stored

        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            record = db.scalars(stmt).first()
            if record is None:
                raise ConflictError(
                    "label record upsert conflict",
                    code="LABEL_RECORD_UPSERT_CONFLICT",
                    detail={
                        "query_id": query_id,
                        "row_identity": row_identity,
                        "field_key": field_key,
                    },
                ) from None
            record.value = stored
            try:
                db.flush()
            except IntegrityError as exc:
                db.rollback()
                raise ConflictError(
                    "label record upsert conflict",
                    code="LABEL_RECORD_UPSERT_CONFLICT",
                    detail={
                        "query_id": query_id,
                        "row_identity": row_identity,
                        "field_key": field_key,
                    },
                ) from exc

        db.refresh(record)
        db.commit()
        return record

    @staticmethod
    def _find_field(schema: LabelSchemaPayload, field_key: str) -> LabelField:
        for field in schema.fields:
            if field.key == field_key:
                return field

        raise ValidationError(
            "label field not found",
            code="LABEL_FIELD_NOT_FOUND",
            http_status=status.HTTP_400_BAD_REQUEST,
            detail={"field_key": field_key},
        )

    @staticmethod
    def _validate_identity(*, row_identity: str, field_key: str) -> None:
        if not row_identity:
            raise ValidationError(
                "row_identity is required",
                code="LABEL_ROW_IDENTITY_INVALID",
                http_status=status.HTTP_400_BAD_REQUEST,
            )
        if len(row_identity) > MAX_ROW_IDENTITY_LENGTH:
            raise ValidationError(
                "row_identity is too long",
                code="LABEL_ROW_IDENTITY_INVALID",
                http_status=status.HTTP_400_BAD_REQUEST,
                detail={"max_length": MAX_ROW_IDENTITY_LENGTH},
            )
        if not field_key:
            raise ValidationError(
                "field_key is required",
                code="LABEL_FIELD_KEY_INVALID",
                http_status=status.HTTP_400_BAD_REQUEST,
            )
        if len(field_key) > MAX_FIELD_KEY_LENGTH:
            raise ValidationError(
                "field_key is too long",
                code="LABEL_FIELD_KEY_INVALID",
                http_status=status.HTTP_400_BAD_REQUEST,
                detail={"max_length": MAX_FIELD_KEY_LENGTH},
            )

    @staticmethod
    def _validate_value(field: LabelField, value: Any | None) -> None:
        if value is None:
            return

        if isinstance(field, SingleSelectField):
            if not isinstance(value, str):
                raise _invalid_label_value(
                    field,
                    "single_select label values must be strings.",
                    value,
                )
            option_values = {option.value for option in field.options}
            if value not in option_values:
                raise _invalid_label_value(
                    field,
                    "single_select label value is not in field options.",
                    value,
                )
            return

        if isinstance(field, MultiSelectField):
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise _invalid_label_value(
                    field,
                    "multi_select label values must be string arrays.",
                    value,
                )
            option_values = {option.value for option in field.options}
            invalid_values = [item for item in value if item not in option_values]
            if invalid_values:
                raise _invalid_label_value(
                    field,
                    "multi_select label values must all be in field options.",
                    value,
                    detail={"invalid_values": invalid_values},
                )
            return

        if isinstance(field, TextField):
            if not isinstance(value, str):
                raise _invalid_label_value(
                    field,
                    "text label values must be strings.",
                    value,
                )
            return

        raise _invalid_label_value(field, "Unsupported label field type.", value)


def _invalid_label_value(
    field: LabelField,
    message: str,
    value: Any,
    *,
    detail: dict[str, Any] | None = None,
) -> ValidationError:
    merged_detail: dict[str, Any] = {
        "field_key": field.key,
        "field_type": field.type,
        "value": value,
    }
    if detail is not None:
        merged_detail.update(detail)
    return ValidationError(
        message,
        code="LABEL_VALUE_INVALID",
        http_status=status.HTTP_400_BAD_REQUEST,
        detail=merged_detail,
    )


label_service = LabelService()
