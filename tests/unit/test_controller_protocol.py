from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

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
    validate_command,
)
from forge.task_state import TaskStatus


FIXTURES = Path(__file__).parents[1] / "fixtures" / "controller"
BODY = "Review the synthetic change and produce a plan."
TASK_ID = "tsk_" + "a" * 32
REQUEST_ID = "req_" + "b" * 32
LINE_TERMINATORS = ("\n", "\r", "\u2028", "\u2029")

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


def test_raw_and_typed_commands_obey_exact_size_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = GetTaskCommand(TASK_ID)
    canonical_projection = (
        b'{"operation":"getTask","protocolVersion":"forge.dev/controller/v1alpha1",'
        b'"taskId":"tsk_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'
    )
    monkeypatch.setattr(protocol, "MAX_COMMAND_BYTES", len(canonical_projection))

    assert parse_command(canonical_projection) == command
    assert validate_command(command) is command

    monkeypatch.setattr(protocol, "MAX_COMMAND_BYTES", len(canonical_projection) - 1)
    with pytest.raises(ProtocolError) as raw:
        parse_command(canonical_projection)
    assert raw.value.code is ErrorCode.INVALID_REQUEST
    assert raw.value.operation is None
    with pytest.raises(ProtocolError) as typed:
        validate_command(command)
    assert typed.value.code is ErrorCode.INVALID_REQUEST
    assert typed.value.operation is ControllerOperation.GET_TASK


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


def command_schema_validator() -> Draft202012Validator:
    resource = files("forge").joinpath(
        "resources/schemas/controller-command-v1alpha1.schema.json"
    )
    return Draft202012Validator(json.loads(resource.read_text(encoding="utf-8")))


def response_schema_validator() -> Draft202012Validator:
    resource = files("forge").joinpath(
        "resources/schemas/controller-response-v1alpha1.schema.json"
    )
    return Draft202012Validator(json.loads(resource.read_text(encoding="utf-8")))


COMMAND_PATTERN_FIELDS = (
    (("request", "sourceNamespace"), ControllerOperation.SUBMIT_REQUEST),
    (("request", "sourceEventId"), ControllerOperation.SUBMIT_REQUEST),
    (("request", "sourceEventTime"), ControllerOperation.SUBMIT_REQUEST),
    (("request", "actorRef"), ControllerOperation.SUBMIT_REQUEST),
    (("request", "channelRef"), ControllerOperation.SUBMIT_REQUEST),
    (("request", "projectRef"), ControllerOperation.SUBMIT_REQUEST),
    (("request", "repositoryRef"), ControllerOperation.SUBMIT_REQUEST),
    (("request", "security", "objectId"), ControllerOperation.SUBMIT_REQUEST),
    (("request", "security", "objectType"), ControllerOperation.SUBMIT_REQUEST),
    (("request", "security", "createdAt"), ControllerOperation.SUBMIT_REQUEST),
    (("request", "security", "taint", "0"), ControllerOperation.SUBMIT_REQUEST),
    (("request", "security", "provenanceRef"), ControllerOperation.SUBMIT_REQUEST),
    (("request", "security", "producerClass"), ControllerOperation.SUBMIT_REQUEST),
    (("request", "security", "classification"), ControllerOperation.SUBMIT_REQUEST),
    (("request", "security", "retentionHint"), ControllerOperation.SUBMIT_REQUEST),
    (("taskId",), ControllerOperation.GET_TASK),
)


def command_with_terminated_field(
    path: tuple[str, ...], terminator: str
) -> dict[str, object]:
    document = (
        fixture_document("valid-get-task.json")
        if path == ("taskId",)
        else valid_submission()
    )
    copied = json.loads(json.dumps(document))
    cursor: object = copied
    for part in path[:-1]:
        if type(cursor) is list:
            cursor = cursor[int(part)]
        else:
            assert type(cursor) is dict
            cursor = cursor[part]
    if type(cursor) is list:
        index = int(path[-1])
        value = cursor[index]
        assert type(value) is str
        cursor[index] = value + terminator
    else:
        assert type(cursor) is dict
        value = cursor[path[-1]]
        assert type(value) is str
        cursor[path[-1]] = value + terminator
    return copied


@pytest.mark.parametrize(("path", "operation"), COMMAND_PATTERN_FIELDS)
@pytest.mark.parametrize("terminator", LINE_TERMINATORS)
def test_packaged_command_schema_rejects_trailing_line_terminators(
    path: tuple[str, ...],
    operation: ControllerOperation,
    terminator: str,
) -> None:
    document = command_with_terminated_field(path, terminator)

    assert list(command_schema_validator().iter_errors(document)), (
        path,
        operation,
        repr(terminator),
    )


@pytest.mark.parametrize(("path", "operation"), COMMAND_PATTERN_FIELDS)
@pytest.mark.parametrize("terminator", LINE_TERMINATORS)
def test_parse_command_rejects_trailing_line_terminators_in_pattern_fields(
    path: tuple[str, ...],
    operation: ControllerOperation,
    terminator: str,
) -> None:
    with pytest.raises(ProtocolError) as raised:
        parse_command(encode_command(command_with_terminated_field(path, terminator)))

    assert raised.value.code is ErrorCode.INVALID_REQUEST
    assert raised.value.operation is operation


class _PermissiveValidator:
    def iter_errors(self, document: object) -> tuple[object, ...]:
        return ()


@pytest.mark.parametrize(("path", "operation"), COMMAND_PATTERN_FIELDS)
def test_parse_command_semantics_reject_trailing_newline_without_schema_help(
    monkeypatch: pytest.MonkeyPatch,
    path: tuple[str, ...],
    operation: ControllerOperation,
) -> None:
    monkeypatch.setattr(protocol, "_command_validator", _PermissiveValidator)

    with pytest.raises(ProtocolError) as raised:
        parse_command(encode_command(command_with_terminated_field(path, "\n")))

    assert raised.value.code is ErrorCode.INVALID_REQUEST
    assert raised.value.operation is operation


RESPONSE_PATTERN_FIELDS = (
    ("valid-submit-created-response.json", ("result", "requestId")),
    ("valid-submit-created-response.json", ("result", "taskId")),
    ("valid-get-task-response.json", ("result", "requestId")),
    ("valid-get-task-response.json", ("result", "taskId")),
    ("valid-get-task-response.json", ("result", "reasonCode")),
    ("valid-get-task-response.json", ("result", "createdAt")),
    ("valid-get-task-response.json", ("result", "updatedAt")),
)


def response_with_terminated_field(
    fixture: str, path: tuple[str, ...], terminator: str
) -> dict[str, object]:
    document = fixture_document(fixture)
    cursor = document
    for part in path[:-1]:
        value = cursor[part]
        assert type(value) is dict
        cursor = value
    baseline = "controller_restart" if path[-1] == "reasonCode" else cursor[path[-1]]
    assert type(baseline) is str
    cursor[path[-1]] = baseline + terminator
    return document


@pytest.mark.parametrize(("fixture", "path"), RESPONSE_PATTERN_FIELDS)
@pytest.mark.parametrize("terminator", LINE_TERMINATORS)
def test_packaged_response_schema_rejects_trailing_line_terminators(
    fixture: str,
    path: tuple[str, ...],
    terminator: str,
) -> None:
    document = response_with_terminated_field(fixture, path, terminator)

    assert list(response_schema_validator().iter_errors(document)), (
        fixture,
        path,
        repr(terminator),
    )


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


@pytest.mark.parametrize("field", ("request_id", "task_id"))
@pytest.mark.parametrize("terminator", LINE_TERMINATORS)
def test_submit_encoder_rejects_trailing_line_terminators_in_ids(
    field: str, terminator: str
) -> None:
    values = {"request_id": REQUEST_ID, "task_id": TASK_ID}
    values[field] += terminator
    result = SubmitResult(
        values["request_id"],
        values["task_id"],
        TaskStatus.QUEUED,
        Disposition.CREATED,
    )

    with pytest.raises(
        ValueError, match=r"^response does not satisfy the controller contract$"
    ):
        encode_submit_success(result)


