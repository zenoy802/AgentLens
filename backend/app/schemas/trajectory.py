from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.schemas.common import WarningRead
from app.schemas.view_config import TrajectoryConfig


class TrajectoryMessage(BaseModel):
    row_identity: str
    role: str
    content: Any
    tool_calls: Any | None = None
    raw: dict[str, Any]


class Trajectory(BaseModel):
    group_key: str
    message_count: int
    messages: list[TrajectoryMessage]


class TrajectoryAggregateRequest(BaseModel):
    use_saved_config: bool = True
    trajectory_config: TrajectoryConfig | None = None


class TrajectoryAggregateResponse(BaseModel):
    trajectories: list[Trajectory]
    warnings: list[WarningRead]
