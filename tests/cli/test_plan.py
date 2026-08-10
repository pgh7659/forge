from __future__ import annotations

from io import StringIO
import json
from pathlib import Path

import pytest

from forge.adapters import PlanningRegistry, PlanningUnavailable
from forge.cli import _run_plan, main
from forge.config import ValidatedEnvironment
from forge.planning import AdapterKey, verify_plan


ROOT = Path(__file__).resolve().parents[2]


def _write_environment(
    path: Path,
    *,
    connection_adapter: str = "noop",
    runtime_adapter: str = "noop",
    config: str = "{}",
    reordered: bool = False,
) -> None:
    if reordered:
        path.write_text(
            "kind: Environment\n"
            "spec:\n"
            "  target:\n"
            f"    runtimeAdapter: {runtime_adapter}\n"
            f"    config: {config}\n"
            f"    connectionAdapter: {connection_adapter}\n"
            "metadata: {name: example-noop}\n"
            "apiVersion: forge.dev/v1alpha1\n",
            encoding="utf-8",
        )
        return

    path.write_text(
        "apiVersion: forge.dev/v1alpha1\n"
        "kind: Environment\n"
        "metadata: {name: example-noop}\n"
        "spec:\n"
        "  target:\n"
        f"    connectionAdapter: {connection_adapter}\n"
        f"    runtimeAdapter: {runtime_adapter}\n"
        f"    config: {config}\n",
        encoding="utf-8",
    )


def test_plan_requires_config(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["plan"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert captured.err.startswith("usage: forge plan")
    assert "the following arguments are required: -f/--config" in captured.err


def test_plan_writes_one_verified_canonical_artifact_without_target_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = tmp_path / "environment.yaml"
    secret = "fixture-secret-value"
    target_path = tmp_path / "opaque-target-path"
    _write_environment(
        config_path,
        config=f"{{token: {secret}, path: {target_path}}}",
    )

    exit_code = main(["plan", "-f", str(config_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert captured.out.endswith("\n")
    assert captured.out.count("\n") == 1
    assert verify_plan(json.loads(captured.out)).plan_id.startswith("sha256:")
    assert secret not in captured.out
    assert str(target_path) not in captured.out


def test_equivalent_reordered_configuration_has_byte_identical_plan_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first_path = tmp_path / "first.yaml"
    second_path = tmp_path / "second.yaml"
    _write_environment(first_path, config="{alpha: 1, beta: 2}")
    _write_environment(
        second_path, config="{beta: 2, alpha: 1}", reordered=True
    )

    assert main(["plan", "-f", str(first_path)]) == 0
    first = capsys.readouterr()
    assert main(["plan", "-f", str(second_path)]) == 0
    second = capsys.readouterr()

    assert first.err == second.err == ""
    assert first.out == second.out


def test_plan_reports_exact_missing_ssh_systemd_adapter(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        ["plan", "-f", str(ROOT / "examples/environments/minimal.yaml")]
    )
    captured = capsys.readouterr()

    assert exit_code == 5
    assert captured.out == ""
    assert captured.err == "PLAN_UNAVAILABLE ssh+systemd: adapter not registered\n"


@pytest.mark.parametrize(
    ("connection_adapter", "runtime_adapter", "adapter_key"),
    [("noop", "systemd", "noop+systemd"), ("ssh", "noop", "ssh+noop")],
)
def test_plan_does_not_fallback_for_unregistered_adapter_tuples(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    connection_adapter: str,
    runtime_adapter: str,
    adapter_key: str,
) -> None:
    config_path = tmp_path / f"{adapter_key}.yaml"
    _write_environment(
        config_path,
        connection_adapter=connection_adapter,
        runtime_adapter=runtime_adapter,
    )

    exit_code = main(["plan", "--config", str(config_path)])
    captured = capsys.readouterr()

    assert exit_code == 5
    assert captured.out == ""
    assert captured.err == f"PLAN_UNAVAILABLE {adapter_key}: adapter not registered\n"


@pytest.mark.parametrize(
    ("path", "expected_code", "expected_prefix"),
    [
        (Path("does-not-exist.yaml"), 3, "READ_ERROR does-not-exist.yaml:"),
        (
            ROOT / "tests/fixtures/environments/invalid-syntax.yaml",
            3,
            "READ_ERROR ",
        ),
        (
            ROOT / "tests/fixtures/environments/invalid-extra-key.yaml",
            4,
            "INVALID 1 issue(s)\n/spec/unexpected:",
        ),
    ],
)
def test_plan_preserves_owned_read_parse_and_validation_errors(
    capsys: pytest.CaptureFixture[str],
    path: Path,
    expected_code: int,
    expected_prefix: str,
) -> None:
    exit_code = main(["plan", "--config", str(path)])
    captured = capsys.readouterr()

    assert exit_code == expected_code
    assert captured.out == ""
    assert captured.err.startswith(expected_prefix)
    assert "Traceback" not in captured.err


class _RegistrySpy:
    def resolve(self, adapter_key: AdapterKey) -> object:
        raise AssertionError("registry access must follow successful validation")


def test_plan_validates_before_registry_access(tmp_path: Path) -> None:
    config_path = tmp_path / "invalid.yaml"
    _write_environment(config_path, config="{value: 9007199254740992}")
    stdout = StringIO()
    stderr = StringIO()

    exit_code = _run_plan(config_path, stdout, stderr, _RegistrySpy())  # type: ignore[arg-type]

    assert exit_code == 4
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == (
        "INVALID 1 issue(s)\n"
        "/spec/target/config/value: "
        "integers must be within the I-JSON interoperable range\n"
    )


class _UnavailableAdapter:
    def observe(self, environment: ValidatedEnvironment) -> object:
        raise PlanningUnavailable(
            AdapterKey("spoofed-connection", "spoofed-runtime"),
            "observation unavailable",
        )

    def plan(
        self, environment: ValidatedEnvironment, observation: object
    ) -> tuple[dict[str, object], ...]:
        raise AssertionError("unavailable observation must not be planned")


class _OutOfRangeAdapter:
    def observe(self, environment: ValidatedEnvironment) -> object:
        return {"value": 9007199254740992}

    def plan(
        self, environment: ValidatedEnvironment, observation: object
    ) -> tuple[dict[str, object], ...]:
        raise AssertionError("invalid observation must not be planned")


@pytest.mark.parametrize(
    ("adapter", "reason"),
    [(_UnavailableAdapter(), "observation unavailable"), (_OutOfRangeAdapter(), "invalid adapter result")],
)
def test_plan_redacts_expected_adapter_failures_without_partial_output(
    tmp_path: Path, adapter: object, reason: str
) -> None:
    config_path = tmp_path / "custom.yaml"
    secret = "opaque-target-secret"
    target_path = tmp_path / "private-target"
    _write_environment(
        config_path,
        connection_adapter="custom",
        runtime_adapter="runtime",
        config=f"{{token: {secret}, path: {target_path}}}",
    )
    registry = PlanningRegistry(((AdapterKey("custom", "runtime"), adapter),))  # type: ignore[arg-type]
    stdout = StringIO()
    stderr = StringIO()

    exit_code = _run_plan(config_path, stdout, stderr, registry)

    assert exit_code == 5
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == f"PLAN_UNAVAILABLE custom+runtime: {reason}\n"
    assert secret not in stderr.getvalue()
    assert str(target_path) not in stderr.getvalue()
    assert "9007199254740992" not in stderr.getvalue()
    assert "Traceback" not in stderr.getvalue()


class _BrokenAdapter:
    def observe(self, environment: ValidatedEnvironment) -> object:
        raise RuntimeError("unexpected programming error")

    def plan(
        self, environment: ValidatedEnvironment, observation: object
    ) -> tuple[dict[str, object], ...]:
        return ()


def test_plan_does_not_translate_unexpected_adapter_errors(tmp_path: Path) -> None:
    config_path = tmp_path / "broken.yaml"
    _write_environment(
        config_path, connection_adapter="custom", runtime_adapter="runtime"
    )
    stdout = StringIO()
    stderr = StringIO()
    registry = PlanningRegistry(
        ((AdapterKey("custom", "runtime"), _BrokenAdapter()),)
    )

    with pytest.raises(RuntimeError, match="unexpected programming error"):
        _run_plan(config_path, stdout, stderr, registry)

    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""
