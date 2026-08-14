from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode

from forge.canonical import CanonicalizationError, canonical_json_bytes


class ConfigReadError(Exception):
    """The document could not be read or parsed."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects ambiguous duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate mapping key: {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    pointer: str
    message: str


class ConfigValidationError(Exception):
    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        self.issues = issues
        super().__init__(f"environment has {len(issues)} validation issue(s)")


@dataclass(frozen=True, slots=True, init=False)
class ValidatedEnvironment:
    _canonical_bytes: bytes

    @property
    def name(self) -> str:
        return self.document["metadata"]["name"]

    @property
    def api_version(self) -> str:
        return self.document["apiVersion"]

    @property
    def digest(self) -> str:
        return hashlib.sha256(self._canonical_bytes).hexdigest()

    @property
    def document(self) -> dict[str, Any]:
        value = json.loads(self._canonical_bytes)
        assert isinstance(value, dict)
        return value


def _validated_environment(canonical_bytes: bytes) -> ValidatedEnvironment:
    environment = object.__new__(ValidatedEnvironment)
    object.__setattr__(environment, "_canonical_bytes", canonical_bytes)
    return environment


def _json_pointer(parts: list[object]) -> str:
    if not parts:
        return ""
    encoded = [
        _printable_pointer_part(part).replace("~", "~0").replace("/", "~1")
        for part in parts
    ]
    return "/" + "/".join(encoded)


def _printable_pointer_part(part: object) -> str:
    value = str(part)
    return "".join(
        f"\\u{ord(character):04x}"
        if 0xD800 <= ord(character) <= 0xDFFF
        else character
        for character in value
    )


def _has_surrogate_code_point(value: str) -> bool:
    return any(0xD800 <= ord(character) <= 0xDFFF for character in value)


def _issue_pointer(error: Any) -> str:
    return _json_pointer(list(error.absolute_path))


_SCHEMA_ISSUE_MESSAGES = {
    "additionalProperties": "unexpected property is not allowed",
    "const": "value does not match the required constant",
    "maxLength": "string is longer than allowed",
    "minLength": "string is shorter than allowed",
    "minimum": "number is below the allowed minimum",
    "not": "value matches a prohibited form",
    "pattern": "string does not match the required pattern",
    "required": "required property is missing",
    "type": "value has the wrong type",
}


def _schema_issue_message(error: Any) -> str:
    return _SCHEMA_ISSUE_MESSAGES.get(
        error.validator,
        "value does not satisfy the configuration schema",
    )


def _schema_error_sort_key(error: Any) -> tuple[object, ...]:
    return (
        tuple(str(part) for part in error.absolute_path),
        tuple(str(part) for part in error.absolute_schema_path),
        str(error.validator),
    )


_ENVIRONMENT_ROOT_KEYS = frozenset({"apiVersion", "kind", "metadata", "spec"})
_ENVIRONMENT_METADATA_KEYS = frozenset({"name"})
_ENVIRONMENT_SPEC_KEYS = frozenset(
    {
        "target",
        "gateway",
        "assistant",
        "executor",
        "state",
        "workspace",
        "sourceControl",
        "secrets",
    }
)
_ENVIRONMENT_ADAPTER_SECTIONS = _ENVIRONMENT_SPEC_KEYS - {"target"}
_ENVIRONMENT_TARGET_KEYS = frozenset(
    {"connectionAdapter", "runtimeAdapter", "config"}
)
_ENVIRONMENT_ADAPTER_KEYS = frozenset({"adapter", "config"})
_ENVIRONMENT_EXECUTOR_KEYS = _ENVIRONMENT_ADAPTER_KEYS | {"maxConcurrency"}


def _known_environment_mapping_keys(path: tuple[str, ...]) -> frozenset[str]:
    if path == ():
        return _ENVIRONMENT_ROOT_KEYS
    if path == ("metadata",):
        return _ENVIRONMENT_METADATA_KEYS
    if path == ("spec",):
        return _ENVIRONMENT_SPEC_KEYS
    if path == ("spec", "target"):
        return _ENVIRONMENT_TARGET_KEYS
    if (
        len(path) == 2
        and path[0] == "spec"
        and path[1] in _ENVIRONMENT_ADAPTER_SECTIONS
    ):
        if path[1] == "executor":
            return _ENVIRONMENT_EXECUTOR_KEYS
        return _ENVIRONMENT_ADAPTER_KEYS
    return frozenset()


def _json_compatibility_issues(document: object) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    active_containers: set[int] = set()

    def visit(
        value: object,
        pointer_parts: tuple[str, ...],
        schema_path: tuple[str, ...] | None,
    ) -> None:
        if value is None or type(value) is bool:
            return
        if type(value) is str:
            if _has_surrogate_code_point(value):
                issues.append(
                    ValidationIssue(
                        pointer=_json_pointer(list(pointer_parts)),
                        message="strings must not contain Unicode surrogate code points",
                    )
                )
            return
        if type(value) is int:
            if not -9007199254740991 <= value <= 9007199254740991:
                issues.append(
                    ValidationIssue(
                        pointer=_json_pointer(list(pointer_parts)),
                        message="integers must be within the I-JSON interoperable range",
                    )
                )
            return
        if type(value) is float:
            if not math.isfinite(value):
                issues.append(
                    ValidationIssue(
                        pointer=_json_pointer(list(pointer_parts)),
                        message="non-finite floats are not representable as JSON",
                    )
                )
            return
        if type(value) is list or type(value) is dict:
            container_id = id(value)
            if container_id in active_containers:
                issues.append(
                    ValidationIssue(
                        pointer=_json_pointer(list(pointer_parts)),
                        message="recursive values are not representable as JSON",
                    )
                )
                return
            active_containers.add(container_id)
            try:
                if type(value) is list:
                    for item in value:
                        visit(item, pointer_parts, None)
                else:
                    known_keys = (
                        _known_environment_mapping_keys(schema_path)
                        if schema_path is not None
                        else frozenset()
                    )
                    for key, item in value.items():
                        if type(key) is not str:
                            issues.append(
                                ValidationIssue(
                                    pointer=_json_pointer(list(pointer_parts)),
                                    message="object keys must be strings for JSON",
                                )
                            )
                            child_pointer = pointer_parts
                            child_schema_path = None
                        elif _has_surrogate_code_point(key):
                            issues.append(
                                ValidationIssue(
                                    pointer=_json_pointer(list(pointer_parts)),
                                    message=(
                                        "object keys must not contain Unicode "
                                        "surrogate code points"
                                    ),
                                )
                            )
                            child_pointer = pointer_parts
                            child_schema_path = None
                        elif key in known_keys:
                            assert schema_path is not None
                            child_pointer = (*pointer_parts, key)
                            child_schema_path = (
                                None
                                if key == "config"
                                else (*schema_path, key)
                            )
                        else:
                            child_pointer = pointer_parts
                            child_schema_path = None
                        visit(item, child_pointer, child_schema_path)
            finally:
                active_containers.remove(container_id)
            return
        issues.append(
            ValidationIssue(
                pointer=_json_pointer(list(pointer_parts)),
                message="value is not representable as JSON",
            )
        )

    visit(document, (), ())
    return tuple(sorted(issues, key=lambda issue: (issue.pointer, issue.message)))


def _schema() -> dict[str, Any]:
    resource = files("forge").joinpath(
        "resources/schemas/environment-v1alpha1.schema.json"
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def _read_error_message(error: OSError) -> str:
    if isinstance(error, FileNotFoundError):
        reason = "file not found"
    elif isinstance(error, PermissionError):
        reason = "permission denied"
    elif isinstance(error, IsADirectoryError):
        reason = "path is a directory"
    else:
        reason = "I/O error"
    return f"cannot read configuration: {reason}"


def _yaml_error_message(error: yaml.YAMLError) -> str:
    if isinstance(error, ConstructorError):
        problem = getattr(error, "problem", None)
        if isinstance(problem, str) and problem.startswith("duplicate mapping key"):
            reason = "duplicate mapping key"
        elif problem == "unhashable mapping key":
            reason = "unhashable mapping key"
        else:
            reason = "unsupported YAML structure"
    else:
        reason = "invalid syntax"

    mark = getattr(error, "problem_mark", None)
    if mark is None:
        mark = getattr(error, "context_mark", None)
    line = getattr(mark, "line", None)
    column = getattr(mark, "column", None)
    if isinstance(line, int) and isinstance(column, int):
        return f"{reason} at line {line + 1}, column {column + 1}"
    return reason


def load_raw_document(path: Path) -> object:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        read_error = ConfigReadError(_read_error_message(exc))
    except UnicodeError:
        read_error = ConfigReadError("cannot decode UTF-8 configuration")
    else:
        read_error = None

    if read_error is not None:
        raise read_error

    try:
        return yaml.load(text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        parse_error = ConfigReadError(
            f"cannot parse YAML or JSON: {_yaml_error_message(exc)}"
        )

    raise parse_error


def validate_document(document: object) -> ValidatedEnvironment:
    compatibility_issues = _json_compatibility_issues(document)
    if compatibility_issues:
        raise ConfigValidationError(compatibility_issues)

    validator = Draft202012Validator(_schema())
    errors = sorted(validator.iter_errors(document), key=_schema_error_sort_key)
    if errors:
        issues = tuple(
            ValidationIssue(
                pointer=_issue_pointer(error),
                message=_schema_issue_message(error),
            )
            for error in errors
        )
        raise ConfigValidationError(issues)

    assert isinstance(document, dict)
    try:
        canonical_bytes = canonical_json_bytes(document)
    except CanonicalizationError:
        canonical_error = ConfigValidationError(
            (
                ValidationIssue(
                    pointer="",
                    message="value is not representable as canonical JSON",
                ),
            )
        )
    else:
        return _validated_environment(canonical_bytes)

    raise canonical_error


def load_and_validate(path: Path) -> ValidatedEnvironment:
    return validate_document(load_raw_document(path))
