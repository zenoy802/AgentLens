from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from functools import cmp_to_key
from typing import Any, TypeAlias
from uuid import UUID

from loguru import logger
from openpyxl import Workbook  # type: ignore[import-untyped]
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.executor_registry import get_executor_service
from app.models.label import LabelRecord, LabelSchema
from app.models.named_query import NamedQuery
from app.models.view_config import ViewConfig
from app.schemas.export import ExportFormat, JsonSerialization
from app.schemas.label import (
    LabelField,
    MultiSelectField,
    SingleSelectField,
    label_fields_adapter,
)
from app.schemas.view_config import SortConfig, TableConfig
from app.services.query_executor import ExecutorService
from app.services.query_service import QueryService

RowPair: TypeAlias = tuple[dict[str, Any], str]
IndexedRowPair: TypeAlias = tuple[int, RowPair]
SortableToken: TypeAlias = tuple[int, int | str]

_LABEL_COLUMN_PREFIX = "label__"
_EXCEL_CELL_LIMIT = 32767
_SPREADSHEET_FORMULA_PREFIXES = frozenset(("=", "+", "-", "@"))
_FILENAME_SAFE_PATTERN = re.compile(r'[\\/:*?"<>|\r\n\t]+')
_SORT_NUMBER_PATTERN = re.compile(r"(\d+)")
_table_config_adapter = TableConfig.model_validate_json


class ExportService:
    def __init__(self, executor_service: ExecutorService | None = None) -> None:
        self._executor_service = executor_service or get_executor_service()

    def export(
        self,
        db: Session,
        query_id: int,
        format: ExportFormat,
        include_labels: bool = True,
        json_serialization: JsonSerialization = "string",
    ) -> tuple[bytes, str]:
        query = self._get_query_or_raise(db, query_id)
        view_config = self._get_or_create_view_config(db, query)
        label_fields = _load_label_fields(query.label_schema)
        outcome = QueryService(db, self._executor_service).execute_readonly(
            query,
            timeout=query.connection.default_timeout,
            row_limit=query.connection.default_row_limit,
        )

        columns = [column.name for column in outcome.execution_result.columns]
        table_config = _load_table_config(view_config)
        exported_columns = _ordered_visible_columns(columns, view_config, table_config)
        row_pairs = _sorted_row_pairs(
            outcome.execution_result.rows,
            outcome.row_identities,
            table_config,
        )
        labels_by_row = (
            _load_label_records(db, query_id=query.id) if include_labels and label_fields else {}
        )
        rows = _build_export_rows(
            row_pairs=row_pairs,
            columns=exported_columns,
            label_fields=label_fields if include_labels else [],
            labels_by_row=labels_by_row,
            json_serialization=json_serialization,
        )
        headers = [
            *exported_columns,
            *[_label_column_name(field) for field in label_fields if include_labels],
        ]

        file_bytes = _serialize(rows, headers=headers, format=format)
        return file_bytes, _build_filename(query.name, format)

    @staticmethod
    def _get_query_or_raise(db: Session, query_id: int) -> NamedQuery:
        query = db.get(NamedQuery, query_id)
        if query is None:
            raise NotFoundError(
                "Named query not found.",
                code="NOT_FOUND",
                detail={"query_id": query_id},
            )
        return query

    @staticmethod
    def _get_or_create_view_config(db: Session, query: NamedQuery) -> ViewConfig:
        if query.view_config is not None:
            return query.view_config

        view_config = ViewConfig(field_renders="{}", table_config="{}")
        query.view_config = view_config
        db.add(view_config)
        db.flush()
        return view_config


def _load_label_fields(label_schema: LabelSchema | None) -> list[LabelField]:
    if label_schema is None:
        return []

    try:
        return label_fields_adapter.validate_json(label_schema.fields or "[]")
    except (PydanticValidationError, ValueError) as exc:
        logger.warning("Invalid label_schema.fields for query {}: {}", label_schema.query_id, exc)
        return []


def _load_label_records(db: Session, *, query_id: int) -> dict[str, dict[str, str]]:
    stmt = select(LabelRecord).where(LabelRecord.query_id == query_id)
    labels_by_row: dict[str, dict[str, str]] = {}
    for record in db.scalars(stmt):
        labels_by_row.setdefault(record.row_identity, {})[record.field_key] = record.value
    return labels_by_row


