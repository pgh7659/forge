from __future__ import annotations

import hashlib
import hmac
import re
import sqlite3
import threading
from collections import Counter
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from types import TracebackType

from forge.controller_protocol import CONTROLLER_PROTOCOL_VERSION
from forge.request_crypto import (
    EncryptedValue,
    EncryptionError,
    KeyHandle,
    RequestCipher,
    state_key_verifier_aad,
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
    StateTransitionConflict,
    TaskNotFound,
    TaskSnapshot,
)
from forge.task_state import (
    InvalidTaskTransition,
    TaskStatus,
    validate_claim_transition,
    validate_general_transition,
    validate_initial_status,
)


SCHEMA_V1_DDL = """CREATE TABLE ledger_metadata (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    active_key_id TEXT NOT NULL,
    encryption_algorithm TEXT NOT NULL,
    verifier_nonce BLOB NOT NULL CHECK (length(verifier_nonce) = 12),
    verifier_ciphertext BLOB NOT NULL CHECK (length(verifier_ciphertext) >= 16),
    next_queue_sequence INTEGER NOT NULL CHECK (next_queue_sequence >= 1)
);

CREATE TABLE requests (
    request_id TEXT PRIMARY KEY,
    protocol_version TEXT NOT NULL,
    source_namespace TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    source_event_time TEXT NOT NULL,
    actor_ref TEXT NOT NULL,
    channel_ref TEXT NOT NULL,
    project_ref TEXT NOT NULL,
    repository_ref TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode = 'plan'),
    security_envelope BLOB NOT NULL,
    submission_digest TEXT NOT NULL,
    body_digest TEXT NOT NULL,
    security_digest TEXT NOT NULL,
    encryption_algorithm TEXT NOT NULL,
    key_id TEXT NOT NULL,
    nonce BLOB NOT NULL CHECK (length(nonce) = 12),
    ciphertext BLOB NOT NULL CHECK (length(ciphertext) >= 16),
    received_at TEXT NOT NULL,
    UNIQUE (source_namespace, source_event_id)
);

CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE
        REFERENCES requests(request_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    project_ref TEXT NOT NULL,
    repository_ref TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode = 'plan'),
    status TEXT NOT NULL CHECK (status IN (
        'queued', 'running', 'waiting_user', 'waiting_approval',
        'review_ready', 'completed', 'failed', 'cancelled'
    )),
    reason_code TEXT,
    queue_sequence INTEGER NOT NULL UNIQUE CHECK (queue_sequence >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX ux_tasks_running_repository
    ON tasks(repository_ref) WHERE status = 'running';
CREATE INDEX ix_tasks_queue
    ON tasks(status, queue_sequence, task_id);

CREATE TABLE task_events (
    event_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    task_id TEXT NOT NULL
        REFERENCES tasks(task_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    previous_status TEXT CHECK (previous_status IS NULL OR previous_status IN (
        'queued', 'running', 'waiting_user', 'waiting_approval',
        'review_ready', 'completed', 'failed', 'cancelled'
    )),
    next_status TEXT NOT NULL CHECK (next_status IN (
        'queued', 'running', 'waiting_user', 'waiting_approval',
        'review_ready', 'completed', 'failed', 'cancelled'
    )),
    reason_code TEXT,
    actor_ref TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE INDEX ix_task_events_task_sequence
    ON task_events(task_id, event_sequence);"""

_SCHEMA_VERSION = 1
_KEY_VERIFIER_PLAINTEXT = b"forge-state-key-verifier/v1"
_REQUEST_ID_PATTERN = re.compile(r"req_[0-9a-f]{32}")
_TASK_ID_PATTERN = re.compile(r"tsk_[0-9a-f]{32}")
_EVENT_ID_PATTERN = re.compile(r"evt_[0-9a-f]{32}")
_REFERENCE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}")
_TOKEN_PATTERN = re.compile(r"[a-z][a-z0-9._:-]{0,127}")
_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_TIMESTAMP_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?Z"
)
_APPLICATION_OBJECT_NAMES = frozenset(
    {
        "ledger_metadata",
        "requests",
        "tasks",
        "task_events",
        "ux_tasks_running_repository",
        "ix_tasks_queue",
        "ix_task_events_task_sequence",
    }
)

