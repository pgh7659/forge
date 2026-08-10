from __future__ import annotations

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

from forge.canonical import sha256_hex


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


@dataclass(frozen=True, slots=True)
class ValidatedEnvironment:
    name: str
    api_version: str
    digest: str
    document: dict[str, Any]


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
    parts = list(error.absolute_path)
    if error.validator == "additionalProperties" and isinstance(
        error.instance, dict
    ):
        known = set(error.schema.get("properties", {}))
        unexpected = sorted(set(error.instance) - known)
        if len(unexpected) == 1:
            parts.append(unexpected[0])
    return _json_pointer(parts)


def _json_compatibility_issues(document: object) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    active_containers: set[int] = set()

    def visit(value: object, parts: list[object]) -> None:
        if value is None or type(value) is bool:
            return
        if type(value) is str:
            if _has_surrogate_code_point(value):
                issues.append(
                    ValidationIssue(
                        pointer=_json_pointer(parts),
                        message="strings must not contain Unicode surrogate code points",
                    )
                )
            return
        if type(value) is int:
            if not -9007199254740991 <= value <= 9007199254740991:
                issues.append(
                    ValidationIssue(
                        pointer=_json_pointer(parts),
                        message="integers must be within the I-JSON interoperable range",
                    )
                )
            return
        if type(value) is float:
            if not math.isfinite(value):
                issues.append(
                    ValidationIssue(
                        pointer=_json_pointer(parts),
                        message="non-finite floats are not representable as JSON",
                    )
                )
            return
        if isinstance(value, (list, dict)):
            container_id = id(value)
            if container_id in active_containers:
                issues.append(
                    ValidationIssue(
                        pointer=_json_pointer(parts),
                        message="recursive values are not representable as JSON",
                    )
                )
                return
            active_containers.add(container_id)
            try:
                if isinstance(value, list):
                    for index, item in enumerate(value):
                        visit(item, [*parts, index])
                else:
                    for key, item in value.items():
                        if not isinstance(key, str):
                            issues.append(
                                ValidationIssue(
                                    pointer=_json_pointer([*parts, key]),
                                    message="object keys must be strings for JSON",
                                )
                            )
                        elif _has_surrogate_code_point(key):
                            issues.append(
                                ValidationIssue(
                                    pointer=_json_pointer([*parts, key]),
                                    message=(
                                        "object keys must not contain Unicode "
                                        "surrogate code points"
                                    ),
                                )
                            )
                        visit(item, [*parts, key])
            finally:
                active_containers.remove(container_id)
            return
        issues.append(
            ValidationIssue(
                pointer=_json_pointer(parts),
                message="value is not representable as JSON",
            )
        )

    visit(document, [])
    return tuple(sorted(issues, key=lambda issue: (issue.pointer, issue.message)))


def _schema() -> dict[str, Any]:
    resource = files("forge").joinpath(
        "resources/schemas/environment-v1alpha1.schema.json"
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def load_raw_document(path: Path) -> object:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigReadError(f"cannot read {path}: {exc.strerror}") from exc
    except UnicodeError as exc:
        raise ConfigReadError(f"cannot decode UTF-8 from {path}: {exc}") from exc

    try:
        return yaml.load(text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise ConfigReadError(f"cannot parse YAML or JSON from {path}: {exc}") from exc


def validate_document(document: object) -> ValidatedEnvironment:
    compatibility_issues = _json_compatibility_issues(document)
    if compatibility_issues:
        raise ConfigValidationError(compatibility_issues)

    validator = Draft202012Validator(_schema())
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        ),
    )
    if errors:
        issues = tuple(
            ValidationIssue(
                pointer=_issue_pointer(error),
                message=error.message,
            )
            for error in errors
        )
        raise ConfigValidationError(issues)

    assert isinstance(document, dict)
    return ValidatedEnvironment(
        name=document["metadata"]["name"],
        api_version=document["apiVersion"],
        digest=sha256_hex(document),
        document=document,
    )


def load_and_validate(path: Path) -> ValidatedEnvironment:
    return validate_document(load_raw_document(path))
