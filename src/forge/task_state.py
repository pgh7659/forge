from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    WAITING_APPROVAL = "waiting_approval"
    REVIEW_READY = "review_ready"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
)


class InvalidTaskTransition(ValueError):
    def __init__(self, current: TaskStatus | None, target: TaskStatus) -> None:
        self.current = current
        self.target = target
        current_value = "new" if current is None else current.value
        super().__init__(f"task transition {current_value} -> {target.value} is invalid")


_APPROVED_TRANSITIONS = MappingProxyType(
    {
        TaskStatus.QUEUED: frozenset(
            {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED}
        ),
        TaskStatus.RUNNING: frozenset(
            {
                TaskStatus.WAITING_USER,
                TaskStatus.WAITING_APPROVAL,
                TaskStatus.REVIEW_READY,
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            }
        ),
        TaskStatus.WAITING_USER: frozenset(
            {TaskStatus.QUEUED, TaskStatus.FAILED, TaskStatus.CANCELLED}
        ),
        TaskStatus.WAITING_APPROVAL: frozenset(
            {TaskStatus.QUEUED, TaskStatus.FAILED, TaskStatus.CANCELLED}
        ),
        TaskStatus.REVIEW_READY: frozenset(
            {
                TaskStatus.QUEUED,
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            }
        ),
    }
)


def validate_initial_status(status: TaskStatus) -> None:
    if status is not TaskStatus.QUEUED:
        raise InvalidTaskTransition(None, status)


def validate_general_transition(current: TaskStatus, target: TaskStatus) -> None:
    if target is TaskStatus.RUNNING:
        raise InvalidTaskTransition(current, target)
    if target not in _APPROVED_TRANSITIONS.get(current, frozenset()):
        raise InvalidTaskTransition(current, target)


def validate_claim_transition(current: TaskStatus) -> None:
    if current is not TaskStatus.QUEUED:
        raise InvalidTaskTransition(current, TaskStatus.RUNNING)
