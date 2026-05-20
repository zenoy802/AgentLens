from __future__ import annotations

import pytest

from agentlens_mcp.config import ConfigError, parse_args

DEFAULT_TIMEOUT = 30


def test_parse_args_requires_author() -> None:
    with pytest.raises(ConfigError, match="--author is required"):
        parse_args([])


def test_parse_args_rejects_invalid_author() -> None:
    with pytest.raises(ConfigError, match="--author must match"):
        parse_args(["--author", "agent bad"])


def test_parse_args_defaults() -> None:
    args = parse_args(["--author", "agent:claude-code"])

    assert args.backend_url == "http://127.0.0.1:8765"
    assert args.timeout == DEFAULT_TIMEOUT
    assert args.author == "agent:claude-code"
