from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from forge.canonical import canonical_json_bytes
from forge.controller import (
    ControllerError,
    ControllerService,
    SystemClock,
    SystemIdSource,
    start_controller,
)
from forge.controller_protocol import (
    CONTROLLER_PROTOCOL_VERSION,
    MAX_COMMAND_BYTES,
    ControllerOperation,
    ErrorCode,
    GetTaskCommand,
    ProtocolError,
    SubmitRequestCommand,
    TaskInspectionResult,
    parse_command,
)
from forge.request_crypto import (
    EncryptedValue,
    EncryptionError,
    KeyHandle,
    RequestCipher,
)
from forge.state_ledger import (
    ControllerAlreadyRunning,
    EncryptedRequestRecord,
    IdempotencyConflict,
    IngestBundle,
    IngestOutcome,
    NewTaskEvent,
    NewTaskRecord,
    StateError,
    StateLedger,
    StateTransitionConflict,
    TaskNotFound,
    TaskSnapshot,
)
from forge.task_state import InvalidTaskTransition, TaskStatus


FIXTURES = Path(__file__).parents[1] / "fixtures" / "controller"
FIXED_TIME = datetime(2026, 8, 11, 0, 0, 1, tzinfo=UTC)
FIXED_TIMESTAMP = "2026-08-11T00:00:01Z"
GENERATED_REQUEST_ID = "req_" + "a" * 32
GENERATED_TASK_ID = "tsk_" + "b" * 32
DURABLE_REQUEST_ID = "req_" + "b" * 32
DURABLE_TASK_ID = "tsk_" + "a" * 32
KEY = KeyHandle("key:synthetic", b"K" * 32)
BODY = "Review the synthetic change and produce a plan."
SENSITIVE = "private body /tmp/private.db key:synthetic CCCCCCCC"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def decoded(payload: bytes) -> dict[str, object]:
    document = json.loads(payload)
    assert type(document) is dict
    return document


def snapshot(
    *,
    request_id: str = GENERATED_REQUEST_ID,
    task_id: str = GENERATED_TASK_ID,
    status: TaskStatus = TaskStatus.QUEUED,
    reason_code: str | None = None,
) -> TaskSnapshot:
    return TaskSnapshot(
        request_id=request_id,
        task_id=task_id,
        project_ref="project:example",
        repository_ref="repository:example",
        mode="plan",
        status=status,
        reason_code=reason_code,
        created_at=FIXED_TIMESTAMP,
        updated_at=FIXED_TIMESTAMP,
    )


class FixedClock:
    def now(self) -> datetime:
        return FIXED_TIME


class SequenceIds:
    def __init__(self) -> None:
        self.event_number = 0
        self.request_calls = 0
        self.task_calls = 0

    def new_request_id(self) -> str:
        self.request_calls += 1
        return GENERATED_REQUEST_ID

    def new_task_id(self) -> str:
        self.task_calls += 1
        return GENERATED_TASK_ID

    def new_event_id(self) -> str:
        self.event_number += 1
        return f"evt_{self.event_number:032x}"


class RecordingCipher:
    algorithm = "AES-256-GCM"

    def __init__(self) -> None:
        self.encrypt_calls: list[tuple[bytes, bytes, KeyHandle]] = []
        self.error: Exception | None = None

    def encrypt(
        self, plaintext: bytes, associated_data: bytes, key: KeyHandle
    ) -> EncryptedValue:
        self.encrypt_calls.append((plaintext, associated_data, key))
        if self.error is not None:
            raise self.error
        return EncryptedValue(b"N" * 12, b"C" * 32)

    def decrypt(
        self, value: EncryptedValue, associated_data: bytes, key: KeyHandle
    ) -> bytes:
        raise AssertionError("controller must not decrypt request bodies")


