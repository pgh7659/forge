from __future__ import annotations

import re
import secrets
import threading
from datetime import UTC, datetime
from typing import Protocol

from forge.canonical import canonical_json_bytes
from forge.controller_protocol import (
    CONTROLLER_PROTOCOL_VERSION,
    ControllerOperation,
    Disposition,
    ErrorCode,
    GetTaskCommand,
    ProtocolError,
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
    security_document,
    validate_command,
)
from forge.request_crypto import (
    EncryptionError,
    KeyHandle,
    RequestCipher,
    request_body_aad,
)
from forge.state_ledger import (
    ControllerAlreadyRunning,
    EncryptedRequestRecord,
    IdempotencyConflict,
    IngestBundle,
    NewTaskEvent,
    NewTaskRecord,
    StateError,
    StateLedger,
    StateTransitionConflict,
    TaskNotFound,
    TaskSnapshot,
)
from forge.task_state import InvalidTaskTransition, TaskStatus, validate_general_transition


_REQUEST_ID_PATTERN = re.compile(r"req_[0-9a-f]{32}")
_TASK_ID_PATTERN = re.compile(r"tsk_[0-9a-f]{32}")
_EVENT_ID_PATTERN = re.compile(r"evt_[0-9a-f]{32}")


class Clock(Protocol):
    def now(self) -> datetime:
        raise NotImplementedError


class IdSource(Protocol):
    def new_request_id(self) -> str:
        raise NotImplementedError

    def new_task_id(self) -> str:
        raise NotImplementedError

    def new_event_id(self) -> str:
        raise NotImplementedError


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class SystemIdSource:
    def new_request_id(self) -> str:
        return "req_" + secrets.token_hex(16)

    def new_task_id(self) -> str:
        return "tsk_" + secrets.token_hex(16)

    def new_event_id(self) -> str:
        return "evt_" + secrets.token_hex(16)


class ControllerError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("state operation failed")


_EXPECTED_ERROR_CODES: tuple[tuple[type[Exception], ErrorCode], ...] = (
    (IdempotencyConflict, ErrorCode.IDEMPOTENCY_CONFLICT),
    (TaskNotFound, ErrorCode.TASK_NOT_FOUND),
    (StateTransitionConflict, ErrorCode.INVALID_TRANSITION),
    (ControllerAlreadyRunning, ErrorCode.CONTROLLER_ALREADY_RUNNING),
    (StateError, ErrorCode.STATE_ERROR),
    (ControllerError, ErrorCode.STATE_ERROR),
    (InvalidTaskTransition, ErrorCode.INVALID_TRANSITION),
    (EncryptionError, ErrorCode.ENCRYPTION_ERROR),
)


class ControllerService:
    def __init__(
        self,
        *,
        ledger: StateLedger,
        cipher: RequestCipher,
        key_handle: KeyHandle,
        max_concurrency: int,
        clock: Clock,
        ids: IdSource,
    ) -> None:
        if type(max_concurrency) is not int or max_concurrency <= 0:
            raise ControllerError()
        self._ledger = ledger
        self._cipher = cipher
        self._key_handle = key_handle
        self._max_concurrency = max_concurrency
        self._clock = clock
        self._ids = ids
        self._lock = threading.RLock()
        self._ready = False
        self._closed = False

    def _start(self) -> None:
        with self._lock:
            if self._ready or self._closed:
                raise ControllerAlreadyRunning()
            occurred_at = format_utc_timestamp(self._clock.now())
            self._ledger.assert_encryption_binding(
                cipher=self._cipher, key_handle=self._key_handle
            )
            self._ledger.reconcile_running(
                event_id_factory=self._new_event_id,
                actor_ref="controller:startup",
                occurred_at=occurred_at,
            )
            self._ready = True

    def _require_ready(self) -> None:
        if not self._ready or self._closed:
            raise ControllerError()

    @staticmethod
    def _validated_id(value: object, pattern: re.Pattern[str]) -> str:
        if type(value) is not str or pattern.fullmatch(value) is None:
            raise ControllerError()
        return value

    def _new_request_id(self) -> str:
        return self._validated_id(self._ids.new_request_id(), _REQUEST_ID_PATTERN)

    def _new_task_id(self) -> str:
        return self._validated_id(self._ids.new_task_id(), _TASK_ID_PATTERN)

    def _new_event_id(self) -> str:
        return self._validated_id(self._ids.new_event_id(), _EVENT_ID_PATTERN)

    def handle(self, payload: bytes) -> bytes:
        operation: ControllerOperation | None = None
        try:
            command = parse_command(payload)
            if isinstance(command, SubmitRequestCommand):
                operation = ControllerOperation.SUBMIT_REQUEST
                return encode_submit_success(self.submit_request(command))
            operation = ControllerOperation.GET_TASK
            return encode_task_success(self.get_task(command))
        except ProtocolError as exc:
            return encode_error(exc.operation, exc.code)
        except _expected_error_types() as exc:
            return encode_error(operation, _error_code(exc))

    def submit_request(self, command: SubmitRequestCommand) -> SubmitResult:
        with self._lock:
            validate_command(
                command, expected_operation=ControllerOperation.SUBMIT_REQUEST
            )
            self._require_ready()
            occurred_at = format_utc_timestamp(self._clock.now())
            request = command.request
            submission_hash = request_digest(command)
            body_hash = body_digest(request.body)
            security_hash = security_digest(request.security)
            request_id = self._new_request_id()
            task_id = self._new_task_id()
            event_id = self._new_event_id()
            aad = request_body_aad(
                CONTROLLER_PROTOCOL_VERSION,
                request_id,
                request.source_namespace,
                request.source_event_id,
                request.project_ref,
                request.repository_ref,
                body_hash,
                security_hash,
                self._cipher.algorithm,
                self._key_handle.key_id,
            )
            encrypted = self._cipher.encrypt(
                request.body.encode("utf-8"), aad, self._key_handle
            )
            outcome = self._ledger.ingest(
                IngestBundle(
                    request=EncryptedRequestRecord(
                        request_id=request_id,
                        protocol_version=CONTROLLER_PROTOCOL_VERSION,
                        source_namespace=request.source_namespace,
                        source_event_id=request.source_event_id,
                        source_event_time=request.source_event_time,
                        actor_ref=request.actor_ref,
                        channel_ref=request.channel_ref,
                        project_ref=request.project_ref,
                        repository_ref=request.repository_ref,
                        mode=request.mode,
                        security_envelope=canonical_json_bytes(
                            security_document(request.security)
                        ),
                        submission_digest=submission_hash,
                        body_digest=body_hash,
                        security_digest=security_hash,
                        encryption_algorithm=self._cipher.algorithm,
                        key_id=self._key_handle.key_id,
                        nonce=encrypted.nonce,
                        ciphertext=encrypted.ciphertext,
                        received_at=occurred_at,
                    ),
                    task=NewTaskRecord(
                        task_id=task_id,
                        request_id=request_id,
                        project_ref=request.project_ref,
                        repository_ref=request.repository_ref,
                        mode=request.mode,
                        created_at=occurred_at,
                    ),
                    event=NewTaskEvent(
                        event_id=event_id,
                        task_id=task_id,
                        previous_status=None,
                        next_status=TaskStatus.QUEUED,
                        reason_code=None,
                        actor_ref=request.actor_ref,
                        occurred_at=occurred_at,
                    ),
                )
            )
            disposition = Disposition.CREATED if outcome.created else Disposition.REPLAYED
            return SubmitResult(
                request_id=outcome.task.request_id,
                task_id=outcome.task.task_id,
                status=outcome.task.status,
                disposition=disposition,
            )

    def get_task(self, command: GetTaskCommand) -> TaskInspectionResult:
        with self._lock:
            validate_command(command, expected_operation=ControllerOperation.GET_TASK)
            self._require_ready()
            task = self._ledger.get_task(command.task_id)
            if task is None:
                raise TaskNotFound()
            return TaskInspectionResult(
                request_id=task.request_id,
                task_id=task.task_id,
                mode=task.mode,
                status=task.status,
                reason_code=task.reason_code,
                created_at=_parse_timestamp(task.created_at),
                updated_at=_parse_timestamp(task.updated_at),
            )

    def claim_next_eligible(self, *, actor_ref: str) -> TaskSnapshot | None:
        with self._lock:
            self._require_ready()
            occurred_at = format_utc_timestamp(self._clock.now())
            return self._ledger.claim_next_eligible(
                max_concurrency=self._max_concurrency,
                actor_ref=actor_ref,
                event_id=self._new_event_id(),
                occurred_at=occurred_at,
            )

    def transition_task(
        self,
        *,
        task_id: str,
        expected_status: TaskStatus,
        target_status: TaskStatus,
        reason_code: str | None,
        actor_ref: str,
    ) -> TaskSnapshot:
        with self._lock:
            self._require_ready()
            if (
                type(expected_status) is not TaskStatus
                or type(target_status) is not TaskStatus
            ):
                raise ControllerError()
            validate_general_transition(expected_status, target_status)
            occurred_at = format_utc_timestamp(self._clock.now())
            return self._ledger.transition(
                task_id=task_id,
                expected_status=expected_status,
                target_status=target_status,
                reason_code=reason_code,
                actor_ref=actor_ref,
                event_id=self._new_event_id(),
                occurred_at=occurred_at,
            )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._ready = False
            self._ledger.close()


def _expected_error_types() -> tuple[type[Exception], ...]:
    return tuple(error_type for error_type, _ in _EXPECTED_ERROR_CODES)


def _error_code(error: Exception) -> ErrorCode:
    for error_type, code in _EXPECTED_ERROR_CODES:
        if isinstance(error, error_type):
            return code
    raise AssertionError("unreachable expected error mapping")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")


def start_controller(
    *,
    ledger: StateLedger,
    cipher: RequestCipher,
    key_handle: KeyHandle,
    max_concurrency: int,
    clock: Clock,
    ids: IdSource,
) -> ControllerService:
    service = ControllerService(
        ledger=ledger,
        cipher=cipher,
        key_handle=key_handle,
        max_concurrency=max_concurrency,
        clock=clock,
        ids=ids,
    )
    try:
        service._start()
    except Exception:
        ledger.close()
        raise
    return service
