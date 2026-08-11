from __future__ import annotations

import hmac
import re
import sqlite3
import threading
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path
from types import TracebackType

from forge.request_crypto import (
    EncryptedValue,
    EncryptionError,
    KeyHandle,
    RequestCipher,
    state_key_verifier_aad,
)
from forge.state_ledger import (
    ControllerAlreadyRunning,
    StateError,
    TaskSnapshot,
)
from forge.task_state import TaskStatus


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
_EVENT_ID_PATTERN = re.compile(r"evt_[0-9a-f]{32}")
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
    if not all(
        type(value) is str
        for value in (
            request_id,
            task_id,
            project_ref,
            repository_ref,
            mode,
            status,
            created,
            updated,
        )
    ) or (reason is not None and type(reason) is not str):
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


class SqliteStateLedger:
    def __init__(self, connection: sqlite3.Connection, lock: threading.RLock) -> None:
        self._connection: sqlite3.Connection | None = connection
        self._lock = lock

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
                connection.execute("COMMIT")
                ledger = cls(connection, lock)
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

    def get_task(self, task_id: str) -> TaskSnapshot | None:
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

    def reconcile_running(
        self,
        *,
        event_id_factory: Callable[[], str],
        actor_ref: str,
        occurred_at: str,
    ) -> tuple[TaskSnapshot, ...]:
        with self._lock:
            connection = self._active_connection()
            if (
                not callable(event_id_factory)
                or type(actor_ref) is not str
                or not actor_ref
                or type(occurred_at) is not str
                or not occurred_at
            ):
                raise StateError()
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
