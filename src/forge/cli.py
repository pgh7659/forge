from __future__ import annotations

import argparse
from collections.abc import Sequence
import sys
from pathlib import Path
from typing import BinaryIO, TextIO

from forge import __version__
from forge.adapters import (
    PlanningRegistry,
    PlanningUnavailable,
    default_planning_registry,
    plan_environment,
)
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
            pointer = issue.pointer or "<root>"
            print(f"{pointer}: {issue.message}", file=stderr)
        return 4

    print(
        f"VALID {environment.name} {environment.api_version} "
        f"sha256:{environment.digest}",
        file=stdout,
    )
    return 0


def _run_plan(
    path: Path,
    stdout: BinaryIO,
    stderr: TextIO,
    registry: PlanningRegistry,
) -> int:
    try:
        environment = load_and_validate(path)
    except ConfigReadError as exc:
        print(f"READ_ERROR {path}: {exc}", file=stderr)
        return 3
    except ConfigValidationError as exc:
        print(f"INVALID {len(exc.issues)} issue(s)", file=stderr)
        for issue in exc.issues:
            pointer = issue.pointer or "<root>"
            print(f"{pointer}: {issue.message}", file=stderr)
        return 4

    try:
        artifact = plan_environment(environment, registry)
    except PlanningUnavailable as exc:
        connection_adapter = _diagnostic_adapter_component(
            exc.adapter_key.connection_adapter
        )
        runtime_adapter = _diagnostic_adapter_component(
            exc.adapter_key.runtime_adapter
        )
        print(
            "PLAN_UNAVAILABLE "
            f"{connection_adapter}+{runtime_adapter}: {exc.reason}",
            file=stderr,
        )
        return 5

    stdout.write(artifact.canonical_bytes + b"\n")
    return 0


def _diagnostic_adapter_component(value: str) -> str:
    return (
        value.replace("\n", r"\n")
        .replace("\r", r"\r")
        .replace("\u2028", r"\u2028")
        .replace("\u2029", r"\u2029")
    )


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
    plan_parser = subcommands.add_parser(
        "plan",
        help="Create a deterministic Forge plan without target access.",
    )
    plan_parser.add_argument(
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
    if args.command == "plan":
        return _run_plan(
            args.config,
            sys.stdout.buffer,
            sys.stderr,
            default_planning_registry(),
        )

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
