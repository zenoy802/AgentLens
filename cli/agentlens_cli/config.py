from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentlens_client import DEFAULT_BACKEND_URL, DEFAULT_TIMEOUT

DEFAULT_CONFIG_PATH = Path.home() / ".agentlens" / "cli.toml"
DEFAULT_AUTHOR = "human"
DEFAULT_FORMAT = "json"
OUTPUT_FORMATS = ("json", "jsonl", "csv", "pretty")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CliConfig:
    backend_url: str
    timeout: int
    author: str
    output_format: str


def resolve_config(
    *,
    backend_url: str | None = None,
    timeout: int | None = None,
    author: str | None = None,
    output_format: str | None = None,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> CliConfig:
    file_config = _load_config(config_path)
    resolved_backend_url = _first_non_empty(
        backend_url,
        os.environ.get("AGENTLENS_BACKEND_URL"),
        _nested(file_config, "backend", "url"),
        DEFAULT_BACKEND_URL,
    )
    resolved_timeout = _resolve_timeout(
        timeout,
        os.environ.get("AGENTLENS_TIMEOUT"),
        _nested(file_config, "backend", "timeout"),
        DEFAULT_TIMEOUT,
    )
    resolved_author = _first_non_empty(
        author,
        os.environ.get("AGENTLENS_AUTHOR"),
        _nested(file_config, "author", "default"),
        DEFAULT_AUTHOR,
    )
    resolved_format = _first_non_empty(
        output_format,
        os.environ.get("AGENTLENS_OUTPUT_FORMAT"),
        _nested(file_config, "output", "default_format"),
        DEFAULT_FORMAT,
    )
    if resolved_format not in OUTPUT_FORMATS:
        raise ConfigError(
            f"Invalid output format '{resolved_format}'. Expected one of: "
            f"{', '.join(OUTPUT_FORMATS)}."
        )
    return CliConfig(
        backend_url=str(resolved_backend_url),
        timeout=resolved_timeout,
        author=str(resolved_author),
        output_format=str(resolved_format),
    )


def _load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML config at {path}: {exc}") from exc
    if not isinstance(data, dict):
        return {}
    return data


def _nested(data: dict[str, Any], section: str, key: str) -> Any | None:
    section_data = data.get(section)
    if not isinstance(section_data, dict):
        return None
    return section_data.get(key)


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _resolve_timeout(*values: Any) -> int:
    value = _first_non_empty(*values)
    try:
        resolved = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError("Timeout must be an integer.") from exc
    if resolved <= 0:
        raise ConfigError("Timeout must be greater than 0.")
    return resolved
