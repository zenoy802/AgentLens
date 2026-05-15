from __future__ import annotations

from typing import Any, cast

import httpx
import pytest
from starlette import status

from app.db.session import get_session_factory, initialize_metadata_database
from app.main import app
from app.models.misc import GlobalRenderRule

HTTP_CREATED = status.HTTP_201_CREATED
HTTP_OK = status.HTTP_200_OK
HTTP_NO_CONTENT = status.HTTP_204_NO_CONTENT
HTTP_NOT_FOUND = status.HTTP_404_NOT_FOUND
HTTP_UNPROCESSABLE_ENTITY = status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_render_rules_api_crud() -> None:
    initialize_metadata_database()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_response = await client.post(
            "/api/v1/render-rules",
            json={
                "match_pattern": "content",
                "match_type": "exact",
                "render_config": {"type": "markdown"},
                "priority": 100,
                "enabled": True,
            },
        )
        assert create_response.status_code == HTTP_CREATED
        created = create_response.json()
        assert created["match_pattern"] == "content"
        assert created["render_config"] == {"type": "markdown"}

        trajectory_response = await client.post(
            "/api/v1/render-rules",
            json={
                "match_pattern": "session_id",
                "match_type": "exact",
                "render_config": {"type": "trajectory_config", "field": "group_by"},
                "priority": 100,
                "enabled": True,
            },
        )
        assert trajectory_response.status_code == HTTP_CREATED
        trajectory_rule = trajectory_response.json()
        assert trajectory_rule["render_config"] == {
            "type": "trajectory_config",
            "field": "group_by",
            "order_direction": None,
        }

        enum_response = await client.post(
            "/api/v1/render-rules",
            json={
                "match_pattern": "status",
                "match_type": "exact",
                "render_config": {"type": "enum", "colors": {"ok": "#10b981"}},
                "priority": 80,
                "enabled": True,
            },
        )
        assert enum_response.status_code == HTTP_CREATED
        enum_rule = enum_response.json()
        assert enum_rule["render_config"] == {"type": "enum", "colors": {"ok": "#10b981"}}

        list_response = await client.get("/api/v1/render-rules")
        assert list_response.status_code == HTTP_OK
        assert [rule["id"] for rule in list_response.json()] == [
            created["id"],
            trajectory_rule["id"],
            enum_rule["id"],
        ]

        get_response = await client.get(f"/api/v1/render-rules/{created['id']}")
        assert get_response.status_code == HTTP_OK
        assert get_response.json()["id"] == created["id"]

        patch_response = await client.patch(
            f"/api/v1/render-rules/{created['id']}",
            json={
                "match_pattern": ".*_json$",
                "match_type": "regex",
                "render_config": {"type": "json", "collapsed": False},
                "enabled": False,
            },
        )
        assert patch_response.status_code == HTTP_OK
        patched = patch_response.json()
        assert patched["match_type"] == "regex"
        assert patched["render_config"] == {"type": "json", "collapsed": False}
        assert patched["enabled"] is False

        delete_response = await client.delete(f"/api/v1/render-rules/{created['id']}")
        assert delete_response.status_code == HTTP_NO_CONTENT

        missing_response = await client.get(f"/api/v1/render-rules/{created['id']}")
        assert missing_response.status_code == HTTP_NOT_FOUND


@pytest.mark.asyncio
async def test_render_rules_api_rejects_invalid_regex_and_render_config() -> None:
    initialize_metadata_database()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        invalid_regex = await client.post(
            "/api/v1/render-rules",
            json={
                "match_pattern": "[",
                "match_type": "regex",
                "render_config": {"type": "markdown"},
            },
        )
        assert invalid_regex.status_code == HTTP_UNPROCESSABLE_ENTITY
        assert invalid_regex.json()["error"]["code"] == "RENDER_RULE_INVALID_REGEX"

        invalid_render = await client.post(
            "/api/v1/render-rules",
            json={
                "match_pattern": "content",
                "match_type": "exact",
                "render_config": {"type": "unknown"},
            },
        )
        assert invalid_render.status_code == HTTP_UNPROCESSABLE_ENTITY
        assert invalid_render.json()["error"]["code"] == "VALIDATION_ERROR"

        invalid_trajectory_order = await client.post(
            "/api/v1/render-rules",
            json={
                "match_pattern": "session_id",
                "match_type": "exact",
                "render_config": {
                    "type": "trajectory_config",
                    "field": "group_by",
                    "order_direction": "desc",
                },
            },
        )
        assert invalid_trajectory_order.status_code == HTTP_UNPROCESSABLE_ENTITY
        assert invalid_trajectory_order.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_render_rules_api_lists_rules_with_invalid_stored_render_config() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        rule = GlobalRenderRule(
            match_pattern="content",
            match_type="exact",
            render_config='{"type":"unknown"}',
            priority=0,
            enabled=True,
        )
        session.add(rule)
        session.commit()
        rule_id = rule.id
    finally:
        session.close()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        list_response = await client.get("/api/v1/render-rules")
        get_response = await client.get(f"/api/v1/render-rules/{rule_id}")

    assert list_response.status_code == HTTP_OK
    assert list_response.json()[0]["render_config"] == {"type": "text"}
    assert get_response.status_code == HTTP_OK
    assert get_response.json()["render_config"] == {"type": "text"}
