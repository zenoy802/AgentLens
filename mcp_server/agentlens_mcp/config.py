from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from agentlens_client import DEFAULT_BACKEND_URL

DEFAULT_TIMEOUT = 30
AUTHOR_PATTERN = re.compile(r"^[a-zA-Z0-9_:.-]+$")


@dataclass(frozen=True, slots=True)
class Args:
    backend_url: str
    author: str
    timeout: int


class ConfigError(ValueError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentlens-mcp",
        description="AgentLens MCP server using stdio transport.",
    )
    parser.add_argument(
        "--backend-url",
        default=DEFAULT_BACKEND_URL,
        help=f"AgentLens backend URL. Defaults to {DEFAULT_BACKEND_URL}.",
    )
    parser.add_argument(
        "--author",
        default=None,
        help="Required annotation author, for example agent:claude-code.",
    )
    parser.add_argument(
        "--timeout",
        default=DEFAULT_TIMEOUT,
        type=int,
        help=f"Backend request timeout in seconds. Defaults to {DEFAULT_TIMEOUT}.",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> Args:
    namespace = build_parser().parse_args(argv)
    author = namespace.author
    if author is None:
        raise ConfigError("--author is required. Example: agentlens-mcp --author agent:claude-code")
    validate_author(author)
    timeout = int(namespace.timeout)
    if timeout < 1:
        raise ConfigError("--timeout must be a positive integer.")
    return Args(
        backend_url=str(namespace.backend_url),
        author=author,
        timeout=timeout,
    )


def validate_author(author: str) -> None:
    if not AUTHOR_PATTERN.fullmatch(author):
        raise ConfigError("--author must match ^[a-zA-Z0-9_:.-]+$.")


def print_config_error(exc: ConfigError) -> None:
    print(f"agentlens-mcp: error: {exc}", file=sys.stderr)


__all__ = [
    "AUTHOR_PATTERN",
    "DEFAULT_BACKEND_URL",
    "DEFAULT_TIMEOUT",
    "Args",
    "ConfigError",
    "build_parser",
    "parse_args",
    "print_config_error",
    "validate_author",
]
