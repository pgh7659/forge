from __future__ import annotations

import argparse
from collections.abc import Sequence

from forge import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forge",
        description="Validate and reconcile portable Forge environments.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"forge {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
