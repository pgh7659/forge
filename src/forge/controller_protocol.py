from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from importlib.resources import files
from types import MappingProxyType

from jsonschema import Draft202012Validator, SchemaError

from forge.canonical import CanonicalizationError, canonical_json_bytes, sha256_identifier
from forge.task_state import TaskStatus


CONTROLLER_PROTOCOL_VERSION = "forge.dev/controller/v1alpha1"
SECURITY_CONTRACT_VERSION = "forge.dev/security/v1alpha1"
MAX_COMMAND_BYTES = 262_144

_REFERENCE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}")
_TOKEN_PATTERN = re.compile(r"[a-z][a-z0-9._:-]{0,127}")
_REQUEST_ID_PATTERN = re.compile(r"req_[0-9a-f]{32}")
_TASK_ID_PATTERN = re.compile(r"tsk_[0-9a-f]{32}")
_TIMESTAMP_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?Z"
)


class ControllerOperation(StrEnum):
    SUBMIT_REQUEST = "submitRequest"
    GET_TASK = "getTask"


class Disposition(StrEnum):
    CREATED = "created"
    REPLAYED = "replayed"


class ErrorCode(StrEnum):
    UNSUPPORTED_PROTOCOL = "unsupported_protocol"
    INVALID_REQUEST = "invalid_request"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    TASK_NOT_FOUND = "task_not_found"
    INVALID_TRANSITION = "invalid_transition"
    CONTROLLER_ALREADY_RUNNING = "controller_already_running"
    STATE_ERROR = "state_error"
    ENCRYPTION_ERROR = "encryption_error"


PUBLIC_ERROR_MESSAGES = MappingProxyType(
    {
        ErrorCode.UNSUPPORTED_PROTOCOL: "protocol version is not supported",
        ErrorCode.INVALID_REQUEST: "request does not satisfy the controller contract",
        ErrorCode.IDEMPOTENCY_CONFLICT: "request identity conflicts with durable state",
        ErrorCode.TASK_NOT_FOUND: "task was not found",
        ErrorCode.INVALID_TRANSITION: "task transition is not allowed",
        ErrorCode.CONTROLLER_ALREADY_RUNNING: "controller already owns this state",
        ErrorCode.STATE_ERROR: "state operation failed",
        ErrorCode.ENCRYPTION_ERROR: "encryption operation failed",
    }
)


@dataclass(frozen=True, slots=True, repr=False)
class SecurityEnvelope:
    contract_version: str
    object_id: str
    object_type: str
    created_at: str
    trust: str
    taint: tuple[str, ...]
    provenance_ref: str
    producer_class: str
    classification: str
    retention_hint: str


@dataclass(frozen=True, slots=True)
class EngineeringRequest:
    source_namespace: str
    source_event_id: str
    source_event_time: str
    actor_ref: str
    channel_ref: str
    project_ref: str
    repository_ref: str
    mode: str
    body: str = field(repr=False)
    security: SecurityEnvelope = field(repr=False)


@dataclass(frozen=True, slots=True)
class SubmitRequestCommand:
    request: EngineeringRequest


@dataclass(frozen=True, slots=True)
class GetTaskCommand:
    task_id: str


@dataclass(frozen=True, slots=True)
class SubmitResult:
    request_id: str
    task_id: str
    status: TaskStatus
    disposition: Disposition


@dataclass(frozen=True, slots=True)
class TaskInspectionResult:
    request_id: str
    task_id: str
    mode: str
    status: TaskStatus
    reason_code: str | None
    created_at: datetime
    updated_at: datetime


class ProtocolError(ValueError):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        operation: ControllerOperation | None = None,
    ) -> None:
        self.code = code
        self.operation = operation
        super().__init__(message)


class _DuplicateKeyError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise _DuplicateKeyError
        document[key] = value
    return document


def _reject_json_constant(value: str) -> object:
    raise ValueError("invalid JSON constant")


