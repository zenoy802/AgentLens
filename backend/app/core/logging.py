import re
import sys
from typing import Any

from loguru import logger

from app.core.config import get_settings

_SENSITIVE_KEYS = {"password", "password_enc", "api_key", "api_key_enc", "authorization"}
_MESSAGE_PATTERNS = [
    re.compile(r"(?i)(password\s*[=:]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)([^\s,;]+)"),
]


def _sanitize_value(value: Any, *, key: str | None = None) -> Any:
    if key is not None and key.lower() in _SENSITIVE_KEYS:
        return "***"
    if isinstance(value, dict):
        return {
            item_key: _sanitize_value(item_value, key=item_key)
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_value(item) for item in value)
    return value


def mask_sensitive(record: Any) -> None:
    record["extra"] = _sanitize_value(record.get("extra", {}))

    message = record.get("message", "")
    if not isinstance(message, str):
        return

    for pattern in _MESSAGE_PATTERNS:
        message = pattern.sub(r"\1***", message)
    record["message"] = message


def setup_logging() -> None:
    settings = get_settings()
    settings.ensure_directories()

    logger.remove()
    logger.configure(patcher=mask_sensitive)
    logger.add(
        sys.stdout,
        colorize=True,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:"
        "<cyan>{line}</cyan> | <level>{message}</level>",
    )
    logger.add(
        settings.log_dir / "agentlens.log",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
        level="INFO",
        backtrace=False,
        diagnose=False,
    )
