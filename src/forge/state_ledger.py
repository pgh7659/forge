from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from forge.request_crypto import KeyHandle, RequestCipher
from forge.task_state import TaskStatus


@dataclass(frozen=True, slots=True)
class EncryptedRequestRecord:
    request_id: str
    protocol_version: str
    source_namespace: str
    source_event_id: str
    source_event_time: str
    actor_ref: str
    channel_ref: str
    project_ref: str
    repository_ref: str
    mode: str
    security_envelope: bytes = field(repr=False)
    submission_digest: str
    body_digest: str
    security_digest: str
    encryption_algorithm: str
    key_id: str = field(repr=False)
    nonce: bytes = field(repr=False)
    ciphertext: bytes = field(repr=False)
    received_at: str


@dataclass(frozen=True, slots=True)
class NewTaskRecord:
    task_id: str
    request_id: str
    project_ref: str
    repository_ref: str
    mode: str
    created_at: str


@dataclass(frozen=True, slots=True)
class NewTaskEvent:
    event_id: str
    task_id: str
    previous_status: TaskStatus | None
    next_status: TaskStatus
    reason_code: str | None
    actor_ref: str
    occurred_at: str


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    request_id: str
    task_id: str
    project_ref: str
    repository_ref: str
    mode: str
    status: TaskStatus
    reason_code: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class IngestBundle:
    request: EncryptedRequestRecord
    task: NewTaskRecord
    event: NewTaskEvent


@dataclass(frozen=True, slots=True)
class IngestOutcome:
    task: TaskSnapshot
    created: bool


class StateError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("state operation failed")


class IdempotencyConflict(StateError):
    def __init__(self) -> None:
        RuntimeError.__init__(self, "request identity conflicts with durable state")


class TaskNotFound(StateError):
    def __init__(self) -> None:
        RuntimeError.__init__(self, "task was not found")


class StateTransitionConflict(StateError):
    def __init__(self) -> None:
        RuntimeError.__init__(self, "task transition is not allowed")


class ControllerAlreadyRunning(StateError):
    def __init__(self) -> None:
        RuntimeError.__init__(self, "controller already owns this state")


@runtime_checkable
class StateLedger(Protocol):
    def ingest(self, bundle: IngestBundle) -> IngestOutcome:
        raise NotImplementedError

    def get_task(self, task_id: str) -> TaskSnapshot | None:
        raise NotImplementedError

    def load_encrypted_request(
        self, request_id: str
    ) -> EncryptedRequestRecord | None:
        raise NotImplementedError

    def assert_encryption_binding(
        self, *, cipher: RequestCipher, key_handle: KeyHandle
    ) -> None:
        raise NotImplementedError

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
        raise NotImplementedError

    def claim_next_eligible(
        self,
        *,
        max_concurrency: int,
        actor_ref: str,
        event_id: str,
        occurred_at: str,
    ) -> TaskSnapshot | None:
        raise NotImplementedError

    def reconcile_running(
        self,
        *,
        event_id_factory: Callable[[], str],
        actor_ref: str,
        occurred_at: str,
    ) -> tuple[TaskSnapshot, ...]:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
