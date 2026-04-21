from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class WarningRead(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] | None = None
