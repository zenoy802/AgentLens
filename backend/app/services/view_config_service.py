from __future__ import annotations

from typing import cast

from loguru import logger
from pydantic import TypeAdapter
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.named_query import NamedQuery
from app.models.view_config import ViewConfig
from app.schemas.render import FieldRender
from app.schemas.view_config import (
    TableConfig,
    TrajectoryConfig,
    TrajectoryConfigSource,
    ViewConfigPayload,
    ViewConfigRead,
)

_field_renders_adapter: TypeAdapter[dict[str, FieldRender]] = TypeAdapter(dict[str, FieldRender])
_table_config_adapter: TypeAdapter[TableConfig] = TypeAdapter(TableConfig)
_trajectory_config_adapter: TypeAdapter[TrajectoryConfig] = TypeAdapter(TrajectoryConfig)


class ViewConfigService:
    def get(self, db: Session, query_id: int) -> ViewConfigRead:
        query = self._get_query_or_raise(db, query_id)
        view_config = self._get_or_create_view_config(db, query)

        return ViewConfigRead(
            query_id=query_id,
            field_renders=self._load_field_renders(view_config),
            table_config=self._load_table_config(view_config),
            trajectory_config=self._load_trajectory_config(view_config),
            trajectory_config_source=self._load_trajectory_config_source(view_config),
            row_identity_column=view_config.row_identity_column,
            updated_at=view_config.updated_at,
        )

    def put(
        self,
        db: Session,
        query_id: int,
        payload: ViewConfigPayload,
    ) -> ViewConfigRead:
        query = self._get_query_or_raise(db, query_id)
        view_config = self._get_or_create_view_config(db, query)
        old_row_identity_column = view_config.row_identity_column

        if old_row_identity_column != payload.row_identity_column:
            logger.warning(
                "row_identity_column changed for query {} from {!r} to {!r}; existing "
                "label_records are not migrated.",
                query_id,
                old_row_identity_column,
                payload.row_identity_column,
            )

        view_config.field_renders = _field_renders_adapter.dump_json(payload.field_renders).decode()
        view_config.table_config = payload.table_config.model_dump_json()
        view_config.trajectory_config = (
            None
            if payload.trajectory_config is None
            else payload.trajectory_config.model_dump_json()
        )
        view_config.trajectory_config_source = payload.trajectory_config_source
        view_config.row_identity_column = payload.row_identity_column

        db.commit()
        db.refresh(view_config)
        return self.get(db, query_id)

    @staticmethod
    def _get_query_or_raise(db: Session, query_id: int) -> NamedQuery:
        query = db.get(NamedQuery, query_id)
        if query is None:
            raise NotFoundError(
                "query not found",
                code="NOT_FOUND",
                detail={"query_id": query_id},
            )
        return query

    @staticmethod
    def _get_or_create_view_config(db: Session, query: NamedQuery) -> ViewConfig:
        stmt = select(ViewConfig).where(ViewConfig.query_id == query.id)
        view_config = db.scalars(stmt).first()
        if view_config is not None:
            return view_config

        view_config = ViewConfig(query_id=query.id, field_renders="{}", table_config="{}")
        db.add(view_config)
        db.commit()
        db.refresh(view_config)
        return view_config

    @staticmethod
    def _load_field_renders(view_config: ViewConfig) -> dict[str, FieldRender]:
        try:
            return _field_renders_adapter.validate_json(view_config.field_renders or "{}")
        except (PydanticValidationError, ValueError) as exc:
            logger.warning(
                "Invalid view_config.field_renders for query {}: {}",
                view_config.query_id,
                exc,
            )
            return {}

    @staticmethod
    def _load_table_config(view_config: ViewConfig) -> TableConfig:
        try:
            return _table_config_adapter.validate_json(view_config.table_config or "{}")
        except (PydanticValidationError, ValueError) as exc:
            logger.warning(
                "Invalid view_config.table_config for query {}: {}",
                view_config.query_id,
                exc,
            )
            return TableConfig()

    @staticmethod
    def _load_trajectory_config(view_config: ViewConfig) -> TrajectoryConfig | None:
        if view_config.trajectory_config is None:
            return None

        try:
            return _trajectory_config_adapter.validate_json(view_config.trajectory_config)
        except (PydanticValidationError, ValueError) as exc:
            logger.warning(
                "Invalid view_config.trajectory_config for query {}: {}",
                view_config.query_id,
                exc,
            )
            return None

    @staticmethod
    def _load_trajectory_config_source(
        view_config: ViewConfig,
    ) -> TrajectoryConfigSource | None:
        source = view_config.trajectory_config_source
        if source in ("manual", "suggested"):
            return cast(TrajectoryConfigSource, source)
        if source is not None:
            logger.warning(
                "Invalid view_config.trajectory_config_source for query {}: {}",
                view_config.query_id,
                source,
            )
        return None


view_config_service = ViewConfigService()
