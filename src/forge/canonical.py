from __future__ import annotations

import hashlib

import rfc8785


class CanonicalizationError(ValueError):
    """A value cannot be represented by the Forge RFC 8785 profile."""


def canonical_json_bytes(value: object) -> bytes:
    try:
        return rfc8785.dumps(value)
    except rfc8785.CanonicalizationError as exc:
        raise CanonicalizationError("value is not RFC 8785 canonicalizable") from exc


def sha256_hex(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_identifier(value: object) -> str:
    return f"sha256:{sha256_hex(value)}"