class RecordingLedger:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.ingest_outcome = IngestOutcome(snapshot(), True)
        self.task: TaskSnapshot | None = snapshot()
        self.transition_outcome = snapshot(status=TaskStatus.FAILED, reason_code="failed")
        self.claim_outcome: TaskSnapshot | None = None
        self.binding_error: Exception | None = None
        self.reconcile_error: Exception | None = None
        self.ingest_error: Exception | None = None
        self.get_error: Exception | None = None
        self.transition_error: Exception | None = None
        self.close_count = 0

    def ingest(self, bundle: IngestBundle) -> IngestOutcome:
        self.calls.append(("ingest", bundle))
        if self.ingest_error is not None:
            raise self.ingest_error
        return self.ingest_outcome

    def get_task(self, task_id: str) -> TaskSnapshot | None:
        self.calls.append(("get_task", task_id))
        if self.get_error is not None:
            raise self.get_error
        return self.task

    def load_encrypted_request(
        self, request_id: str
    ) -> EncryptedRequestRecord | None:
        self.calls.append(("load_encrypted_request", request_id))
        return None

    def assert_encryption_binding(
        self, *, cipher: RequestCipher, key_handle: KeyHandle
    ) -> None:
        self.calls.append(("assert_encryption_binding", cipher, key_handle))
        if self.binding_error is not None:
            raise self.binding_error

    def transition(
        self,
        *,
        task_id: str,
        expected_status: TaskStatus,
        target_status: TaskStatus,
        reason_code: str | None,
        actor_ref: str,
        event_id: str,
        occurred_at: str,
    ) -> TaskSnapshot:
        self.calls.append(
            (
                "transition",
                task_id,
                expected_status,
                target_status,
                reason_code,
                actor_ref,
                event_id,
                occurred_at,
            )
        )
        if self.transition_error is not None:
            raise self.transition_error
        return self.transition_outcome

    def claim_next_eligible(
        self,
        *,
        max_concurrency: int,
        actor_ref: str,
        event_id: str,
        occurred_at: str,
    ) -> TaskSnapshot | None:
        self.calls.append(
            (
                "claim_next_eligible",
                max_concurrency,
                actor_ref,
                event_id,
                occurred_at,
            )
        )
        return self.claim_outcome

    def reconcile_running(
        self,
        *,
        event_id_factory: Callable[[], str],
        actor_ref: str,
        occurred_at: str,
    ) -> tuple[TaskSnapshot, ...]:
        self.calls.append(
            (
                "reconcile_running",
                actor_ref,
                occurred_at,
                event_id_factory(),
            )
        )
        if self.reconcile_error is not None:
            raise self.reconcile_error
        return ()

    def close(self) -> None:
        self.calls.append(("close",))
        self.close_count += 1


def started(
    ledger: RecordingLedger | None = None,
    cipher: RecordingCipher | None = None,
    *,
    max_concurrency: int = 2,
    ids: SequenceIds | None = None,
    clock: FixedClock | None = None,
) -> tuple[ControllerService, RecordingLedger, RecordingCipher, SequenceIds]:
    actual_ledger = RecordingLedger() if ledger is None else ledger
    actual_cipher = RecordingCipher() if cipher is None else cipher
    actual_ids = SequenceIds() if ids is None else ids
    service = start_controller(
        ledger=actual_ledger,
        cipher=actual_cipher,
        key_handle=KEY,
        max_concurrency=max_concurrency,
        clock=FixedClock() if clock is None else clock,
        ids=actual_ids,
    )
    return service, actual_ledger, actual_cipher, actual_ids


