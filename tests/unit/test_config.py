from pathlib import Path

import pytest

from forge.config import (
    ConfigReadError,
    ConfigValidationError,
    load_and_validate,
    validate_document,
)


ROOT = Path(__file__).resolve().parents[2]


def test_minimal_environment_is_valid() -> None:
    result = load_and_validate(ROOT / "examples/environments/minimal.yaml")

    assert result.name == "example-primary"
    assert result.api_version == "forge.dev/v1alpha1"
    assert len(result.digest) == 64


def test_unknown_property_reports_json_pointer() -> None:
    with pytest.raises(ConfigValidationError) as raised:
        load_and_validate(
            ROOT / "tests/fixtures/environments/invalid-extra-key.yaml"
        )

    assert raised.value.issues[0].pointer == "/spec/unexpected"
    assert "Additional properties are not allowed" in raised.value.issues[0].message


def test_invalid_yaml_is_a_read_error() -> None:
    with pytest.raises(ConfigReadError) as raised:
        load_and_validate(ROOT / "tests/fixtures/environments/invalid-syntax.yaml")

    assert "cannot parse YAML or JSON" in str(raised.value)


def test_duplicate_key_is_a_read_error() -> None:
    with pytest.raises(ConfigReadError) as raised:
        load_and_validate(
            ROOT / "tests/fixtures/environments/invalid-duplicate-key.yaml"
        )

    assert "duplicate mapping key" in str(raised.value)


def test_non_utf8_document_is_a_read_error(tmp_path: Path) -> None:
    path = tmp_path / "non-utf8.yaml"
    path.write_bytes(b"\xff")

    with pytest.raises(ConfigReadError) as raised:
        load_and_validate(path)

    assert "cannot decode UTF-8" in str(raised.value)


def test_digest_is_independent_of_mapping_order(tmp_path: Path) -> None:
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"
    first.write_text(
        "apiVersion: forge.dev/v1alpha1\nkind: Environment\n"
        "metadata: {name: same}\nspec:\n  target:\n"
        "    connectionAdapter: ssh\n    runtimeAdapter: systemd\n",
        encoding="utf-8",
    )
    second.write_text(
        "kind: Environment\nspec:\n  target:\n"
        "    runtimeAdapter: systemd\n    connectionAdapter: ssh\n"
        "metadata: {name: same}\napiVersion: forge.dev/v1alpha1\n",
        encoding="utf-8",
    )

    assert load_and_validate(first).digest == load_and_validate(second).digest


def test_implicit_yaml_date_is_a_validation_error(tmp_path: Path) -> None:
    path = tmp_path / "implicit-date.yaml"
    path.write_text(
        "apiVersion: forge.dev/v1alpha1\nkind: Environment\n"
        "metadata: {name: implicit-date}\nspec:\n  target:\n"
        "    connectionAdapter: ssh\n    runtimeAdapter: systemd\n"
        "    config: {startDate: 2026-08-10}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError) as raised:
        load_and_validate(path)

    assert raised.value.issues[0].pointer == "/spec/target/config/startDate"
    assert raised.value.issues[0].message == "value is not representable as JSON"


def test_non_finite_float_is_a_validation_error(tmp_path: Path) -> None:
    path = tmp_path / "non-finite-float.yaml"
    path.write_text(
        "apiVersion: forge.dev/v1alpha1\nkind: Environment\n"
        "metadata: {name: non-finite-float}\nspec:\n  target:\n"
        "    connectionAdapter: ssh\n    runtimeAdapter: systemd\n"
        "    config: {ratio: .nan}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError) as raised:
        load_and_validate(path)

    assert raised.value.issues[0].pointer == "/spec/target/config/ratio"
    assert (
        raised.value.issues[0].message
        == "non-finite floats are not representable as JSON"
    )


@pytest.mark.parametrize("value", [9007199254740992, -9007199254740992])
def test_out_of_range_integer_is_a_validation_error(
    tmp_path: Path, value: int
) -> None:
    path = tmp_path / "out-of-range-integer.yaml"
    path.write_text(
        "apiVersion: forge.dev/v1alpha1\nkind: Environment\n"
        "metadata: {name: out-of-range-integer}\nspec:\n  target:\n"
        "    connectionAdapter: ssh\n    runtimeAdapter: systemd\n"
        f"    config: {{value: {value}}}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError) as raised:
        load_and_validate(path)

    assert raised.value.issues[0].pointer == "/spec/target/config/value"
    assert (
        raised.value.issues[0].message
        == "integers must be within the I-JSON interoperable range"
    )


def test_non_string_mapping_key_is_a_validation_error(tmp_path: Path) -> None:
    path = tmp_path / "non-string-key.yaml"
    path.write_text(
        "apiVersion: forge.dev/v1alpha1\nkind: Environment\n"
        "metadata: {name: non-string-key}\nspec:\n  target:\n"
        "    connectionAdapter: ssh\n    runtimeAdapter: systemd\n"
        "    config: {1: value}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError) as raised:
        load_and_validate(path)

    assert raised.value.issues[0].pointer == "/spec/target/config/1"
    assert raised.value.issues[0].message == "object keys must be strings for JSON"


def test_root_schema_issue_uses_the_rfc_6901_root_pointer() -> None:
    with pytest.raises(ConfigValidationError) as raised:
        validate_document([])

    assert raised.value.issues[0].pointer == ""