def _schema(name: str) -> dict[str, object]:
    resource = files("forge").joinpath(f"resources/schemas/{name}")
    try:
        document = json.loads(resource.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(document)
    except (OSError, UnicodeError, json.JSONDecodeError, SchemaError) as exc:
        # Packaged schemas are trusted build artifacts; callers still receive an owned error.
        raise RuntimeError("controller schema is unavailable") from exc
    assert isinstance(document, dict)
    return document


def _command_validator() -> Draft202012Validator:
    return Draft202012Validator(_schema("controller-command-v1alpha1.schema.json"))


def _response_validator() -> Draft202012Validator:
    return Draft202012Validator(_schema("controller-response-v1alpha1.schema.json"))


def _invalid(operation: ControllerOperation | None = None) -> ProtocolError:
    return ProtocolError(
        ErrorCode.INVALID_REQUEST,
        PUBLIC_ERROR_MESSAGES[ErrorCode.INVALID_REQUEST],
        operation,
    )


def _operation(document: object) -> ControllerOperation | None:
    if type(document) is not dict:
        return None
    value = document.get("operation")
    try:
        return ControllerOperation(value) if type(value) is str else None
    except ValueError:
        return None


def _require_fullmatch(value: object, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise ValueError("value does not satisfy the controller contract")
    return value


def _validate_timestamp(value: object) -> None:
    rendered = _require_fullmatch(value, _TIMESTAMP_PATTERN)
    try:
        parsed = datetime.fromisoformat(rendered[:-1] + "+00:00")
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("invalid UTC timestamp")


def _validate_command_semantics(document: dict[str, object], operation: ControllerOperation) -> None:
    if operation is ControllerOperation.GET_TASK:
        _require_fullmatch(document.get("taskId"), _TASK_ID_PATTERN)
        return
    request = document.get("request")
    if type(request) is not dict:
        raise ValueError("request does not satisfy the controller contract")
    security = request.get("security")
    if type(security) is not dict:
        raise ValueError("request does not satisfy the controller contract")

    for field in ("sourceEventId", "actorRef", "channelRef", "projectRef", "repositoryRef"):
        _require_fullmatch(request.get(field), _REFERENCE_PATTERN)
    for field in ("objectId", "provenanceRef"):
        _require_fullmatch(security.get(field), _REFERENCE_PATTERN)
    _require_fullmatch(request.get("sourceNamespace"), _TOKEN_PATTERN)
    for field in ("objectType", "producerClass", "classification", "retentionHint"):
        _require_fullmatch(security.get(field), _TOKEN_PATTERN)
    _validate_timestamp(request.get("sourceEventTime"))
    _validate_timestamp(security.get("createdAt"))

    taint = security.get("taint")
    if type(taint) is not list:
        raise ValueError("request does not satisfy the controller contract")
    for value in taint:
        _require_fullmatch(value, _TOKEN_PATTERN)
    if len(set(taint)) != len(taint) or tuple(sorted(taint)) != tuple(taint):
        raise _invalid(operation)


def _validate_response_semantics(document: dict[str, object]) -> None:
    result = document.get("result")
    if result is None:
        return
    if type(result) is not dict:
        raise ValueError("response does not satisfy the controller contract")
    _require_fullmatch(result.get("requestId"), _REQUEST_ID_PATTERN)
    _require_fullmatch(result.get("taskId"), _TASK_ID_PATTERN)
    if document.get("operation") == ControllerOperation.GET_TASK.value:
        reason = result.get("reasonCode")
        if reason is not None:
            _require_fullmatch(reason, _TOKEN_PATTERN)
        _validate_timestamp(result.get("createdAt"))
        _validate_timestamp(result.get("updatedAt"))


def _validate_command_document(
    document: dict[str, object], operation: ControllerOperation
) -> None:
    try:
        canonical_json_bytes(document)
    except (CanonicalizationError, TypeError, ValueError, RecursionError) as exc:
        raise _invalid(operation) from exc
    if document.get("protocolVersion") != CONTROLLER_PROTOCOL_VERSION:
        if type(document.get("protocolVersion")) is str:
            raise ProtocolError(
                ErrorCode.UNSUPPORTED_PROTOCOL,
                PUBLIC_ERROR_MESSAGES[ErrorCode.UNSUPPORTED_PROTOCOL],
                operation,
            )
        raise _invalid(operation)
    try:
        if any(_command_validator().iter_errors(document)):
            raise _invalid(operation)
        _validate_command_semantics(document, operation)
    except ProtocolError:
        raise
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise _invalid(operation) from exc


def parse_command(payload: bytes) -> SubmitRequestCommand | GetTaskCommand:
    if type(payload) is not bytes or len(payload) > MAX_COMMAND_BYTES:
        raise _invalid()
    try:
        text = payload.decode("utf-8", errors="strict")
        parsed = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (
        UnicodeDecodeError,
        UnicodeError,
        json.JSONDecodeError,
        _DuplicateKeyError,
        ValueError,
        TypeError,
        RecursionError,
        CanonicalizationError,
    ) as exc:
        raise _invalid() from exc

    if type(parsed) is not dict:
        raise _invalid()
    operation = _operation(parsed)
    if operation is None:
        raise _invalid()
    _validate_command_document(parsed, operation)

    if operation is ControllerOperation.GET_TASK:
        task_id = parsed["taskId"]
        assert type(task_id) is str
        return GetTaskCommand(task_id)

    request = parsed["request"]
    assert type(request) is dict
    security = request["security"]
    assert type(security) is dict
    taint = security["taint"]
    assert type(taint) is list
    return SubmitRequestCommand(
        EngineeringRequest(
            source_namespace=request["sourceNamespace"],
            source_event_id=request["sourceEventId"],
            source_event_time=request["sourceEventTime"],
            actor_ref=request["actorRef"],
            channel_ref=request["channelRef"],
            project_ref=request["projectRef"],
            repository_ref=request["repositoryRef"],
            mode=request["mode"],
            body=request["body"],
            security=SecurityEnvelope(
                contract_version=security["contractVersion"],
                object_id=security["objectId"],
                object_type=security["objectType"],
                created_at=security["createdAt"],
                trust=security["trust"],
                taint=tuple(taint),
                provenance_ref=security["provenanceRef"],
                producer_class=security["producerClass"],
                classification=security["classification"],
                retention_hint=security["retentionHint"],
            ),
        )
    )


def validate_command(
    command: object,
    *,
    expected_operation: ControllerOperation | None = None,
) -> SubmitRequestCommand | GetTaskCommand:
    operation: ControllerOperation | None = None
    try:
        if type(command) is SubmitRequestCommand:
            operation = ControllerOperation.SUBMIT_REQUEST
            if (
                type(command.request) is not EngineeringRequest
                or type(command.request.security) is not SecurityEnvelope
                or type(command.request.security.taint) is not tuple
            ):
                raise _invalid(operation)
            document = {
                "protocolVersion": CONTROLLER_PROTOCOL_VERSION,
                "operation": operation.value,
                "request": request_document(command.request),
            }
        elif type(command) is GetTaskCommand:
            operation = ControllerOperation.GET_TASK
            document = {
                "protocolVersion": CONTROLLER_PROTOCOL_VERSION,
                "operation": operation.value,
                "taskId": command.task_id,
            }
        else:
            raise _invalid(expected_operation)
        if expected_operation is not None and operation is not expected_operation:
            raise _invalid(expected_operation)
    except ProtocolError:
        raise
    except (AttributeError, TypeError, ValueError, RecursionError) as exc:
        raise _invalid(expected_operation or operation) from exc

    _validate_command_document(document, operation)
    return command


def security_document(envelope: SecurityEnvelope) -> dict[str, object]:
    return {
        "contractVersion": envelope.contract_version,
        "objectId": envelope.object_id,
        "objectType": envelope.object_type,
        "createdAt": envelope.created_at,
        "trust": envelope.trust,
        "taint": list(envelope.taint),
        "provenanceRef": envelope.provenance_ref,
        "producerClass": envelope.producer_class,
        "classification": envelope.classification,
        "retentionHint": envelope.retention_hint,
    }


def request_document(request: EngineeringRequest) -> dict[str, object]:
    return {
        "sourceNamespace": request.source_namespace,
        "sourceEventId": request.source_event_id,
        "sourceEventTime": request.source_event_time,
        "actorRef": request.actor_ref,
        "channelRef": request.channel_ref,
        "projectRef": request.project_ref,
        "repositoryRef": request.repository_ref,
        "mode": request.mode,
        "body": request.body,
        "security": security_document(request.security),
    }


def request_identity_document(command: SubmitRequestCommand) -> dict[str, object]:
    return {
        "protocolVersion": CONTROLLER_PROTOCOL_VERSION,
        "request": request_document(command.request),
    }


def body_digest(body: str) -> str:
    value = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return f"sha256:{value}"


def request_digest(command: SubmitRequestCommand) -> str:
    return sha256_identifier(request_identity_document(command))


def security_digest(envelope: SecurityEnvelope) -> str:
    return sha256_identifier(security_document(envelope))


def format_utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be timezone-aware UTC")
    rendered = value.isoformat(timespec="seconds" if value.microsecond == 0 else "microseconds")
    return rendered.replace("+00:00", "Z")


def _encode_response(document: dict[str, object]) -> bytes:
    try:
        _validate_response_semantics(document)
        if any(_response_validator().iter_errors(document)):
            raise ValueError("response does not satisfy the controller contract")
        return canonical_json_bytes(document)
    except (CanonicalizationError, KeyError, TypeError, ValueError, RecursionError) as exc:
        if str(exc) == "response does not satisfy the controller contract":
            raise
        raise ValueError("response does not satisfy the controller contract") from exc


def encode_submit_success(result: SubmitResult) -> bytes:
    return _encode_response(
        {
            "protocolVersion": CONTROLLER_PROTOCOL_VERSION,
            "operation": ControllerOperation.SUBMIT_REQUEST.value,
            "ok": True,
            "result": {
                "requestId": result.request_id,
                "taskId": result.task_id,
                "status": result.status.value,
                "disposition": result.disposition.value,
            },
        }
    )


def encode_task_success(result: TaskInspectionResult) -> bytes:
    response_result: dict[str, object] = {
        "requestId": result.request_id,
        "taskId": result.task_id,
        "mode": result.mode,
        "status": result.status.value,
        "createdAt": format_utc_timestamp(result.created_at),
        "updatedAt": format_utc_timestamp(result.updated_at),
    }
    if result.reason_code is not None:
        response_result["reasonCode"] = result.reason_code
    return _encode_response(
        {
            "protocolVersion": CONTROLLER_PROTOCOL_VERSION,
            "operation": ControllerOperation.GET_TASK.value,
            "ok": True,
            "result": response_result,
        }
    )


def encode_error(operation: ControllerOperation | None, code: ErrorCode) -> bytes:
    return _encode_response(
        {
            "protocolVersion": CONTROLLER_PROTOCOL_VERSION,
            "operation": "unknown" if operation is None else operation.value,
            "ok": False,
            "error": {"code": code.value, "message": PUBLIC_ERROR_MESSAGES[code]},
        }
    )
