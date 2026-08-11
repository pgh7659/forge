from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

import forge.controller_protocol as protocol
from forge.controller_protocol import (
    CONTROLLER_PROTOCOL_VERSION,
    MAX_COMMAND_BYTES,
    ControllerOperation,
    Disposition,
    EngineeringRequest,
    ErrorCode,
    GetTaskCommand,
    ProtocolError,
    SecurityEnvelope,
    SubmitRequestCommand,
    SubmitResult,
    TaskInspectionResult,
    body_digest,
    encode_error,
    encode_submit_success,
    encode_task_success,
    format_utc_timestamp,
    parse_command,
    request_digest,
    security_digest,
)
from forge.task_state import TaskStatus


FIXTURES = Path(__file__).parents[1] / "fixtures" / "controller"
BODY = "Review the synthetic change and produce a plan."
TASK_ID = "tsk_" + "a" * 32
REQUEST_ID = "req_" + "b" * 32

INVALID_BYTES = (
    b"",
    b"\xff",
    b'{"protocolVersion":"forge.dev/controller/v1alpha1","operation":"getTask","operation":"submitRequest"}',
    b'{"protocolVersion":"forge.dev/controller/v1alpha1","operation":"getTask","taskId":"tsk_\\ud800"}',
    b'{"protocolVersion":"forge.dev/controller/v1alpha1","operation":"getTask","taskId":"tsk_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","n":NaN}',
    b'{"protocolVersion":"forge.dev/controller/v1alpha1","operation":"getTask","taskId":"tsk_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","n":9007199254740992}',
)


def fixture_document(name: str) -> dict[str, object]:
    value = json.loads((FIXTURES / name).read_bytes())
    assert isinstance(value, dict)
    return value


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def valid_submission() -> dict[str, object]:
    return fixture_document("valid-submit.json")


def encode_command(document: dict[str, object]) -> bytes:
    return json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode()


def assert_invalid(payload: bytes, code: ErrorCode = ErrorCode.INVALID_REQUEST) -> None:
    with pytest.raises(ProtocolError) as raised:
        parse_command(payload)
    assert raised.value.code is code
    assert len(str(raised.value)) <= 256
    decoded = payload.decode("utf-8", errors="ignore")
    if decoded:
        assert decoded not in str(raised.value)


def test_parses_immutable_submit_command_without_exposing_body() -> None:
    command = parse_command(fixture_bytes("valid-submit.json"))

    assert isinstance(command, SubmitRequestCommand)
    assert isinstance(command.request, EngineeringRequest)
    assert isinstance(command.request.security, SecurityEnvelope)
    assert command.request.mode == "plan"
    assert command.request.security.taint == ("external-input", "user-supplied")
    assert BODY not in repr(command)
    with pytest.raises(FrozenInstanceError):
        command.request.mode = "run"  # type: ignore[misc]


def test_parses_immutable_get_task_command() -> None:
    command = parse_command(fixture_bytes("valid-get-task.json"))

    assert isinstance(command, GetTaskCommand)
    assert command.task_id == TASK_ID
    with pytest.raises(FrozenInstanceError):
        command.task_id = "tsk_" + "c" * 32  # type: ignore[misc]


@pytest.mark.parametrize("payload", INVALID_BYTES)
def test_invalid_json_bytes_have_owned_invalid_request_errors(payload: bytes) -> None:
    assert_invalid(payload)


