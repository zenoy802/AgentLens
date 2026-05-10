from __future__ import annotations

import json

import pytest

from app.core.errors import NotFoundError, ValidationError
from app.db.session import get_session_factory, initialize_metadata_database
from app.models.misc import GlobalRenderRule
from app.schemas.render import MarkdownRender, TextRender
from app.schemas.render_rule import RenderRuleCreate, RenderRuleUpdate, TrajectoryConfigRule
from app.services.render_rule_service import RenderRuleService


def test_render_rule_service_crud_and_ordering() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        service = RenderRuleService(session)

        lower = service.create_rule(
            RenderRuleCreate(
                match_pattern="message",
                match_type="exact",
                render_config=TextRender(),
                priority=10,
                enabled=True,
            )
        )
        higher = service.create_rule(
            RenderRuleCreate(
                match_pattern="content",
                match_type="exact",
                render_config=MarkdownRender(),
                priority=100,
                enabled=True,
            )
        )

        listed = service.list_rules()
        assert [rule.id for rule in listed] == [higher.id, lower.id]

        fetched = service.get_rule(higher.id)
        assert fetched.match_pattern == "content"
        assert fetched.render_config.type == "markdown"

        updated = service.update_rule(
            lower.id,
            RenderRuleUpdate(match_pattern="message_", match_type="prefix", enabled=False),
        )
        assert updated.match_pattern == "message_"
        assert updated.match_type == "prefix"
        assert updated.enabled is False

        service.delete_rule(higher.id)
        assert [rule.id for rule in service.list_rules()] == [lower.id]
    finally:
        session.close()


def test_render_rule_service_rejects_invalid_regex() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        service = RenderRuleService(session)

        with pytest.raises(ValidationError) as exc_info:
            service.create_rule(
                RenderRuleCreate(
                    match_pattern="[",
                    match_type="regex",
                    render_config=MarkdownRender(),
                )
            )
    finally:
        session.close()

    assert exc_info.value.code == "RENDER_RULE_INVALID_REGEX"


def test_render_rule_service_accepts_trajectory_config_rule() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        service = RenderRuleService(session)

        created = service.create_rule(
            RenderRuleCreate(
                match_pattern="session_id",
                match_type="exact",
                render_config=TrajectoryConfigRule(field="group_by"),
                priority=100,
                enabled=True,
            )
        )
    finally:
        session.close()

    assert isinstance(created.render_config, TrajectoryConfigRule)
    assert created.render_config.field == "group_by"


def test_render_rule_service_falls_back_for_invalid_stored_render_config() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        rule = GlobalRenderRule(
            match_pattern="content",
            match_type="exact",
            render_config=json.dumps({"type": "unknown"}),
            priority=0,
            enabled=True,
        )
        session.add(rule)
        session.commit()

        service = RenderRuleService(session)
        fetched = service.get_rule(rule.id)
    finally:
        session.close()

    assert fetched.render_config.type == "text"


def test_render_rule_service_missing_rule_raises_not_found() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        service = RenderRuleService(session)
        with pytest.raises(NotFoundError):
            service.get_rule(404)
    finally:
        session.close()
