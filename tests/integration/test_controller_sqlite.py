from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
from collections.abc import Callable
from contextlib import closing
from dataclasses import fields, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from forge.controller import start_controller
from forge.controller_protocol import CONTROLLER_PROTOCOL_VERSION
from forge.request_crypto import (
    Aes256GcmRequestCipher,
    EncryptedValue,
    EncryptionError,
    KeyHandle,
    request_body_aad,
)
from forge.sqlite_state import SqliteStateLedger
from forge.state_ledger import (
    EncryptedRequestRecord,
    IdempotencyConflict,
    IngestBundle,
    IngestOutcome,
    NewTaskEvent,
    NewTaskRecord,
    StateError,
    StateTransitionConflict,
    TaskNotFound,
    TaskSnapshot,
)
from forge.task_state import InvalidTaskTransition, TaskStatus


KEY = KeyHandle("key:synthetic", b"K" * 32)
TIMESTAMP = "2026-08-11T00:00:01Z"
EVENT_TIME = "2026-08-11T00:00:00Z"
SECURITY_ENVELOPE = (
    b'{"classification":"private",'
    b'"contractVersion":"forge.dev/security/v1alpha1",'
    b'"createdAt":"2026-08-11T00:00:00Z",'
    b'"objectId":"object:synthetic","objectType":"engineering-request",'
    b'"producerClass":"gateway-adapter",'
    b'"provenanceRef":"provenance:synthetic",'
    b'"retentionHint":"task-lifecycle",'
    b'"taint":["external-input","user-supplied"],"trust":"unknown"}'
)
ALT_SECURITY_ENVELOPE = SECURITY_ENVELOPE.replace(b'"private"', b'"internal"')
PLAINTEXT_SENTINEL = "BODY-PLAINTEXT-SENTINEL-7f3c"


def _digest(value: bytes | str) -> str:
    payload = value.encode("utf-8") if type(value) is str else value
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _bundle(
    number: int,
    *,
    source_event_id: str | None = None,
    repository_ref: str = "repository:synthetic",
    submission_digest: str | None = None,
    event_id: str | None = None,
    ciphertext: bytes | None = None,
) -> IngestBundle:
    request_id = f"req_{number:032x}"
    task_id = f"tsk_{number:032x}"
    return IngestBundle(
        request=EncryptedRequestRecord(
            request_id=request_id,
            protocol_version=CONTROLLER_PROTOCOL_VERSION,
            source_namespace="synthetic-source",
            source_event_id=source_event_id or f"event:{number}",
            source_event_time=EVENT_TIME,
            actor_ref="actor:synthetic",
            channel_ref="channel:synthetic",
            project_ref="project:synthetic",
            repository_ref=repository_ref,
            mode="plan",
            security_envelope=SECURITY_ENVELOPE,
            submission_digest=submission_digest or _digest(f"submission:{number}"),
            body_digest=_digest(f"body:{number}"),
            security_digest=_digest(SECURITY_ENVELOPE),
            encryption_algorithm="AES-256-GCM",
            key_id=KEY.key_id,
            nonce=number.to_bytes(12, "big"),
            ciphertext=ciphertext or bytes([65 + number % 26]) * 32,
            received_at=TIMESTAMP,
        ),
        task=NewTaskRecord(
            task_id=task_id,
            request_id=request_id,
            project_ref="project:synthetic",
            repository_ref=repository_ref,
            mode="plan",
            created_at=TIMESTAMP,
        ),
        event=NewTaskEvent(
            event_id=event_id or f"evt_{number:032x}",
            task_id=task_id,
            previous_status=None,
            next_status=TaskStatus.QUEUED,
            reason_code=None,
            actor_ref="actor:synthetic",
            occurred_at=TIMESTAMP,
        ),
    )


def _initialize(path: Path) -> None:
    SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    ).close()


def _domain_snapshot(path: Path) -> tuple[tuple[str, tuple[tuple[Any, ...], ...]], ...]:
    with closing(sqlite3.connect(path)) as connection:
        tables = ("ledger_metadata", "requests", "tasks", "task_events")
        return tuple(
            (name, tuple(connection.execute(f'SELECT * FROM "{name}" ORDER BY rowid')))
            for name in tables
        )