_EXPECTED_TABLE_XINFO = {
    "ledger_metadata": (
        (0, "singleton", "INTEGER", 0, None, 1, 0),
        (1, "active_key_id", "TEXT", 1, None, 0, 0),
        (2, "encryption_algorithm", "TEXT", 1, None, 0, 0),
        (3, "verifier_nonce", "BLOB", 1, None, 0, 0),
        (4, "verifier_ciphertext", "BLOB", 1, None, 0, 0),
        (5, "next_queue_sequence", "INTEGER", 1, None, 0, 0),
    ),
    "requests": (
        (0, "request_id", "TEXT", 0, None, 1, 0),
        (1, "protocol_version", "TEXT", 1, None, 0, 0),
        (2, "source_namespace", "TEXT", 1, None, 0, 0),
        (3, "source_event_id", "TEXT", 1, None, 0, 0),
        (4, "source_event_time", "TEXT", 1, None, 0, 0),
        (5, "actor_ref", "TEXT", 1, None, 0, 0),
        (6, "channel_ref", "TEXT", 1, None, 0, 0),
        (7, "project_ref", "TEXT", 1, None, 0, 0),
        (8, "repository_ref", "TEXT", 1, None, 0, 0),
        (9, "mode", "TEXT", 1, None, 0, 0),
        (10, "security_envelope", "BLOB", 1, None, 0, 0),
        (11, "submission_digest", "TEXT", 1, None, 0, 0),
        (12, "body_digest", "TEXT", 1, None, 0, 0),
        (13, "security_digest", "TEXT", 1, None, 0, 0),
        (14, "encryption_algorithm", "TEXT", 1, None, 0, 0),
        (15, "key_id", "TEXT", 1, None, 0, 0),
        (16, "nonce", "BLOB", 1, None, 0, 0),
        (17, "ciphertext", "BLOB", 1, None, 0, 0),
        (18, "received_at", "TEXT", 1, None, 0, 0),
    ),
    "tasks": (
        (0, "task_id", "TEXT", 0, None, 1, 0),
        (1, "request_id", "TEXT", 1, None, 0, 0),
        (2, "project_ref", "TEXT", 1, None, 0, 0),
        (3, "repository_ref", "TEXT", 1, None, 0, 0),
        (4, "mode", "TEXT", 1, None, 0, 0),
        (5, "status", "TEXT", 1, None, 0, 0),
        (6, "reason_code", "TEXT", 0, None, 0, 0),
        (7, "queue_sequence", "INTEGER", 1, None, 0, 0),
        (8, "created_at", "TEXT", 1, None, 0, 0),
        (9, "updated_at", "TEXT", 1, None, 0, 0),
    ),
    "task_events": (
        (0, "event_sequence", "INTEGER", 0, None, 1, 0),
        (1, "event_id", "TEXT", 1, None, 0, 0),
        (2, "task_id", "TEXT", 1, None, 0, 0),
        (3, "previous_status", "TEXT", 0, None, 0, 0),
        (4, "next_status", "TEXT", 1, None, 0, 0),
        (5, "reason_code", "TEXT", 0, None, 0, 0),
        (6, "actor_ref", "TEXT", 1, None, 0, 0),
        (7, "occurred_at", "TEXT", 1, None, 0, 0),
    ),
}

_EXPECTED_FOREIGN_KEYS = {
    "ledger_metadata": (),
    "requests": (),
    "tasks": (
        (0, 0, "requests", "request_id", "request_id", "RESTRICT", "RESTRICT", "NONE"),
    ),
    "task_events": (
        (0, 0, "tasks", "task_id", "task_id", "RESTRICT", "RESTRICT", "NONE"),
    ),
}

_EXPECTED_EXPLICIT_INDEXES = {
    "ledger_metadata": {},
    "requests": {},
    "tasks": {
        "ux_tasks_running_repository": (1, "c", 1, ("repository_ref",)),
        "ix_tasks_queue": (0, "c", 0, ("status", "queue_sequence", "task_id")),
    },
    "task_events": {
        "ix_task_events_task_sequence": (
            0,
            "c",
            0,
            ("task_id", "event_sequence"),
        ),
    },
}

_EXPECTED_AUTOINDEXES = {
    "ledger_metadata": Counter(),
    "requests": Counter(
        {
            (1, "pk", 0, ("request_id",)): 1,
            (1, "u", 0, ("source_namespace", "source_event_id")): 1,
        }
    ),
    "tasks": Counter(
        {
            (1, "pk", 0, ("task_id",)): 1,
            (1, "u", 0, ("request_id",)): 1,
            (1, "u", 0, ("queue_sequence",)): 1,
        }
    ),
    "task_events": Counter({(1, "u", 0, ("event_id",)): 1}),
}

_TASK_COLUMNS = """
    request_id, task_id, project_ref, repository_ref, mode,
    status, reason_code, created_at, updated_at
"""

_ENCRYPTED_REQUEST_COLUMNS = """
    request_id, protocol_version, source_namespace, source_event_id,
    source_event_time, actor_ref, channel_ref, project_ref, repository_ref,
    mode, security_envelope, submission_digest, body_digest, security_digest,
    encryption_algorithm, key_id, nonce, ciphertext, received_at
"""


def _matches(value: object, pattern: re.Pattern[str]) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _valid_timestamp(value: object) -> bool:
    if not _matches(value, _TIMESTAMP_PATTERN):
        return False
    assert type(value) is str
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    offset = parsed.utcoffset()
    return offset is not None and offset.total_seconds() == 0