def test_command_larger_than_bound_is_rejected_before_json_load(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_loads(*args: object, **kwargs: object) -> object:
        raise AssertionError("json.loads must not be called")

    monkeypatch.setattr(protocol.json, "loads", fail_loads)

    assert MAX_COMMAND_BYTES == 262_144
    assert_invalid(b" " * (MAX_COMMAND_BYTES + 1))


def test_recognized_operation_is_preserved_for_a_post_parse_contract_failure() -> None:
    payload = b'{"protocolVersion":"forge.dev/controller/v1alpha1","operation":"getTask","taskId":"tsk_\\ud800"}'
    with pytest.raises(ProtocolError) as raised:
        parse_command(payload)
    assert raised.value.code is ErrorCode.INVALID_REQUEST
    assert raised.value.operation is ControllerOperation.GET_TASK


def mutate(document: dict[str, object], path: tuple[str, ...], value: object) -> dict[str, object]:
    copied = json.loads(json.dumps(document))
    cursor = copied
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = value
    return copied


def remove(document: dict[str, object], path: tuple[str, ...]) -> dict[str, object]:
    copied = json.loads(json.dumps(document))
    cursor = copied
    for part in path[:-1]:
        cursor = cursor[part]
    del cursor[path[-1]]
    return copied


@pytest.mark.parametrize(
    ("path", "value", "code"),
    [
        (("protocolVersion",), "forge.dev/controller/v2", ErrorCode.UNSUPPORTED_PROTOCOL),
        (("protocolVersion",), None, ErrorCode.INVALID_REQUEST),
        (("extra",), "unexpected", ErrorCode.INVALID_REQUEST),
        (("request", "extra"), "unexpected", ErrorCode.INVALID_REQUEST),
        (("request", "security", "extra"), "unexpected", ErrorCode.INVALID_REQUEST),
        (("request", "security"), None, ErrorCode.INVALID_REQUEST),
        (("request", "security", "contractVersion"), "forge.dev/security/v2", ErrorCode.INVALID_REQUEST),
        (("request", "security", "trust"), "approved", ErrorCode.INVALID_REQUEST),
        (("request", "mode"), "run", ErrorCode.INVALID_REQUEST),
        (("request", "body"), "", ErrorCode.INVALID_REQUEST),
        (("request", "body"), "a" * 65_537, ErrorCode.INVALID_REQUEST),
        (("request", "actorRef"), " actor", ErrorCode.INVALID_REQUEST),
        (("request", "sourceNamespace"), "Example", ErrorCode.INVALID_REQUEST),
        (("request", "security", "taint"), ["external-input", "external-input"], ErrorCode.INVALID_REQUEST),
        (("request", "security", "taint"), ["user-supplied", "external-input"], ErrorCode.INVALID_REQUEST),
        (("request", "sourceEventTime"), "2026-99-11T00:00:00Z", ErrorCode.INVALID_REQUEST),
        (("request", "sourceEventTime"), "2026-08-11T00:00:00+00:00", ErrorCode.INVALID_REQUEST),
        (("request", "sourceEventTime"), "2026-08-11T00:00:00.1234567Z", ErrorCode.INVALID_REQUEST),
    ],
)
def test_submit_contract_failures_are_rejected(
    path: tuple[str, ...], value: object, code: ErrorCode
) -> None:
    assert_invalid(encode_command(mutate(valid_submission(), path, value)), code)


@pytest.mark.parametrize("path", (("protocolVersion",), ("request", "security")))
def test_required_submit_fields_cannot_be_omitted(path: tuple[str, ...]) -> None:
    assert_invalid(encode_command(remove(valid_submission(), path)))


@pytest.mark.parametrize("operation", ("claimNextEligible", "transitionTask", "reconcileRunning"))
def test_internal_operations_cannot_be_received_at_ingress(operation: str) -> None:
    assert_invalid(
        json.dumps(
            {"protocolVersion": CONTROLLER_PROTOCOL_VERSION, "operation": operation}
        ).encode()
    )


def test_request_identity_is_order_independent_and_excludes_operation() -> None:
    command = parse_command(fixture_bytes("valid-submit.json"))
    valid = valid_submission()
    reordered = parse_command(
        encode_command(
            {
                "operation": "submitRequest",
                "request": valid["request"],
                "protocolVersion": "forge.dev/controller/v1alpha1",
            }
        )
    )
    assert isinstance(command, SubmitRequestCommand)
    assert isinstance(reordered, SubmitRequestCommand)
    assert request_digest(command) == request_digest(reordered)
    identity = protocol.request_identity_document(command)
    assert identity == {
        "protocolVersion": "forge.dev/controller/v1alpha1",
        "request": fixture_document("valid-submit.json")["request"],
    }
    assert "operation" not in identity


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("request", "sourceNamespace"), "alternate-source"),
        (("request", "sourceEventId"), "event:0124"),
        (("request", "sourceEventTime"), "2026-08-11T00:00:01Z"),
        (("request", "actorRef"), "actor:other"),
        (("request", "channelRef"), "channel:other"),
        (("request", "projectRef"), "project:other"),
        (("request", "repositoryRef"), "repository:other"),
        (("request", "body"), BODY + "!"),
        (("request", "security", "objectId"), "object:other"),
        (("request", "security", "objectType"), "other-request"),
        (("request", "security", "createdAt"), "2026-08-11T00:00:01Z"),
        (("request", "security", "trust"), "trusted"),
        (("request", "security", "taint"), ["external-input", "namespaced:valid"]),
        (("request", "security", "provenanceRef"), "provenance:other"),
        (("request", "security", "producerClass"), "other-adapter"),
        (("request", "security", "classification"), "internal"),
        (("request", "security", "retentionHint"), "short"),
    ],
)
def test_request_digest_changes_for_each_identity_mutation(
    path: tuple[str, ...], value: object
) -> None:
    baseline = parse_command(fixture_bytes("valid-submit.json"))
    changed = parse_command(encode_command(mutate(valid_submission(), path, value)))
    assert isinstance(baseline, SubmitRequestCommand)
    assert isinstance(changed, SubmitRequestCommand)
    assert request_digest(changed) != request_digest(baseline)