def test_storage_records_are_immutable_minimized_and_redacted_in_repr() -> None:
    request = EncryptedRequestRecord(
        request_id=GENERATED_REQUEST_ID,
        protocol_version=CONTROLLER_PROTOCOL_VERSION,
        source_namespace="example-source",
        source_event_id="event:0123",
        source_event_time="2026-08-11T00:00:00Z",
        actor_ref="actor:example",
        channel_ref="channel:example",
        project_ref="project:example",
        repository_ref="repository:example",
        mode="plan",
        security_envelope=b"security-sensitive",
        submission_digest="sha256:" + "a" * 64,
        body_digest="sha256:" + "b" * 64,
        security_digest="sha256:" + "c" * 64,
        encryption_algorithm="AES-256-GCM",
        key_id="key:synthetic",
        nonce=b"nonce-sensitive",
        ciphertext=b"ciphertext-sensitive",
        received_at=FIXED_TIMESTAMP,
    )
    task = NewTaskRecord(
        GENERATED_TASK_ID,
        GENERATED_REQUEST_ID,
        "project:example",
        "repository:example",
        "plan",
        FIXED_TIMESTAMP,
    )
    event = NewTaskEvent(
        "evt_" + "1" * 32,
        GENERATED_TASK_ID,
        None,
        TaskStatus.QUEUED,
        None,
        "actor:example",
        FIXED_TIMESTAMP,
    )
    bundle = IngestBundle(request, task, event)
    outcome = IngestOutcome(snapshot(), True)

    for record in (request, task, event, bundle, outcome, outcome.task):
        with pytest.raises(FrozenInstanceError):
            setattr(record, fields(record)[0].name, "changed")
    rendered = repr(request)
    for secret in (
        "security-sensitive",
        "key:synthetic",
        "nonce-sensitive",
        "ciphertext-sensitive",
    ):
        assert secret not in rendered
    assert {item.name for item in fields(TaskSnapshot)} == {
        "request_id",
        "task_id",
        "project_ref",
        "repository_ref",
        "mode",
        "status",
        "reason_code",
        "created_at",
        "updated_at",
    }
    assert "body" not in repr(outcome.task)
    assert "security" not in repr(outcome.task)
    assert isinstance(RecordingLedger(), StateLedger)


@pytest.mark.parametrize("value", [True, 0, -1])
def test_invalid_concurrency_fails_before_ledger_access(value: object) -> None:
    ledger = RecordingLedger()

    with pytest.raises(ControllerError) as raised:
        start_controller(
            ledger=ledger,
            cipher=RecordingCipher(),
            key_handle=KEY,
            max_concurrency=value,  # type: ignore[arg-type]
            clock=FixedClock(),
            ids=SequenceIds(),
        )

    assert str(raised.value) == "state operation failed"
    assert ledger.calls == []


def test_start_binds_exact_cipher_and_key_before_reconciliation_and_readiness() -> None:
    ledger = RecordingLedger()
    cipher = RecordingCipher()

    service, _, _, _ = started(ledger, cipher)

    assert ledger.calls[:2] == [
        ("assert_encryption_binding", cipher, KEY),
        (
            "reconcile_running",
            "controller:startup",
            FIXED_TIMESTAMP,
            "evt_" + "0" * 31 + "1",
        ),
    ]
    assert decoded(service.handle(fixture_bytes("valid-get-task.json")))["ok"] is True


@pytest.mark.parametrize("stage", ["binding", "reconciliation"])
def test_owned_start_failure_closes_ledger_without_sensitive_error(stage: str) -> None:
    ledger = RecordingLedger()
    error = StateError()
    error.__cause__ = RuntimeError(SENSITIVE)
    if stage == "binding":
        ledger.binding_error = error
    else:
        ledger.reconcile_error = error

    with pytest.raises(StateError) as raised:
        started(ledger)

    assert str(raised.value) == "state operation failed"
    assert SENSITIVE not in str(raised.value)
    assert ledger.close_count == 1
    if stage == "binding":
        assert not any(call[0] == "reconcile_running" for call in ledger.calls)


def test_unstarted_service_is_not_ready_and_close_is_idempotent() -> None:
    ledger = RecordingLedger()
    service = ControllerService(
        ledger=ledger,
        cipher=RecordingCipher(),
        key_handle=KEY,
        max_concurrency=2,
        clock=FixedClock(),
        ids=SequenceIds(),
    )

    response = decoded(service.handle(fixture_bytes("valid-get-task.json")))
    service.close()
    service.close()

    assert response == {
        "protocolVersion": CONTROLLER_PROTOCOL_VERSION,
        "operation": "getTask",
        "ok": False,
        "error": {"code": "state_error", "message": "state operation failed"},
    }
    assert ledger.close_count == 1