def _validate_encrypted_request(
    record: object,
    *,
    active_key_id: str,
    encryption_algorithm: str,
) -> EncryptedRequestRecord:
    if type(record) is not EncryptedRequestRecord:
        raise StateError()
    if (
        not _matches(record.request_id, _REQUEST_ID_PATTERN)
        or record.protocol_version != CONTROLLER_PROTOCOL_VERSION
        or not _matches(record.source_namespace, _TOKEN_PATTERN)
        or not _matches(record.source_event_id, _REFERENCE_PATTERN)
        or not _valid_timestamp(record.source_event_time)
        or not _matches(record.actor_ref, _REFERENCE_PATTERN)
        or not _matches(record.channel_ref, _REFERENCE_PATTERN)
        or not _matches(record.project_ref, _REFERENCE_PATTERN)
        or not _matches(record.repository_ref, _REFERENCE_PATTERN)
        or record.mode != "plan"
        or type(record.security_envelope) is not bytes
        or not record.security_envelope
        or not _matches(record.submission_digest, _DIGEST_PATTERN)
        or not _matches(record.body_digest, _DIGEST_PATTERN)
        or not _matches(record.security_digest, _DIGEST_PATTERN)
        or record.security_digest
        != "sha256:" + hashlib.sha256(record.security_envelope).hexdigest()
        or type(record.encryption_algorithm) is not str
        or record.encryption_algorithm != encryption_algorithm
        or not _matches(record.key_id, _REFERENCE_PATTERN)
        or record.key_id != active_key_id
        or type(record.nonce) is not bytes
        or len(record.nonce) != 12
        or type(record.ciphertext) is not bytes
        or len(record.ciphertext) < 16
        or not _valid_timestamp(record.received_at)
    ):
        raise StateError()
    return record


def _validate_ingest_bundle(
    bundle: object,
    *,
    active_key_id: str,
    encryption_algorithm: str,
) -> IngestBundle:
    if type(bundle) is not IngestBundle:
        raise StateError()
    request = _validate_encrypted_request(
        bundle.request,
        active_key_id=active_key_id,
        encryption_algorithm=encryption_algorithm,
    )
    task = bundle.task
    event = bundle.event
    if (
        type(task) is not NewTaskRecord
        or not _matches(task.task_id, _TASK_ID_PATTERN)
        or not _matches(task.request_id, _REQUEST_ID_PATTERN)
        or not _matches(task.project_ref, _REFERENCE_PATTERN)
        or not _matches(task.repository_ref, _REFERENCE_PATTERN)
        or task.mode != "plan"
        or not _valid_timestamp(task.created_at)
        or task.request_id != request.request_id
        or task.project_ref != request.project_ref
        or task.repository_ref != request.repository_ref
        or task.mode != request.mode
        or type(event) is not NewTaskEvent
        or not _matches(event.event_id, _EVENT_ID_PATTERN)
        or not _matches(event.task_id, _TASK_ID_PATTERN)
        or event.task_id != task.task_id
        or event.previous_status is not None
        or type(event.next_status) is not TaskStatus
        or event.reason_code is not None
        or not _matches(event.actor_ref, _REFERENCE_PATTERN)
        or not _valid_timestamp(event.occurred_at)
        or request.received_at != task.created_at
        or task.created_at != event.occurred_at
    ):
        raise StateError()
    try:
        validate_initial_status(event.next_status)
    except InvalidTaskTransition:
        raise StateError() from None
    return bundle


def _validate_event_metadata(
    *,
    reason_code: object,
    actor_ref: object,
    occurred_at: object,
) -> None:
    if (
        (reason_code is not None and not _matches(reason_code, _TOKEN_PATTERN))
        or not _matches(actor_ref, _REFERENCE_PATTERN)
        or not _valid_timestamp(occurred_at)
    ):
        raise StateError()


def _validate_event_arguments(
    *,
    reason_code: object,
    actor_ref: object,
    event_id: object,
    occurred_at: object,
) -> None:
    _validate_event_metadata(
        reason_code=reason_code,
        actor_ref=actor_ref,
        occurred_at=occurred_at,
    )
    if not _matches(event_id, _EVENT_ID_PATTERN):
        raise StateError()


def _allocate_queue_sequence(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        """
        UPDATE ledger_metadata
        SET next_queue_sequence = next_queue_sequence + 1
        WHERE singleton = 1
        RETURNING next_queue_sequence - 1
        """
    ).fetchone()
    if row is None or len(row) != 1 or type(row[0]) is not int or row[0] < 1:
        raise StateError()
    return row[0]


def _rollback_transaction(connection: sqlite3.Connection) -> None:
    try:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
    except sqlite3.Error:
        pass


def _schema_statements() -> Iterator[str]:
    buffered = ""
    for line in SCHEMA_V1_DDL.splitlines(keepends=True):
        buffered += line
        if sqlite3.complete_statement(buffered):
            yield buffered.strip()
            buffered = ""
    if buffered.strip():
        raise AssertionError("incomplete built-in SQLite schema")


def _normalize_sql(sql: str) -> str:
    source = sql.strip().rstrip(";").rstrip()
    normalized: list[str] = []
    closing_quote: str | None = None
    pending_space = False
    index = 0
    while index < len(source):
        character = source[index]
        if closing_quote is not None:
            normalized.append(character)
            if character == closing_quote:
                if index + 1 < len(source) and source[index + 1] == closing_quote:
                    normalized.append(source[index + 1])
                    index += 2
                    continue
                closing_quote = None
            index += 1
            continue

        if character.isspace():
            pending_space = True
            index += 1
            continue
        if pending_space and normalized:
            normalized.append(" ")
        pending_space = False
        normalized.append(character.casefold())
        if character in {"'", '"', "`"}:
            closing_quote = character
        elif character == "[":
            closing_quote = "]"
        index += 1
    return "".join(normalized)