def _counts(path: Path) -> tuple[int, int, int]:
    with closing(sqlite3.connect(path)) as connection:
        return tuple(
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("requests", "tasks", "task_events")
        )  # type: ignore[return-value]


def _seed_tasks(
    path: Path, specifications: list[tuple[TaskStatus, str]]
) -> list[str]:
    task_ids: list[str] = []
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for sequence, (status, repository_ref) in enumerate(specifications, start=1):
            number = 10_000 + sequence
            request_id = f"req_{number:032x}"
            task_id = f"tsk_{number:032x}"
            event_id = f"evt_{number:032x}"
            connection.execute(
                """
                INSERT INTO requests (
                    request_id, protocol_version, source_namespace,
                    source_event_id, source_event_time, actor_ref, channel_ref,
                    project_ref, repository_ref, mode, security_envelope,
                    submission_digest, body_digest, security_digest,
                    encryption_algorithm, key_id, nonce, ciphertext, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'plan', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    CONTROLLER_PROTOCOL_VERSION,
                    "seed-source",
                    f"seed-event:{sequence}",
                    EVENT_TIME,
                    "actor:seed",
                    "channel:seed",
                    "project:synthetic",
                    repository_ref,
                    SECURITY_ENVELOPE,
                    _digest(f"seed-submission:{sequence}"),
                    _digest(f"seed-body:{sequence}"),
                    _digest(SECURITY_ENVELOPE),
                    "AES-256-GCM",
                    KEY.key_id,
                    sequence.to_bytes(12, "big"),
                    b"C" * 32,
                    TIMESTAMP,
                ),
            )
            connection.execute(
                """
                INSERT INTO tasks (
                    task_id, request_id, project_ref, repository_ref, mode,
                    status, reason_code, queue_sequence, created_at, updated_at
                ) VALUES (?, ?, 'project:synthetic', ?, 'plan', ?, NULL, ?, ?, ?)
                """,
                (task_id, request_id, repository_ref, status.value, sequence, TIMESTAMP, TIMESTAMP),
            )
            connection.execute(
                """
                INSERT INTO task_events (
                    event_id, task_id, previous_status, next_status,
                    reason_code, actor_ref, occurred_at
                ) VALUES (?, ?, NULL, ?, NULL, 'actor:seed', ?)
                """,
                (event_id, task_id, status.value, TIMESTAMP),
            )
            task_ids.append(task_id)
        connection.execute(
            "UPDATE ledger_metadata SET next_queue_sequence = ? WHERE singleton = 1",
            (len(specifications) + 1,),
        )
    return task_ids


def _race(calls: list[Callable[[], object]]) -> tuple[list[object | None], list[Exception | None]]:
    barrier = threading.Barrier(len(calls))
    results: list[object | None] = [None] * len(calls)
    errors: list[Exception | None] = [None] * len(calls)

    def run(index: int) -> None:
        try:
            barrier.wait(timeout=5)
            results[index] = calls[index]()
        except Exception as error:  # captured for assertions in the joining thread
            errors[index] = error

    threads = [threading.Thread(target=run, args=(index,)) for index in range(len(calls))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert all(not thread.is_alive() for thread in threads)
    return results, errors


def test_ingest_commits_linked_rows_replays_original_and_conflicts_without_mutation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.db"
    digest = _digest("stable submission")
    original = _bundle(
        1,
        source_event_id="event:stable",
        submission_digest=digest,
        ciphertext=b"O" * 32,
    )
    replay = _bundle(
        2,
        source_event_id="event:stable",
        submission_digest=digest,
        ciphertext=b"R" * 32,
    )

    with SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    ) as ledger:
        created = ledger.ingest(original)
        replayed = ledger.ingest(replay)
        assert created == IngestOutcome(
            TaskSnapshot(
                request_id=original.request.request_id,
                task_id=original.task.task_id,
                project_ref=original.task.project_ref,
                repository_ref=original.task.repository_ref,
                mode="plan",
                status=TaskStatus.QUEUED,
                reason_code=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            ),
            True,
        )
        assert replayed == IngestOutcome(created.task, False)

        proposal = _bundle(
            20,
            source_event_id="event:stable",
            submission_digest=_digest("changed source event time"),
        )
        changed_security = ALT_SECURITY_ENVELOPE
        conflicts = (
            replace(
                proposal,
                request=replace(proposal.request, source_event_time="2026-08-11T00:00:02Z"),
            ),
            replace(
                proposal,
                request=replace(
                    proposal.request,
                    actor_ref="actor:changed",
                    submission_digest=_digest("changed actor"),
                ),
            ),
            replace(
                proposal,
                request=replace(
                    proposal.request,
                    channel_ref="channel:changed",
                    submission_digest=_digest("changed channel"),
                ),
            ),
            replace(
                proposal,
                request=replace(
                    proposal.request,
                    project_ref="project:changed",
                    submission_digest=_digest("changed project"),
                ),
                task=replace(proposal.task, project_ref="project:changed"),
            ),
            replace(
                proposal,
                request=replace(
                    proposal.request,
                    repository_ref="repository:changed",
                    submission_digest=_digest("changed repository"),
                ),
                task=replace(proposal.task, repository_ref="repository:changed"),
            ),
            replace(
                proposal,
                request=replace(
                    proposal.request,
                    body_digest=_digest("changed body"),
                    submission_digest=_digest("changed body submission"),
                ),
            ),
            replace(
                proposal,
                request=replace(
                    proposal.request,
                    security_envelope=changed_security,
                    security_digest=_digest(changed_security),
                    submission_digest=_digest("changed security"),
                ),
            ),
        )
        for conflicting in conflicts:
            with pytest.raises(
                IdempotencyConflict,
                match=r"^request identity conflicts with durable state$",
            ):
                ledger.ingest(conflicting)

        encrypted = ledger.load_encrypted_request(original.request.request_id)
        assert encrypted == original.request
        assert ledger.load_encrypted_request(replay.request.request_id) is None

    assert _counts(path) == (1, 1, 1)
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT next_queue_sequence FROM ledger_metadata"
        ).fetchone() == (2,)
        assert connection.execute(
            "SELECT previous_status, next_status, reason_code FROM task_events"
        ).fetchone() == (None, "queued", None)
        assert connection.execute(
            "SELECT request_id, ciphertext FROM requests"
        ).fetchone() == (original.request.request_id, b"O" * 32)


def test_ingest_rolls_back_request_task_and_counter_on_late_failures(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.db"
    _initialize(path)
    unrelated_task = _seed_tasks(path, [(TaskStatus.QUEUED, "repository:other")])[0]
    duplicate_event = f"evt_{10_001:032x}"
    before = _domain_snapshot(path)

    ledger = SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    )
    with pytest.raises(StateError, match=r"^state operation failed$"):
        ledger.ingest(_bundle(50, event_id=duplicate_event))
    colliding_task = _bundle(52)
    colliding_task = replace(
        colliding_task,
        task=replace(colliding_task.task, task_id=unrelated_task),
        event=replace(colliding_task.event, task_id=unrelated_task),
    )
    with pytest.raises(StateError, match=r"^state operation failed$"):
        ledger.ingest(colliding_task)
    malformed = _bundle(51)
    malformed = replace(
        malformed,
        request=replace(malformed.request, mode="apply"),
        task=replace(malformed.task, mode="apply"),
    )
    with pytest.raises(StateError, match=r"^state operation failed$"):
        ledger.ingest(malformed)
    assert ledger.get_task(unrelated_task) is not None
    ledger.close()

    assert _domain_snapshot(path) == before


def test_concurrent_equivalent_ingest_creates_once_and_replays_once(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.db"
    digest = _digest("concurrent equivalent")
    first = _bundle(61, source_event_id="event:race", submission_digest=digest)
    second = _bundle(62, source_event_id="event:race", submission_digest=digest)
    ledger = SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    )

    results, errors = _race(
        [lambda: ledger.ingest(first), lambda: ledger.ingest(second)]
    )
    ledger.close()

    assert errors == [None, None]
    outcomes = [result for result in results if isinstance(result, IngestOutcome)]
    assert sorted(outcome.created for outcome in outcomes) == [False, True]
    assert len({outcome.task.task_id for outcome in outcomes}) == 1
    assert _counts(path) == (1, 1, 1)


def test_concurrent_conflicting_ingest_commits_one_and_rejects_one(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.db"
    ledger = SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    )
    first = _bundle(
        71,
        source_event_id="event:conflicting-race",
        submission_digest=_digest("first"),
    )
    second = _bundle(
        72,
        source_event_id="event:conflicting-race",
        submission_digest=_digest("second"),
    )

    results, errors = _race(
        [lambda: ledger.ingest(first), lambda: ledger.ingest(second)]
    )
    ledger.close()

    assert sum(isinstance(result, IngestOutcome) and result.created for result in results) == 1
    assert sum(isinstance(error, IdempotencyConflict) for error in errors) == 1
    assert _counts(path) == (1, 1, 1)


GENERAL_ALLOWED = (
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
)
GENERAL_DISALLOWED = tuple(
    (current, target)
    for current in TaskStatus
    for target in TaskStatus
    if (current, target) not in GENERAL_ALLOWED
)


@pytest.mark.parametrize(("current", "target"), GENERAL_ALLOWED)
def test_general_transition_commits_state_and_matching_event_atomically(
    tmp_path: Path, current: TaskStatus, target: TaskStatus
) -> None:
    path = tmp_path / "state.db"
    _initialize(path)
    task_id = _seed_tasks(path, [(current, "repository:transition")])[0]

    with SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    ) as ledger:
        snapshot = ledger.transition(
            task_id=task_id,
            expected_status=current,
            target_status=target,
            reason_code="transition_test",
            actor_ref="actor:transition",
            event_id=f"evt_{20_001:032x}",
            occurred_at="2026-08-11T00:00:02Z",
        )
        assert snapshot.status is target
        assert snapshot.reason_code == "transition_test"
        assert snapshot.updated_at == "2026-08-11T00:00:02Z"

    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute(
            "SELECT status, reason_code, queue_sequence FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone() == (
            target.value,
            "transition_test",
            2 if target is TaskStatus.QUEUED else 1,
        )
        assert connection.execute(
            """
            SELECT previous_status, next_status, reason_code, actor_ref, occurred_at
            FROM task_events WHERE task_id = ? ORDER BY event_sequence DESC LIMIT 1
            """,
            (task_id,),
        ).fetchone() == (
            current.value,
            target.value,
            "transition_test",
            "actor:transition",
            "2026-08-11T00:00:02Z",
        )
        assert connection.execute("SELECT count(*) FROM task_events").fetchone() == (2,)


@pytest.mark.parametrize(("current", "target"), GENERAL_DISALLOWED)
def test_general_transition_rejects_every_disallowed_pair_without_mutation(
    tmp_path: Path, current: TaskStatus, target: TaskStatus
) -> None:
    path = tmp_path / "state.db"
    _initialize(path)
    task_id = _seed_tasks(path, [(current, "repository:transition")])[0]
    before = _domain_snapshot(path)

    ledger = SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    )
    with pytest.raises(InvalidTaskTransition):
        ledger.transition(
            task_id=task_id,
            expected_status=current,
            target_status=target,
            reason_code=None,
            actor_ref="actor:transition",
            event_id=f"evt_{20_002:032x}",
            occurred_at="2026-08-11T00:00:02Z",
        )
    ledger.close()

    assert _domain_snapshot(path) == before


def test_transition_stale_missing_and_duplicate_event_fail_without_partial_change(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.db"
    _initialize(path)
    task_id = _seed_tasks(path, [(TaskStatus.WAITING_USER, "repository:transition")])[0]
    duplicate_event_id = f"evt_{10_001:032x}"
    missing_id = f"tsk_{999_999:032x}"
    before = _domain_snapshot(path)
    ledger = SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    )

    with pytest.raises(StateTransitionConflict):
        ledger.transition(
            task_id=task_id,
            expected_status=TaskStatus.RUNNING,
            target_status=TaskStatus.FAILED,
            reason_code="stale",
            actor_ref="actor:transition",
            event_id=f"evt_{20_003:032x}",
            occurred_at="2026-08-11T00:00:02Z",
        )
    with pytest.raises(TaskNotFound) as missing:
        ledger.transition(
            task_id=missing_id,
            expected_status=TaskStatus.QUEUED,
            target_status=TaskStatus.FAILED,
            reason_code="missing",
            actor_ref="actor:transition",
            event_id=f"evt_{20_004:032x}",
            occurred_at="2026-08-11T00:00:02Z",
        )
    assert missing_id not in str(missing.value)
    with pytest.raises(StateError, match=r"^state operation failed$"):
        ledger.transition(
            task_id=task_id,
            expected_status=TaskStatus.WAITING_USER,
            target_status=TaskStatus.QUEUED,
            reason_code="reply_received",
            actor_ref="actor:transition",
            event_id=duplicate_event_id,
            occurred_at="2026-08-11T00:00:02Z",
        )
    ledger.close()

    assert _domain_snapshot(path) == before


@pytest.mark.parametrize("max_concurrency", [1, 2, 3])
def test_claim_honors_each_configured_positive_capacity(
    tmp_path: Path, max_concurrency: int
) -> None:
    path = tmp_path / "state.db"
    _initialize(path)
    _seed_tasks(
        path,
        [(TaskStatus.QUEUED, f"repository:{number}") for number in range(4)],
    )
    ledger = SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    )

    outcomes = [
        ledger.claim_next_eligible(
            max_concurrency=max_concurrency,
            actor_ref="executor:synthetic",
            event_id=f"evt_{30_000 + number:032x}",
            occurred_at="2026-08-11T00:00:03Z",
        )
        for number in range(max_concurrency + 1)
    ]
    ledger.close()

    assert all(outcome is not None for outcome in outcomes[:max_concurrency])
    assert outcomes[-1] is None
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute(
            "SELECT count(*) FROM tasks WHERE status = 'running'"
        ).fetchone() == (max_concurrency,)
        assert connection.execute(
            "SELECT count(*) FROM tasks WHERE status = 'queued'"
        ).fetchone() == (4 - max_concurrency,)


def test_claim_uses_eligible_fifo_and_requeue_tail_with_defensive_repository_index(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.db"
    _initialize(path)
    task_ids = _seed_tasks(
        path,
        [
            (TaskStatus.QUEUED, "repository:a"),
            (TaskStatus.QUEUED, "repository:a"),
            (TaskStatus.QUEUED, "repository:b"),
            (TaskStatus.QUEUED, "repository:c"),
        ],
    )
    ledger = SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    )

    first = ledger.claim_next_eligible(
        max_concurrency=2,
        actor_ref="executor:one",
        event_id=f"evt_{31_001:032x}",
        occurred_at="2026-08-11T00:00:03Z",
    )
    second = ledger.claim_next_eligible(
        max_concurrency=2,
        actor_ref="executor:two",
        event_id=f"evt_{31_002:032x}",
        occurred_at="2026-08-11T00:00:03Z",
    )
    full = ledger.claim_next_eligible(
        max_concurrency=2,
        actor_ref="executor:overflow",
        event_id=f"evt_{31_003:032x}",
        occurred_at="2026-08-11T00:00:03Z",
    )
    assert first is not None and first.task_id == task_ids[0]
    assert second is not None and second.task_id == task_ids[2]
    assert full is None
    ledger.transition(
        task_id=task_ids[0],
        expected_status=TaskStatus.RUNNING,
        target_status=TaskStatus.COMPLETED,
        reason_code=None,
        actor_ref="executor:one",
        event_id=f"evt_{31_004:032x}",
        occurred_at="2026-08-11T00:00:04Z",
    )
    newly_eligible = ledger.claim_next_eligible(
        max_concurrency=2,
        actor_ref="executor:three",
        event_id=f"evt_{31_005:032x}",
        occurred_at="2026-08-11T00:00:05Z",
    )
    assert newly_eligible is not None and newly_eligible.task_id == task_ids[1]
    ledger.close()

    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute(
            "SELECT task_id, status FROM tasks ORDER BY queue_sequence"
        ).fetchall() == [
            (task_ids[0], "completed"),
            (task_ids[1], "running"),
            (task_ids[2], "running"),
            (task_ids[3], "queued"),
        ]
        with pytest.raises(sqlite3.IntegrityError):
            with connection:
                connection.execute(
                    "UPDATE tasks SET status = 'running' WHERE task_id = ?",
                    (task_ids[0],),
                )


@pytest.mark.parametrize("invalid", [True, 0, -1])
def test_invalid_claim_capacity_fails_before_transaction_mutation(
    tmp_path: Path, invalid: object
) -> None:
    path = tmp_path / "state.db"
    _initialize(path)
    _seed_tasks(path, [(TaskStatus.QUEUED, "repository:a")])
    before = _domain_snapshot(path)
    ledger = SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    )

    with pytest.raises(StateError, match=r"^state operation failed$"):
        ledger.claim_next_eligible(
            max_concurrency=invalid,  # type: ignore[arg-type]
            actor_ref="executor:synthetic",
            event_id=f"evt_{32_001:032x}",
            occurred_at="2026-08-11T00:00:03Z",
        )
    ledger.close()

    assert _domain_snapshot(path) == before


def test_competing_claims_preserve_global_and_repository_limits_and_make_progress(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.db"
    _initialize(path)
    task_ids = _seed_tasks(
        path,
        [
            (TaskStatus.QUEUED, "repository:a"),
            (TaskStatus.QUEUED, "repository:a"),
            (TaskStatus.QUEUED, "repository:b"),
            (TaskStatus.QUEUED, "repository:b"),
            (TaskStatus.QUEUED, "repository:c"),
            (TaskStatus.QUEUED, "repository:c"),
        ],
    )
    ledger = SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    )
    calls = [
        (
            lambda number=number: ledger.claim_next_eligible(
                max_concurrency=2,
                actor_ref=f"executor:{number}",
                event_id=f"evt_{40_000 + number:032x}",
                occurred_at="2026-08-11T00:00:04Z",
            )
        )
        for number in range(4)
    ]

    results, errors = _race(calls)
    assert errors == [None] * 4
    claimed = [result for result in results if isinstance(result, TaskSnapshot)]
    assert len(claimed) == 2
    assert len({task.repository_ref for task in claimed}) == 2
    assert {task.task_id for task in claimed} == {task_ids[0], task_ids[2]}

    freed = claimed[0]
    ledger.transition(
        task_id=freed.task_id,
        expected_status=TaskStatus.RUNNING,
        target_status=TaskStatus.COMPLETED,
        reason_code=None,
        actor_ref="executor:finished",
        event_id=f"evt_{40_010:032x}",
        occurred_at="2026-08-11T00:00:05Z",
    )
    later, later_errors = _race(
        [
            lambda: ledger.claim_next_eligible(
                max_concurrency=2,
                actor_ref="executor:later-one",
                event_id=f"evt_{40_011:032x}",
                occurred_at="2026-08-11T00:00:06Z",
            ),
            lambda: ledger.claim_next_eligible(
                max_concurrency=2,
                actor_ref="executor:later-two",
                event_id=f"evt_{40_012:032x}",
                occurred_at="2026-08-11T00:00:06Z",
            ),
        ]
    )
    assert later_errors == [None, None]
    assert sum(isinstance(item, TaskSnapshot) for item in later) == 1
    ledger.close()

    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute(
            "SELECT repository_ref, status FROM tasks ORDER BY queue_sequence"
        ).fetchall()
        running_repositories = [repo for repo, status in rows if status == "running"]
        assert len(running_repositories) == 2
        assert len(set(running_repositories)) == 2
        assert sum(status == "queued" for _, status in rows) == 3
        assert connection.execute(
            "SELECT count(*) FROM task_events WHERE previous_status = 'queued' AND next_status = 'running'"
        ).fetchone() == (3,)


def test_competing_claims_for_one_repository_claim_exactly_one(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.db"
    _initialize(path)
    _seed_tasks(
        path,
        [(TaskStatus.QUEUED, "repository:one") for _ in range(6)],
    )
    ledger = SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    )
    results, errors = _race(
        [
            (
                lambda number=number: ledger.claim_next_eligible(
                    max_concurrency=4,
                    actor_ref=f"executor:{number}",
                    event_id=f"evt_{41_000 + number:032x}",
                    occurred_at="2026-08-11T00:00:04Z",
                )
            )
            for number in range(4)
        ]
    )
    ledger.close()

    assert errors == [None] * 4
    assert sum(isinstance(item, TaskSnapshot) for item in results) == 1
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute(
            "SELECT count(*) FROM tasks WHERE status = 'running'"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM tasks WHERE status = 'queued'"
        ).fetchone() == (5,)


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 11, 0, 0, 10, tzinfo=UTC)


class _SequenceIds:
    def __init__(self) -> None:
        self.request_number = 50_000
        self.task_number = 60_000
        self.event_number = 70_000

    def new_request_id(self) -> str:
        self.request_number += 1
        return f"req_{self.request_number:032x}"

    def new_task_id(self) -> str:
        self.task_number += 1
        return f"tsk_{self.task_number:032x}"

    def new_event_id(self) -> str:
        self.event_number += 1
        return f"evt_{self.event_number:032x}"


def _submit_payload(
    *, source_event_id: str, repository_ref: str, body: str
) -> bytes:
    document = {
        "protocolVersion": CONTROLLER_PROTOCOL_VERSION,
        "operation": "submitRequest",
        "request": {
            "sourceNamespace": "vertical-source",
            "sourceEventId": source_event_id,
            "sourceEventTime": EVENT_TIME,
            "actorRef": "actor:vertical",
            "channelRef": "channel:vertical",
            "projectRef": "project:vertical",
            "repositoryRef": repository_ref,
            "mode": "plan",
            "body": body,
            "security": {
                "contractVersion": "forge.dev/security/v1alpha1",
                "objectId": "object:vertical",
                "objectType": "engineering-request",
                "createdAt": EVENT_TIME,
                "trust": "unknown",
                "taint": ["external-input", "user-supplied"],
                "provenanceRef": "provenance:vertical-private",
                "producerClass": "gateway-adapter",
                "classification": "private",
                "retentionHint": "task-lifecycle",
            },
        },
    }
    return json.dumps(document, separators=(",", ":")).encode("utf-8")


def _get_payload(task_id: str) -> bytes:
    return json.dumps(
        {
            "protocolVersion": CONTROLLER_PROTOCOL_VERSION,
            "operation": "getTask",
            "taskId": task_id,
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _decode(payload: bytes) -> dict[str, Any]:
    document = json.loads(payload)
    assert type(document) is dict
    return document


def _state_file_contents(path: Path) -> tuple[bytes, ...]:
    return tuple(
        candidate.read_bytes()
        for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm"))
        if candidate.exists()
    )


def test_real_controller_sqlite_vertical_path_encrypts_replays_schedules_and_recovers(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    path = tmp_path / "private-state.db"
    key = KeyHandle("key:vertical", b"V" * 32)
    cipher = Aes256GcmRequestCipher()
    ids = _SequenceIds()
    body = f"{PLAINTEXT_SENTINEL} private-location={path}"
    first_payload = _submit_payload(
        source_event_id="event:vertical-one",
        repository_ref="repository:vertical-one",
        body=body,
    )
    second_payload = _submit_payload(
        source_event_id="event:vertical-two",
        repository_ref="repository:vertical-two",
        body="queued synthetic work",
    )
    ledger = SqliteStateLedger.open(path, cipher=cipher, key_handle=key)
    service = start_controller(
        ledger=ledger,
        cipher=cipher,
        key_handle=key,
        max_concurrency=2,
        clock=_FixedClock(),
        ids=ids,
    )

    created_bytes = service.handle(first_payload)
    created = _decode(created_bytes)
    assert created["ok"] is True
    assert created["result"]["disposition"] == "created"
    request_id = created["result"]["requestId"]
    task_id = created["result"]["taskId"]
    get_before_bytes = service.handle(_get_payload(task_id))
    assert _decode(get_before_bytes)["result"] == {
        "requestId": request_id,
        "taskId": task_id,
        "mode": "plan",
        "status": "queued",
        "createdAt": "2026-08-11T00:00:10Z",
        "updatedAt": "2026-08-11T00:00:10Z",
    }

    replay_bytes = service.handle(first_payload)
    replay = _decode(replay_bytes)
    assert replay["result"] == {
        "requestId": request_id,
        "taskId": task_id,
        "status": "queued",
        "disposition": "replayed",
    }
    changed_body = first_payload.replace(
        PLAINTEXT_SENTINEL.encode("utf-8"), b"different-body"
    )
    conflict_bytes = service.handle(changed_body)
    assert _decode(conflict_bytes)["error"] == {
        "code": "idempotency_conflict",
        "message": "request identity conflicts with durable state",
    }

    queued_bytes = service.handle(second_payload)
    queued = _decode(queued_bytes)
    queued_task_id = queued["result"]["taskId"]
    claimed = service.claim_next_eligible(actor_ref="executor:in-process")
    assert claimed is not None and claimed.task_id == task_id

    encrypted = ledger.load_encrypted_request(request_id)
    assert encrypted is not None
    assert "body" not in {field.name for field in fields(encrypted)}
    assert not any("decrypt" in name for name in dir(ledger))
    assert not any("decrypt" in name for name in dir(service))
    assert not hasattr(service, "_executor")
    aad = request_body_aad(
        encrypted.protocol_version,
        encrypted.request_id,
        encrypted.source_namespace,
        encrypted.source_event_id,
        encrypted.project_ref,
        encrypted.repository_ref,
        encrypted.body_digest,
        encrypted.security_digest,
        encrypted.encryption_algorithm,
        encrypted.key_id,
    )
    assert cipher.decrypt(
        EncryptedValue(encrypted.nonce, encrypted.ciphertext), aad, key
    ) == body.encode("utf-8")
    with pytest.raises(EncryptionError, match=r"^encryption operation failed$"):
        cipher.decrypt(
            EncryptedValue(encrypted.nonce, encrypted.ciphertext), aad + b" ", key
        )

    open_files = _state_file_contents(path)
    assert open_files
    assert all(PLAINTEXT_SENTINEL.encode("utf-8") not in data for data in open_files)
    service.close()
    closed_files = _state_file_contents(path)
    assert all(PLAINTEXT_SENTINEL.encode("utf-8") not in data for data in closed_files)
    with closing(sqlite3.connect(path)) as checkpoint:
        checkpoint.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    checkpointed_files = _state_file_contents(path)
    assert all(
        PLAINTEXT_SENTINEL.encode("utf-8") not in data for data in checkpointed_files
    )

    reopened_ledger = SqliteStateLedger.open(path, cipher=cipher, key_handle=key)
    restarted = start_controller(
        ledger=reopened_ledger,
        cipher=cipher,
        key_handle=key,
        max_concurrency=2,
        clock=_FixedClock(),
        ids=ids,
    )
    failed_bytes = restarted.handle(_get_payload(task_id))
    queued_after_bytes = restarted.handle(_get_payload(queued_task_id))
    assert _decode(failed_bytes)["result"]["status"] == "failed"
    assert _decode(failed_bytes)["result"]["reasonCode"] == "controller_restart"
    assert _decode(queued_after_bytes)["result"]["status"] == "queued"
    assert reopened_ledger.get_task(task_id).status is TaskStatus.FAILED
    assert reopened_ledger.get_task(queued_task_id).status is TaskStatus.QUEUED
    restarted.close()

    public_material = b"\n".join(
        (
            created_bytes,
            get_before_bytes,
            replay_bytes,
            conflict_bytes,
            queued_bytes,
            failed_bytes,
            queued_after_bytes,
            repr(encrypted).encode("utf-8"),
            repr(service).encode("utf-8"),
            caplog.text.encode("utf-8"),
        )
    )
    for forbidden in (
        body.encode("utf-8"),
        b"provenance:vertical-private",
        key.key_id.encode("utf-8"),
        key.key_bytes,
        key.key_bytes.hex().encode("ascii"),
        encrypted.nonce,
        encrypted.nonce.hex().encode("ascii"),
        encrypted.ciphertext,
        encrypted.ciphertext.hex().encode("ascii"),
        str(path).encode("utf-8"),
        b"database is locked",
        b"InvalidTag",
        b"sqlite3",
        b"cryptography",
    ):
        assert forbidden not in public_material

    durable_material = b"".join(_state_file_contents(path))
    for forbidden in (
        PLAINTEXT_SENTINEL.encode("utf-8"),
        str(path).encode("utf-8"),
        key.key_bytes,
        key.key_bytes.hex().encode("ascii"),
        b"database is locked",
        b"InvalidTag",
    ):
        assert forbidden not in durable_material
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute(
            "SELECT count(*) FROM requests"
        ).fetchone() == (2,)
        assert connection.execute(
            "SELECT count(*) FROM tasks WHERE status = 'running'"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM tasks WHERE status = 'queued'"
        ).fetchone() == (1,)
