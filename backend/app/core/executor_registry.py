from __future__ import annotations

from functools import lru_cache

from app.core.crypto import CryptoService
from app.services.query_executor import ExecutorService


@lru_cache(maxsize=1)
def get_executor_service() -> ExecutorService:
    return ExecutorService(CryptoService())
