from __future__ import annotations

from loguru import logger


async def close_http_clients() -> None:
    logger.info("Global HTTP client shutdown complete: disposed=0")
