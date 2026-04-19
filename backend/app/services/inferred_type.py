from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any, Literal, cast

from pymysql.constants import FIELD_TYPE  # type: ignore[import-untyped]

InferredType = Literal[
    "text",
    "integer",
    "float",
    "boolean",
    "json",
    "timestamp",
    "binary",
    "unknown",
]

_DESC_TYPE_CODE_INDEX = 1
_DESC_INTERNAL_SIZE_INDEX = 3


def _field_type_code(name: str) -> int:
    return cast(int, getattr(FIELD_TYPE, name))


_TYPE_CODE_NAMES: dict[int, str] = {
    _field_type_code("VARCHAR"): "VARCHAR",
    _field_type_code("VAR_STRING"): "VAR_STRING",
    _field_type_code("STRING"): "STRING",
    _field_type_code("TINY_BLOB"): "TINY_BLOB",
    _field_type_code("BLOB"): "BLOB",
    _field_type_code("MEDIUM_BLOB"): "MEDIUM_BLOB",
    _field_type_code("LONG_BLOB"): "LONG_BLOB",
    _field_type_code("TINY"): "TINY",
    _field_type_code("SHORT"): "SHORT",
    _field_type_code("LONG"): "LONG",
    _field_type_code("LONGLONG"): "LONGLONG",
    _field_type_code("INT24"): "INT24",
    _field_type_code("FLOAT"): "FLOAT",
    _field_type_code("DOUBLE"): "DOUBLE",
    _field_type_code("DECIMAL"): "DECIMAL",
    _field_type_code("NEWDECIMAL"): "NEWDECIMAL",
    _field_type_code("DATE"): "DATE",
    _field_type_code("DATETIME"): "DATETIME",
    _field_type_code("TIMESTAMP"): "TIMESTAMP",
    _field_type_code("JSON"): "JSON",
    _field_type_code("BIT"): "BIT",
}

MYSQL_TYPE_MAPPING: dict[int | str, InferredType] = {
    _field_type_code("VARCHAR"): "text",
    _field_type_code("VAR_STRING"): "text",
    _field_type_code("STRING"): "text",
    _field_type_code("TINY_BLOB"): "text",
    _field_type_code("BLOB"): "text",
    _field_type_code("MEDIUM_BLOB"): "text",
    _field_type_code("LONG_BLOB"): "text",
    _field_type_code("TINY"): "integer",
    _field_type_code("SHORT"): "integer",
    _field_type_code("LONG"): "integer",
    _field_type_code("LONGLONG"): "integer",
    _field_type_code("INT24"): "integer",
    _field_type_code("FLOAT"): "float",
    _field_type_code("DOUBLE"): "float",
    _field_type_code("DECIMAL"): "float",
    _field_type_code("NEWDECIMAL"): "float",
    _field_type_code("DATE"): "timestamp",
    _field_type_code("DATETIME"): "timestamp",
    _field_type_code("TIMESTAMP"): "timestamp",
    _field_type_code("JSON"): "json",
    _field_type_code("BIT"): "binary",
    "VARCHAR": "text",
    "VAR_STRING": "text",
    "STRING": "text",
    "TEXT": "text",
    "TINY_BLOB": "text",
    "BLOB": "text",
    "MEDIUM_BLOB": "text",
    "LONG_BLOB": "text",
    "TINY": "integer",
    "SHORT": "integer",
    "LONG": "integer",
    "LONGLONG": "integer",
    "INT24": "integer",
    "FLOAT": "float",
    "DOUBLE": "float",
    "DECIMAL": "float",
    "NEWDECIMAL": "float",
    "DATE": "timestamp",
    "DATETIME": "timestamp",
    "TIMESTAMP": "timestamp",
    "JSON": "json",
    "BIT": "binary",
}


def from_cursor_description(desc_item: Sequence[Any]) -> tuple[str, InferredType]:
    type_code = desc_item[_DESC_TYPE_CODE_INDEX] if len(desc_item) > _DESC_TYPE_CODE_INDEX else None
    internal_size = (
        desc_item[_DESC_INTERNAL_SIZE_INDEX] if len(desc_item) > _DESC_INTERNAL_SIZE_INDEX else None
    )

    sql_type_name = _sql_type_name(type_code)
    if sql_type_name == "BIT":
        return sql_type_name, "boolean" if internal_size == 1 else "binary"

    inferred = MYSQL_TYPE_MAPPING.get(type_code)
    if inferred is None:
        inferred = MYSQL_TYPE_MAPPING.get(sql_type_name, "unknown")
    return sql_type_name, inferred


def infer_from_value(value: Any) -> InferredType:
    inferred: InferredType
    if value is None:
        inferred = "unknown"
    elif isinstance(value, bool):
        inferred = "boolean"
    elif isinstance(value, int):
        inferred = "integer"
    elif isinstance(value, float):
        inferred = "float"
    elif isinstance(value, datetime | date):
        inferred = "timestamp"
    elif isinstance(value, bytes | bytearray | memoryview):
        inferred = "binary"
    elif isinstance(value, dict | list):
        inferred = "json"
    elif isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            inferred = "text"
        else:
            inferred = "json" if isinstance(decoded, dict | list) else "text"
    else:
        inferred = "unknown"
    return inferred


def _sql_type_name(type_code: object) -> str:
    if isinstance(type_code, int):
        return _TYPE_CODE_NAMES.get(type_code, str(type_code))
    if isinstance(type_code, str):
        return type_code.upper()
    return "UNKNOWN"