def test_submit_encrypts_exact_body_and_persists_one_minimized_ingest_bundle() -> None:
    service, ledger, cipher, _ = started()
    ledger.calls.clear()

    response = decoded(service.handle(fixture_bytes("valid-submit.json")))

    assert response == {
        "protocolVersion": CONTROLLER_PROTOCOL_VERSION,
        "operation": "submitRequest",
        "ok": True,
        "result": {
            "requestId": GENERATED_REQUEST_ID,
            "taskId": GENERATED_TASK_ID,
            "status": "queued",
            "disposition": "created",
        },
    }
    assert len(cipher.encrypt_calls) == 1
    plaintext, aad, key = cipher.encrypt_calls[0]
    assert plaintext == BODY.encode("utf-8")
    assert key is KEY
    assert aad == (
        b'{"algorithm":"AES-256-GCM","bodyDigest":"sha256:'
        b'a8a98829cdbe3a7ce3eb9037fa6439fcfcf238a355b416f8203e30a1911d2066",'
        b'"domain":"forge.request-body/v1","idempotencyKey":'
        b'{"sourceEventId":"event:0123","sourceNamespace":"example-source"},'
        b'"keyId":"key:synthetic","projectRef":"project:example",'
        b'"protocolVersion":"forge.dev/controller/v1alpha1",'
        b'"repositoryRef":"repository:example",'
        b'"requestId":"req_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
        b'"securityDigest":"sha256:'
        b'1516dd775610128d00455fec497670f62bafcad6c2666432d1421a7a4460a9c2"}'
    )
    assert b"operation" not in aad
    assert len(ledger.calls) == 1
    _, bundle = ledger.calls[0]
    assert isinstance(bundle, IngestBundle)
    assert bundle.request == EncryptedRequestRecord(
        request_id=GENERATED_REQUEST_ID,
        protocol_version=CONTROLLER_PROTOCOL_VERSION,
        source_namespace="example-source",
        source_event_id="event:0123",
        source_event_time="2026-08-11T00:00:00Z",
        actor_ref="actor:example",
        channel_ref="channel:example",
        project_ref="project:example",
        repository_ref="repository:example",
        mode="plan",
        security_envelope=(
            b'{"classification":"private",'
            b'"contractVersion":"forge.dev/security/v1alpha1",'
            b'"createdAt":"2026-08-11T00:00:00Z",'
            b'"objectId":"object:example","objectType":"engineering-request",'
            b'"producerClass":"gateway-adapter",'
            b'"provenanceRef":"provenance:example",'
            b'"retentionHint":"task-lifecycle",'
            b'"taint":["external-input","user-supplied"],"trust":"unknown"}'
        ),
        submission_digest="sha256:58d9c0b8ad1be3342255d5a9699f701389292227aa9534fe4253fde5182ddd9f",
        body_digest="sha256:a8a98829cdbe3a7ce3eb9037fa6439fcfcf238a355b416f8203e30a1911d2066",
        security_digest="sha256:1516dd775610128d00455fec497670f62bafcad6c2666432d1421a7a4460a9c2",
        encryption_algorithm="AES-256-GCM",
        key_id="key:synthetic",
        nonce=b"N" * 12,
        ciphertext=b"C" * 32,
        received_at=FIXED_TIMESTAMP,
    )
    assert bundle.task == NewTaskRecord(
        GENERATED_TASK_ID,
        GENERATED_REQUEST_ID,
        "project:example",
        "repository:example",
        "plan",
        FIXED_TIMESTAMP,
    )
    assert bundle.event == NewTaskEvent(
        "evt_" + "0" * 31 + "2",
        GENERATED_TASK_ID,
        None,
        TaskStatus.QUEUED,
        None,
        "actor:example",
        FIXED_TIMESTAMP,
    )
    assert "body" not in {item.name for item in fields(bundle.request)}


def test_identical_replay_returns_only_existing_durable_ids() -> None:
    ledger = RecordingLedger()
    ledger.ingest_outcome = IngestOutcome(
        snapshot(request_id=DURABLE_REQUEST_ID, task_id=DURABLE_TASK_ID), False
    )
    service, ledger, _, _ = started(ledger)
    ledger.calls.clear()

    response = service.handle(fixture_bytes("valid-submit.json"))

    assert decoded(response)["result"] == {
        "requestId": DURABLE_REQUEST_ID,
        "taskId": DURABLE_TASK_ID,
        "status": "queued",
        "disposition": "replayed",
    }
    assert GENERATED_REQUEST_ID.encode() not in response
    assert GENERATED_TASK_ID.encode() not in response
    assert b"CCCC" not in response