def test_body_digest_uses_exact_utf8_bytes_without_unicode_normalization() -> None:
    composed = "\u00e9"
    decomposed = "e\u0301"
    assert body_digest(composed) == "sha256:" + hashlib.sha256(b"\xc3\xa9").hexdigest()
    assert body_digest(decomposed) == "sha256:" + hashlib.sha256(b"e\xcc\x81").hexdigest()
    assert body_digest(composed) != body_digest(decomposed)


def test_security_digest_covers_complete_preserved_envelope() -> None:
    command = parse_command(
        encode_command(
            mutate(
                valid_submission(),
                ("request", "security", "taint"),
                ["external-input", "namespaced:valid", "user-supplied"],
            )
        )
    )
    baseline = parse_command(fixture_bytes("valid-submit.json"))
    assert isinstance(command, SubmitRequestCommand)
    assert isinstance(baseline, SubmitRequestCommand)
    assert command.request.security.taint == (
        "external-input",
        "namespaced:valid",
        "user-supplied",
    )
    assert security_digest(command.request.security) != security_digest(
        baseline.request.security
    )


def test_format_utc_timestamp_has_exact_utc_format_and_rejects_other_datetimes() -> None:
    assert format_utc_timestamp(datetime(2026, 8, 11, 0, 0, 1, tzinfo=UTC)) == "2026-08-11T00:00:01Z"
    assert format_utc_timestamp(datetime(2026, 8, 11, 0, 0, 1, 123456, tzinfo=UTC)) == "2026-08-11T00:00:01.123456Z"
    with pytest.raises(ValueError) as naive:
        format_utc_timestamp(datetime(2026, 8, 11, 0, 0, 1))
    with pytest.raises(ValueError) as non_utc:
        format_utc_timestamp(datetime(2026, 8, 11, 9, 0, 1, tzinfo=timezone(timedelta(hours=9))))
    assert len(str(naive.value)) <= 256
    assert len(str(non_utc.value)) <= 256


def test_encoders_match_fixtures_and_exclude_sensitive_data() -> None:
    created = encode_submit_success(
        SubmitResult(REQUEST_ID, TASK_ID, TaskStatus.QUEUED, Disposition.CREATED)
    )
    replayed = encode_submit_success(
        SubmitResult(REQUEST_ID, TASK_ID, TaskStatus.QUEUED, Disposition.REPLAYED)
    )
    task = encode_task_success(
        TaskInspectionResult(
            request_id=REQUEST_ID,
            task_id=TASK_ID,
            mode="plan",
            status=TaskStatus.QUEUED,
            reason_code=None,
            created_at=datetime(2026, 8, 11, 0, 0, 1, tzinfo=UTC),
            updated_at=datetime(2026, 8, 11, 0, 0, 1, tzinfo=UTC),
        )
    )
    error = encode_error(None, ErrorCode.INVALID_REQUEST)

    for encoded, fixture in (
        (created, "valid-submit-created-response.json"),
        (replayed, "valid-submit-replayed-response.json"),
        (task, "valid-get-task-response.json"),
        (error, "valid-error-response.json"),
    ):
        document = json.loads(encoded)
        assert document == fixture_document(fixture)
        serialized = json.dumps(document)
        for sensitive_key in (
            "body",
            "projectRef",
            "repositoryRef",
            "security",
            "ciphertext",
            "nonce",
            "keyId",
            "details",
        ):
            assert sensitive_key not in serialized
