from __future__ import annotations

import pytest

from forge.task_state import (
    TERMINAL_STATUSES,
    InvalidTaskTransition,
    TaskStatus,
    validate_claim_transition,
    validate_general_transition,
    validate_initial_status,
)


GENERAL_TRANSITIONS = {
    (TaskStatus.QUEUED, TaskStatus.FAILED),
    (TaskStatus.QUEUED, TaskStatus.CANCELLED),
    (TaskStatus.RUNNING, TaskStatus.WAITING_USER),
    (TaskStatus.RUNNING, TaskStatus.WAITING_APPROVAL),
    (TaskStatus.RUNNING, TaskStatus.REVIEW_READY),
    (TaskStatus.RUNNING, TaskStatus.COMPLETED),
    (TaskStatus.RUNNING, TaskStatus.FAILED),
    (TaskStatus.RUNNING, TaskStatus.CANCELLED),
    (TaskStatus.WAITING_USER, TaskStatus.QUEUED),
    (TaskStatus.WAITING_USER, TaskStatus.FAILED),
    (TaskStatus.WAITING_USER, TaskStatus.CANCELLED),
    (TaskStatus.WAITING_APPROVAL, TaskStatus.QUEUED),
    (TaskStatus.WAITING_APPROVAL, TaskStatus.FAILED),
    (TaskStatus.WAITING_APPROVAL, TaskStatus.CANCELLED),
    (TaskStatus.REVIEW_READY, TaskStatus.QUEUED),
    (TaskStatus.REVIEW_READY, TaskStatus.COMPLETED),
    (TaskStatus.REVIEW_READY, TaskStatus.FAILED),
    (TaskStatus.REVIEW_READY, TaskStatus.CANCELLED),
}


def test_state_vocabulary_and_terminal_set_are_exact() -> None:
    assert {status.value for status in TaskStatus} == {
        "queued",
        "running",
        "waiting_user",
        "waiting_approval",
        "review_ready",
        "completed",
        "failed",
        "cancelled",
    }
    assert TERMINAL_STATUSES == {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    }


def test_only_queued_is_a_valid_initial_state() -> None:
    validate_initial_status(TaskStatus.QUEUED)
    for status in set(TaskStatus) - {TaskStatus.QUEUED}:
        with pytest.raises(InvalidTaskTransition):
            validate_initial_status(status)


@pytest.mark.parametrize("current", list(TaskStatus))
@pytest.mark.parametrize("target", list(TaskStatus))
def test_general_transition_matrix(current: TaskStatus, target: TaskStatus) -> None:
    if (current, target) in GENERAL_TRANSITIONS:
        validate_general_transition(current, target)
    else:
        with pytest.raises(InvalidTaskTransition):
            validate_general_transition(current, target)


def test_running_entry_is_claim_only() -> None:
    with pytest.raises(InvalidTaskTransition):
        validate_general_transition(TaskStatus.QUEUED, TaskStatus.RUNNING)

    validate_claim_transition(TaskStatus.QUEUED)

    for current in set(TaskStatus) - {TaskStatus.QUEUED}:
        with pytest.raises(InvalidTaskTransition):
            validate_claim_transition(current)


@pytest.mark.parametrize("terminal", TERMINAL_STATUSES)
@pytest.mark.parametrize("target", list(TaskStatus))
def test_terminal_states_have_no_outgoing_path(
    terminal: TaskStatus, target: TaskStatus
) -> None:
    with pytest.raises(InvalidTaskTransition):
        validate_general_transition(terminal, target)