class CountingClock(FixedClock):
    def __init__(self) -> None:
        self.calls = 0

    def now(self) -> datetime:
        self.calls += 1
        return super().now()


def invalid_direct_submit(case: str) -> SubmitRequestCommand:
    command = parse_command(fixture_bytes("valid-submit.json"))
    assert isinstance(command, SubmitRequestCommand)
    request = command.request
    security = request.security
    if case == "security-version":
        security = replace(security, contract_version="forge.dev/security/v2")
    elif case == "trust":
        security = replace(security, trust="approved")
    elif case == "taint-token":
        security = replace(security, taint=("external-input\n",))
    elif case == "taint-shape":
        security = replace(security, taint=["external-input"])  # type: ignore[arg-type]
    elif case == "body-bound":
        request = replace(request, body="x" * 65_537)
    elif case == "timestamp":
        request = replace(request, source_event_time="2026-99-11T00:00:00Z")
    elif case == "mode":
        request = replace(request, mode="apply")
    elif case == "reference":
        request = replace(request, repository_ref="repository:example\n")
    else:  # pragma: no cover - the parametrization is the complete caller
        raise AssertionError("unknown invalid direct-submit case")
    return SubmitRequestCommand(replace(request, security=security))


@pytest.mark.parametrize(
    "case",
    (
        "security-version",
        "trust",
        "taint-token",
        "taint-shape",
        "body-bound",
        "timestamp",
        "mode",
        "reference",
    ),
)
def test_direct_submit_revalidates_complete_command_before_any_side_effect(
    case: str,
) -> None:
    clock = CountingClock()
    ids = SequenceIds()
    service, ledger, cipher, _ = started(ids=ids, clock=clock)
    ledger.calls.clear()
    cipher.encrypt_calls.clear()
    before = (clock.calls, ids.request_calls, ids.task_calls, ids.event_number)

    with pytest.raises(ProtocolError) as raised:
        service.submit_request(invalid_direct_submit(case))

    assert raised.value.code is ErrorCode.INVALID_REQUEST
    assert raised.value.operation is ControllerOperation.SUBMIT_REQUEST
    assert str(raised.value) == "request does not satisfy the controller contract"
    assert (clock.calls, ids.request_calls, ids.task_calls, ids.event_number) == before
    assert cipher.encrypt_calls == []
    assert ledger.calls == []


def test_direct_submit_rejects_oversized_canonical_command_before_any_side_effect() -> None:
    baseline = parse_command(fixture_bytes("valid-submit.json"))
    assert isinstance(baseline, SubmitRequestCommand)
    taint = tuple(
        f"oversized:{index:04d}:" + "x" * 113 for index in range(2_100)
    )
    assert taint == tuple(sorted(set(taint)))
    assert all(len(value) == 128 for value in taint)
    document = decoded(fixture_bytes("valid-submit.json"))
    request_document = document["request"]
    assert type(request_document) is dict
    security_document = request_document["security"]
    assert type(security_document) is dict
    security_document["taint"] = list(taint)
    assert len(canonical_json_bytes(document)) > MAX_COMMAND_BYTES
    command = SubmitRequestCommand(
        replace(
            baseline.request,
            security=replace(baseline.request.security, taint=taint),
        )
    )
    clock = CountingClock()
    ids = SequenceIds()
    service, ledger, cipher, _ = started(ids=ids, clock=clock)
    ledger.calls.clear()
    cipher.encrypt_calls.clear()
    before = (clock.calls, ids.request_calls, ids.task_calls, ids.event_number)

    with pytest.raises(ProtocolError) as raised:
        service.submit_request(command)

    assert raised.value.code is ErrorCode.INVALID_REQUEST
    assert raised.value.operation is ControllerOperation.SUBMIT_REQUEST
    assert str(raised.value) == "request does not satisfy the controller contract"
    assert (clock.calls, ids.request_calls, ids.task_calls, ids.event_number) == before
    assert cipher.encrypt_calls == []
    assert ledger.calls == []