def _statement_identity(statement: str) -> tuple[str, str, str]:
    match = re.match(
        r"CREATE\s+(?:(UNIQUE)\s+)?(TABLE|INDEX)\s+([A-Za-z_][A-Za-z0-9_]*)",
        statement,
        flags=re.IGNORECASE,
    )
    if match is None:
        raise AssertionError("unrecognized built-in SQLite schema statement")
    object_type = match.group(2).casefold()
    name = match.group(3)
    if object_type == "table":
        table_name = name
    else:
        table_match = re.search(
            r"\bON\s+([A-Za-z_][A-Za-z0-9_]*)", statement, flags=re.IGNORECASE
        )
        if table_match is None:
            raise AssertionError("unrecognized built-in SQLite index statement")
        table_name = table_match.group(1)
    return object_type, name, table_name


_EXPECTED_OBJECTS = {
    name: (object_type, table_name, _normalize_sql(statement))
    for statement in _schema_statements()
    for object_type, name, table_name in (_statement_identity(statement),)
}


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _is_busy(error: sqlite3.Error) -> bool:
    code = getattr(error, "sqlite_errorcode", None)
    return type(code) is int and code & 0xFF == sqlite3.SQLITE_BUSY


def _rollback_and_close(connection: sqlite3.Connection | None) -> None:
    if connection is None:
        return
    try:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
    except sqlite3.Error:
        pass
    try:
        connection.close()
    except sqlite3.Error:
        pass


def _configure_connection(connection: sqlite3.Connection) -> None:
    settings = (
        ("PRAGMA busy_timeout=0", "PRAGMA busy_timeout", 0),
        ("PRAGMA foreign_keys=ON", "PRAGMA foreign_keys", 1),
        (
            "PRAGMA main.locking_mode=EXCLUSIVE",
            "PRAGMA main.locking_mode",
            "exclusive",
        ),
        ("PRAGMA main.journal_mode=WAL", "PRAGMA main.journal_mode", "wal"),
        ("PRAGMA main.synchronous=FULL", "PRAGMA main.synchronous", 2),
    )
    for setting, readback, expected in settings:
        connection.execute(setting)
        row = connection.execute(readback).fetchone()
        if row is None:
            raise StateError()
        actual = row[0]
        if isinstance(expected, str):
            if type(actual) is not str or actual.casefold() != expected:
                raise StateError()
        elif type(actual) is not int or actual != expected:
            raise StateError()


def _application_objects(
    connection: sqlite3.Connection,
) -> tuple[tuple[str, str, str, str | None], ...]:
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


def _index_columns(
    connection: sqlite3.Connection, index_name: str
) -> tuple[str, ...]:
    rows = tuple(
        connection.execute(f"PRAGMA index_xinfo({_quote_identifier(index_name)})")
    )
    columns: list[str] = []
    for row in rows:
        if row[5] != 1:
            continue
        if type(row[2]) is not str:
            raise StateError()
        columns.append(row[2])
    return tuple(columns)


def _validate_indexes(connection: sqlite3.Connection, table_name: str) -> set[str]:
    explicit = _EXPECTED_EXPLICIT_INDEXES[table_name]
    actual_explicit: dict[str, tuple[int, str, int, tuple[str, ...]]] = {}
    actual_auto: Counter[tuple[int, str, int, tuple[str, ...]]] = Counter()
    auto_names: set[str] = set()
    for row in connection.execute(
        f"PRAGMA index_list({_quote_identifier(table_name)})"
    ):
        _, index_name, unique, origin, partial = row
        if (
            type(index_name) is not str
            or type(unique) is not int
            or type(origin) is not str
            or type(partial) is not int
        ):
            raise StateError()
        signature = (unique, origin, partial, _index_columns(connection, index_name))
        if origin in {"pk", "u"}:
            if not index_name.startswith(f"sqlite_autoindex_{table_name}_"):
                raise StateError()
            schema_row = connection.execute(
                "SELECT type, tbl_name, sql FROM sqlite_schema WHERE name = ?",
                (index_name,),
            ).fetchone()
            if schema_row != ("index", table_name, None):
                raise StateError()
            actual_auto[signature] += 1
            auto_names.add(index_name)
        elif origin == "c":
            actual_explicit[index_name] = signature
        else:
            raise StateError()
    if actual_explicit != explicit or actual_auto != _EXPECTED_AUTOINDEXES[table_name]:
        raise StateError()
    return auto_names


