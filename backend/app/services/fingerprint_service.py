from __future__ import annotations

import hashlib
import json
from typing import Any

import sqlparse

_FINGERPRINT_PREFIX = "sha256:"


def compute_sql_fingerprint(sql: str) -> str:
    normalized = sqlparse.format(
        sql,
        keyword_case="lower",
        strip_comments=True,
        reindent=False,
    )
    normalized = " ".join(normalized.split())
    return _sha256(normalized)


def compute_schema_fingerprint(columns: list[dict[str, Any]]) -> str:
    normalized = [
        {
            "key": col["key"],
            "type": col.get("type"),
            "render": col.get("render"),
        }
        for col in columns
    ]
    payload = json.dumps(
        normalized,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return _sha256(payload)


def compute_result_fingerprint(row_identities: list[str]) -> str:
    normalized = {
        "row_count": len(row_identities),
        "row_identities": row_identities,
    }
    payload = json.dumps(
        normalized,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return _sha256(payload)


def _sha256(payload: str) -> str:
    return f"{_FINGERPRINT_PREFIX}{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
