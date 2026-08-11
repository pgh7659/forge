from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from forge.canonical import canonical_json_bytes


_KEY_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}")
_NONCE_BYTES = 12


class EncryptionError(ValueError):
    def __init__(self) -> None:
        super().__init__("encryption operation failed")


@dataclass(frozen=True, slots=True)
class KeyHandle:
    key_id: str = field(repr=False)
    key_bytes: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.key_id) is not str
            or _KEY_ID_PATTERN.fullmatch(self.key_id) is None
            or type(self.key_bytes) is not bytes
            or len(self.key_bytes) != 32
        ):
            raise EncryptionError()


@dataclass(frozen=True, slots=True)
class EncryptedValue:
    nonce: bytes = field(repr=False)
    ciphertext: bytes = field(repr=False)


class RequestCipher(Protocol):
    algorithm: str

    def encrypt(
        self, plaintext: bytes, associated_data: bytes, key: KeyHandle
    ) -> EncryptedValue:
        raise NotImplementedError

    def decrypt(
        self, value: EncryptedValue, associated_data: bytes, key: KeyHandle
    ) -> bytes:
        raise NotImplementedError


def request_body_aad(
    protocol_version: str,
    request_id: str,
    source_namespace: str,
    source_event_id: str,
    project_ref: str,
    repository_ref: str,
    body_digest: str,
    security_digest: str,
    algorithm: str,
    key_id: str,
) -> bytes:
    return canonical_json_bytes(
        {
            "domain": "forge.request-body/v1",
            "protocolVersion": protocol_version,
            "requestId": request_id,
            "idempotencyKey": {
                "sourceNamespace": source_namespace,
                "sourceEventId": source_event_id,
            },
            "projectRef": project_ref,
            "repositoryRef": repository_ref,
            "bodyDigest": body_digest,
            "securityDigest": security_digest,
            "algorithm": algorithm,
            "keyId": key_id,
        }
    )


def state_key_verifier_aad(algorithm: str, key_id: str) -> bytes:
    return canonical_json_bytes(
        {
            "domain": "forge.state-key-verifier/v1",
            "algorithm": algorithm,
            "keyId": key_id,
        }
    )


class Aes256GcmRequestCipher:
    algorithm = "AES-256-GCM"

    def __init__(self, nonce_source: Callable[[int], bytes] = secrets.token_bytes) -> None:
        self._nonce_source = nonce_source

    def encrypt(
        self, plaintext: bytes, associated_data: bytes, key: KeyHandle
    ) -> EncryptedValue:
        if (
            type(plaintext) is not bytes
            or type(associated_data) is not bytes
            or type(key) is not KeyHandle
        ):
            raise EncryptionError()
        try:
            nonce = self._nonce_source(_NONCE_BYTES)
            if type(nonce) is not bytes or len(nonce) != _NONCE_BYTES:
                raise TypeError("invalid nonce source output")
            ciphertext = AESGCM(key.key_bytes).encrypt(nonce, plaintext, associated_data)
        except (InvalidTag, TypeError, ValueError) as exc:
            raise EncryptionError() from exc
        return EncryptedValue(nonce=nonce, ciphertext=ciphertext)

    def decrypt(
        self, value: EncryptedValue, associated_data: bytes, key: KeyHandle
    ) -> bytes:
        if (
            type(value) is not EncryptedValue
            or type(associated_data) is not bytes
            or type(key) is not KeyHandle
            or type(value.nonce) is not bytes
            or len(value.nonce) != _NONCE_BYTES
            or type(value.ciphertext) is not bytes
        ):
            raise EncryptionError()
        try:
            return AESGCM(key.key_bytes).decrypt(
                value.nonce, value.ciphertext, associated_data
            )
        except (InvalidTag, TypeError, ValueError) as exc:
            raise EncryptionError() from exc
