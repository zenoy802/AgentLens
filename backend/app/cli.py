from collections.abc import Sequence

from app.server_runtime import run_server


def main(argv: Sequence[str] | None = None) -> int:
    _ = argv
    run_server(emit=print)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
