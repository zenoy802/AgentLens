from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


def compute(row: dict[str, Any], identity_column: str | None) -> str:
    if identity_column and identity_column in row:
        value = row[identity_column]
        if value is not None:
            return str(value)

    normalized = _normalize(row)
    payload = json.dumps(normalized, sort_keys=True).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def _normalize(value: Any) -> Any:
    normalized: Any
    if isinstance(value, dict):
        normalized = {key: _normalize(value[key]) for key in sorted(value)}
    elif isinstance(value, list | tuple):
        normalized = [_normalize(item) for item in value]
    elif isinstance(value, datetime | date):
        normalized = value.isoformat()
    elif value is None:
        normalized = {"__agent_lens_type__": "null"}
    elif isinstance(value, bytes | bytearray | memoryview):
        normalized = base64.b64encode(bytes(value)).decode("ascii")
    elif isinstance(value, Decimal | UUID):
        normalized = str(value)
    elif isinstance(value, set | frozenset):
        normalized_items = [_normalize(item) for item in value]
        normalized = sorted(
            normalized_items,
            key=lambda item: json.dumps(item, sort_keys=True, default=str),
        )
    elif not isinstance(value, str | int | float | bool):
        normalized = str(value)
    else:
        normalized = value
    return normalized
