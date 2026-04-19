from __future__ import annotations

from pydantic import BaseModel


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int

