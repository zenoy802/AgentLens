from __future__ import annotations

from typing import Any

import pytest

from app.core.errors import ValidationError
from app.schemas.view_config import TrajectoryConfig
from app.services.trajectory_service import aggregate

EXPECTED_TWO = 2


def _config(
    *,
    order_by: str | None = None,
    tool_calls_column: str | None = None,
) -> TrajectoryConfig:
    return TrajectoryConfig(
        group_by="session_id",
        role_column="role",
        content_column="content",
        tool_calls_column=tool_calls_column,
        order_by=order_by,
        order_direction="asc",
    )


def test_empty_rows_returns_empty_trajectories() -> None:
    trajectories, warnings = aggregate([], _config())

    assert trajectories == []
    assert warnings == []


def test_single_group_aggregates_and_sorts() -> None:
    rows = [
        {
            "_row_identity": "row-2",
            "session_id": "s1",
            "role": "assistant",
            "content": "second",
            "created_at": 2,
        },
        {
            "_row_identity": "row-1",
            "session_id": "s1",
            "role": "user",
            "content": "first",
            "created_at": 1,
        },
    ]

    trajectories, warnings = aggregate(rows, _config(order_by="created_at"))

    assert warnings == []
    assert len(trajectories) == 1
    assert trajectories[0].group_key == "s1"
    assert trajectories[0].message_count == EXPECTED_TWO
    assert [message.row_identity for message in trajectories[0].messages] == ["row-1", "row-2"]
    assert "_row_identity" not in trajectories[0].messages[0].raw


def test_multiple_groups_keep_first_seen_group_order() -> None:
    rows = [
        {"_row_identity": "a", "session_id": "s2", "role": "user", "content": "one"},
        {"_row_identity": "b", "session_id": "s1", "role": "user", "content": "two"},
        {"_row_identity": "c", "session_id": "s2", "role": "assistant", "content": "three"},
    ]

    trajectories, warnings = aggregate(rows, _config())

    assert warnings == []
    assert [trajectory.group_key for trajectory in trajectories] == ["s2", "s1"]
    assert [trajectory.message_count for trajectory in trajectories] == [2, 1]


def test_null_group_key_does_not_merge_with_literal_null_sentinel() -> None:
    rows: list[dict[str, Any]] = [
        {"_row_identity": "null", "session_id": None, "role": "user", "content": "null group"},
        {
            "_row_identity": "literal",
            "session_id": "__null__",
            "role": "assistant",
            "content": "literal sentinel group",
        },
    ]

    trajectories, warnings = aggregate(rows, _config())

    assert warnings == []
    assert len(trajectories) == EXPECTED_TWO
    assert [trajectory.group_key for trajectory in trajectories] == ["__null__", "__null__"]
    assert [trajectory.messages[0].row_identity for trajectory in trajectories] == [
        "null",
        "literal",
    ]


def test_null_role_becomes_unknown_and_warns() -> None:
    rows: list[dict[str, Any]] = [
        {"_row_identity": "a", "session_id": "s1", "role": None, "content": "one"},
        {"_row_identity": "b", "session_id": "s1", "role": "", "content": "two"},
    ]

    trajectories, warnings = aggregate(rows, _config())

    assert [message.role for message in trajectories[0].messages] == ["unknown", "unknown"]
    assert len(warnings) == 1
    assert warnings[0].code == "MISSING_ROLE_COLUMN"
    assert warnings[0].detail == {"group_key": "s1", "column": "role", "count": 2}


def test_missing_order_by_column_keeps_input_order() -> None:
    rows = [
        {"_row_identity": "b", "session_id": "s1", "role": "assistant", "content": "two"},
        {"_row_identity": "a", "session_id": "s1", "role": "user", "content": "one"},
    ]

    trajectories, warnings = aggregate(rows, _config(order_by="created_at"))

    assert len(warnings) == 1
    assert warnings[0].code == "MISSING_ORDER_COLUMN"
    assert warnings[0].detail == {
        "group_key": "s1",
        "column": "created_at",
        "count": EXPECTED_TWO,
    }
    assert [message.row_identity for message in trajectories[0].messages] == ["b", "a"]


def test_tool_calls_json_string_is_parsed() -> None:
    rows = [
        {
            "_row_identity": "a",
            "session_id": "s1",
            "role": "assistant",
            "content": "using tool",
            "tool_calls": '[{"name": "search", "args": {"q": "AgentLens"}}]',
        }
    ]

    trajectories, warnings = aggregate(rows, _config(tool_calls_column="tool_calls"))

    assert warnings == []
    assert trajectories[0].messages[0].tool_calls == [
        {"name": "search", "args": {"q": "AgentLens"}}
    ]


def test_missing_group_by_column_raises_validation_error() -> None:
    rows = [{"_row_identity": "a", "role": "user", "content": "missing group"}]

    with pytest.raises(ValidationError) as exc_info:
        aggregate(rows, _config())

    assert exc_info.value.code == "TRAJECTORY_GROUP_BY_MISSING"


def test_missing_role_column_raises_validation_error() -> None:
    rows = [{"_row_identity": "a", "session_id": "s1", "content": "missing role"}]

    with pytest.raises(ValidationError) as exc_info:
        aggregate(rows, _config())

    assert exc_info.value.code == "TRAJECTORY_REQUIRED_COLUMN_MISSING"
    assert exc_info.value.detail == {"column": "role", "row_index": 0}


def test_missing_content_column_raises_validation_error() -> None:
    rows = [{"_row_identity": "a", "session_id": "s1", "role": "user"}]

    with pytest.raises(ValidationError) as exc_info:
        aggregate(rows, _config())

    assert exc_info.value.code == "TRAJECTORY_REQUIRED_COLUMN_MISSING"
    assert exc_info.value.detail == {"column": "content", "row_index": 0}


def test_mixed_order_by_types_warns_and_keeps_input_order() -> None:
    rows: list[dict[str, Any]] = [
        {
            "_row_identity": "int",
            "session_id": "s1",
            "role": "user",
            "content": "one",
            "created_at": 1,
        },
        {
            "_row_identity": "str",
            "session_id": "s1",
            "role": "assistant",
            "content": "two",
            "created_at": "2",
        },
    ]

    trajectories, warnings = aggregate(rows, _config(order_by="created_at"))

    assert [message.row_identity for message in trajectories[0].messages] == ["int", "str"]
    assert len(warnings) == 1
    assert warnings[0].code == "UNSORTABLE_ORDER_COLUMN"