def _validate_schema_fingerprint(connection: sqlite3.Connection) -> None:
    objects = _application_objects(connection)
    if {row[1] for row in objects} != _APPLICATION_OBJECT_NAMES:
        raise StateError()
    if len(objects) != len(_EXPECTED_OBJECTS):
        raise StateError()
    for object_type, name, table_name, sql in objects:
        expected = _EXPECTED_OBJECTS.get(name)
        if (
            expected is None
            or type(sql) is not str
            or (object_type, table_name, _normalize_sql(sql)) != expected
        ):
            raise StateError()

    allowed_internal = {"sqlite_sequence"}
    for table_name, expected_xinfo in _EXPECTED_TABLE_XINFO.items():
        xinfo = tuple(
            connection.execute(f"PRAGMA table_xinfo({_quote_identifier(table_name)})")
        )
        if xinfo != expected_xinfo:
            raise StateError()
        foreign_keys = tuple(
            connection.execute(
                f"PRAGMA foreign_key_list({_quote_identifier(table_name)})"
            )
        )
        if foreign_keys != _EXPECTED_FOREIGN_KEYS[table_name]:
            raise StateError()
        allowed_internal.update(_validate_indexes(connection, table_name))

    internal_objects = tuple(
        connection.execute(
            """
            SELECT type, name, tbl_name, sql
            FROM sqlite_schema
            WHERE name LIKE 'sqlite_%'
            ORDER BY type, name
            """
        )
    )
    if {row[1] for row in internal_objects} != allowed_internal:
        raise StateError()
    for object_type, name, table_name, sql in internal_objects:
        if name == "sqlite_sequence":
            if object_type != "table" or table_name != "sqlite_sequence":
                raise StateError()
        elif object_type != "index" or sql is not None:
            raise StateError()


def _read_key_metadata(
    connection: sqlite3.Connection,
) -> tuple[str, str, bytes, bytes, int]:
    rows = tuple(
        connection.execute(
            """
            SELECT singleton, active_key_id, encryption_algorithm,
                   verifier_nonce, verifier_ciphertext, next_queue_sequence
            FROM ledger_metadata
            ORDER BY singleton
            """
        )
    )
    if len(rows) != 1:
        raise StateError()
    singleton, key_id, algorithm, nonce, ciphertext, next_sequence = rows[0]
    if (
        singleton != 1
        or type(key_id) is not str
        or type(algorithm) is not str
        or type(nonce) is not bytes
        or len(nonce) != 12
        or type(ciphertext) is not bytes
        or len(ciphertext) < 16
        or type(next_sequence) is not int
        or next_sequence < 1
    ):
        raise StateError()
    return key_id, algorithm, nonce, ciphertext, next_sequence


def _verify_key_binding(
    connection: sqlite3.Connection,
    *,
    cipher: RequestCipher,
    key_handle: KeyHandle,
) -> None:
    key_id, algorithm, nonce, ciphertext, _ = _read_key_metadata(connection)
    try:
        if (
            type(cipher.algorithm) is not str
            or algorithm != cipher.algorithm
            or key_id != key_handle.key_id
        ):
            raise EncryptionError()
        plaintext = cipher.decrypt(
            EncryptedValue(nonce=nonce, ciphertext=ciphertext),
            state_key_verifier_aad(algorithm, key_id),
            key_handle,
        )
        if type(plaintext) is not bytes or not hmac.compare_digest(
            plaintext, _KEY_VERIFIER_PLAINTEXT
        ):
            raise EncryptionError()
    except (EncryptionError, TypeError, ValueError):
        raise EncryptionError() from None


def _snapshot_from_row(row: tuple[object, ...]) -> TaskSnapshot:
    if len(row) != 9:
        raise StateError()
    request_id, task_id, project_ref, repository_ref, mode, status, reason, created, updated = row
    if (
        not _matches(request_id, _REQUEST_ID_PATTERN)
        or not _matches(task_id, _TASK_ID_PATTERN)
        or not _matches(project_ref, _REFERENCE_PATTERN)
        or not _matches(repository_ref, _REFERENCE_PATTERN)
        or mode != "plan"
        or type(status) is not str
        or (reason is not None and not _matches(reason, _TOKEN_PATTERN))
        or not _valid_timestamp(created)
        or not _valid_timestamp(updated)
    ):
        raise StateError()
    try:
        task_status = TaskStatus(status)
    except ValueError:
        raise StateError() from None
    return TaskSnapshot(
        request_id=request_id,
        task_id=task_id,
        project_ref=project_ref,
        repository_ref=repository_ref,
        mode=mode,
        status=task_status,
        reason_code=reason,
        created_at=created,
        updated_at=updated,
    )


def _encrypted_request_from_row(
    row: tuple[object, ...],
    *,
    active_key_id: str,
    encryption_algorithm: str,
) -> EncryptedRequestRecord:
    if len(row) != 19:
        raise StateError()
    record = EncryptedRequestRecord(*row)
    return _validate_encrypted_request(
        record,
        active_key_id=active_key_id,
        encryption_algorithm=encryption_algorithm,
    )


