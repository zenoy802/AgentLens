from __future__ import annotations

import json

import pytest
from sqlalchemy.orm import Session

from app.db.session import get_session_factory, initialize_metadata_database
from app.models.misc import GlobalRenderRule
from app.schemas.common import WarningRead
from app.services.query_executor import Column
from app.services.render_suggestion_service import (
    _match_pattern,
    suggest,
    suggest_trajectory_config,
)


def test_global_rule_takes_priority_over_inferred_type() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        session.add(
            GlobalRenderRule(
                match_pattern="payload",
                match_type="exact",
                render_config=json.dumps({"type": "markdown"}),
                priority=10,
                enabled=True,
            )
        )
        session.commit()

        result = suggest([Column(name="payload", sql_type="JSON", inferred_type="json")], session)
    finally:
        session.close()

    assert result["payload"].type == "markdown"


def test_default_suggestions_use_inferred_type() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        result = suggest(
            [
                Column(name="payload", sql_type="JSON", inferred_type="json"),
                Column(name="created_at", sql_type="DATETIME", inferred_type="timestamp"),
                Column(name="started_at", sql_type="VARCHAR", inferred_type="text"),
                Column(name="content", sql_type="TEXT", inferred_type="text"),
            ],
            session,
        )
    finally:
        session.close()

    assert result["payload"].type == "json"
    assert result["payload"].collapsed is True
    assert result["created_at"].type == "timestamp"
    assert result["created_at"].format == "YYYY-MM-DD HH:mm:ss"
    assert result["started_at"].type == "timestamp"
    assert result["started_at"].format == "YYYY-MM-DD HH:mm:ss"
    assert result["content"].type == "markdown"


def test_trajectory_config_rules_build_complete_config() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        session.add_all(
            [
                GlobalRenderRule(
                    match_pattern="session_id",
                    match_type="exact",
                    render_config=json.dumps({"type": "trajectory_config", "field": "group_by"}),
                    priority=100,
                    enabled=True,
                ),
                GlobalRenderRule(
                    match_pattern="role",
                    match_type="exact",
                    render_config=json.dumps({"type": "trajectory_config", "field": "role_column"}),
                    priority=100,
                    enabled=True,
                ),
                GlobalRenderRule(
                    match_pattern="content",
                    match_type="exact",
                    render_config=json.dumps(
                        {"type": "trajectory_config", "field": "content_column"}
                    ),
                    priority=100,
                    enabled=True,
                ),
                GlobalRenderRule(
                    match_pattern="tool_calls",
                    match_type="exact",
                    render_config=json.dumps(
                        {"type": "trajectory_config", "field": "tool_calls_column"}
                    ),
                    priority=90,
                    enabled=True,
                ),
                GlobalRenderRule(
                    match_pattern="created_at",
                    match_type="exact",
                    render_config=json.dumps(
                        {
                            "type": "trajectory_config",
                            "field": "order_by",
                            "order_direction": "desc",
                        }
                    ),
                    priority=90,
                    enabled=True,
                ),
            ]
        )
        session.commit()

        result = suggest_trajectory_config(
            [
                Column(name="session_id", sql_type="VARCHAR", inferred_type="text"),
                Column(name="role", sql_type="VARCHAR", inferred_type="text"),
                Column(name="content", sql_type="TEXT", inferred_type="text"),
                Column(name="tool_calls", sql_type="JSON", inferred_type="json"),
                Column(name="created_at", sql_type="DATETIME", inferred_type="timestamp"),
            ],
            session,
        )
    finally:
        session.close()

    assert result is not None
    assert result.group_by == "session_id"
    assert result.role_column == "role"
    assert result.content_column == "content"
    assert result.tool_calls_column == "tool_calls"
    assert result.order_by == "created_at"
    assert result.order_direction == "desc"


def test_trajectory_config_rules_do_not_override_field_render_suggestions() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        session.add(
            GlobalRenderRule(
                match_pattern="content",
                match_type="exact",
                render_config=json.dumps({"type": "trajectory_config", "field": "content_column"}),
                priority=100,
                enabled=True,
            )
        )
        session.commit()

        result = suggest([Column(name="content", sql_type="TEXT", inferred_type="text")], session)
    finally:
        session.close()

    assert result["content"].type == "markdown"


@pytest.mark.parametrize("missing_field", ["group_by", "role_column", "content_column"])
def test_trajectory_config_rules_require_core_fields(missing_field: str) -> None:
    initialize_metadata_database()
    trajectory_rules = [
        ("session_id", "group_by"),
        ("role", "role_column"),
        ("content", "content_column"),
    ]
    session = get_session_factory()()
    try:
        session.add_all(
            [
                GlobalRenderRule(
                    match_pattern=match_pattern,
                    match_type="exact",
                    render_config=json.dumps(
                        {"type": "trajectory_config", "field": trajectory_field}
                    ),
                    priority=100,
                    enabled=True,
                )
                for match_pattern, trajectory_field in trajectory_rules
                if trajectory_field != missing_field
            ]
        )
        session.commit()

        result = suggest_trajectory_config(
            [
                Column(name="session_id", sql_type="VARCHAR", inferred_type="text"),
                Column(name="role", sql_type="VARCHAR", inferred_type="text"),
                Column(name="content", sql_type="TEXT", inferred_type="text"),
            ],
            session,
        )
    finally:
        session.close()

    assert result is None


def test_trajectory_config_suggestion_returns_none_without_matching_rules() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        result = suggest_trajectory_config(
            [
                Column(name="session_id", sql_type="VARCHAR", inferred_type="text"),
                Column(name="role", sql_type="VARCHAR", inferred_type="text"),
                Column(name="content", sql_type="TEXT", inferred_type="text"),
            ],
            session,
        )
    finally:
        session.close()

    assert result is None


