from __future__ import annotations

import argparse
from collections.abc import Sequence
import sys
from pathlib import Path
from typing import TextIO

from forge import __version__
from forge.config import ConfigReadError, ConfigValidationError, load_and_validate


def _run_validate(path: Path, stdout: TextIO, stderr: TextIO) -> int:
    try:
        environment = load_and_validate(path)
    except ConfigReadError as exc:
        print(f"READ_ERROR {path}: {exc}", file=stderr)
        return 3
    except ConfigValidationError as exc:
        print(f"INVALID {len(exc.issues)} issue(s)", file=stderr)
        for issue in exc.issues:
            print(f"{issue.pointer}: {issue.message}", file=stderr)
        return 4

    print(
        f"VALID {environment.name} {environment.api_version} "
        f"sha256:{environment.digest}",
        file=stdout,
    )
    return 0


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
    subcommands = parser.add_subparsers(dest="command")
    validate_parser = subcommands.add_parser(
        "validate",
        help="Validate a Forge environment without target access.",
    )
    validate_parser.add_argument(
        "-f",
        "--config",
        type=Path,
        required=True,
        help="Path to a forge.dev/v1alpha1 Environment YAML or JSON document.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    if args.command == "validate":
        return _run_validate(args.config, sys.stdout, sys.stderr)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
