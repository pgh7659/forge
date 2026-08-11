from __future__ import annotations

import logging
import re
import selectors
import sqlite3
import subprocess
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from forge.controller import start_controller
from forge.request_crypto import (
    Aes256GcmRequestCipher,
    EncryptedValue,
    EncryptionError,
    KeyHandle,
    RequestCipher,
    state_key_verifier_aad,
)
from forge.sqlite_state import SqliteStateLedger
from forge.state_ledger import ControllerAlreadyRunning, StateError
from forge.task_state import TaskStatus


KEY = KeyHandle("key:synthetic", b"K" * 32)
VERIFIER_PLAINTEXT = b"forge-state-key-verifier/v1"
OCCURRED_AT = "2026-08-11T00:00:02Z"
APPLICATION_TABLES = {
    "ledger_metadata",
    "requests",
    "tasks",
    "task_events",
}
EXPLICIT_INDEXES = {
    "ux_tasks_running_repository",
    "ix_tasks_queue",
    "ix_task_events_task_sequence",
}


def _normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip().rstrip(";")).casefold()


def _read_connection(path: Path) -> closing[sqlite3.Connection]:
    return closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True))


def _index_columns(connection: sqlite3.Connection, index_name: str) -> tuple[str, ...]:
    quoted = index_name.replace('"', '""')
    return tuple(
        row[2]
        for row in connection.execute(f'PRAGMA index_xinfo("{quoted}")')
        if row[5] == 1
    )


def _index_signatures(
    connection: sqlite3.Connection, table_name: str
) -> Counter[tuple[int, str, int, tuple[str, ...]]]:
    quoted = table_name.replace('"', '""')
    return Counter(
        (
            row[2],
            row[3],
            row[4],
            _index_columns(connection, row[1]),
        )
        for row in connection.execute(f'PRAGMA index_list("{quoted}")')
    )


def _application_definitions(path: Path) -> tuple[tuple[Any, ...], ...]:
    with closing(sqlite3.connect(path)) as connection:
        return tuple(
            connection.execute(
                """
                SELECT type, name, tbl_name, sql
                FROM sqlite_schema
                WHERE name NOT LIKE 'sqlite_%'
                ORDER BY type, name
                """
            )
        )


def _domain_rows(path: Path) -> tuple[tuple[str, tuple[tuple[Any, ...], ...]], ...]:
    with closing(sqlite3.connect(path)) as connection:
        tables = tuple(
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_schema
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            )
        )
        result: list[tuple[str, tuple[tuple[Any, ...], ...]]] = []
        for table_name in tables:
            quoted = table_name.replace('"', '""')
            rows = tuple(connection.execute(f'SELECT * FROM "{quoted}" ORDER BY rowid'))
            result.append((table_name, rows))
        return tuple(result)


def _database_snapshot(path: Path) -> tuple[int, tuple[Any, ...], tuple[Any, ...]]:
    with closing(sqlite3.connect(path)) as connection:
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
    return user_version, _application_definitions(path), _domain_rows(path)


