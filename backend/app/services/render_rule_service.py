from __future__ import annotations

import re
from typing import cast

from loguru import logger
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.models.misc import GlobalRenderRule
from app.schemas.render import TextRender
from app.schemas.render_rule import (
    MatchType,
    RenderRuleConfig,
    RenderRuleCreate,
    RenderRuleRead,
    RenderRuleUpdate,
    render_rule_config_adapter,
)


class RenderRuleService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_rules(self) -> list[RenderRuleRead]:
        rules = self.session.scalars(
            select(GlobalRenderRule).order_by(
                desc(GlobalRenderRule.priority),
                asc(GlobalRenderRule.created_at),
                asc(GlobalRenderRule.id),
            )
        ).all()
        return [self._to_read_model(rule) for rule in rules]

    def create_rule(self, payload: RenderRuleCreate) -> RenderRuleRead:
        self._validate_regex(payload.match_type, payload.match_pattern)
        rule = GlobalRenderRule(
            match_pattern=payload.match_pattern,
            match_type=payload.match_type,
            render_config=self._dump_render_config(payload.render_config),
            priority=payload.priority,
            enabled=payload.enabled,
        )
        self.session.add(rule)
        self.session.commit()
        self.session.refresh(rule)
        return self._to_read_model(rule)

    def get_rule(self, rule_id: int) -> RenderRuleRead:
        return self._to_read_model(self._get_rule_or_raise(rule_id))

    def update_rule(self, rule_id: int, payload: RenderRuleUpdate) -> RenderRuleRead:
        rule = self._get_rule_or_raise(rule_id)
        updated_fields = payload.model_fields_set

        for field_name in ("match_pattern", "match_type", "priority", "enabled"):
            if field_name in updated_fields:
                value = getattr(payload, field_name)
                if value is None:
                    raise ValidationError(
                        code="RENDER_RULE_FIELD_REQUIRED",
                        message=f"{field_name} cannot be null.",
                        detail={"field": field_name},
                    )
                setattr(rule, field_name, value)

        if "render_config" in updated_fields:
            render_config = payload.render_config
            if render_config is None:
                raise ValidationError(
                    code="RENDER_RULE_FIELD_REQUIRED",
                    message="render_config cannot be null.",
                    detail={"field": "render_config"},
                )
            rule.render_config = self._dump_render_config(render_config)

        self._validate_regex(rule.match_type, rule.match_pattern)
        self.session.commit()
        self.session.refresh(rule)
        return self._to_read_model(rule)

    def delete_rule(self, rule_id: int) -> None:
        rule = self._get_rule_or_raise(rule_id)
        self.session.delete(rule)
        self.session.commit()

    def _get_rule_or_raise(self, rule_id: int) -> GlobalRenderRule:
        rule = self.session.get(GlobalRenderRule, rule_id)
        if rule is None:
            raise NotFoundError(
                code="RENDER_RULE_NOT_FOUND",
                message="Render rule not found.",
                detail={"rule_id": rule_id},
            )
        return rule

    @staticmethod
    def _validate_regex(match_type: MatchType | str, match_pattern: str) -> None:
        if match_type != "regex":
            return
        try:
            re.compile(match_pattern)
        except re.error as exc:
            raise ValidationError(
                code="RENDER_RULE_INVALID_REGEX",
                message="match_pattern must be a valid regular expression.",
                detail={"match_pattern": match_pattern, "reason": str(exc)},
            ) from exc

    @staticmethod
    def _dump_render_config(render_config: RenderRuleConfig) -> str:
        try:
            validated = render_rule_config_adapter.validate_python(render_config)
            return render_rule_config_adapter.dump_json(validated).decode()
        except PydanticValidationError as exc:
            raise ValidationError(
                code="RENDER_RULE_INVALID_RENDER_CONFIG",
                message="render_config must be a valid render rule config.",
                detail={"errors": exc.errors()},
            ) from exc

    @staticmethod
    def _load_render_config(rule: GlobalRenderRule) -> RenderRuleConfig:
        try:
            return render_rule_config_adapter.validate_json(rule.render_config)
        except (PydanticValidationError, ValueError) as exc:
            logger.warning(
                "Invalid stored render_config for global render rule {}: {}",
                rule.id,
                exc,
            )
            return TextRender()

    def _to_read_model(self, rule: GlobalRenderRule) -> RenderRuleRead:
        return RenderRuleRead(
            id=rule.id,
            match_pattern=rule.match_pattern,
            match_type=cast(MatchType, rule.match_type),
            render_config=self._load_render_config(rule),
            priority=rule.priority,
            enabled=rule.enabled,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )
