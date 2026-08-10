from pathlib import Path

import pytest

from forge.cli import main


ROOT = Path(__file__).resolve().parents[2]


def test_no_command_prints_help_and_returns_usage_error(capsys) -> None:
    exit_code = main([])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out.startswith("usage: forge")
    assert captured.err == ""


def test_validate_requires_config(capsys) -> None:
    exit_code = main(["validate"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert captured.err.startswith("usage: forge validate")
    assert "the following arguments are required: -f/--config" in captured.err


def test_validate_prints_identity_and_digest(capsys) -> None:
    exit_code = main(
        ["validate", "--config", str(ROOT / "examples/environments/minimal.yaml")]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.startswith(
        "VALID example-primary forge.dev/v1alpha1 sha256:"
    )
    assert len(captured.out.strip().rsplit(":", 1)[1]) == 64
    assert captured.err == ""


def test_validate_short_config_option_prints_identity_and_digest(capsys) -> None:
    exit_code = main(
        ["validate", "-f", str(ROOT / "examples/environments/minimal.yaml")]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.startswith(
        "VALID example-primary forge.dev/v1alpha1 sha256:"
    )
    assert len(captured.out.strip().rsplit(":", 1)[1]) == 64
    assert captured.err == ""


def test_validate_reports_missing_file(capsys) -> None:
    exit_code = main(["validate", "--config", "does-not-exist.yaml"])
    captured = capsys.readouterr()

    assert exit_code == 3
    assert captured.out == ""
    assert captured.err.startswith("READ_ERROR does-not-exist.yaml:")


def test_validate_reports_parse_error(capsys) -> None:
    path = ROOT / "tests/fixtures/environments/invalid-syntax.yaml"
    exit_code = main(["validate", "--config", str(path)])
    captured = capsys.readouterr()

    assert exit_code == 3
    assert captured.out == ""
    assert "cannot parse YAML or JSON" in captured.err


def test_validate_reports_schema_issues(capsys) -> None:
    path = ROOT / "tests/fixtures/environments/invalid-extra-key.yaml"
    exit_code = main(["validate", "--config", str(path)])
    captured = capsys.readouterr()

    assert exit_code == 4
    assert captured.out == ""
    assert captured.err.startswith("INVALID 1 issue(s)\n")
    assert "/spec/unexpected:" in captured.err


def test_validate_reports_unhashable_yaml_key_as_read_error(
    tmp_path: Path, capsys
) -> None:
    path = tmp_path / "unhashable-key.yaml"
    path.write_text("? [foo, bar]\n: value\n", encoding="utf-8")

    exit_code = main(["validate", "--config", str(path)])
    captured = capsys.readouterr()

    assert exit_code == 3
    assert captured.out == ""
    assert captured.err.startswith(f"READ_ERROR {path}:")
    assert "cannot parse YAML or JSON" in captured.err
    assert "Traceback" not in captured.err


def test_validate_rejects_mixed_mapping_keys_before_schema_validation(
    tmp_path: Path, capsys
) -> None:
    path = tmp_path / "mixed-keys.yaml"
    path.write_text(
        "apiVersion: forge.dev/v1alpha1\n"
        "kind: Environment\n"
        "metadata: {name: mixed-keys}\n"
        "spec:\n"
        "  target:\n"
        "    connectionAdapter: ssh\n"
        "    runtimeAdapter: systemd\n"
        "1: value\n"
        "extra: value\n",
        encoding="utf-8",
    )

    exit_code = main(["validate", "--config", str(path)])
    captured = capsys.readouterr()

    assert exit_code == 4
    assert captured.out == ""
    assert captured.err == (
        "INVALID 1 issue(s)\n"
        "/1: object keys must be strings for JSON\n"
    )


def test_validate_rejects_recursive_yaml_alias_without_traceback(
    tmp_path: Path, capsys
) -> None:
    path = tmp_path / "recursive-alias.yaml"
    path.write_text(
        "apiVersion: forge.dev/v1alpha1\n"
        "kind: Environment\n"
        "metadata: {name: recursive-alias}\n"
        "spec:\n"
        "  target:\n"
        "    connectionAdapter: ssh\n"
        "    runtimeAdapter: systemd\n"
        "    config:\n"
        "      loop: &loop [*loop]\n",
        encoding="utf-8",
    )

    exit_code = main(["validate", "--config", str(path)])
    captured = capsys.readouterr()

    assert exit_code == 4
    assert captured.out == ""
    assert captured.err == (
        "INVALID 1 issue(s)\n"
        "/spec/target/config/loop/0: "
        "recursive values are not representable as JSON\n"
    )


@pytest.mark.parametrize("escape", ["\\ud800", "\\udfff"])
def test_validate_rejects_lone_surrogate_without_traceback(
    tmp_path: Path, capsys, escape: str
) -> None:
    path = tmp_path / "surrogate-string.yaml"
    path.write_text(
        "apiVersion: forge.dev/v1alpha1\n"
        "kind: Environment\n"
        "metadata: {name: surrogate-string}\n"
        "spec:\n"
        "  target:\n"
        "    connectionAdapter: noop\n"
        "    runtimeAdapter: noop\n"
        f'    config: {{"value": "{escape}"}}\n',
        encoding="utf-8",
    )

    exit_code = main(["validate", "--config", str(path)])
    captured = capsys.readouterr()

    assert exit_code == 4
    assert captured.out == ""
    assert captured.err == (
        "INVALID 1 issue(s)\n"
        "/spec/target/config/value: "
        "strings must not contain Unicode surrogate code points\n"
    )
    assert "Traceback" not in captured.err
    assert "CanonicalizationError" not in captured.err


def test_validate_displays_root_schema_issue_readably(tmp_path: Path, capsys) -> None:
    path = tmp_path / "root-sequence.yaml"
    path.write_text("[]\n", encoding="utf-8")

    exit_code = main(["validate", "--config", str(path)])
    captured = capsys.readouterr()

    assert exit_code == 4
    assert captured.out == ""
    lines = captured.err.splitlines()
    assert lines[0] == "INVALID 1 issue(s)"
    assert lines[1].startswith("<root>:")