@pytest.mark.parametrize(
    "task_id",
    (
        "tsk_not-hex",
        GENERATED_TASK_ID + "\n",
    ),
)
def test_direct_get_task_revalidates_task_id_before_ledger_access(
    task_id: str,
) -> None:
    service, ledger, cipher, ids = started()
    ledger.calls.clear()
    before = (ids.request_calls, ids.task_calls, ids.event_number)

    with pytest.raises(ProtocolError) as raised:
        service.get_task(GetTaskCommand(task_id))

    assert raised.value.code is ErrorCode.INVALID_REQUEST
    assert raised.value.operation is ControllerOperation.GET_TASK
    assert str(raised.value) == "request does not satisfy the controller contract"
    assert (ids.request_calls, ids.task_calls, ids.event_number) == before
    assert cipher.encrypt_calls == []
    assert ledger.calls == []


@pytest.mark.parametrize(
    ("method", "command", "operation"),
    (
        (
            "submit_request",
            GetTaskCommand(GENERATED_TASK_ID),
            ControllerOperation.SUBMIT_REQUEST,
        ),
        (
            "get_task",
            parse_command(fixture_bytes("valid-submit.json")),
            ControllerOperation.GET_TASK,
        ),
    ),
)
def test_direct_methods_reject_the_other_typed_operation_with_owned_error(
    method: str,
    command: object,
    operation: ControllerOperation,
) -> None:
    service, ledger, cipher, ids = started()
    ledger.calls.clear()
    before = (ids.request_calls, ids.task_calls, ids.event_number)

    with pytest.raises(ProtocolError) as raised:
        getattr(service, method)(command)

    assert raised.value.code is ErrorCode.INVALID_REQUEST
    assert raised.value.operation is operation
    assert (ids.request_calls, ids.task_calls, ids.event_number) == before
    assert cipher.encrypt_calls == []
    assert ledger.calls == []


def test_get_task_returns_minimized_public_result_and_missing_maps_to_error() -> None:
    service, ledger, _, _ = started()
    ledger.calls.clear()

    result = service.get_task(GetTaskCommand(GENERATED_TASK_ID))

    assert result == TaskInspectionResult(
        request_id=GENERATED_REQUEST_ID,
        task_id=GENERATED_TASK_ID,
        mode="plan",
        status=TaskStatus.QUEUED,
        reason_code=None,
        created_at=FIXED_TIME,
        updated_at=FIXED_TIME,
    )
    assert {item.name for item in fields(result)} == {
        "request_id",
        "task_id",
        "mode",
        "status",
        "reason_code",
        "created_at",
        "updated_at",
    }
    assert ledger.calls == [("get_task", GENERATED_TASK_ID)]

    ledger.task = None
    response = decoded(service.handle(fixture_bytes("valid-get-task.json")))
    assert response["error"] == {
        "code": "task_not_found",
        "message": "task was not found",
    }


@pytest.mark.parametrize(
    ("expected", "target"),
    [
        (TaskStatus.QUEUED, TaskStatus.RUNNING),
        (TaskStatus.COMPLETED, TaskStatus.FAILED),
        ("queued", TaskStatus.FAILED),
        (TaskStatus.QUEUED, "failed"),
    ],
)
def test_general_transition_rejects_invalid_statuses_before_ledger_access(
    expected: object, target: object
) -> None:
    service, ledger, _, _ = started()
    ledger.calls.clear()

    with pytest.raises((InvalidTaskTransition, ControllerError)):
        service.transition_task(
            task_id=GENERATED_TASK_ID,
            expected_status=expected,  # type: ignore[arg-type]
            target_status=target,  # type: ignore[arg-type]
            reason_code="failed",
            actor_ref="actor:example",
        )

    assert ledger.calls == []


def test_general_transition_passes_stable_fields_and_maps_compare_and_set_conflict() -> None:
    service, ledger, _, _ = started()
    ledger.calls.clear()

    result = service.transition_task(
        task_id=GENERATED_TASK_ID,
        expected_status=TaskStatus.QUEUED,
        target_status=TaskStatus.FAILED,
        reason_code="executor_failed",
        actor_ref="executor:synthetic",
    )

    assert result is ledger.transition_outcome
    assert ledger.calls == [
        (
            "transition",
            GENERATED_TASK_ID,
            TaskStatus.QUEUED,
            TaskStatus.FAILED,
            "executor_failed",
            "executor:synthetic",
            "evt_" + "0" * 31 + "2",
            FIXED_TIMESTAMP,
        )
    ]

    ledger.transition_error = StateTransitionConflict()
    command = parse_command(fixture_bytes("valid-get-task.json"))
    assert isinstance(command, GetTaskCommand)
    ledger.get_error = ledger.transition_error
    response = decoded(service.handle(fixture_bytes("valid-get-task.json")))
    assert response["error"] == {
        "code": "invalid_transition",
        "message": "task transition is not allowed",
    }


def test_claim_passes_configured_limit_and_none_is_a_normal_outcome() -> None:
    service, ledger, _, _ = started(max_concurrency=7)
    ledger.calls.clear()

    result = service.claim_next_eligible(actor_ref="executor:synthetic")

    assert result is None
    assert ledger.calls == [
        (
            "claim_next_eligible",
            7,
            "executor:synthetic",
            "evt_" + "0" * 31 + "2",
            FIXED_TIMESTAMP,
        )
    ]


def test_controller_serializes_ledger_access_across_threads() -> None:
    class BlockingLedger(RecordingLedger):
        def __init__(self) -> None:
            super().__init__()
            self.get_entered = threading.Event()
            self.release_get = threading.Event()
            self.claim_entered = threading.Event()

        def get_task(self, task_id: str) -> TaskSnapshot | None:
            self.get_entered.set()
            assert self.release_get.wait(timeout=2)
            return super().get_task(task_id)

        def claim_next_eligible(
            self,
            *,
            max_concurrency: int,
            actor_ref: str,
            event_id: str,
            occurred_at: str,
        ) -> TaskSnapshot | None:
            self.claim_entered.set()
            return super().claim_next_eligible(
                max_concurrency=max_concurrency,
                actor_ref=actor_ref,
                event_id=event_id,
                occurred_at=occurred_at,
            )

    ledger = BlockingLedger()
    service, _, _, _ = started(ledger)
    first = threading.Thread(
        target=service.get_task, args=(GetTaskCommand(GENERATED_TASK_ID),)
    )
    second = threading.Thread(
        target=service.claim_next_eligible,
        kwargs={"actor_ref": "executor:synthetic"},
    )

    first.start()
    assert ledger.get_entered.wait(timeout=2)
    second.start()
    assert not ledger.claim_entered.wait(timeout=0.1)
    ledger.release_get.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert ledger.claim_entered.is_set()


EXPECTED_CODES = {
    IdempotencyConflict: ErrorCode.IDEMPOTENCY_CONFLICT,
    TaskNotFound: ErrorCode.TASK_NOT_FOUND,
    StateTransitionConflict: ErrorCode.INVALID_TRANSITION,
    ControllerAlreadyRunning: ErrorCode.CONTROLLER_ALREADY_RUNNING,
    StateError: ErrorCode.STATE_ERROR,
    EncryptionError: ErrorCode.ENCRYPTION_ERROR,
}
EXPECTED_MESSAGES = {
    IdempotencyConflict: "request identity conflicts with durable state",
    TaskNotFound: "task was not found",
    StateTransitionConflict: "task transition is not allowed",
    ControllerAlreadyRunning: "controller already owns this state",
    StateError: "state operation failed",
    EncryptionError: "encryption operation failed",
}


@pytest.mark.parametrize(
    ("error_type", "code"), EXPECTED_CODES.items()
)
def test_owned_errors_map_to_stable_redacted_public_errors(
    error_type: type[Exception], code: ErrorCode
) -> None:
    cipher = RecordingCipher()
    service, ledger, _, _ = started(cipher=cipher)
    error = error_type()
    error.__cause__ = RuntimeError(SENSITIVE)
    if error_type is EncryptionError:
        cipher.error = error
        operation = "submitRequest"
        command = fixture_bytes("valid-submit.json")
    else:
        ledger.get_error = error
        operation = "getTask"
        command = fixture_bytes("valid-get-task.json")

    payload = service.handle(command)
    response = decoded(payload)

    assert response == {
        "protocolVersion": CONTROLLER_PROTOCOL_VERSION,
        "operation": operation,
        "ok": False,
        "error": {
            "code": code.value,
            "message": EXPECTED_MESSAGES[error_type],
        },
    }
    for value in (
        SENSITIVE,
        BODY,
        KEY.key_id,
        "CCCC",
        "/tmp/private.db",
        "provenance:example",
        "gateway-adapter",
    ):
        assert value.encode() not in payload


@pytest.mark.parametrize(
    ("payload", "operation"),
    [
        (
            b'{"protocolVersion":"forge.dev/controller/v1alpha1",'
            b'"operation":"submitRequest"}',
            "submitRequest",
        ),
        (
            b'{"protocolVersion":"forge.dev/controller/v1alpha1",'
            b'"operation":"getTask"}',
            "getTask",
        ),
        (b"{}", "unknown"),
        (
            b'{"operation":"getTask","operation":"submitRequest"}',
            "unknown",
        ),
        (b"not-json", "unknown"),
        (b'{"operation":"unknown"}', "unknown"),
    ],
)
def test_malformed_commands_preserve_only_duplicate_safe_recognized_operation(
    payload: bytes, operation: str
) -> None:
    service, _, _, _ = started()

    response = decoded(service.handle(payload))

    assert response["operation"] == operation
    assert response["error"] == {
        "code": "invalid_request",
        "message": "request does not satisfy the controller contract",
    }


def test_unexpected_runtime_error_propagates() -> None:
    service, ledger, _, _ = started()
    ledger.get_error = RuntimeError(SENSITIVE)

    with pytest.raises(RuntimeError, match=SENSITIVE):
        service.handle(fixture_bytes("valid-get-task.json"))


def test_system_clock_and_id_source_produce_utc_and_opaque_ids() -> None:
    now = SystemClock().now()
    ids = SystemIdSource()

    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)
    for value, prefix in (
        (ids.new_request_id(), "req_"),
        (ids.new_task_id(), "tsk_"),
        (ids.new_event_id(), "evt_"),
    ):
        assert value.startswith(prefix)
        assert len(value) == len(prefix) + 32
        assert all(character in "0123456789abcdef" for character in value[len(prefix) :])


@pytest.mark.parametrize("kind", ["request", "task", "event"])
def test_invalid_injected_ids_fail_before_persistence(kind: str) -> None:
    class InvalidIds(SequenceIds):
        def new_request_id(self) -> str:
            return "req_not-hex" if kind == "request" else super().new_request_id()

        def new_task_id(self) -> str:
            return "tsk_not-hex" if kind == "task" else super().new_task_id()

        def new_event_id(self) -> str:
            return "evt_not-hex" if kind == "event" else super().new_event_id()

    ledger = RecordingLedger()
    ids = InvalidIds()
    if kind == "event":
        with pytest.raises(ControllerError):
            started(ledger, ids=ids)
        assert not any(call[0] == "reconcile_running" for call in ledger.calls)
        return

    service, ledger, _, _ = started(ledger, ids=ids)
    ledger.calls.clear()

    response = decoded(service.handle(fixture_bytes("valid-submit.json")))

    assert response["error"] == {
        "code": "state_error",
        "message": "state operation failed",
    }
    assert not any(call[0] == "ingest" for call in ledger.calls)


def test_timezone_aware_but_non_utc_clock_fails_before_ledger_mutation() -> None:
    class NonUtcClock:
        def now(self) -> datetime:
            return datetime(2026, 8, 11, 9, 0, 1, tzinfo=timezone(timedelta(hours=9)))

    ledger = RecordingLedger()
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        start_controller(
            ledger=ledger,
            cipher=RecordingCipher(),
            key_handle=KEY,
            max_concurrency=2,
            clock=NonUtcClock(),
            ids=SequenceIds(),
        )
    assert ledger.close_count == 1
    assert not any(call[0] == "reconcile_running" for call in ledger.calls)
