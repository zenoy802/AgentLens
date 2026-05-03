from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.services.row_identity_service import _normalize, compute


def test_same_content_with_different_key_order_hashes_same() -> None:
    first = {"a": 1, "b": 2}
    second = {"b": 2, "a": 1}

    assert compute(first, None) == compute(second, None)


def test_nested_dict_hash_is_stable() -> None:
    first = {"outer": {"a": [1, {"x": True}], "b": "value"}}
    second = {"outer": {"b": "value", "a": [1, {"x": True}]}}

    assert compute(first, None) == compute(second, None)


def test_normalize_handles_none_datetime_and_bytes() -> None:
    value = {
        "missing": None,
        "created_at": datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC),
        "raw": b"agentlens",
    }

    assert _normalize(value) == {
        "created_at": "2024-01-02T03:04:05+00:00",
        "missing": {"__agent_lens_type__": "null"},
        "raw": "YWdlbnRsZW5z",
    }


def test_identity_column_takes_precedence_when_value_is_not_none() -> None:
    assert compute({"id": 123, "content": "changed"}, "id") == "123"


def test_identity_column_none_falls_back_to_hash() -> None:
    row = {"id": None, "content": "stable"}

    assert compute(row, "id") == compute(row, None)


def test_null_and_literal_null_marker_hash_differently() -> None:
    assert compute({"value": None}, None) != compute({"value": "__null__"}, None)


def test_compute_handles_non_json_native_values() -> None:
    row = {
        "amount": Decimal("1.23"),
        "trace_id": UUID("12345678-1234-5678-1234-567812345678"),
        "tags": {"beta", "alpha"},
    }

    assert compute(row, None) == compute(row, None)
