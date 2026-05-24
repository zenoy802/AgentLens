import logging
import re
import sys
import traceback
from types import FrameType
from typing import Any

from loguru import logger

from app.core.config import get_settings

_SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "api_key_enc",
    "authorization",
    "cookie",
    "database_url",
    "dsn",
    "fernet_key",
    "mysql_dsn",
    "password",
    "password_enc",
    "refresh_token",
    "secret",
    "set-cookie",
    "token",
}
_SENSITIVE_KEY_MARKERS = frozenset(_SENSITIVE_KEYS)
_SENSITIVE_MESSAGE_KEY_PATTERN = (
    r"(?:password|api[_-]?key|database_url|mysql_dsn|dsn|fernet_key|token|"
    r"access_token|refresh_token|secret)"
)
_MESSAGE_PATTERNS = [
    (
        re.compile(
            r"(?i)(\b" + _SENSITIVE_MESSAGE_KEY_PATTERN + r"\b\s*[=:]\s*\")((?:\\.|[^\"\\])*)(\")"
        ),
        r"\1***\3",
    ),
    (
        re.compile(
            r"(?i)(\b" + _SENSITIVE_MESSAGE_KEY_PATTERN + r"\b\s*[=:]\s*')((?:\\.|[^'\\])*)(')"
        ),
        r"\1***\3",
    ),
    (
        re.compile(
            r"(?i)([\"']"
            + _SENSITIVE_MESSAGE_KEY_PATTERN
            + r"[\"']\s*:\s*\")((?:\\.|[^\"\\])*)(\")"
        ),
        r"\1***\3",
    ),
    (
        re.compile(
            r"(?i)([\"']" + _SENSITIVE_MESSAGE_KEY_PATTERN + r"[\"']\s*:\s*')((?:\\.|[^'\\])*)(')"
        ),
        r"\1***\3",
    ),
    (
        re.compile(
            r"(?i)(\b"
            + _SENSITIVE_MESSAGE_KEY_PATTERN
            + r"\b\s*[=:]\s*\")((?:\\.|[^\"\r\n\\])*)(?=$|[\r\n])"
        ),
        r"\1***",
    ),
    (
        re.compile(
            r"(?i)(\b"
            + _SENSITIVE_MESSAGE_KEY_PATTERN
            + r"\b\s*[=:]\s*')((?:\\.|[^'\r\n\\])*)(?=$|[\r\n])"
        ),
        r"\1***",
    ),
    (
        re.compile(
            r"(?i)([\"']"
            + _SENSITIVE_MESSAGE_KEY_PATTERN
            + r"[\"']\s*:\s*\")((?:\\.|[^\"\r\n\\])*)(?=$|[\r\n])"
        ),
        r"\1***",
    ),
    (
        re.compile(
            r"(?i)([\"']"
            + _SENSITIVE_MESSAGE_KEY_PATTERN
            + r"[\"']\s*:\s*')((?:\\.|[^'\r\n\\])*)(?=$|[\r\n])"
        ),
        r"\1***",
    ),
    (
        re.compile(r"(?i)(\b" + _SENSITIVE_MESSAGE_KEY_PATTERN + r"\b\s*[=:]\s*)([^\"'\s,;}]+)"),
        r"\1***",
    ),
    (
        re.compile(r"(?i)(\b(?:authorization|cookie|set-cookie)\b\s*[:=]\s*)([^\"'\n\r]+)"),
        r"\1***",
    ),
    (
        re.compile(
            r"(?i)([\"'](?:authorization|cookie|set-cookie)[\"']\s*:\s*\")"
            r"((?:\\.|[^\"\\])*)(\")"
        ),
        r"\1***\3",
    ),
    (
        re.compile(
            r"(?i)([\"'](?:authorization|cookie|set-cookie)[\"']\s*:\s*')"
            r"((?:\\.|[^'\\])*)(')"
        ),
        r"\1***\3",
    ),
    (
        re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^:/\s]+:)([^@\s]+)(@)"),
        r"\1***\3",
    ),
]
_SQLALCHEMY_CONTEXT_PATTERN = re.compile(
    r"\s*\[(?:SQL|parameters):.*?\](?=\s*(?:\[[A-Za-z ]+:|\(Background on|$))",
    flags=re.IGNORECASE | re.DOTALL,
)
_SQL_NEAR_SNIPPET_PATTERNS = (
    re.compile(r"(?is)(\bnear\s+)([`'\"]).*(\2)(?=\s+at\s+line\b|$)"),
    re.compile(r"(?is)(\bnear\s+)([`'\"]).*$"),
)


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame: FrameType | None = logging.currentframe()
        depth = 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        exc = record.exc_info[1] if record.exc_info is not None else None
        if exc is not None:
            logger.opt(depth=depth).log(
                level,
                "{} context={}",
                sanitize_log_message(record.getMessage()),
                safe_exception_context(exc),
            )
            return

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _sanitize_value(value: Any, *, key: str | None = None) -> Any:
    if key is not None and _is_sensitive_key(key):
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


