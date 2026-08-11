from pathlib import Path
import re

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


def test_unknown_property_uses_safe_parent_pointer_and_owned_reason() -> None:
    sentinel = "fixture-credential-SENTINEL-unknown-property-93f4a8"
    document = {
        "apiVersion": "forge.dev/v1alpha1",
        "kind": "Environment",
        "metadata": {"name": "unknown-property"},
        "spec": {
            "target": {
                "connectionAdapter": "noop",
                "runtimeAdapter": "noop",
            },
            sentinel: True,
        },
    }

    with pytest.raises(ConfigValidationError) as raised:
        validate_document(document)

    assert raised.value.issues[0].pointer == "/spec"
    assert raised.value.issues[0].message == "unexpected property is not allowed"
    assert sentinel not in repr(raised.value.issues)


def test_invalid_yaml_is_a_read_error() -> None:
    with pytest.raises(ConfigReadError) as raised:
        load_and_validate(ROOT / "tests/fixtures/environments/invalid-syntax.yaml")

    assert "cannot parse YAML or JSON" in str(raised.value)


def test_invalid_yaml_error_owns_safe_location_without_source_or_cause(
    tmp_path: Path,
) -> None:
    sentinel = "fixture-credential-SENTINEL-yaml-source-7d2c91"
    path = tmp_path / "invalid-source.yaml"
    source_line = f"metadata: [name: {sentinel}"
    path.write_text(
        "apiVersion: forge.dev/v1alpha1\n"
        "kind: Environment\n"
        f"{source_line}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigReadError) as raised:
        load_and_validate(path)

    error = raised.value
    assert re.fullmatch(
        r"cannot parse YAML or JSON: invalid syntax at line \d+, column \d+",
        str(error),
    )
    assert sentinel not in str(error)
    assert sentinel not in repr(error)
    assert source_line not in str(error)
    assert error.__cause__ is None
    assert error.__context__ is None


def test_schema_invalid_identifier_uses_owned_value_free_diagnostic() -> None:
    sentinel = "fixture-credential-SENTINEL-invalid-name-6b4e20"
    document = {
        "apiVersion": "forge.dev/v1alpha1",
        "kind": "Environment",
        "metadata": {"name": sentinel},
        "spec": {
            "target": {
                "connectionAdapter": "noop",
                "runtimeAdapter": "noop",
            }
        },
    }

    with pytest.raises(ConfigValidationError) as raised:
        validate_document(document)

    assert raised.value.issues[0].pointer == "/metadata/name"
    assert (
        raised.value.issues[0].message
        == "string does not match the required pattern"
    )
    assert sentinel not in repr(raised.value.issues)


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


@pytest.mark.parametrize("surrogate", ["\ud800", "\udfff"])
def test_direct_document_rejects_lone_surrogate_string(surrogate: str) -> None:
    document = {
        "apiVersion": "forge.dev/v1alpha1",
        "kind": "Environment",
        "metadata": {"name": "surrogate-string"},
        "spec": {
            "target": {
                "connectionAdapter": "noop",
                "runtimeAdapter": "noop",
                "config": {"value": surrogate},
            }
        },
    }

    with pytest.raises(ConfigValidationError) as raised:
        validate_document(document)

    assert raised.value.issues[0].pointer == "/spec/target/config/value"
    assert (
        raised.value.issues[0].message
        == "strings must not contain Unicode surrogate code points"
    )


@pytest.mark.parametrize("escape", ["\\ud800", "\\udfff"])
def test_file_document_rejects_lone_surrogate_string(
    tmp_path: Path, escape: str
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

    with pytest.raises(ConfigValidationError) as raised:
        load_and_validate(path)

    assert raised.value.issues[0].pointer == "/spec/target/config/value"
    assert (
        raised.value.issues[0].message
        == "strings must not contain Unicode surrogate code points"
    )


def test_lone_surrogate_mapping_key_has_a_printable_pointer() -> None:
    document = {
        "apiVersion": "forge.dev/v1alpha1",
        "kind": "Environment",
        "metadata": {"name": "surrogate-key"},
        "spec": {
            "target": {
                "connectionAdapter": "noop",
                "runtimeAdapter": "noop",
                "config": {"\ud800": "value"},
            }
        },
    }

    with pytest.raises(ConfigValidationError) as raised:
        validate_document(document)

    assert raised.value.issues[0].pointer == "/spec/target/config/\\ud800"
    assert (
        raised.value.issues[0].message
        == "object keys must not contain Unicode surrogate code points"
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


def test_validated_environment_owns_an_immutable_snapshot() -> None:
    document = {
        "apiVersion": "forge.dev/v1alpha1",
        "kind": "Environment",
        "metadata": {"name": "snapshot"},
        "spec": {
            "target": {
                "connectionAdapter": "noop",
                "runtimeAdapter": "noop",
                "config": {"nested": {"value": "original"}},
            }
        },
    }
    environment = validate_document(document)
    original_digest = environment.digest

    document["metadata"]["name"] = "caller-mutated"
    document["spec"]["target"]["connectionAdapter"] = "caller-mutated"
    document["spec"]["target"]["config"]["nested"]["value"] = "caller-mutated"
    first_read = environment.document
    first_read["metadata"]["name"] = "consumer-mutated"
    first_read["spec"]["target"]["runtimeAdapter"] = "consumer-mutated"

    assert environment.name == "snapshot"
    assert environment.api_version == "forge.dev/v1alpha1"
    assert environment.digest == original_digest
    assert environment.document["metadata"]["name"] == "snapshot"
    assert environment.document["spec"]["target"] == {
        "connectionAdapter": "noop",
        "runtimeAdapter": "noop",
        "config": {"nested": {"value": "original"}},
    }


@pytest.mark.parametrize("terminator", ["\n", "\r", "\u2028", "\u2029"])
@pytest.mark.parametrize(
    "field",
    ["metadata.name", "target.connectionAdapter", "target.runtimeAdapter"],
)
def test_environment_identifiers_reject_line_terminators(
    terminator: str, field: str
) -> None:
    document = {
        "apiVersion": "forge.dev/v1alpha1",
        "kind": "Environment",
        "metadata": {"name": "example"},
        "spec": {
            "target": {
                "connectionAdapter": "noop",
                "runtimeAdapter": "noop",
            }
        },
    }
    if field == "metadata.name":
        document["metadata"]["name"] += terminator
    elif field == "target.connectionAdapter":
        document["spec"]["target"]["connectionAdapter"] += terminator
    else:
        document["spec"]["target"]["runtimeAdapter"] += terminator

    with pytest.raises(ConfigValidationError):
        validate_document(document)
