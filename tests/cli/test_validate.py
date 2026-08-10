from pathlib import Path

from forge.cli import main


ROOT = Path(__file__).resolve().parents[2]


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
