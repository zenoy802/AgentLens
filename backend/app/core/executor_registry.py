from __future__ import annotations

from functools import lru_cache

from loguru import logger

from app.core.crypto import CryptoService
from app.services.query_executor import ExecutorService


@lru_cache(maxsize=1)
def get_executor_service() -> ExecutorService:
    return ExecutorService(CryptoService())


def dispose_executor_engines() -> None:
    if get_executor_service.cache_info().currsize == 0:
        logger.info("Executor engine shutdown skipped: no executor service initialized")
        return

    disposed = get_executor_service().dispose_all_engines()
    get_executor_service.cache_clear()
    logger.info("Executor engine shutdown complete: disposed={}", disposed)
