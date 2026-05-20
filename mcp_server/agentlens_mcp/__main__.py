from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence

from agentlens_mcp.config import ConfigError, parse_args, print_config_error
from agentlens_mcp.server import run_server


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
    except ConfigError as exc:
        print_config_error(exc)
        return 1

    try:
        asyncio.run(run_server(args))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


__all__ = ["main"]