def _seed_tasks(path: Path, statuses: list[TaskStatus]) -> list[dict[str, str]]:
    seeded: list[dict[str, str]] = []
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for index, status in enumerate(statuses, start=1):
            request_id = f"req_{index:032x}"
            task_id = f"tsk_{index:032x}"
            event_id = f"evt_{index:032x}"
            repository_ref = f"repository:{index}"
            timestamp = f"2026-08-11T00:00:{index:02d}Z"
            reason_code = "seeded_terminal" if status in {
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            } else None
            connection.execute(
                """
                INSERT INTO requests (
                    request_id, protocol_version, source_namespace,
                    source_event_id, source_event_time, actor_ref, channel_ref,
                    project_ref, repository_ref, mode, security_envelope,
                    submission_digest, body_digest, security_digest,
                    encryption_algorithm, key_id, nonce, ciphertext, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    "forge.dev/controller/v1alpha1",
                    "source:test",
                    f"delivery:{index}",
                    timestamp,
                    "actor:test",
                    "channel:test",
                    "project:test",
                    repository_ref,
                    "plan",
                    b"{}",
                    f"submission:{index}",
                    f"body:{index}",
                    f"security:{index}",
                    "AES-256-GCM",
                    KEY.key_id,
                    b"N" * 12,
                    b"C" * 16,
                    timestamp,
                ),
            )
            connection.execute(
                """
                INSERT INTO tasks (
                    task_id, request_id, project_ref, repository_ref, mode,
                    status, reason_code, queue_sequence, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    request_id,
                    "project:test",
                    repository_ref,
                    "plan",
                    status.value,
                    reason_code,
                    index,
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                """
                INSERT INTO task_events (
                    event_id, task_id, previous_status, next_status,
                    reason_code, actor_ref, occurred_at
                ) VALUES (?, ?, NULL, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    task_id,
                    status.value,
                    reason_code,
                    "actor:seed",
                    timestamp,
                ),
            )
            seeded.append(
                {
                    "request_id": request_id,
                    "task_id": task_id,
                    "event_id": event_id,
                    "status": status.value,
                    "reason_code": reason_code or "",
                    "updated_at": timestamp,
                }
            )
    return seeded


def _create_database(path: Path) -> None:
    SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    ).close()


class _RecordingCursor:
    def __init__(self, cursor: sqlite3.Cursor, replacement: object | None) -> None:
        self._cursor = cursor
        self._replacement = replacement

    def fetchone(self) -> tuple[object, ...] | None:
        row = self._cursor.fetchone()
        if row is not None and self._replacement is not None:
            return (self._replacement, *row[1:])
        return row

    def __iter__(self) -> Iterator[tuple[Any, ...]]:
        return iter(self._cursor)

    def __getattr__(self, name: str) -> object:
        return getattr(self._cursor, name)


class _RecordingConnection:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        wrong_pragma: str | None = None,
        wrong_value: object | None = None,
    ) -> None:
        self._connection = connection
        self.statements: list[str] = []
        self.closed = False
        self._wrong_pragma = wrong_pragma
        self._wrong_value = wrong_value

    @staticmethod
    def _normalized(statement: str) -> str:
        normalized = re.sub(r"\s+", " ", statement.strip()).casefold()
        return re.sub(r"\s*=\s*", "=", normalized)

    def execute(
        self, statement: str, parameters: tuple[object, ...] = ()
    ) -> _RecordingCursor:
        normalized = self._normalized(statement)
        self.statements.append(normalized)
        cursor = self._connection.execute(statement, parameters)
        replacement = (
            self._wrong_value if normalized == self._wrong_pragma else None
        )
        return _RecordingCursor(cursor, replacement)

    def close(self) -> None:
        self.closed = True
        self._connection.close()

    def __getattr__(self, name: str) -> object:
        return getattr(self._connection, name)


def _patch_recording_connect(
    monkeypatch: pytest.MonkeyPatch,
    *,
    wrong_pragma: str | None = None,
    wrong_value: object | None = None,
) -> tuple[Callable[..., sqlite3.Connection], list[_RecordingConnection]]:
    from forge import sqlite_state

    real_connect = sqlite3.connect
    created: list[_RecordingConnection] = []

    def recording_connect(*args: object, **kwargs: object) -> _RecordingConnection:
        wrapper = _RecordingConnection(
            real_connect(*args, **kwargs),
            wrong_pragma=wrong_pragma,
            wrong_value=wrong_value,
        )
        created.append(wrapper)
        return wrapper

    monkeypatch.setattr(sqlite_state.sqlite3, "connect", recording_connect)
    return real_connect, created


def test_new_database_uses_exact_schema_durable_settings_and_key_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.db"
    real_connect, created = _patch_recording_connect(monkeypatch)

    with SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    ):
        assert path.is_file()

    assert path.is_file()
    assert len(created) == 1
    assert created[0].closed

    statements = created[0].statements
    begin_index = statements.index("begin immediate")
    required_pragmas = (
        ("pragma busy_timeout=0", "pragma busy_timeout"),
        ("pragma foreign_keys=on", "pragma foreign_keys"),
        ("pragma main.locking_mode=exclusive", "pragma main.locking_mode"),
        ("pragma main.journal_mode=wal", "pragma main.journal_mode"),
        ("pragma main.synchronous=full", "pragma main.synchronous"),
    )
    for setting, readback in required_pragmas:
        assert statements.index(setting) < statements.index(readback) < begin_index

    with closing(real_connect(f"file:{path}?mode=ro", uri=True)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        objects = tuple(
            connection.execute(
                """
                SELECT type, name
                FROM sqlite_schema
                WHERE name NOT LIKE 'sqlite_%'
                ORDER BY type, name
                """
            )
        )
        assert {name for object_type, name in objects if object_type == "table"} == (
            APPLICATION_TABLES
        )
        assert {name for object_type, name in objects if object_type == "index"} == (
            EXPLICIT_INDEXES
        )

        assert _index_signatures(connection, "requests") == Counter(
            {
                (1, "pk", 0, ("request_id",)): 1,
                (1, "u", 0, ("source_namespace", "source_event_id")): 1,
            }
        )
        assert _index_signatures(connection, "tasks") == Counter(
            {
                (1, "pk", 0, ("task_id",)): 1,
                (1, "u", 0, ("request_id",)): 1,
                (1, "u", 0, ("queue_sequence",)): 1,
                (1, "c", 1, ("repository_ref",)): 1,
                (0, "c", 0, ("status", "queue_sequence", "task_id")): 1,
            }
        )
        assert _index_signatures(connection, "task_events") == Counter(
            {
                (1, "u", 0, ("event_id",)): 1,
                (0, "c", 0, ("task_id", "event_sequence")): 1,
            }
        )

        metadata = connection.execute(
            """
            SELECT singleton, active_key_id, encryption_algorithm,
                   verifier_nonce, verifier_ciphertext, next_queue_sequence
            FROM ledger_metadata
            """
        ).fetchone()
        assert metadata is not None
        assert metadata[:3] == (1, KEY.key_id, "AES-256-GCM")
        assert len(metadata[3]) == 12
        assert len(metadata[4]) >= 16
        assert metadata[5] == 1
        assert Aes256GcmRequestCipher().decrypt(
            EncryptedValue(nonce=metadata[3], ciphertext=metadata[4]),
            state_key_verifier_aad("AES-256-GCM", KEY.key_id),
            KEY,
        ) == VERIFIER_PLAINTEXT


@pytest.mark.parametrize(
    ("readback", "wrong_value"),
    [
        ("pragma busy_timeout", 1),
        ("pragma foreign_keys", 0),
        ("pragma main.locking_mode", "normal"),
        ("pragma main.journal_mode", "delete"),
        ("pragma main.synchronous", 1),
    ],
)
def test_open_fails_closed_when_a_required_pragma_readback_is_wrong(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    readback: str,
    wrong_value: object,
) -> None:
    path = tmp_path / "state.db"
    _, created = _patch_recording_connect(
        monkeypatch, wrong_pragma=readback, wrong_value=wrong_value
    )

    with pytest.raises(StateError, match=r"^state operation failed$"):
        SqliteStateLedger.open(
            path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
        )

    assert len(created) == 1
    assert created[0].closed


def _new_unversioned_database_with_unexpected_table(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("CREATE TABLE unexpected (value TEXT NOT NULL)")
        connection.execute("INSERT INTO unexpected VALUES ('preserve-me')")


def _valid_database_with_user_version_two(path: Path) -> None:
    _create_database(path)
    _seed_tasks(path, [TaskStatus.QUEUED])
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA user_version=2")


def _valid_database_missing_index(path: Path) -> None:
    _create_database(path)
    _seed_tasks(path, [TaskStatus.QUEUED])
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("DROP INDEX ix_tasks_queue")


def _rewrite_schema_sql(path: Path, object_name: str, old: str, new: str) -> None:
    with closing(sqlite3.connect(path)) as connection, connection:
        schema_version = connection.execute("PRAGMA schema_version").fetchone()[0]
        connection.execute("PRAGMA writable_schema=ON")
        cursor = connection.execute(
            """
            UPDATE sqlite_schema
            SET sql = replace(sql, ?, ?)
            WHERE name = ?
            """,
            (old, new, object_name),
        )
        assert cursor.rowcount == 1
        connection.execute("PRAGMA writable_schema=OFF")
        connection.execute(f"PRAGMA schema_version={schema_version + 1}")


def _valid_database_with_changed_task_column(path: Path) -> None:
    _create_database(path)
    _seed_tasks(path, [TaskStatus.QUEUED])
    _rewrite_schema_sql(
        path,
        "tasks",
        "project_ref TEXT NOT NULL",
        "project_ref BLOB",
    )


def _valid_database_with_changed_foreign_key(path: Path) -> None:
    _create_database(path)
    _seed_tasks(path, [TaskStatus.QUEUED])
    _rewrite_schema_sql(
        path,
        "tasks",
        "ON UPDATE RESTRICT ON DELETE RESTRICT",
        "ON UPDATE RESTRICT ON DELETE CASCADE",
    )


def _valid_database_with_non_partial_running_index(path: Path) -> None:
    _create_database(path)
    _seed_tasks(path, [TaskStatus.QUEUED])
    _rewrite_schema_sql(
        path,
        "ux_tasks_running_repository",
        " WHERE status = 'running'",
        "",
    )


def _valid_database_with_extra_object(path: Path) -> None:
    _create_database(path)
    _seed_tasks(path, [TaskStatus.QUEUED])
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("CREATE INDEX extra_tasks_index ON tasks(project_ref)")


@pytest.mark.parametrize(
    "prepare",
    [
        _new_unversioned_database_with_unexpected_table,
        _valid_database_with_user_version_two,
        _valid_database_missing_index,
        _valid_database_with_changed_task_column,
        _valid_database_with_changed_foreign_key,
        _valid_database_with_non_partial_running_index,
        _valid_database_with_extra_object,
    ],
    ids=[
        "unversioned-unexpected-table",
        "future-version",
        "missing-index",
        "changed-column",
        "changed-foreign-key",
        "non-partial-running-index",
        "extra-object",
    ],
)
def test_schema_mismatch_fails_closed_without_mutating_schema_or_domain_rows(
    tmp_path: Path, prepare: Callable[[Path], None]
) -> None:
    path = tmp_path / "state.db"
    prepare(path)
    before = _database_snapshot(path)

    with pytest.raises(StateError, match=r"^state operation failed$"):
        SqliteStateLedger.open(
            path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
        )

    assert _database_snapshot(path) == before


class _DifferentAlgorithmCipher:
    algorithm = "synthetic-different-algorithm"

    def encrypt(
        self, plaintext: bytes, associated_data: bytes, key: KeyHandle
    ) -> EncryptedValue:
        raise AssertionError("algorithm mismatch must fail before encryption")

    def decrypt(
        self, value: EncryptedValue, associated_data: bytes, key: KeyHandle
    ) -> bytes:
        raise AssertionError("algorithm mismatch must fail before decryption")


def test_reopen_authenticates_the_same_key_pair(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    _create_database(path)

    with SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    ) as ledger:
        ledger.assert_encryption_binding(
            cipher=Aes256GcmRequestCipher(), key_handle=KEY
        )


@pytest.mark.parametrize(
    "case",
    [
        "wrong-key-bytes",
        "wrong-key-id",
        "different-algorithm",
        "modified-verifier-nonce",
        "modified-verifier-ciphertext",
    ],
)
def test_reopen_rejects_wrong_or_tampered_key_binding_without_leakage_or_row_loss(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    case: str,
) -> None:
    path = tmp_path / "state.db"
    _create_database(path)
    _seed_tasks(path, [TaskStatus.RUNNING])
    cipher: RequestCipher = Aes256GcmRequestCipher()
    key = KEY
    if case == "wrong-key-bytes":
        key = KeyHandle(KEY.key_id, b"B" * 32)
    elif case == "wrong-key-id":
        key = KeyHandle("key:different", KEY.key_bytes)
    elif case == "different-algorithm":
        cipher = _DifferentAlgorithmCipher()
    elif case == "modified-verifier-nonce":
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute(
                "UPDATE ledger_metadata SET verifier_nonce = ? WHERE singleton = 1",
                (b"T" * 12,),
            )
    else:
        with closing(sqlite3.connect(path)) as connection, connection:
            ciphertext = bytearray(
                connection.execute(
                    "SELECT verifier_ciphertext FROM ledger_metadata WHERE singleton = 1"
                ).fetchone()[0]
            )
            ciphertext[-1] ^= 1
            connection.execute(
                "UPDATE ledger_metadata SET verifier_ciphertext = ? WHERE singleton = 1",
                (bytes(ciphertext),),
            )
    before_rows = _domain_rows(path)
    with closing(sqlite3.connect(path)) as connection:
        nonce, ciphertext = connection.execute(
            "SELECT verifier_nonce, verifier_ciphertext FROM ledger_metadata"
        ).fetchone()
    real_connect, created = _patch_recording_connect(monkeypatch)
    caplog.set_level(logging.DEBUG)

    with pytest.raises((EncryptionError, StateError)) as captured:
        SqliteStateLedger.open(path, cipher=cipher, key_handle=key)

    assert str(captured.value) in {
        "encryption operation failed",
        "state operation failed",
    }
    assert len(created) == 1
    assert created[0].closed
    from forge import sqlite_state

    monkeypatch.setattr(sqlite_state.sqlite3, "connect", real_connect)
    assert _domain_rows(path) == before_rows
    output = str(captured.value) + caplog.text
    forbidden = (
        KEY.key_id,
        key.key_id,
        KEY.key_bytes.hex(),
        key.key_bytes.hex(),
        nonce.hex(),
        ciphertext.hex(),
        str(path),
        "InvalidTag",
        "database is locked",
        "constraint failed",
    )
    assert all(value not in output for value in forbidden)


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 11, 0, 0, 2, tzinfo=UTC)


class _UnexpectedIds:
    def new_request_id(self) -> str:
        raise AssertionError("request IDs are not used during startup")

    def new_task_id(self) -> str:
        raise AssertionError("task IDs are not used during startup")

    def new_event_id(self) -> str:
        raise AssertionError("reconciliation must not run after binding failure")


def test_controller_reauthenticates_exact_key_pair_before_reconciliation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.db"
    _create_database(path)
    _seed_tasks(path, [TaskStatus.RUNNING])
    before_rows = _domain_rows(path)
    ledger = SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    )
    wrong_key = KeyHandle(KEY.key_id, b"B" * 32)

    with pytest.raises((EncryptionError, StateError)):
        start_controller(
            ledger=ledger,
            cipher=Aes256GcmRequestCipher(),
            key_handle=wrong_key,
            max_concurrency=1,
            clock=_FixedClock(),
            ids=_UnexpectedIds(),
        )

    assert _domain_rows(path) == before_rows
    SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    ).close()


def _start_holder(path: Path) -> subprocess.Popen[str]:
    root = Path(__file__).parents[2]
    process = subprocess.Popen(
        [
            str(root / ".venv" / "bin" / "python"),
            str(root / "tests" / "helpers" / "hold_sqlite_ledger.py"),
            str(path),
        ],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        assert selector.select(timeout=5), "holder did not report readiness within 5s"
        assert process.stdout.readline().strip() == "ready"
    except BaseException:
        _terminate_holder(process)
        raise
    finally:
        selector.close()
    return process


def _stop_holder_cleanly(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    assert process.stdin is not None
    process.stdin.write("\n")
    process.stdin.flush()
    process.communicate(timeout=5)


def _terminate_holder(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)


def test_exclusive_ownership_rejects_a_second_process_and_releases_on_close(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.db"
    process = _start_holder(path)
    try:
        started = time.monotonic()
        with pytest.raises(ControllerAlreadyRunning):
            SqliteStateLedger.open(
                path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
            )
        assert time.monotonic() - started < 1.0
        _stop_holder_cleanly(process)
        assert process.returncode == 0
        SqliteStateLedger.open(
            path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
        ).close()
    finally:
        _terminate_holder(process)


def test_exclusive_ownership_is_released_when_the_owner_process_is_terminated(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.db"
    process = _start_holder(path)
    try:
        process.terminate()
        process.wait(timeout=5)
        SqliteStateLedger.open(
            path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
        ).close()
    finally:
        _terminate_holder(process)


def _event_id_iterator(values: list[str]) -> Callable[[], str]:
    iterator: Iterator[str] = iter(values)
    return iterator.__next__


def test_reconcile_running_atomically_fails_only_running_tasks(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    _create_database(path)
    statuses = [
        TaskStatus.RUNNING,
        TaskStatus.QUEUED,
        TaskStatus.WAITING_USER,
        TaskStatus.WAITING_APPROVAL,
        TaskStatus.REVIEW_READY,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.RUNNING,
    ]
    seeded = _seed_tasks(path, statuses)
    event_ids = [f"evt_{100 + index:032x}" for index in range(2)]

    with SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    ) as ledger:
        changed = ledger.reconcile_running(
            event_id_factory=_event_id_iterator(event_ids),
            actor_ref="controller:startup",
            occurred_at=OCCURRED_AT,
        )
        assert tuple(task.task_id for task in changed) == (
            seeded[0]["task_id"],
            seeded[-1]["task_id"],
        )
        for task in changed:
            assert task.status is TaskStatus.FAILED
            assert task.reason_code == "controller_restart"
            assert task.updated_at == OCCURRED_AT
        snapshots = {item["task_id"]: ledger.get_task(item["task_id"]) for item in seeded}

    for item in seeded:
        snapshot = snapshots[item["task_id"]]
        assert snapshot is not None
        if item["status"] == TaskStatus.RUNNING.value:
            assert snapshot.status is TaskStatus.FAILED
            assert snapshot.reason_code == "controller_restart"
            assert snapshot.updated_at == OCCURRED_AT
        else:
            assert snapshot.status.value == item["status"]
            assert (snapshot.reason_code or "") == item["reason_code"]
            assert snapshot.updated_at == item["updated_at"]

    with _read_connection(path) as connection:
        events = tuple(
            connection.execute(
                """
                SELECT event_id, task_id, previous_status, next_status,
                       reason_code, actor_ref, occurred_at
                FROM task_events
                ORDER BY event_sequence
                """
            )
        )
        assert len(events) == len(seeded) + 2
        assert events[-2:] == (
            (
                event_ids[0],
                seeded[0]["task_id"],
                "running",
                "failed",
                "controller_restart",
                "controller:startup",
                OCCURRED_AT,
            ),
            (
                event_ids[1],
                seeded[-1]["task_id"],
                "running",
                "failed",
                "controller_restart",
                "controller:startup",
                OCCURRED_AT,
            ),
        )
        assert connection.execute("SELECT count(*) FROM tasks").fetchone() == (
            len(seeded),
        )


def test_reconcile_running_rolls_back_every_change_on_second_event_failure(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.db"
    _create_database(path)
    seeded = _seed_tasks(path, [TaskStatus.RUNNING, TaskStatus.RUNNING])
    before = _domain_rows(path)

    with SqliteStateLedger.open(
        path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
    ) as ledger:
        with pytest.raises(StateError, match=r"^state operation failed$"):
            ledger.reconcile_running(
                event_id_factory=_event_id_iterator(
                    [f"evt_{999:032x}", seeded[1]["event_id"]]
                ),
                actor_ref="controller:startup",
                occurred_at=OCCURRED_AT,
            )
        assert all(
            ledger.get_task(item["task_id"]).status is TaskStatus.RUNNING
            for item in seeded
        )

    assert _domain_rows(path) == before


class _BlockingStartupLedger:
    def __init__(self, ledger: SqliteStateLedger) -> None:
        self._ledger = ledger
        self.entered = threading.Event()
        self.release = threading.Event()

    def assert_encryption_binding(
        self, *, cipher: RequestCipher, key_handle: KeyHandle
    ) -> None:
        self._ledger.assert_encryption_binding(cipher=cipher, key_handle=key_handle)

    def reconcile_running(
        self,
        *,
        event_id_factory: Callable[[], str],
        actor_ref: str,
        occurred_at: str,
    ) -> tuple[Any, ...]:
        self.entered.set()
        if not self.release.wait(timeout=5):
            raise AssertionError("test did not release startup reconciliation")
        return self._ledger.reconcile_running(
            event_id_factory=event_id_factory,
            actor_ref=actor_ref,
            occurred_at=occurred_at,
        )

    def close(self) -> None:
        self._ledger.close()

    def __getattr__(self, name: str) -> object:
        return getattr(self._ledger, name)


class _UnusedIds:
    def new_request_id(self) -> str:
        return f"req_{1:032x}"

    def new_task_id(self) -> str:
        return f"tsk_{1:032x}"

    def new_event_id(self) -> str:
        return f"evt_{999:032x}"


def test_start_controller_returns_only_after_restart_reconciliation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.db"
    _create_database(path)
    blocking = _BlockingStartupLedger(
        SqliteStateLedger.open(
            path, cipher=Aes256GcmRequestCipher(), key_handle=KEY
        )
    )
    outcome: dict[str, object] = {}

    def run_startup() -> None:
        try:
            outcome["service"] = start_controller(
                ledger=blocking,
                cipher=Aes256GcmRequestCipher(),
                key_handle=KEY,
                max_concurrency=1,
                clock=_FixedClock(),
                ids=_UnusedIds(),
            )
        except Exception as exc:  # pragma: no cover - surfaced by the assertion below
            outcome["error"] = exc

    thread = threading.Thread(target=run_startup)
    thread.start()
    try:
        assert blocking.entered.wait(timeout=5)
        assert thread.is_alive()
        assert outcome == {}
        blocking.release.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert "error" not in outcome
        assert "service" in outcome
    finally:
        blocking.release.set()
        thread.join(timeout=5)
        service = outcome.get("service")
        if service is not None:
            service.close()
        else:
            blocking.close()
