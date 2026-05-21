from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, TypeAlias

from app.core.errors import ValidationError
from app.schemas.common import WarningRead
from app.schemas.trajectory import Trajectory, TrajectoryMessage
from app.schemas.view_config import TrajectoryConfig

_ROW_IDENTITY_KEY = "_row_identity"
_NULL_GROUP_KEY = "__null__"
_GroupBucketKey: TypeAlias = tuple[str, str, str]
_IndexedRow: TypeAlias = tuple[int, dict[str, Any]]


def aggregate(
    rows: list[dict[str, Any]],
    config: TrajectoryConfig,
    *,
    row_identity_key: str = _ROW_IDENTITY_KEY,
    row_identities: Sequence[str] | None = None,
) -> tuple[list[Trajectory], list[WarningRead]]:
    if not rows:
        return [], []

    if row_identities is not None and len(row_identities) != len(rows):
        raise ValidationError(
            code="TRAJECTORY_ROW_IDENTITY_COUNT_MISMATCH",
            message="row_identities 数量必须与结果行数量一致",
            detail={"row_count": len(rows), "row_identity_count": len(row_identities)},
        )

    grouped_rows = _group_rows(rows, config)
    warnings: list[WarningRead] = []
    trajectories: list[Trajectory] = []

    for group_bucket_key, group_rows in grouped_rows.items():
        group_key = _display_group_key(group_bucket_key)
        sorted_rows = _sort_group_rows(group_rows, group_key, config, warnings)
        messages, missing_role_count = _build_messages(
            sorted_rows,
            group_key,
            config,
            row_identity_key,
            row_identities,
        )
        if missing_role_count > 0:
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

        trajectories.append(
            Trajectory.model_construct(
                group_key=group_key,
                message_count=len(messages),
                messages=messages,
            )
        )

    return trajectories, warnings


def _group_rows(
    rows: list[dict[str, Any]],
    config: TrajectoryConfig,
) -> dict[_GroupBucketKey, list[_IndexedRow]]:
    grouped_rows: dict[_GroupBucketKey, list[_IndexedRow]] = {}
    required_columns = (config.role_column, config.content_column)
    for index, row in enumerate(rows):
        for column in required_columns:
            if column not in row:
                raise ValidationError(
                    code="TRAJECTORY_REQUIRED_COLUMN_MISSING",
                    message=f"列 '{column}' 不存在, 无法聚合 trajectory",
                    detail={"column": column, "row_index": index},
                )

        if config.group_by not in row:
            raise ValidationError(
                code="TRAJECTORY_GROUP_BY_MISSING",
                message=f"列 '{config.group_by}' 不存在, 无法聚合 trajectory",
                detail={"group_by": config.group_by, "row_index": index},
            )

        group_value = row[config.group_by]
        group_bucket_key = _group_bucket_key(group_value)
        grouped_rows.setdefault(group_bucket_key, []).append((index, row))
    return grouped_rows


def _group_bucket_key(value: Any) -> _GroupBucketKey:
    if value is None:
        return ("null", "NoneType", _NULL_GROUP_KEY)

    return (type(value).__module__, type(value).__qualname__, str(value))


def _display_group_key(group_bucket_key: _GroupBucketKey) -> str:
    return group_bucket_key[2]


def _sort_group_rows(
    rows: list[_IndexedRow],
    group_key: str,
    config: TrajectoryConfig,
    warnings: list[WarningRead],
) -> list[_IndexedRow]:
    order_by = config.order_by
    if order_by is None:
        return rows

    missing_order_count = sum(1 for _, row in rows if order_by not in row)
    if missing_order_count > 0:
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
            key=lambda indexed_row: (
                indexed_row[1][order_by] is None,
                indexed_row[1][order_by],
            ),
            reverse=config.order_direction == "desc",
        )
    except TypeError:
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
    rows: list[_IndexedRow],
    group_key: str,
    config: TrajectoryConfig,
    row_identity_key: str,
    row_identities: Sequence[str] | None,
) -> tuple[list[TrajectoryMessage], int]:
    messages: list[TrajectoryMessage] = []
    missing_role_count = 0
    for original_index, row in rows:
        if row_identities is None:
            if row_identity_key not in row:
                raise ValidationError(
                    code="TRAJECTORY_ROW_IDENTITY_MISSING",
                    message=f"结果行缺少 {row_identity_key}, 无法构造 trajectory message",
                    detail={
                        "group_key": group_key,
                        "row_index": original_index,
                        "row_identity_key": row_identity_key,
                    },
                )
            row_identity: Any = row[row_identity_key]
        else:
            row_identity = row_identities[original_index]

        role, role_missing = _normalize_role(row[config.role_column])
        if role_missing:
            missing_role_count += 1

        raw = {key: value for key, value in row.items() if key != row_identity_key}
        messages.append(
            TrajectoryMessage.model_construct(
                row_identity=str(row_identity),
                role=role,
                content=row[config.content_column],
                tool_calls=_extract_tool_calls(row, config.tool_calls_column),
                raw=raw,
            )
        )

    return messages, missing_role_count


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