def _ordered_visible_columns(
    columns: Sequence[str],
    view_config: ViewConfig,
    table_config: TableConfig,
) -> list[str]:
    hidden_columns = set(table_config.hidden_columns)
    visible_columns = [column for column in columns if column not in hidden_columns]
    visible_column_set = set(visible_columns)
    column_order = [
        column for column in _load_column_order(view_config) if column in visible_column_set
    ]
    ordered = [*column_order]
    ordered_set = set(ordered)
    ordered.extend(column for column in visible_columns if column not in ordered_set)
    return ordered


def _load_table_config(view_config: ViewConfig) -> TableConfig:
    try:
        return _table_config_adapter(view_config.table_config or "{}")
    except (PydanticValidationError, ValueError) as exc:
        logger.warning(
            "Invalid view_config.table_config for query {}: {}",
            view_config.query_id,
            exc,
        )
        return TableConfig()


def _load_column_order(view_config: ViewConfig) -> list[str]:
    try:
        raw_config = json.loads(view_config.table_config or "{}")
    except json.JSONDecodeError as exc:
        logger.warning(
            "Invalid view_config.table_config JSON for query {}: {}",
            view_config.query_id,
            exc,
        )
        return []

    if not isinstance(raw_config, dict):
        return []
    raw_column_order = raw_config.get("column_order")
    if not isinstance(raw_column_order, list):
        return []
    return [item for item in raw_column_order if isinstance(item, str)]


def _build_export_rows(
    *,
    row_pairs: Sequence[RowPair],
    columns: Sequence[str],
    label_fields: Sequence[LabelField],
    labels_by_row: dict[str, dict[str, str]],
    json_serialization: JsonSerialization,
) -> list[list[str]]:
    return [
        [
            *[
                _serialize_export_value(row.get(column), json_serialization=json_serialization)
                for column in columns
            ],
            *[
                _serialize_label_value(
                    labels_by_row.get(row_identity, {}).get(field.key),
                    field,
                )
                for field in label_fields
            ],
        ]
        for row, row_identity in row_pairs
    ]


def _sorted_row_pairs(
    rows: Sequence[dict[str, Any]],
    row_identities: Sequence[str],
    table_config: TableConfig,
) -> list[RowPair]:
    row_pairs = list(zip(rows, row_identities, strict=True))
    sort_config = table_config.sort[0] if table_config.sort else None
    if sort_config is None:
        return row_pairs

    direction_multiplier = 1 if sort_config.direction == "asc" else -1
    indexed_pairs: list[IndexedRowPair] = list(enumerate(row_pairs))

    def compare(left: IndexedRowPair, right: IndexedRowPair) -> int:
        return _compare_indexed_row_pairs(
            left,
            right,
            sort_config,
            direction_multiplier,
        )

    indexed_pairs.sort(key=cmp_to_key(compare))
    return [row_pair for _, row_pair in indexed_pairs]


def _compare_indexed_row_pairs(
    left: IndexedRowPair,
    right: IndexedRowPair,
    sort_config: SortConfig,
    direction_multiplier: int,
) -> int:
    compared = _compare_sort_values(
        left[1][0].get(sort_config.column),
        right[1][0].get(sort_config.column),
    )
    if compared != 0:
        return compared * direction_multiplier
    return _compare_numbers(left[0], right[0])


def _compare_sort_values(left: Any, right: Any) -> int:
    if left is None and right is None:
        return 0
    if left is None:
        return -1
    if right is None:
        return 1
    if isinstance(left, bool) and isinstance(right, bool):
        return _compare_numbers(int(left), int(right))
    if _is_sort_number(left) and _is_sort_number(right):
        return _compare_numbers(left, right)
    return _compare_sort_strings(_to_sortable_string(left), _to_sortable_string(right))


def _is_sort_number(value: Any) -> bool:
    return isinstance(value, int | float | Decimal) and not isinstance(value, bool)


def _compare_numbers(left: int | float | Decimal, right: int | float | Decimal) -> int:
    return (left > right) - (left < right)