def _is_sensitive_key(key: str) -> bool:
    key_lower = key.lower()
    return any(marker in key_lower for marker in _SENSITIVE_KEY_MARKERS)


def sanitize_log_message(message: str) -> str:
    message = _SQLALCHEMY_CONTEXT_PATTERN.sub(" [redacted]", message)
    for pattern in _SQL_NEAR_SNIPPET_PATTERNS:
        message = pattern.sub(r"\1\2***\2", message)
    for pattern, replacement in _MESSAGE_PATTERNS:
        message = pattern.sub(replacement, message)
    return message


def sanitize_exception_message(exc: BaseException) -> str:
    return " ".join(sanitize_log_message(str(exc)).split())


def sanitize_traceback(exc: BaseException) -> str:
    raw_traceback = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return sanitize_log_message(raw_traceback)


def safe_exception_context(exc: BaseException) -> dict[str, Any]:
    context: dict[str, Any] = {"error_class": type(exc).__name__}

    code = getattr(exc, "code", None)
    if isinstance(code, str):
        context["code"] = code
    http_status = getattr(exc, "http_status", None)
    if isinstance(http_status, int):
        context["http_status"] = http_status

    chain = list(_walk_exception_chain(exc))
    if len(chain) > 1:
        context["cause_class"] = type(chain[1]).__name__

    database_exc = next((item for item in chain if _is_database_exception(item)), None)
    if database_exc is None:
        message = sanitize_exception_message(exc)
        if message:
            context["message"] = message

    if database_exc is not None:
        context["database_error_class"] = type(database_exc).__name__
        orig = getattr(database_exc, "orig", None)
        if orig is not None:
            context["dbapi_error_class"] = type(orig).__name__
        error_code = _extract_error_code(orig if orig is not None else database_exc)
        if error_code is not None:
            context["dbapi_error_code"] = error_code
        if getattr(database_exc, "statement", None) is not None:
            context["statement_redacted"] = True
        if getattr(database_exc, "params", None) is not None:
            context["params_redacted"] = True

    return context


def has_database_exception_context(exc: BaseException) -> bool:
    return any(_is_database_exception(item) for item in _walk_exception_chain(exc))


def _walk_exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return chain


def _is_database_exception(exc: BaseException) -> bool:
    module = type(exc).__module__
    if module.startswith(("sqlalchemy.", "pymysql.")):
        return True
    return type(exc).__name__ in {
        "DatabaseError",
        "DataError",
        "IntegrityError",
        "OperationalError",
        "ProgrammingError",
    }


def _extract_error_code(exc: BaseException | None) -> int | None:
    if exc is None:
        return None
    args = getattr(exc, "args", ())
    if isinstance(args, tuple) and args and isinstance(args[0], int):
        return args[0]
    return None


def mask_sensitive(record: Any) -> None:
    record["extra"] = _sanitize_value(record.get("extra", {}))

    message = record.get("message", "")
    if not isinstance(message, str):
        return

    record["message"] = sanitize_log_message(message)


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
        retention="14 days",
        compression="zip",
        encoding="utf-8",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | "
        "{message} | {extra}",
        backtrace=False,
        diagnose=False,
    )

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy"):
        std_logger = logging.getLogger(logger_name)
        std_logger.handlers = [InterceptHandler()]
        std_logger.propagate = False

    logger.info("Logging initialized: file={}", settings.log_dir / "agentlens.log")
