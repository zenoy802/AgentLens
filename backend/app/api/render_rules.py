from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.render_rule import RenderRuleCreate, RenderRuleRead, RenderRuleUpdate
from app.services.render_rule_service import RenderRuleService

router = APIRouter(prefix="/render-rules", tags=["render-rules"])


def get_render_rule_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> RenderRuleService:
    return RenderRuleService(session)


@router.get("", response_model=list[RenderRuleRead])
def list_render_rules(
    service: Annotated[RenderRuleService, Depends(get_render_rule_service)],
) -> list[RenderRuleRead]:
    return service.list_rules()


@router.post("", response_model=RenderRuleRead, status_code=status.HTTP_201_CREATED)
def create_render_rule(
    payload: RenderRuleCreate,
    service: Annotated[RenderRuleService, Depends(get_render_rule_service)],
) -> RenderRuleRead:
    return service.create_rule(payload)


@router.get("/{rule_id}", response_model=RenderRuleRead)
def get_render_rule(
    rule_id: int,
    service: Annotated[RenderRuleService, Depends(get_render_rule_service)],
) -> RenderRuleRead:
    return service.get_rule(rule_id)


@router.patch("/{rule_id}", response_model=RenderRuleRead)
def update_render_rule(
    rule_id: int,
    payload: RenderRuleUpdate,
    service: Annotated[RenderRuleService, Depends(get_render_rule_service)],
) -> RenderRuleRead:
    return service.update_rule(rule_id, payload)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_render_rule(
    rule_id: int,
    service: Annotated[RenderRuleService, Depends(get_render_rule_service)],
) -> Response:
    service.delete_rule(rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
