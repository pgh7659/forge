from __future__ import annotations

import hashlib
import math

import rfc8785


class CanonicalizationError(ValueError):
    """A value cannot be represented by the Forge RFC 8785 profile."""


_JSON_COMPATIBILITY_ERROR = "value is not JSON/I-JSON compatible"


def _validate_json_compatible(value: object) -> None:
    active_containers: set[int] = set()

    def visit(item: object) -> None:
        item_type = type(item)
        if item is None or item_type is bool:
            return
        if item_type is str:
            if any(0xD800 <= ord(character) <= 0xDFFF for character in item):
                raise CanonicalizationError(_JSON_COMPATIBILITY_ERROR)
            return
        if item_type is int:
            if not -9007199254740991 <= item <= 9007199254740991:
                raise CanonicalizationError(_JSON_COMPATIBILITY_ERROR)
            return
        if item_type is float:
            if not math.isfinite(item):
                raise CanonicalizationError(_JSON_COMPATIBILITY_ERROR)
            return
        if item_type is not list and item_type is not dict:
            raise CanonicalizationError(_JSON_COMPATIBILITY_ERROR)

        container_id = id(item)
        if container_id in active_containers:
            raise CanonicalizationError(_JSON_COMPATIBILITY_ERROR)
        active_containers.add(container_id)
        try:
            if item_type is list:
                for child in item:
                    visit(child)
            else:
                for key, child in item.items():
                    if type(key) is not str:
                        raise CanonicalizationError(_JSON_COMPATIBILITY_ERROR)
                    visit(key)
                    visit(child)
        finally:
            active_containers.remove(container_id)

    visit(value)


def canonical_json_bytes(value: object) -> bytes:
    _validate_json_compatible(value)
    try:
        return rfc8785.dumps(value)
    except (rfc8785.CanonicalizationError, RecursionError, UnicodeError) as exc:
        raise CanonicalizationError(_JSON_COMPATIBILITY_ERROR) from exc


def sha256_hex(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_identifier(value: object) -> str:
    return f"sha256:{sha256_hex(value)}"
