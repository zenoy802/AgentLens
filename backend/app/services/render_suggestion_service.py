from __future__ import annotations

import json
import re
from collections.abc import Sequence
from json import JSONDecodeError

from loguru import logger
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.misc import GlobalRenderRule
from app.schemas.common import WarningRead
from app.schemas.render import (
    FieldRender,
    JsonRender,
    MarkdownRender,
    TextRender,
    TimestampRender,
    field_render_adapter,
)
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
        return field_render_adapter.validate_python(raw_config)
    except PydanticValidationError as exc:
        _warn_invalid_rule(
            rule,
            "render_config failed validation",
            warnings,
            warned_invalid_rule_ids,
        )
        logger.warning("Skipping invalid global render rule {}: {}", rule.id, exc)
        return None


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
        warnings.append(
            WarningRead(
                code="RENDER_RULE_INVALID",
                message=f"Skipped invalid global render rule {rule.id}: {reason}.",
                detail={"rule_id": rule.id, "reason": reason},
            )
        )
