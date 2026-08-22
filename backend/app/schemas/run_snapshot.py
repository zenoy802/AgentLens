from __future__ import annotations

from datetime import datetime
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import CursorPagination
from app.schemas.trace_contract import CanonicalRunRow

SnapshotStatus: TypeAlias = Literal["building", "ready", "failed", "corrupted", "deleted"]


class StrictSnapshotSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SnapshotBuildPolicy(StrictSnapshotSchema):
    version: Literal["snapshot-build/v1"] = "snapshot-build/v1"
    max_source_rows: int = Field(default=100_000, ge=1, le=1_000_000)
    max_runs: int = Field(default=10_000, ge=1, le=100_000)
    timeout_seconds: int = Field(default=30, ge=1, le=300)


class RunSnapshotCreate(StrictSnapshotSchema):
    name: str = Field(min_length=1, max_length=200)
    connection_id: int = Field(gt=0)
    named_query_id: int = Field(gt=0)
    trace_contract_id: str = Field(min_length=36, max_length=36)
    build_policy: SnapshotBuildPolicy = Field(default_factory=SnapshotBuildPolicy)


class SnapshotErrorInfo(StrictSnapshotSchema):
    code: str
    message: str


class SnapshotQueryManifest(StrictSnapshotSchema):
    named_query_id: int
    sql_sha256: str


class SnapshotContractManifest(StrictSnapshotSchema):
    id: str
    version: int
    definition_sha256: str


class RunSnapshotManifest(StrictSnapshotSchema):
    schema_version: Literal["run-snapshot/v1"] = "run-snapshot/v1"
    snapshot_id: str
    created_at: datetime
    query: SnapshotQueryManifest
    contract: SnapshotContractManifest
    policy: SnapshotBuildPolicy
    source_row_count: int = Field(ge=0)
    run_count: int = Field(ge=0)


class RunSnapshotRead(StrictSnapshotSchema):
    schema_version: Literal["run-snapshot-resource/v1"] = "run-snapshot-resource/v1"
    id: str
    name: str
    trace_contract_id: str
    trace_contract_version: int
    connection_id: int
    named_query_id: int
    named_query_name: str | None
    status: SnapshotStatus
    input_fingerprint: str
    content_sha256: str | None
    artifact_sha256: str | None
    artifact_size_bytes: int = Field(ge=0)
    source_row_count: int = Field(ge=0)
    run_count: int = Field(ge=0)
    progress_source_rows: int = Field(ge=0)
    progress_runs: int = Field(ge=0)
    pairing_key_field_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    build_policy: SnapshotBuildPolicy
    error: SnapshotErrorInfo | None
    manifest: RunSnapshotManifest | None
    created_at: datetime
    completed_at: datetime | None
    deleted_at: datetime | None


class RunSnapshotStatusRead(StrictSnapshotSchema):
    schema_version: Literal["run-snapshot-status/v1"] = "run-snapshot-status/v1"
    id: str
    status: SnapshotStatus
    progress_source_rows: int = Field(ge=0)
    progress_runs: int = Field(ge=0)
    error: SnapshotErrorInfo | None
    completed_at: datetime | None


class RunSnapshotListResponse(StrictSnapshotSchema):
    items: list[RunSnapshotRead]
    pagination: CursorPagination


class RunSnapshotRowsResponse(StrictSnapshotSchema):
    schema_version: Literal["run-snapshot-rows/v1"] = "run-snapshot-rows/v1"
    items: list[CanonicalRunRow]
    pagination: CursorPagination