def _compare_sort_strings(left: str, right: str) -> int:
    left_tokens = _sortable_tokens(left.casefold())
    right_tokens = _sortable_tokens(right.casefold())
    return _compare_token_sequences(left_tokens, right_tokens)


def _sortable_tokens(value: str) -> list[SortableToken]:
    tokens: list[SortableToken] = []
    for part in _SORT_NUMBER_PATTERN.split(value):
        if not part:
            continue
        if part.isdigit():
            tokens.append((0, int(part)))
        else:
            tokens.append((1, part))
    return tokens


def _compare_token_sequences(left: Sequence[SortableToken], right: Sequence[SortableToken]) -> int:
    for left_token, right_token in zip(left, right, strict=False):
        if left_token == right_token:
            continue
        return (left_token > right_token) - (left_token < right_token)
    return _compare_numbers(len(left), len(right))


def _to_sortable_string(value: Any) -> str:
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False)
    try:
        return str(value)
    except Exception:
        return ""


def _serialize_export_value(value: Any, *, json_serialization: JsonSerialization) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict | list) and json_serialization == "string":
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal | UUID):
        return str(value)
    return str(value)


def _serialize_label_value(raw_value: str | None, field: LabelField) -> str:
    if raw_value is None:
        return ""

    value = _parse_label_record_value(raw_value)
    if isinstance(field, SingleSelectField):
        if value is None:
            return ""
        return _option_label(field, str(value))
    if isinstance(field, MultiSelectField):
        values = value if isinstance(value, list) else [value]
        return "|".join(_option_label(field, str(item)) for item in values if item is not None)
    if value is None:
        return ""
    return (
        value
        if isinstance(value, str)
        else _serialize_export_value(value, json_serialization="string")
    )


def _parse_label_record_value(raw_value: str) -> Any:
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return raw_value


def _option_label(field: SingleSelectField | MultiSelectField, value: str) -> str:
    for option in field.options:
        if option.value == value:
            return option.label
    return value


def _label_column_name(field: LabelField) -> str:
    return f"{_LABEL_COLUMN_PREFIX}{field.key}"


def _serialize(
    rows: Sequence[Sequence[str]], *, headers: Sequence[str], format: ExportFormat
) -> bytes:
    if format == "csv":
        return _serialize_csv(rows, headers=headers)
    if format == "xlsx":
        return _serialize_xlsx(rows, headers=headers)

    raise ValueError(f"Unsupported export format: {format}")


def _serialize_csv(rows: Sequence[Sequence[str]], *, headers: Sequence[str]) -> bytes:
    buf = io.StringIO(newline="")
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow(_escape_spreadsheet_cells(headers))
    writer.writerows(_escape_spreadsheet_cells(row) for row in rows)
    return buf.getvalue().encode("utf-8")


def _serialize_xlsx(rows: Sequence[Sequence[str]], *, headers: Sequence[str]) -> bytes:
    workbook = Workbook(write_only=True)
    worksheet = workbook.create_sheet(title="Export")
    worksheet.append([_prepare_xlsx_cell(header) for header in headers])
    for row in rows:
        worksheet.append([_prepare_xlsx_cell(cell) for cell in row])

    buf = io.BytesIO()
    workbook.save(buf)
    return buf.getvalue()


def _escape_spreadsheet_cells(values: Sequence[str]) -> list[str]:
    return [_escape_spreadsheet_formula(value) for value in values]


def _prepare_xlsx_cell(value: str) -> str:
    return _truncate_excel_cell(_escape_spreadsheet_formula(value))


def _escape_spreadsheet_formula(value: str) -> str:
    stripped = value.lstrip()
    if stripped and stripped[0] in _SPREADSHEET_FORMULA_PREFIXES:
        return f"'{value}"
    return value


def _truncate_excel_cell(value: str) -> str:
    if len(value) <= _EXCEL_CELL_LIMIT:
        return value
    return value[:_EXCEL_CELL_LIMIT]


def _build_filename(query_name: str | None, format: ExportFormat) -> str:
    base_name = _sanitize_filename(query_name or "query")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{base_name}_{timestamp}.{format}"


def _sanitize_filename(value: str) -> str:
    sanitized = _FILENAME_SAFE_PATTERN.sub("_", value).strip(" ._")
    return sanitized or "query"
