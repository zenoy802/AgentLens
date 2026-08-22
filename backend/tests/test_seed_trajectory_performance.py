from __future__ import annotations

import json
from pathlib import Path

import pytest
from tiktoken import Encoding

from scripts.seed_trajectory_performance import (
    SeedConfig,
    _to_insert_params,
    build_content,
    iter_jsonl,
    validate_table_name,
    write_jsonl,
)

_CONTENT_TOKEN_COUNT = 256
_SMALL_CONTENT_TOKEN_COUNT = 128
_EXPECTED_ROW_COUNT = 6


@pytest.fixture(scope="module")
def offline_encoding() -> Encoding:
    return Encoding(
        name="agentlens_test_byte_encoding",
        pat_str=r"(?s).",
        mergeable_ranks={bytes([value]): value for value in range(256)},
        special_tokens={},
    )


def test_build_content_matches_requested_token_count(offline_encoding: Encoding) -> None:
    content = build_content(
        encoding=offline_encoding,
        token_count=_CONTENT_TOKEN_COUNT,
        session_id="perf-trajectory-01",
        message_index=3,
        role="tool",
    )

    assert len(offline_encoding.encode(content)) == _CONTENT_TOKEN_COUNT
    assert "perf-trajectory-01" in content


def test_write_jsonl_persists_expected_trajectory_shape(
    tmp_path: Path, offline_encoding: Encoding
) -> None:
    output_path = tmp_path / "trajectories.jsonl"
    config = SeedConfig(
        trajectory_count=2,
        messages_per_trajectory=3,
        tokens_per_message=_SMALL_CONTENT_TOKEN_COUNT,
    )
    row_count = write_jsonl(output_path, config, offline_encoding)
    rows = list(iter_jsonl(output_path))

    assert row_count == _EXPECTED_ROW_COUNT
    assert len(rows) == _EXPECTED_ROW_COUNT
    assert {row["session_id"] for row in rows} == {
        "perf-trajectory-01",
        "perf-trajectory-02",
    }
    assert [row["message_index"] for row in rows[:3]] == [0, 1, 2]
    assert all(row["content_token_count"] == _SMALL_CONTENT_TOKEN_COUNT for row in rows)
    assert all(
        len(offline_encoding.encode(row["content"])) == _SMALL_CONTENT_TOKEN_COUNT for row in rows
    )
    assert json.loads(json.dumps(rows[0]))["message_id"] == "perf-t01-m000"


@pytest.mark.parametrize("table", ["messages; DROP TABLE users", "has-dash", "1messages"])
def test_validate_table_name_rejects_unsafe_identifiers(table: str) -> None:
    with pytest.raises(ValueError, match="letters, digits, and underscores"):
        validate_table_name(table)


def test_insert_params_converts_utc_iso_time_for_mysql_datetime(
    tmp_path: Path, offline_encoding: Encoding
) -> None:
    output = tmp_path / "single-perf-row.jsonl"
    write_jsonl(
        output,
        SeedConfig(trajectory_count=1, messages_per_trajectory=1, tokens_per_message=32),
        offline_encoding,
    )
    row = next(iter_jsonl(output))

    params = _to_insert_params(row)

    assert params["created_at"].isoformat() == "2026-01-01T00:01:00"
