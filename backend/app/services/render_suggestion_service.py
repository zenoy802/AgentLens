from __future__ import annotations

import json
import re
from collections.abc import Sequence
from json import JSONDecodeError
from typing import Literal, TypeGuard

from loguru import logger
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.misc import GlobalRenderRule
from app.schemas.common import WarningRead
from app.schemas.render import FieldRender, JsonRender, MarkdownRender, TextRender, TimestampRender
from app.schemas.render_rule import (
    RenderRuleConfig,
    TrajectoryConfigRule,
    render_rule_config_adapter,
)
from app.schemas.view_config import TrajectoryConfig
from app.services.query_executor import Column


def suggest(
    columns: list[Column],
    db: Session,
    *,
    warnings: list[WarningRead] | None = None,
) -> dict[str, FieldRender]:
    rules = db.scalars(
        select(GlobalRenderRule)
        .where(GlobalRenderRule.enabled.is_(True))
        .order_by(desc(GlobalRenderRule.priority), GlobalRenderRule.id.asc())
    ).all()

    suggestions: dict[str, FieldRender] = {}
    warned_invalid_rule_ids: set[int] = set()
    for column in columns:
        suggestions[column.name] = _suggest_column_render(
            column,
            rules,
            warnings=warnings,
            warned_invalid_rule_ids=warned_invalid_rule_ids,
        )
    return suggestions


def suggest_trajectory_config(
    columns: list[Column],
    db: Session,
    *,
    warnings: list[WarningRead] | None = None,
) -> TrajectoryConfig | None:
    rules = db.scalars(
        select(GlobalRenderRule)
        .where(GlobalRenderRule.enabled.is_(True))
        .order_by(desc(GlobalRenderRule.priority), GlobalRenderRule.id.asc())
    ).all()

    assigned_columns: dict[str, str] = {}
    order_direction: Literal["asc", "desc"] = "asc"
    warned_invalid_rule_ids: set[int] = set()
    for rule in rules:
        matched_column = _first_matching_column(
            columns,
            rule,
            warnings=warnings,
            warned_invalid_rule_ids=warned_invalid_rule_ids,
        )
        if matched_column is None:
            continue

        rule_config = _load_rule_trajectory_config(
            rule,
            warnings=warnings,
            warned_invalid_rule_ids=warned_invalid_rule_ids,
        )
        if rule_config is None or rule_config.field in assigned_columns:
            continue

        assigned_columns[rule_config.field] = matched_column.name
        if rule_config.field == "order_by" and rule_config.order_direction is not None:
            order_direction = rule_config.order_direction

    group_by = assigned_columns.get("group_by")
    role_column = assigned_columns.get("role_column")
    content_column = assigned_columns.get("content_column")
    if group_by is None or role_column is None or content_column is None:
        return None

    return TrajectoryConfig(
        group_by=group_by,
        role_column=role_column,
        content_column=content_column,
        tool_calls_column=assigned_columns.get("tool_calls_column"),
        order_by=assigned_columns.get("order_by"),
        order_direction=order_direction,
    )


def _suggest_column_render(
    column: Column,
    rules: Sequence[GlobalRenderRule],
    *,
    warnings: list[WarningRead] | None,
    warned_invalid_rule_ids: set[int],
) -> FieldRender:
    for rule in rules:
        if _match_pattern(
            column.name,
            rule,
            warnings=warnings,
            warned_invalid_rule_ids=warned_invalid_rule_ids,
        ):
            render_config = _load_rule_render_config(
                rule,
                warnings=warnings,
                warned_invalid_rule_ids=warned_invalid_rule_ids,
            )
            if render_config is not None:
                return render_config
    return _default_render_for_column(column)


def _load_rule_render_config(
    rule: GlobalRenderRule,
    *,
    warnings: list[WarningRead] | None,
    warned_invalid_rule_ids: set[int],
) -> FieldRender | None:
    rule_config = _load_rule_config(
        rule,
        warnings=warnings,
        warned_invalid_rule_ids=warned_invalid_rule_ids,
    )
    if rule_config is None or not _is_field_render_config(rule_config):
        return None
    return rule_config


