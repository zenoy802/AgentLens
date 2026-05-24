from __future__ import annotations

import json
from typing import Any, TypeAlias

from loguru import logger

from app.core.errors import ValidationError
from app.schemas.common import WarningRead
from app.schemas.trajectory import Trajectory, TrajectoryMessage
from app.schemas.view_config import TrajectoryConfig

_ROW_IDENTITY_KEY = "_row_identity"
_NULL_GROUP_KEY = "__null__"
_MISSING_GROUP_KEY = "__missing_group_by__"
_LARGE_TRAJECTORY_MESSAGE_COUNT = 1000
_GroupBucketKey: TypeAlias = tuple[str, str, str]


def aggregate(
    rows: list[dict[str, Any]],
    config: TrajectoryConfig,
    *,
    row_identity_key: str = _ROW_IDENTITY_KEY,
) -> tuple[list[Trajectory], list[WarningRead]]:
    if not rows:
        logger.info("Trajectory aggregation completed: rows=0 trajectories=0 warnings=0")
        return [], []

    warnings: list[WarningRead] = []
    grouped_rows = _group_rows(rows, config.group_by, warnings)
    trajectories: list[Trajectory] = []

    for group_bucket_key, group_rows in grouped_rows.items():
        group_key = _display_group_key(group_bucket_key)
        sorted_rows = _sort_group_rows(group_rows, group_key, config, warnings)
        messages, missing_role_count, missing_content_count = _build_messages(
            sorted_rows,
            group_key,
            config,
            row_identity_key,
        )
        if missing_role_count > 0:
            logger.warning(
                "Trajectory aggregation missing roles: group_key={} count={}",
                group_key,
                missing_role_count,
            )
            warnings.append(
                WarningRead(
                    code="MISSING_ROLE_COLUMN",
                    message=f"列 '{config.role_column}' 在部分行为空",
                    detail={
                        "group_key": group_key,
                        "column": config.role_column,
                        "count": missing_role_count,
                    },
                )
            )
        if missing_content_count > 0:
            logger.warning(
                "Trajectory aggregation missing content: group_key={} count={}",
                group_key,
                missing_content_count,
            )
            warnings.append(
                WarningRead(
                    code="MISSING_CONTENT_COLUMN",
                    message=f"列 '{config.content_column}' 在部分行缺失",
                    detail={
                        "group_key": group_key,
                        "column": config.content_column,
                        "count": missing_content_count,
                    },
                )
            )
        if len(messages) > _LARGE_TRAJECTORY_MESSAGE_COUNT:
            logger.warning(
                "Trajectory has large message count: group_key={} message_count={}",
                group_key,
                len(messages),
            )
            warnings.append(
                WarningRead(
                    code="TRAJECTORY_MESSAGE_COUNT_LARGE",
                    message=(
                        "Trajectory message count is large; the UI may initially show a subset."
                    ),
                    detail={
                        "group_key": group_key,
                        "message_count": len(messages),
                        "default_visible_messages": 200,
                    },
                )
            )

        trajectories.append(
            Trajectory(
                group_key=group_key,
                message_count=len(messages),
                messages=messages,
            )
        )
    logger.info(
        "Trajectory aggregation completed: rows={} trajectories={} warnings={}",
        len(rows),
        len(trajectories),
        len(warnings),
    )
    return trajectories, warnings


def _group_rows(
    rows: list[dict[str, Any]],
    group_by: str,
    warnings: list[WarningRead],
) -> dict[_GroupBucketKey, list[dict[str, Any]]]:
    grouped_rows: dict[_GroupBucketKey, list[dict[str, Any]]] = {}
    missing_count = 0
    for row in rows:
        if group_by not in row:
            missing_count += 1
            group_value = _MISSING_GROUP_KEY
        else:
            group_value = row[group_by]
        group_bucket_key = _group_bucket_key(group_value)
        grouped_rows.setdefault(group_bucket_key, []).append(row)
    if missing_count > 0:
        logger.warning(
            "Trajectory group_by column missing: column={} count={}",
            group_by,
            missing_count,
        )
        warnings.append(
            WarningRead(
                code="MISSING_GROUP_BY_COLUMN",
                message=f"列 '{group_by}' 在部分行缺失, 使用 fallback group",
                detail={"group_by": group_by, "count": missing_count},
            )
        )
    return grouped_rows


def _group_bucket_key(value: Any) -> _GroupBucketKey:
    if value is None:
        return ("null", "NoneType", _NULL_GROUP_KEY)

    return (type(value).__module__, type(value).__qualname__, str(value))


def _display_group_key(group_bucket_key: _GroupBucketKey) -> str:
    return group_bucket_key[2]


def _sort_group_rows(
    rows: list[dict[str, Any]],
    group_key: str,
    config: TrajectoryConfig,
    warnings: list[WarningRead],
) -> list[dict[str, Any]]:
    order_by = config.order_by
    if order_by is None:
        return rows

    missing_order_count = sum(1 for row in rows if order_by not in row)
    if missing_order_count > 0:
        logger.warning(
            "Trajectory order column missing: group_key={} column={} count={}",
            group_key,
            order_by,
            missing_order_count,
        )
        warnings.append(
            WarningRead(
                code="MISSING_ORDER_COLUMN",
                message=f"列 '{order_by}' 在部分行缺失, 保持输入顺序",
                detail={
                    "group_key": group_key,
                    "column": order_by,
                    "count": missing_order_count,
                },
            )
        )
        return rows

    try:
        return sorted(
            rows,
            key=lambda row: (row[order_by] is None, row[order_by]),
            reverse=config.order_direction == "desc",
        )
    except TypeError:
        logger.warning(
            "Trajectory order column unsortable: group_key={} column={}", group_key, order_by
        )
        warnings.append(
            WarningRead(
                code="UNSORTABLE_ORDER_COLUMN",
                message=f"列 '{order_by}' 混合类型无法排序",
                detail={
                    "group_key": group_key,
                    "column": order_by,
                    "order_direction": config.order_direction,
                },
            )
        )
        return rows


def _build_messages(
    rows: list[dict[str, Any]],
    group_key: str,
    config: TrajectoryConfig,
    row_identity_key: str,
) -> tuple[list[TrajectoryMessage], int, int]:
    messages: list[TrajectoryMessage] = []
    missing_role_count = 0
    missing_content_count = 0
    for index, row in enumerate(rows):
        if row_identity_key not in row:
            raise ValidationError(
                code="TRAJECTORY_ROW_IDENTITY_MISSING",
                message=f"结果行缺少 {row_identity_key}, 无法构造 trajectory message",
                detail={
                    "group_key": group_key,
                    "row_index": index,
                    "row_identity_key": row_identity_key,
                },
            )

        role_value = row.get(config.role_column)
        role, role_missing = _normalize_role(role_value)
        if role_missing:
            missing_role_count += 1
        if config.content_column in row:
            content = row[config.content_column]
        else:
            missing_content_count += 1
            content = None

        raw = {key: value for key, value in row.items() if key != row_identity_key}
        messages.append(
            TrajectoryMessage(
                row_identity=str(row[row_identity_key]),
                role=role,
                content=content,
                tool_calls=_extract_tool_calls(row, config.tool_calls_column),
                raw=raw,
            )
        )

    return messages, missing_role_count, missing_content_count


def _normalize_role(value: Any) -> tuple[str, bool]:
    if value is None:
        return "unknown", True

    role = str(value).strip()
    if role == "":
        return "unknown", True
    return role, False


def _extract_tool_calls(row: dict[str, Any], column: str | None) -> Any | None:
    if column is None:
        return None

    value = row.get(column)
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value