@pytest.mark.parametrize("field", ("request_id", "task_id", "reason_code"))
@pytest.mark.parametrize("terminator", LINE_TERMINATORS)
def test_task_encoder_rejects_trailing_line_terminators_in_pattern_fields(
    field: str, terminator: str
) -> None:
    values: dict[str, str | None] = {
        "request_id": REQUEST_ID,
        "task_id": TASK_ID,
        "reason_code": "controller_restart",
    }
    value = values[field]
    assert type(value) is str
    values[field] = value + terminator
    result = TaskInspectionResult(
        request_id=values["request_id"],  # type: ignore[arg-type]
        task_id=values["task_id"],  # type: ignore[arg-type]
        mode="plan",
        status=TaskStatus.FAILED,
        reason_code=values["reason_code"],
        created_at=datetime(2026, 8, 11, 0, 0, 1, tzinfo=UTC),
        updated_at=datetime(2026, 8, 11, 0, 0, 1, tzinfo=UTC),
    )

    with pytest.raises(
        ValueError, match=r"^response does not satisfy the controller contract$"
    ):
        encode_task_success(result)


def test_task_encoder_rejects_trailing_newline_in_formatted_timestamps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        protocol,
        "format_utc_timestamp",
        lambda value: "2026-08-11T00:00:01Z\n",
    )
    result = TaskInspectionResult(
        request_id=REQUEST_ID,
        task_id=TASK_ID,
        mode="plan",
        status=TaskStatus.QUEUED,
        reason_code=None,
        created_at=datetime(2026, 8, 11, 0, 0, 1, tzinfo=UTC),
        updated_at=datetime(2026, 8, 11, 0, 0, 1, tzinfo=UTC),
    )

    with pytest.raises(
        ValueError, match=r"^response does not satisfy the controller contract$"
    ):
        encode_task_success(result)


@pytest.mark.parametrize("encoder", ("submit-request-id", "submit-task-id", "task-reason"))
def test_response_semantics_reject_trailing_newline_without_schema_help(
    monkeypatch: pytest.MonkeyPatch, encoder: str
) -> None:
    monkeypatch.setattr(protocol, "_response_validator", _PermissiveValidator)

    if encoder == "submit-request-id":
        call = lambda: encode_submit_success(
            SubmitResult(
                REQUEST_ID + "\n",
                TASK_ID,
                TaskStatus.QUEUED,
                Disposition.CREATED,
            )
        )
    elif encoder == "submit-task-id":
        call = lambda: encode_submit_success(
            SubmitResult(
                REQUEST_ID,
                TASK_ID + "\n",
                TaskStatus.QUEUED,
                Disposition.CREATED,
            )
        )
    else:
        call = lambda: encode_task_success(
            TaskInspectionResult(
                request_id=REQUEST_ID,
                task_id=TASK_ID,
                mode="plan",
                status=TaskStatus.FAILED,
                reason_code="controller_restart\n",
                created_at=datetime(2026, 8, 11, 0, 0, 1, tzinfo=UTC),
                updated_at=datetime(2026, 8, 11, 0, 0, 1, tzinfo=UTC),
            )
        )

    with pytest.raises(
        ValueError, match=r"^response does not satisfy the controller contract$"
    ):
        call()


def test_response_timestamp_semantics_reject_trailing_newline_without_schema_help(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(protocol, "_response_validator", _PermissiveValidator)
    monkeypatch.setattr(
        protocol,
        "format_utc_timestamp",
        lambda value: "2026-08-11T00:00:01Z\n",
    )

    with pytest.raises(
        ValueError, match=r"^response does not satisfy the controller contract$"
    ):
        encode_task_success(
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
