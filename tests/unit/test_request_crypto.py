from __future__ import annotations

import logging

import pytest

from forge.request_crypto import (
    Aes256GcmRequestCipher,
    EncryptedValue,
    EncryptionError,
    KeyHandle,
    request_body_aad,
    state_key_verifier_aad,
)


KEY = KeyHandle("key:synthetic", b"K" * 32)
PLAINTEXT = b"sensitive request body"
ASSOCIATED_DATA = b"sensitive authenticated metadata"


def assert_encryption_failure(call: object, *sensitive_values: bytes | str) -> None:
    assert callable(call)
    with pytest.raises(EncryptionError) as raised:
        call()

    message = str(raised.value)
    assert message == "encryption operation failed"
    for value in sensitive_values:
        rendered = value.decode("utf-8", errors="ignore") if type(value) is bytes else value
        assert rendered not in message
    assert "InvalidTag" not in message


@pytest.mark.parametrize(
    ("key_id", "key_bytes"),
    [
        ("key:synthetic", b"K" * 31),
        ("key:synthetic", b"K" * 33),
        ("key:synthetic", bytearray(b"K" * 32)),
        ("", b"K" * 32),
        ("not valid", b"K" * 32),
        (None, b"K" * 32),
    ],
)
def test_key_handle_rejects_invalid_public_key_records(
    key_id: object, key_bytes: object
) -> None:
    assert_encryption_failure(
        lambda: KeyHandle(key_id, key_bytes),  # type: ignore[arg-type]
        "key:synthetic",
        b"K" * 32,
    )


def test_key_and_encrypted_value_representations_redact_sensitive_values() -> None:
    key = KeyHandle("key:synthetic", b"K" * 32)
    value = EncryptedValue(nonce=b"N" * 12, ciphertext=b"C" * 32)

    assert "key:synthetic" not in repr(key)
    assert "KKKK" not in repr(key)
    assert "NNNN" not in repr(value)
    assert "CCCC" not in repr(value)


def test_request_body_aad_is_the_exact_canonical_binding_document() -> None:
    aad = request_body_aad(
        "forge.dev/controller/v1alpha1",
        "req_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "example-source",
        "event:0123",
        "project:example",
        "repository:example",
        "sha256:" + "b" * 64,
        "sha256:" + "c" * 64,
        "AES-256-GCM",
        "key:synthetic",
    )

    assert aad == (
        b'{"algorithm":"AES-256-GCM","bodyDigest":"sha256:'
        + b"b" * 64
        + b'","domain":"forge.request-body/v1","idempotencyKey":'
        + b'{"sourceEventId":"event:0123","sourceNamespace":"example-source"}'
        + b',"keyId":"key:synthetic","projectRef":"project:example",'
        + b'"protocolVersion":"forge.dev/controller/v1alpha1",'
        + b'"repositoryRef":"repository:example",'
        + b'"requestId":"req_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
        + b'"securityDigest":"sha256:'
        + b"c" * 64
        + b'"}'
    )


def test_state_key_verifier_aad_is_the_exact_canonical_binding_document() -> None:
    assert state_key_verifier_aad("AES-256-GCM", "key:synthetic") == (
        b'{"algorithm":"AES-256-GCM",'
        b'"domain":"forge.state-key-verifier/v1",'
        b'"keyId":"key:synthetic"}'
    )


def test_encrypt_decrypt_round_trip_uses_a_96_bit_nonce_and_no_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    nonce_sizes: list[int] = []

    def nonce_source(size: int) -> bytes:
        nonce_sizes.append(size)
        return b"N" * size

    cipher = Aes256GcmRequestCipher(nonce_source)
    with caplog.at_level(logging.DEBUG):
        value = cipher.encrypt(PLAINTEXT, ASSOCIATED_DATA, KEY)
        result = cipher.decrypt(value, ASSOCIATED_DATA, KEY)

    assert nonce_sizes == [12]
    assert value.nonce == b"N" * 12
    assert len(value.ciphertext) > len(PLAINTEXT)
    assert result == PLAINTEXT
    assert caplog.records == []


def test_repeated_encryption_uses_distinct_nonces() -> None:
    cipher = Aes256GcmRequestCipher()

    first = cipher.encrypt(PLAINTEXT, ASSOCIATED_DATA, KEY)
    second = cipher.encrypt(PLAINTEXT, ASSOCIATED_DATA, KEY)

    assert len(first.nonce) == 12
    assert len(second.nonce) == 12
    assert first.nonce != second.nonce


@pytest.mark.parametrize(
    "operation",
    [
        lambda cipher, value: cipher.decrypt(value, ASSOCIATED_DATA, KeyHandle("key:other", b"W" * 32)),
        lambda cipher, value: cipher.decrypt(value, b"modified associated data", KEY),
        lambda cipher, value: cipher.decrypt(
            EncryptedValue(b"M" + value.nonce[1:], value.ciphertext), ASSOCIATED_DATA, KEY
        ),
        lambda cipher, value: cipher.decrypt(
            EncryptedValue(value.nonce, value.ciphertext[:-1]), ASSOCIATED_DATA, KEY
        ),
        lambda cipher, value: cipher.decrypt(
            EncryptedValue(value.nonce, value.ciphertext[:-1] + bytes([value.ciphertext[-1] ^ 1])),
            ASSOCIATED_DATA,
            KEY,
        ),
    ],
)
def test_decrypt_rejects_tampering_with_owned_redacted_errors_and_no_logs(
    caplog: pytest.LogCaptureFixture,
    operation: object,
) -> None:
    assert callable(operation)
    cipher = Aes256GcmRequestCipher(lambda size: b"N" * size)
    value = cipher.encrypt(PLAINTEXT, ASSOCIATED_DATA, KEY)

    with caplog.at_level(logging.DEBUG):
        assert_encryption_failure(
            lambda: operation(cipher, value),  # type: ignore[operator]
            PLAINTEXT,
            ASSOCIATED_DATA,
            KEY.key_id,
            KEY.key_bytes,
            value.nonce,
            value.ciphertext,
        )

    assert caplog.records == []


@pytest.mark.parametrize(
    "plaintext,associated_data,nonce_source",
    [
        (bytearray(PLAINTEXT), ASSOCIATED_DATA, lambda size: b"N" * size),
        (PLAINTEXT, bytearray(ASSOCIATED_DATA), lambda size: b"N" * size),
        (PLAINTEXT, ASSOCIATED_DATA, lambda size: b"N" * (size - 1)),
        (PLAINTEXT, ASSOCIATED_DATA, lambda size: bytearray(b"N" * size)),
    ],
)
def test_encrypt_rejects_invalid_inputs_with_owned_redacted_errors(
    plaintext: object,
    associated_data: object,
    nonce_source: object,
) -> None:
    assert callable(nonce_source)
    cipher = Aes256GcmRequestCipher(nonce_source)  # type: ignore[arg-type]

    assert_encryption_failure(
        lambda: cipher.encrypt(plaintext, associated_data, KEY),  # type: ignore[arg-type]
        PLAINTEXT,
        ASSOCIATED_DATA,
        KEY.key_id,
        KEY.key_bytes,
    )