class SqliteStateLedger:
    def __init__(
        self,
        connection: sqlite3.Connection,
        lock: threading.RLock,
        *,
        active_key_id: str,
        encryption_algorithm: str,
    ) -> None:
        self._connection: sqlite3.Connection | None = connection
        self._lock = lock
        self._active_key_id = active_key_id
        self._encryption_algorithm = encryption_algorithm

    @classmethod
    def open(
        cls,
        path: Path,
        *,
        cipher: RequestCipher,
        key_handle: KeyHandle,
    ) -> SqliteStateLedger:
        connection: sqlite3.Connection | None = None
        connection_transferred = False
        lock = threading.RLock()
        try:
            connection = sqlite3.connect(
                path,
                timeout=0.0,
                isolation_level=None,
                check_same_thread=False,
                uri=False,
            )
            with lock:
                try:
                    _configure_connection(connection)
                    connection.execute("BEGIN IMMEDIATE")
                except sqlite3.Error as error:
                    if _is_busy(error):
                        raise ControllerAlreadyRunning() from None
                    raise StateError() from None

                version_row = connection.execute("PRAGMA user_version").fetchone()
                if version_row is None or type(version_row[0]) is not int:
                    raise StateError()
                version = version_row[0]
                application_objects = _application_objects(connection)
                if version == 0 and not application_objects:
                    for statement in _schema_statements():
                        connection.execute(statement)
                    encrypted = cipher.encrypt(
                        _KEY_VERIFIER_PLAINTEXT,
                        state_key_verifier_aad(cipher.algorithm, key_handle.key_id),
                        key_handle,
                    )
                    connection.execute(
                        """
                        INSERT INTO ledger_metadata (
                            singleton, active_key_id, encryption_algorithm,
                            verifier_nonce, verifier_ciphertext,
                            next_queue_sequence
                        ) VALUES (1, ?, ?, ?, ?, 1)
                        """,
                        (
                            key_handle.key_id,
                            cipher.algorithm,
                            encrypted.nonce,
                            encrypted.ciphertext,
                        ),
                    )
                    connection.execute("PRAGMA user_version=1")
                elif version != _SCHEMA_VERSION:
                    raise StateError()

                _validate_schema_fingerprint(connection)
                _verify_key_binding(
                    connection, cipher=cipher, key_handle=key_handle
                )
                active_key_id, encryption_algorithm, _, _, _ = _read_key_metadata(
                    connection
                )
                connection.execute("COMMIT")
                ledger = cls(
                    connection,
                    lock,
                    active_key_id=active_key_id,
                    encryption_algorithm=encryption_algorithm,
                )
                connection_transferred = True
                return ledger
        except ControllerAlreadyRunning:
            raise
        except EncryptionError:
            raise EncryptionError() from None
        except StateError:
            raise
        except sqlite3.Error:
            raise StateError() from None
        except Exception:
            raise StateError() from None
        finally:
            if not connection_transferred:
                _rollback_and_close(connection)

    def __enter__(self) -> SqliteStateLedger:
        with self._lock:
            if self._connection is None:
                raise StateError()
            return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _active_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise StateError()
        return self._connection

    def assert_encryption_binding(
        self, *, cipher: RequestCipher, key_handle: KeyHandle
    ) -> None:
        with self._lock:
            connection = self._active_connection()
            try:
                _verify_key_binding(
                    connection, cipher=cipher, key_handle=key_handle
                )
            except EncryptionError:
                raise EncryptionError() from None
            except sqlite3.Error:
                raise StateError() from None

    def ingest(self, bundle: IngestBundle) -> IngestOutcome:
        validated = _validate_ingest_bundle(
            bundle,
            active_key_id=self._active_key_id,
            encryption_algorithm=self._encryption_algorithm,
        )
        request = validated.request
        task = validated.task
        event = validated.event
        with self._lock:
            connection = self._active_connection()
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    """
                    SELECT request_id, submission_digest
                    FROM requests
                    WHERE source_namespace = ? AND source_event_id = ?
                    """,
                    (request.source_namespace, request.source_event_id),
                ).fetchone()
                if existing is not None:
                    if (
                        len(existing) != 2
                        or not _matches(existing[0], _REQUEST_ID_PATTERN)
                        or not _matches(existing[1], _DIGEST_PATTERN)
                    ):
                        raise StateError()
                    if existing[1] != request.submission_digest:
                        raise IdempotencyConflict()
                    row = connection.execute(
                        f"SELECT {_TASK_COLUMNS} FROM tasks WHERE request_id = ?",
                        (existing[0],),
                    ).fetchone()
                    if row is None:
                        raise StateError()
                    snapshot = _snapshot_from_row(row)
                    connection.execute("COMMIT")
                    return IngestOutcome(task=snapshot, created=False)

                queue_sequence = _allocate_queue_sequence(connection)
                connection.execute(
                    """
                    INSERT INTO requests (
                        request_id, protocol_version, source_namespace,
                        source_event_id, source_event_time, actor_ref,
                        channel_ref, project_ref, repository_ref, mode,
                        security_envelope, submission_digest, body_digest,
                        security_digest, encryption_algorithm, key_id, nonce,
                        ciphertext, received_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.request_id,
                        request.protocol_version,
                        request.source_namespace,
                        request.source_event_id,
                        request.source_event_time,
                        request.actor_ref,
                        request.channel_ref,
                        request.project_ref,
                        request.repository_ref,
                        request.mode,
                        request.security_envelope,
                        request.submission_digest,
                        request.body_digest,
                        request.security_digest,
                        request.encryption_algorithm,
                        request.key_id,
                        request.nonce,
                        request.ciphertext,
                        request.received_at,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO tasks (
                        task_id, request_id, project_ref, repository_ref, mode,
                        status, reason_code, queue_sequence, created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'queued', NULL, ?, ?, ?)
                    """,
                    (
                        task.task_id,
                        task.request_id,
                        task.project_ref,
                        task.repository_ref,
                        task.mode,
                        queue_sequence,
                        task.created_at,
                        task.created_at,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO task_events (
                        event_id, task_id, previous_status, next_status,
                        reason_code, actor_ref, occurred_at
                    ) VALUES (?, ?, NULL, 'queued', NULL, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.task_id,
                        event.actor_ref,
                        event.occurred_at,
                    ),
                )
                row = connection.execute(
                    f"SELECT {_TASK_COLUMNS} FROM tasks WHERE task_id = ?",
                    (task.task_id,),
                ).fetchone()
                if row is None:
                    raise StateError()
                snapshot = _snapshot_from_row(row)
                connection.execute("COMMIT")
                return IngestOutcome(task=snapshot, created=True)
            except IdempotencyConflict:
                _rollback_transaction(connection)
                raise
            except StateError:
                _rollback_transaction(connection)
                raise
            except Exception:
                _rollback_transaction(connection)
                raise StateError() from None

    def load_encrypted_request(
        self, request_id: str
    ) -> EncryptedRequestRecord | None:
        if not _matches(request_id, _REQUEST_ID_PATTERN):
            raise StateError()
        with self._lock:
            connection = self._active_connection()
            try:
                row = connection.execute(
                    f"SELECT {_ENCRYPTED_REQUEST_COLUMNS} FROM requests WHERE request_id = ?",
                    (request_id,),
                ).fetchone()
                if row is None:
                    return None
                return _encrypted_request_from_row(
                    row,
                    active_key_id=self._active_key_id,
                    encryption_algorithm=self._encryption_algorithm,
                )
            except StateError:
                raise
            except sqlite3.Error:
                raise StateError() from None

    def get_task(self, task_id: str) -> TaskSnapshot | None:
        if not _matches(task_id, _TASK_ID_PATTERN):
            raise StateError()
        with self._lock:
            connection = self._active_connection()
            try:
                row = connection.execute(
                    f"SELECT {_TASK_COLUMNS} FROM tasks WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                if row is None:
                    return None
                return _snapshot_from_row(row)
            except StateError:
                raise
            except sqlite3.Error:
                raise StateError() from None

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
        if (
            type(expected_status) is not TaskStatus
            or type(target_status) is not TaskStatus
        ):
            raise StateError()
        if not _matches(task_id, _TASK_ID_PATTERN):
            raise StateError()
        _validate_event_arguments(
            reason_code=reason_code,
            actor_ref=actor_ref,
            event_id=event_id,
            occurred_at=occurred_at,
        )
        with self._lock:
            connection = self._active_connection()
            try:
                connection.execute("BEGIN IMMEDIATE")
                current_row = connection.execute(
                    "SELECT status, queue_sequence FROM tasks WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                if current_row is None:
                    raise TaskNotFound()
                if (
                    len(current_row) != 2
                    or type(current_row[0]) is not str
                    or type(current_row[1]) is not int
                    or current_row[1] < 1
                ):
                    raise StateError()
                try:
                    current_status = TaskStatus(current_row[0])
                except ValueError:
                    raise StateError() from None
                if current_status is not expected_status:
                    raise StateTransitionConflict()
                validate_general_transition(current_status, target_status)
                queue_sequence = current_row[1]
                if target_status is TaskStatus.QUEUED:
                    queue_sequence = _allocate_queue_sequence(connection)
                updated = connection.execute(
                    """
                    UPDATE tasks
                    SET status = ?, reason_code = ?, queue_sequence = ?, updated_at = ?
                    WHERE task_id = ? AND status = ?
                    """,
                    (
                        target_status.value,
                        reason_code,
                        queue_sequence,
                        occurred_at,
                        task_id,
                        expected_status.value,
                    ),
                )
                if updated.rowcount != 1:
                    raise StateTransitionConflict()
                connection.execute(
                    """
                    INSERT INTO task_events (
                        event_id, task_id, previous_status, next_status,
                        reason_code, actor_ref, occurred_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        task_id,
                        current_status.value,
                        target_status.value,
                        reason_code,
                        actor_ref,
                        occurred_at,
                    ),
                )
                row = connection.execute(
                    f"SELECT {_TASK_COLUMNS} FROM tasks WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                if row is None:
                    raise StateError()
                snapshot = _snapshot_from_row(row)
                connection.execute("COMMIT")
                return snapshot
            except (InvalidTaskTransition, StateTransitionConflict, TaskNotFound):
                _rollback_transaction(connection)
                raise
            except StateError:
                _rollback_transaction(connection)
                raise
            except Exception:
                _rollback_transaction(connection)
                raise StateError() from None

    def claim_next_eligible(
        self,
        *,
        max_concurrency: int,
        actor_ref: str,
        event_id: str,
        occurred_at: str,
    ) -> TaskSnapshot | None:
        if type(max_concurrency) is not int or max_concurrency <= 0:
            raise StateError()
        _validate_event_arguments(
            reason_code=None,
            actor_ref=actor_ref,
            event_id=event_id,
            occurred_at=occurred_at,
        )
        with self._lock:
            connection = self._active_connection()
            try:
                connection.execute("BEGIN IMMEDIATE")
                count_row = connection.execute(
                    "SELECT count(*) FROM tasks WHERE status = 'running'"
                ).fetchone()
                if (
                    count_row is None
                    or len(count_row) != 1
                    or type(count_row[0]) is not int
                    or count_row[0] < 0
                ):
                    raise StateError()
                if count_row[0] >= max_concurrency:
                    connection.execute("COMMIT")
                    return None
                selected = connection.execute(
                    """
                    SELECT q.task_id
                    FROM tasks AS q
                    WHERE q.status = 'queued'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM tasks AS r
                          WHERE r.repository_ref = q.repository_ref
                            AND r.status = 'running'
                      )
                    ORDER BY q.queue_sequence, q.task_id
                    LIMIT 1
                    """
                ).fetchone()
                if selected is None:
                    connection.execute("COMMIT")
                    return None
                if len(selected) != 1 or not _matches(
                    selected[0], _TASK_ID_PATTERN
                ):
                    raise StateError()
                task_id = selected[0]
                current_row = connection.execute(
                    "SELECT status FROM tasks WHERE task_id = ?", (task_id,)
                ).fetchone()
                if (
                    current_row is None
                    or len(current_row) != 1
                    or type(current_row[0]) is not str
                ):
                    raise StateError()
                try:
                    current_status = TaskStatus(current_row[0])
                except ValueError:
                    raise StateError() from None
                validate_claim_transition(current_status)
                updated = connection.execute(
                    """
                    UPDATE tasks
                    SET status = 'running', reason_code = NULL, updated_at = ?
                    WHERE task_id = ? AND status = 'queued'
                    """,
                    (occurred_at, task_id),
                )
                if updated.rowcount != 1:
                    raise StateTransitionConflict()
                connection.execute(
                    """
                    INSERT INTO task_events (
                        event_id, task_id, previous_status, next_status,
                        reason_code, actor_ref, occurred_at
                    ) VALUES (?, ?, 'queued', 'running', NULL, ?, ?)
                    """,
                    (event_id, task_id, actor_ref, occurred_at),
                )
                row = connection.execute(
                    f"SELECT {_TASK_COLUMNS} FROM tasks WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                if row is None:
                    raise StateError()
                snapshot = _snapshot_from_row(row)
                connection.execute("COMMIT")
                return snapshot
            except (InvalidTaskTransition, StateTransitionConflict):
                _rollback_transaction(connection)
                raise
            except StateError:
                _rollback_transaction(connection)
                raise
            except Exception:
                _rollback_transaction(connection)
                raise StateError() from None

    def reconcile_running(
        self,
        *,
        event_id_factory: Callable[[], str],
        actor_ref: str,
        occurred_at: str,
    ) -> tuple[TaskSnapshot, ...]:
        if not callable(event_id_factory):
            raise StateError()
        _validate_event_metadata(
            reason_code="controller_restart",
            actor_ref=actor_ref,
            occurred_at=occurred_at,
        )
        with self._lock:
            connection = self._active_connection()
            try:
                connection.execute("BEGIN IMMEDIATE")
                rows = tuple(
                    connection.execute(
                        f"""
                        SELECT {_TASK_COLUMNS}
                        FROM tasks
                        WHERE status = 'running'
                        ORDER BY task_id
                        """
                    )
                )
                task_ids: list[str] = []
                for row in rows:
                    snapshot = _snapshot_from_row(row)
                    event_id = event_id_factory()
                    if (
                        type(event_id) is not str
                        or _EVENT_ID_PATTERN.fullmatch(event_id) is None
                    ):
                        raise StateError()
                    updated = connection.execute(
                        """
                        UPDATE tasks
                        SET status = 'failed',
                            reason_code = 'controller_restart',
                            updated_at = ?
                        WHERE task_id = ? AND status = 'running'
                        """,
                        (occurred_at, snapshot.task_id),
                    )
                    if updated.rowcount != 1:
                        raise StateError()
                    connection.execute(
                        """
                        INSERT INTO task_events (
                            event_id, task_id, previous_status, next_status,
                            reason_code, actor_ref, occurred_at
                        ) VALUES (?, ?, 'running', 'failed',
                                  'controller_restart', ?, ?)
                        """,
                        (event_id, snapshot.task_id, actor_ref, occurred_at),
                    )
                    task_ids.append(snapshot.task_id)

                snapshots: list[TaskSnapshot] = []
                for task_id in task_ids:
                    row = connection.execute(
                        f"SELECT {_TASK_COLUMNS} FROM tasks WHERE task_id = ?",
                        (task_id,),
                    ).fetchone()
                    if row is None:
                        raise StateError()
                    snapshots.append(_snapshot_from_row(row))
                connection.execute("COMMIT")
                return tuple(snapshots)
            except Exception:
                try:
                    if connection.in_transaction:
                        connection.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise StateError() from None

    def close(self) -> None:
        with self._lock:
            connection = self._connection
            if connection is None:
                return
            self._connection = None
            try:
                connection.close()
            except sqlite3.Error:
                raise StateError() from None
