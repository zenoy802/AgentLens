import argparse
from collections.abc import Sequence

import uvicorn

from app.core.config import get_settings


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()

    parser = argparse.ArgumentParser(prog="agentlens")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run the AgentLens API server.")
    run_parser.add_argument("--host", default=settings.host, help="Host to bind the server to.")
    run_parser.add_argument("--port", default=settings.port, type=int, help="Port to bind to.")
    run_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "run":
        parser.print_help()
        return 1

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