def _load_rule_trajectory_config(
    rule: GlobalRenderRule,
    *,
    warnings: list[WarningRead] | None,
    warned_invalid_rule_ids: set[int],
) -> TrajectoryConfigRule | None:
    rule_config = _load_rule_config(
        rule,
        warnings=warnings,
        warned_invalid_rule_ids=warned_invalid_rule_ids,
    )
    if isinstance(rule_config, TrajectoryConfigRule):
        return rule_config
    return None


def _load_rule_config(
    rule: GlobalRenderRule,
    *,
    warnings: list[WarningRead] | None,
    warned_invalid_rule_ids: set[int],
) -> RenderRuleConfig | None:
    try:
        raw_config = json.loads(rule.render_config)
    except JSONDecodeError as exc:
        _warn_invalid_rule(rule, "contains invalid JSON", warnings, warned_invalid_rule_ids)
        logger.warning("Skipping invalid global render rule {}: {}", rule.id, exc)
        return None

    if not isinstance(raw_config, dict):
        _warn_invalid_rule(
            rule,
            "render_config must be an object",
            warnings,
            warned_invalid_rule_ids,
        )
        return None
    try:
        return render_rule_config_adapter.validate_python(raw_config)
    except PydanticValidationError as exc:
        _warn_invalid_rule(
            rule,
            "render_config failed validation",
            warnings,
            warned_invalid_rule_ids,
        )
        logger.warning("Skipping invalid global render rule {}: {}", rule.id, exc)
        return None


def _is_field_render_config(config: RenderRuleConfig) -> TypeGuard[FieldRender]:
    return config.type != "trajectory_config"


def _default_render_for_column(column: Column) -> FieldRender:
    if column.inferred_type == "json":
        return JsonRender()
    if column.inferred_type == "timestamp":
        return TimestampRender()
    if column.inferred_type == "text" and _looks_like_timestamp_column(column.name):
        return TimestampRender()
    if column.inferred_type == "text" and _looks_like_markdown_column(column.name):
        return MarkdownRender()
    return TextRender()


def _looks_like_timestamp_column(name: str) -> bool:
    normalized = name.lower()
    return normalized in {"timestamp", "time", "date", "datetime"} or normalized.endswith(
        ("_at", "_time", "_timestamp", "_date", "_datetime")
    )


def _looks_like_markdown_column(name: str) -> bool:
    normalized = name.lower()
    return normalized in {"content", "markdown", "md"} or normalized.endswith(
        ("_content", "_markdown", "_md")
    )


def _first_matching_column(
    columns: Sequence[Column],
    rule: GlobalRenderRule,
    *,
    warnings: list[WarningRead] | None,
    warned_invalid_rule_ids: set[int],
) -> Column | None:
    for column in columns:
        if _match_pattern(
            column.name,
            rule,
            warnings=warnings,
            warned_invalid_rule_ids=warned_invalid_rule_ids,
        ):
            return column
    return None


def _match_pattern(
    name: str,
    rule: GlobalRenderRule,
    *,
    warnings: list[WarningRead] | None = None,
    warned_invalid_rule_ids: set[int] | None = None,
) -> bool:
    pattern = rule.match_pattern
    match_type = rule.match_type
    if match_type == "exact":
        return name == pattern
    if match_type == "prefix":
        return name.startswith(pattern)
    if match_type == "suffix":
        return name.endswith(pattern)
    if match_type == "regex":
        try:
            return re.fullmatch(pattern, name) is not None
        except re.error as exc:
            logger.warning("Skipping invalid global render rule {} regex: {}", rule.id, exc)
            if warned_invalid_rule_ids is not None:
                _warn_invalid_rule(
                    rule,
                    f"invalid regex: {exc}",
                    warnings,
                    warned_invalid_rule_ids,
                )
            return False
    return False


def _warn_invalid_rule(
    rule: GlobalRenderRule,
    reason: str,
    warnings: list[WarningRead] | None,
    warned_invalid_rule_ids: set[int],
) -> None:
    if rule.id in warned_invalid_rule_ids:
        return
    warned_invalid_rule_ids.add(rule.id)
    if warnings is not None:
        if any(
            warning.code == "RENDER_RULE_INVALID"
            and warning.detail is not None
            and warning.detail.get("rule_id") == rule.id
            for warning in warnings
        ):
            return
        warnings.append(
            WarningRead(
                code="RENDER_RULE_INVALID",
                message=f"Skipped invalid global render rule {rule.id}: {reason}.",
                detail={"rule_id": rule.id, "reason": reason},
            )
        )