def test_trajectory_config_highest_priority_matching_rule_wins() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        session.add_all(
            [
                GlobalRenderRule(
                    match_pattern="session_id",
                    match_type="exact",
                    render_config=json.dumps({"type": "trajectory_config", "field": "group_by"}),
                    priority=10,
                    enabled=True,
                ),
                GlobalRenderRule(
                    match_pattern="conversation_id",
                    match_type="exact",
                    render_config=json.dumps({"type": "trajectory_config", "field": "group_by"}),
                    priority=100,
                    enabled=True,
                ),
                GlobalRenderRule(
                    match_pattern="role",
                    match_type="exact",
                    render_config=json.dumps({"type": "trajectory_config", "field": "role_column"}),
                    priority=100,
                    enabled=True,
                ),
                GlobalRenderRule(
                    match_pattern="content",
                    match_type="exact",
                    render_config=json.dumps(
                        {"type": "trajectory_config", "field": "content_column"}
                    ),
                    priority=100,
                    enabled=True,
                ),
            ]
        )
        session.commit()

        result = suggest_trajectory_config(
            [
                Column(name="session_id", sql_type="VARCHAR", inferred_type="text"),
                Column(name="conversation_id", sql_type="VARCHAR", inferred_type="text"),
                Column(name="role", sql_type="VARCHAR", inferred_type="text"),
                Column(name="content", sql_type="TEXT", inferred_type="text"),
            ],
            session,
        )
    finally:
        session.close()

    assert result is not None
    assert result.group_by == "conversation_id"


@pytest.mark.parametrize(
    ("match_type", "pattern", "name"),
    [
        ("exact", "content", "content"),
        ("prefix", "tool_", "tool_calls"),
        ("suffix", "_json", "payload_json"),
        ("regex", r"message_[0-9]+", "message_123"),
    ],
)
def test_match_pattern_supports_all_match_types(
    match_type: str,
    pattern: str,
    name: str,
) -> None:
    rule = GlobalRenderRule(
        match_pattern=pattern,
        match_type=match_type,
        render_config=json.dumps({"type": "text"}),
        priority=0,
        enabled=True,
    )

    assert _match_pattern(name, rule) is True


def test_disabled_rule_is_ignored() -> None:
    initialize_metadata_database()
    session: Session = get_session_factory()()
    try:
        session.add(
            GlobalRenderRule(
                match_pattern="payload",
                match_type="exact",
                render_config=json.dumps({"type": "markdown"}),
                priority=100,
                enabled=False,
            )
        )
        session.commit()

        result = suggest([Column(name="payload", sql_type="JSON", inferred_type="json")], session)
    finally:
        session.close()

    assert result["payload"].type == "json"


def test_highest_priority_matching_rule_wins() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        session.add_all(
            [
                GlobalRenderRule(
                    match_pattern="content",
                    match_type="exact",
                    render_config=json.dumps({"type": "text"}),
                    priority=10,
                    enabled=True,
                ),
                GlobalRenderRule(
                    match_pattern="content",
                    match_type="exact",
                    render_config=json.dumps({"type": "markdown"}),
                    priority=100,
                    enabled=True,
                ),
            ]
        )
        session.commit()

        result = suggest([Column(name="content", sql_type="TEXT", inferred_type="text")], session)
    finally:
        session.close()

    assert result["content"].type == "markdown"


def test_same_priority_matching_rule_uses_lowest_id() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        first_rule = GlobalRenderRule(
            match_pattern="content",
            match_type="exact",
            render_config=json.dumps({"type": "markdown"}),
            priority=100,
            enabled=True,
        )
        second_rule = GlobalRenderRule(
            match_pattern="content",
            match_type="exact",
            render_config=json.dumps({"type": "json"}),
            priority=100,
            enabled=True,
        )
        session.add_all([first_rule, second_rule])
        session.commit()

        result = suggest([Column(name="content", sql_type="TEXT", inferred_type="text")], session)
    finally:
        session.close()

    assert result["content"].type == "markdown"


def test_invalid_rule_is_skipped_with_warning() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        session.add(
            GlobalRenderRule(
                match_pattern="payload",
                match_type="prefix",
                render_config="{not-json",
                priority=100,
                enabled=True,
            )
        )
        session.commit()
        warnings: list[WarningRead] = []

        result = suggest(
            [
                Column(name="payload", sql_type="JSON", inferred_type="json"),
                Column(name="payload_copy", sql_type="JSON", inferred_type="json"),
            ],
            session,
            warnings=warnings,
        )
    finally:
        session.close()

    assert result["payload"].type == "json"
    assert result["payload_copy"].type == "json"
    assert [warning.code for warning in warnings] == ["RENDER_RULE_INVALID"]
    assert warnings[0].detail == {"rule_id": 1, "reason": "contains invalid JSON"}


def test_invalid_regex_rule_is_skipped_with_warning() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        session.add(
            GlobalRenderRule(
                match_pattern="[",
                match_type="regex",
                render_config=json.dumps({"type": "markdown"}),
                priority=100,
                enabled=True,
            )
        )
        session.commit()
        warnings: list[WarningRead] = []

        result = suggest(
            [
                Column(name="payload", sql_type="JSON", inferred_type="json"),
                Column(name="content", sql_type="TEXT", inferred_type="text"),
            ],
            session,
            warnings=warnings,
        )
    finally:
        session.close()

    assert result["payload"].type == "json"
    assert result["content"].type == "markdown"
    assert [warning.code for warning in warnings] == ["RENDER_RULE_INVALID"]
    assert warnings[0].detail is not None
    assert warnings[0].detail["rule_id"] == 1
    assert "invalid regex" in str(warnings[0].detail["reason"])
