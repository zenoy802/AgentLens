from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Pagination

JsonPrimitive = str | int | float | bool | None


class ConnectionBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    db_type: Literal["mysql"] = "mysql"
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=3306, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=200)
    username: str | None = Field(default=None, max_length=200)
    extra_params: dict[str, JsonPrimitive] | None = None
    default_timeout: int = Field(default=30, ge=1, le=300)
    default_row_limit: int = Field(default=10000, ge=1, le=100000)


class ConnectionCreate(ConnectionBase):
    password: str | None = None


class ConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    db_type: Literal["mysql"] | None = None
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    database: str | None = Field(default=None, min_length=1, max_length=200)
    username: str | None = Field(default=None, max_length=200)
    password: str | None = None
    extra_params: dict[str, JsonPrimitive] | None = None
    default_timeout: int | None = Field(default=None, ge=1, le=300)
    default_row_limit: int | None = Field(default=None, ge=1, le=100000)


class ConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    db_type: str
    host: str | None
    port: int | None
    database: str
    username: str | None
    extra_params: dict[str, JsonPrimitive] | None
    default_timeout: int
    default_row_limit: int
    created_at: datetime
    updated_at: datetime
    last_tested_at: datetime | None
    last_test_ok: bool | None


class ConnectionListResponse(BaseModel):
    items: list[ConnectionRead]
    pagination: Pagination


class ConnectionTestResponse(BaseModel):
    ok: bool
    latency_ms: int | None = None
    server_version: str | None = None
    tested_at: datetime
    error: str | None = None
