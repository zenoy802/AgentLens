from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pymysql.constants import FIELD_TYPE  # type: ignore[import-untyped]

from app.services.inferred_type import from_cursor_description, infer_from_value


@pytest.mark.parametrize(
    "type_code,internal_size,expected_sql_type,expected_inferred",
    [
        (FIELD_TYPE.VAR_STRING, None, "VAR_STRING", "text"),
        (FIELD_TYPE.LONGLONG, None, "LONGLONG", "integer"),
        (FIELD_TYPE.NEWDECIMAL, None, "NEWDECIMAL", "float"),
        (FIELD_TYPE.DATETIME, None, "DATETIME", "timestamp"),
        (FIELD_TYPE.JSON, None, "JSON", "json"),
        (FIELD_TYPE.BIT, 1, "BIT", "boolean"),
        (FIELD_TYPE.BIT, 8, "BIT", "binary"),
        (99999, None, "99999", "unknown"),
    ],
)
def test_from_cursor_description_maps_mysql_types(
    type_code: int,
    internal_size: int | None,
    expected_sql_type: str,
    expected_inferred: str,
) -> None:
    assert from_cursor_description(("col", type_code, None, internal_size, None, None, True)) == (
        expected_sql_type,
        expected_inferred,
    )


@pytest.mark.parametrize(
    "value,expected",
    [
        ('{"x": 1}', "json"),
        ("[1, 2]", "json"),
        ('"scalar"', "text"),
        ("plain", "text"),
        (1, "integer"),
        (1.5, "float"),
        (True, "boolean"),
        (datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC), "timestamp"),
        (b"\x00\x01", "binary"),
        ({"x": 1}, "json"),
        (None, "unknown"),
    ],
)
def test_infer_from_value(value: Any, expected: str) -> None:
    assert infer_from_value(value) == expected
