from __future__ import annotations

from app.services.fingerprint_service import (
    compute_result_fingerprint,
    compute_schema_fingerprint,
    compute_sql_fingerprint,
)


def test_sql_fingerprint_is_stable_for_comments_case_and_whitespace() -> None:
    first = "SELECT  *  FROM traces -- ignored\nWHERE id = 1"
    second = "select * from traces where id = 1"

    assert compute_sql_fingerprint(first) == compute_sql_fingerprint(second)
    assert compute_sql_fingerprint(first).startswith("sha256:")


def test_sql_fingerprint_changes_for_different_sql() -> None:
    assert compute_sql_fingerprint("SELECT * FROM traces WHERE id = 1") != (
        compute_sql_fingerprint("SELECT * FROM traces WHERE id = 2")
    )


def test_schema_fingerprint_uses_key_type_and_render() -> None:
    base = [{"key": "content", "type": "text", "render": {"type": "markdown"}, "ignored": True}]
    same = [{"render": {"type": "markdown"}, "type": "text", "key": "content"}]
    changed = [{"key": "content", "type": "text", "render": {"type": "json"}}]

    assert compute_schema_fingerprint(base) == compute_schema_fingerprint(same)
    assert compute_schema_fingerprint(base) != compute_schema_fingerprint(changed)


def test_result_fingerprint_tracks_count_and_ordered_row_identities() -> None:
    first = ["row-1", "row-2"]
    same = ["row-1", "row-2"]
    reordered = ["row-2", "row-1"]

    assert compute_result_fingerprint(first) == compute_result_fingerprint(same)
    assert compute_result_fingerprint(first) != compute_result_fingerprint(reordered)
