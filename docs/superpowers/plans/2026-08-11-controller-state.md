# Controller and State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Plan status:** This delivery slice is implemented in the current source
> tree. The unchecked boxes preserve the original procedure; they are not a
> retrospective execution record and do not claim that every prescribed RED
> observation was captured. Current delivery status is tracked in the
> [roadmap](../../roadmap.md).

**Goal:** Add a strict transport-neutral controller protocol, an injected in-process controller core, authenticated request-body encryption, and a single-controller SQLite ledger with idempotent ingestion, atomic task transitions, bounded scheduling, and conservative restart reconciliation.

**Architecture:** Immutable protocol models feed a controller application service that owns request identity, encryption orchestration, readiness, and public error mapping. Pure state rules and a database-neutral ledger protocol isolate policy from persistence; the first SQLite adapter owns one long-lived serialized connection, exact schema version 1, exclusive process ownership, transactions, scheduling, and reconciliation. AES-256-GCM receives caller-supplied key material through a narrow cipher boundary; no transport, executor, workspace, secret provider, or host adapter is connected in this slice.

**Tech Stack:** Python 3.12+, frozen dataclasses, `Protocol`, jsonschema Draft 2020-12, RFC 8785 through `rfc8785`, SHA-256, `cryptography>=50,<51` AES-GCM, Python `sqlite3`, pytest, Make, and GitHub Actions on Python 3.12 and 3.14.

## Global Constraints

- The governing design is `docs/superpowers/specs/2026-08-11-controller-state-design.md`; the durable decision is ADR-0010.
- The controller protocol is exactly `forge.dev/controller/v1alpha1`; the embedded envelope version is exactly `forge.dev/security/v1alpha1`.
- The envelope implementation validates and preserves only the controller request's minimum security metadata. It does not implement the complete security-contract family, authenticate a caller, validate a provenance chain or attestation, declassify taint, make policy decisions, deliver secrets, or prove runtime/host enforcement.
- Ingress exposes exactly `submitRequest` and `getTask`. Claim, transition, reconciliation, encrypted-material loading, and plaintext recovery are not client commands.
- One command is at most 262,144 bytes before UTF-8 decoding. Unknown fields, duplicate keys, malformed UTF-8 or Unicode, non-finite numbers, out-of-range I-JSON integers, unsupported versions, and invalid timestamps fail closed.
- Request identity is SHA-256 over RFC 8785 bytes for exactly `{"protocolVersion": "forge.dev/controller/v1alpha1", "request": <validated request>}`. The operation discriminator and generated values are excluded.
- The request body is encoded to UTF-8 without normalization or rewriting. Only that body is encrypted; minimized security and routing metadata remain plaintext ledger columns or canonical bytes.
- AES-256-GCM accepts exactly 32 key bytes and produces a fresh 12-byte nonce per encryption. Key IDs, key bytes, nonce, ciphertext, plaintext, private paths, raw SQLite messages, and raw cryptographic exceptions never appear in public responses or normal logs.
- The request AAD domain is `forge.request-body/v1`; the key-verifier AAD domain is `forge.state-key-verifier/v1`. Algorithm and key ID are bound before encryption and are never inferred from ciphertext.
- SQLite is one adapter, not a portable-core requirement. It uses one long-lived connection, `busy_timeout=0`, `foreign_keys=ON`, `main.locking_mode=EXCLUSIVE`, WAL, `synchronous=FULL`, `BEGIN IMMEDIATE`, and exact `PRAGMA user_version=1` validation.
- `maxConcurrency` is a required positive integer; `bool`, zero, and negative values are invalid. Core has no default or public maximum. Tests cover an effective value of 2 while the reference deployment remains at its separately approved rollout value of 1.
- Global running count is at most N and running count per repository is at most one. Full capacity or no eligible repository returns an empty claim and leaves overflow queued.
- Only atomic `claim_next_eligible` may enter `running`; the general transition API rejects `target_status=running` from every state.
- Startup verifies the active key before reconciliation, changes only `running` tasks to `failed` with `controller_restart`, appends matching events in the same transaction, never retries, and becomes ready only after commit.
- All fixtures use synthetic identifiers, content, key bytes, repositories, and `tmp_path` databases. Tests make no network, OCI, Hermes, Discord, Codex, systemd, credential-provider, repository, publication, merge, or deployment call.
- Runtime databases are never automatically deleted. Test-framework temporary directories are the only cleanup scope.

## File map

- `src/forge/task_state.py`: state vocabulary, terminal set, and separate general-versus-claim transition validators.
- `src/forge/controller_protocol.py`: bounded strict JSON parser, immutable commands/results, digest projections, packaged schema loading, canonical response encoding, and stable error vocabulary.
- `src/forge/request_crypto.py`: redacted key/cipher records, cipher protocol, canonical AAD builders, and AES-256-GCM implementation.
- `src/forge/state_ledger.py`: immutable storage records, snapshots, typed owned exceptions, and the database-neutral ledger protocol.
- `src/forge/controller.py`: injected clock/ID boundaries, readiness factory, serialized application operations, encryption orchestration, and response/error mapping.
- `src/forge/sqlite_state.py`: exact schema v1, key verifier, exclusive ownership, transactions, idempotency, state/event CAS, scheduling, and reconciliation.
- `src/forge/resources/schemas/controller-command-v1alpha1.schema.json`: exact `submitRequest` and `getTask` shapes.
- `src/forge/resources/schemas/controller-response-v1alpha1.schema.json`: exact submit, inspection, and redacted-error response shapes.
- `tests/fixtures/controller/*.json`: valid synthetic commands and response documents only; byte-invalid cases stay Python byte literals.
- `tests/unit/test_task_state.py`, `tests/unit/test_controller_protocol.py`, `tests/unit/test_request_crypto.py`, `tests/unit/test_controller.py`: pure and fake-boundary contracts.
- `tests/integration/test_sqlite_startup.py`, `tests/integration/test_controller_sqlite.py`: lifecycle, process ownership, recovery, atomicity, concurrency, and real vertical integration.
- `tests/helpers/hold_sqlite_ledger.py`: local subprocess used only to prove cross-process exclusive ownership and lock release.
- `tests/wheel_controller_smoke.py`: installed-wheel schema, AES-GCM, and temporary SQLite evidence.
- `pyproject.toml`, `tests/validate-contracts.sh`, `.github/workflows/validate.yml`: dependency, packaged contract, and CI evidence.
- `README.md`, `config/README.md`, `examples/README.md`, `tests/README.md`, `SECURITY.md`, `docs/architecture.md`, `docs/roadmap.md`, `docs/security/threat-model.md`, `docs/security/trust-taint-provenance.md`: implemented boundary and remaining non-goals.

---

### Task 1: Pure task-state contract

**Files:**
- Create: `src/forge/task_state.py`
- Create: `tests/unit/test_task_state.py`

**Interfaces:**
- Produces: `TaskStatus`, `TERMINAL_STATUSES`, `InvalidTaskTransition`, `validate_initial_status`, `validate_general_transition`, and `validate_claim_transition`.
- `validate_initial_status(status: TaskStatus) -> None` accepts only `queued`.
- `validate_general_transition(current: TaskStatus, target: TaskStatus) -> None` checks the approved table but always rejects entry to `running`.
- `validate_claim_transition(current: TaskStatus) -> None` accepts only `queued` and is the sole validator for entry to `running`.

- [ ] **Step 1: Write the failing state-vocabulary and terminal tests**

Create `tests/unit/test_task_state.py` with the exact vocabulary and terminal assertions:

```python
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
```

- [ ] **Step 2: Add an exhaustive RED transition matrix**

Define this complete general-transition set in the test and assert all 64 state pairs against it:

```python
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


@pytest.mark.parametrize("current", list(TaskStatus))
@pytest.mark.parametrize("target", list(TaskStatus))
def test_general_transition_matrix(current: TaskStatus, target: TaskStatus) -> None:
    if (current, target) in GENERAL_TRANSITIONS:
        validate_general_transition(current, target)
    else:
        with pytest.raises(InvalidTaskTransition):
            validate_general_transition(current, target)
```

Add a focused assertion that `queued -> running` fails through the general validator, `validate_claim_transition(queued)` succeeds, and every other claim source fails. Assert terminal states have no outgoing path.

- [ ] **Step 3: Run the focused test and confirm RED**

```bash
.venv/bin/python -m pytest tests/unit/test_task_state.py -q
```

Expected: collection fails because `forge.task_state` does not exist.

- [ ] **Step 4: Implement the minimal state module**

Create `src/forge/task_state.py` using `StrEnum`, a frozen transition table, and an owned error whose string contains only state vocabulary:

```python
class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    WAITING_APPROVAL = "waiting_approval"
    REVIEW_READY = "review_ready"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvalidTaskTransition(ValueError):
    def __init__(self, current: TaskStatus | None, target: TaskStatus) -> None:
        self.current = current
        self.target = target
        current_value = "new" if current is None else current.value
        super().__init__(f"task transition {current_value} -> {target.value} is invalid")
```

Store exactly the approved transitions, including `queued -> running`, in a private immutable mapping. `validate_general_transition` must reject `target is TaskStatus.RUNNING` before consulting it; `validate_claim_transition` must require `current is TaskStatus.QUEUED`.

- [ ] **Step 5: Make Task 1 GREEN and commit**

```bash
.venv/bin/python -m pytest tests/unit/test_task_state.py -q
make validate
git diff --check
git add src/forge/task_state.py tests/unit/test_task_state.py
git commit -m "feat: define controller task transitions"
```

Expected: the exhaustive matrix, terminal, initial, and claim-only tests pass; the existing suite remains green.

---

### Task 2: Strict versioned controller protocol

**Files:**
- Create: `src/forge/controller_protocol.py`
- Create: `src/forge/resources/schemas/controller-command-v1alpha1.schema.json`
- Create: `src/forge/resources/schemas/controller-response-v1alpha1.schema.json`
- Create: `tests/unit/test_controller_protocol.py`
- Create: `tests/fixtures/controller/valid-submit.json`
- Create: `tests/fixtures/controller/valid-get-task.json`
- Create: `tests/fixtures/controller/valid-submit-created-response.json`
- Create: `tests/fixtures/controller/valid-submit-replayed-response.json`
- Create: `tests/fixtures/controller/valid-get-task-response.json`
- Create: `tests/fixtures/controller/valid-error-response.json`

**Interfaces:**
- Produces: `CONTROLLER_PROTOCOL_VERSION`, `SECURITY_CONTRACT_VERSION`, `MAX_COMMAND_BYTES`, `ControllerOperation`, `Disposition`, `ErrorCode`, `SecurityEnvelope`, `EngineeringRequest`, `SubmitRequestCommand`, `GetTaskCommand`, `SubmitResult`, `TaskInspectionResult`, and `ProtocolError`.
- Produces: `parse_command(payload: bytes) -> SubmitRequestCommand | GetTaskCommand`.
- Produces: `request_identity_document`, `request_digest`, `body_digest`, `security_document`, `security_digest`, `format_utc_timestamp`, `encode_submit_success`, `encode_task_success`, and `encode_error`.
- Consumes: `TaskStatus` from Task 1 and canonical helpers from `forge.canonical`.

The exact encoder signatures are:

```text
encode_submit_success(result: SubmitResult) -> bytes
encode_task_success(result: TaskInspectionResult) -> bytes
encode_error(operation: ControllerOperation | None, code: ErrorCode) -> bytes
```

`encode_error` selects its message from an immutable internal mapping; it never accepts a raw caller or exception string.

- [ ] **Step 1: Add valid command and response fixtures**

Use the approved design's synthetic submission unchanged for `valid-submit.json`. Use `tsk_` plus 32 lowercase `a` characters for `valid-get-task.json`. Response fixtures use `req_` plus 32 `b` characters, the same task ID, timestamps `2026-08-11T00:00:01Z`, and these exact discriminators:

```json
{"protocolVersion":"forge.dev/controller/v1alpha1","operation":"submitRequest","ok":true,"result":{"requestId":"req_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","taskId":"tsk_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","status":"queued","disposition":"created"}}
```

Create the replay fixture by changing only `disposition` to `replayed`. The task response contains only `requestId`, `taskId`, `mode`, `status`, optional `reasonCode`, `createdAt`, and `updatedAt`. The error fixture is exactly:

```json
{"protocolVersion":"forge.dev/controller/v1alpha1","operation":"unknown","ok":false,"error":{"code":"invalid_request","message":"request does not satisfy the controller contract"}}
```

- [ ] **Step 2: Write failing parser boundary tests**

In `tests/unit/test_controller_protocol.py`, parse both valid command fixtures and assert frozen typed models, tuple taint, `mode == "plan"`, and `repr(command)` does not contain the body. Add byte-literal tests for:

```python
INVALID_BYTES = (
    b"",
    b"\xff",
    b'{"protocolVersion":"forge.dev/controller/v1alpha1","operation":"getTask","operation":"submitRequest"}',
    b'{"protocolVersion":"forge.dev/controller/v1alpha1","operation":"getTask","taskId":"tsk_\\ud800"}',
    b'{"protocolVersion":"forge.dev/controller/v1alpha1","operation":"getTask","taskId":"tsk_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","n":NaN}',
    b'{"protocolVersion":"forge.dev/controller/v1alpha1","operation":"getTask","taskId":"tsk_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","n":9007199254740992}',
)
```

Assert every case raises `ProtocolError` with `ErrorCode.INVALID_REQUEST`, a bounded owned message, and no raw byte content. Assert 262,145 bytes fails before `json.loads` is called by monkeypatching it to raise if invoked.

- [ ] **Step 3: Add strict shape and semantic RED tests**

Parameterize mutations of the valid submission for unsupported/missing protocol, unknown root/request/security fields, missing security, wrong security version, arbitrary trust value `approved`, non-`plan` mode, empty or 65,537-scalar body, invalid references, invalid token fields, duplicate/unsorted taints, invalid dates, timezone offsets, and seven fractional digits. Require `unsupported_protocol` only for a present unsupported protocol version; all other contract failures are `invalid_request`.

Also assert these operation names fail ingress rather than becoming internal authority:

```python
for operation in ("claimNextEligible", "transitionTask", "reconcileRunning"):
    payload = json.dumps(
        {"protocolVersion": CONTROLLER_PROTOCOL_VERSION, "operation": operation}
    ).encode("utf-8")
    with pytest.raises(ProtocolError):
        parse_command(payload)
```

- [ ] **Step 4: Add identity and response RED tests**

Assert the request digest is stable across input member order, changes for every request/security/body identity mutation, and does not include the operation discriminator. Assert body digest is SHA-256 over exact UTF-8 bytes, so composed and decomposed Unicode remain distinct. Assert security digest covers the complete preserved envelope and unknown valid namespaced taints remain present.

Assert `format_utc_timestamp` converts aware UTC datetimes exactly to `2026-08-11T00:00:01Z` or `2026-08-11T00:00:01.123456Z`, never emits `+00:00`, and rejects naïve or non-UTC datetimes with an owned error. Controller-generated timestamps use this one formatter; source timestamps remain the validated original strings.

Parse each encoded response back to a document and assert it equals its fixture. Scan success/error documents to ensure none contains `body`, `projectRef`, `repositoryRef`, `security`, `ciphertext`, `nonce`, `keyId`, or an arbitrary `details` member.

- [ ] **Step 5: Run protocol tests and confirm RED**

```bash
.venv/bin/python -m pytest tests/unit/test_controller_protocol.py -q
```

Expected: collection fails because the protocol module and schemas do not exist.

- [ ] **Step 6: Implement both strict Draft 2020-12 schemas**

The command schema must use two `oneOf` branches with `additionalProperties: false` at every object boundary. Reuse these exact definitions inside the schema:

```json
{
  "reference": {"type":"string","pattern":"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$"},
  "token": {"type":"string","pattern":"^[a-z][a-z0-9._:-]{0,127}$"},
  "controllerTaskId": {"type":"string","pattern":"^tsk_[0-9a-f]{32}$"},
  "utcTimestamp": {"type":"string","pattern":"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\\.[0-9]{1,6})?Z$"}
}
```

The submit branch requires the exact normative fields, source namespace as a token, opaque source/actor/channel/project/repository references, `body` length 1 through 65,536, and `mode` constant `plan`. Its security object requires the contract constant, object ID and provenance as references, object type/producer/classification/retention as tokens, a valid UTC creation time, `trust` as exactly `trusted | untrusted | unknown`, and `taint` as a unique array of zero or more tokens. The get branch requires only protocol, operation, and task ID. Add `$comment` explaining that envelope validation proves structure only, not authentication, authorization, provenance validity, trust, policy, or host enforcement.

The response schema uses three `oneOf` branches: submit success, task success, and error. Error `operation` is `submitRequest`, `getTask`, or `unknown`; code is one of the eight approved codes; message is a 1-to-256-character string; there is no details field.

- [ ] **Step 7: Implement immutable models and strict parsing**

Use frozen slotted dataclasses and hide sensitive fields:

```python
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
```

`parse_command` must check `type(payload) is bytes`, check the byte bound, decode strict UTF-8, reject duplicate keys with `object_pairs_hook`, reject `NaN`/infinities with `parse_constant`, and normalize JSON/decode/recursion/canonicalization/schema failures without embedding their values. After duplicate-safe construction it records a valid `submitRequest` or `getTask` discriminator even when another field is malformed; only missing, duplicate, unparseable, or unknown operations become `operation=None`. It then runs `canonical_json_bytes` for whole-document I-JSON validation, accepts only the supported version, validates against the packaged schema, validates timestamps with `datetime.fromisoformat`, enforces sorted taint with `tuple(sorted(taint)) == tuple(taint)`, and constructs models. Never return a raw dict.

`format_utc_timestamp` requires a timezone-aware value whose UTC offset is zero, uses seconds when microseconds are zero and exactly six fractional digits otherwise, and replaces `+00:00` with `Z`.

- [ ] **Step 8: Implement exact digests and canonical encoders**

Use these projections and prefixes:

```python
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
```

Each encoder builds its exact response document, validates it with the packaged response validator, and returns `canonical_json_bytes(document)` without a transport newline.

Use this exact stable public message registry:

```python
PUBLIC_ERROR_MESSAGES = {
    ErrorCode.UNSUPPORTED_PROTOCOL: "protocol version is not supported",
    ErrorCode.INVALID_REQUEST: "request does not satisfy the controller contract",
    ErrorCode.IDEMPOTENCY_CONFLICT: "request identity conflicts with durable state",
    ErrorCode.TASK_NOT_FOUND: "task was not found",
    ErrorCode.INVALID_TRANSITION: "task transition is not allowed",
    ErrorCode.CONTROLLER_ALREADY_RUNNING: "controller already owns this state",
    ErrorCode.STATE_ERROR: "state operation failed",
    ErrorCode.ENCRYPTION_ERROR: "encryption operation failed",
}
```

- [ ] **Step 9: Make Task 2 GREEN and commit**

```bash
.venv/bin/python -m pytest tests/unit/test_controller_protocol.py tests/unit/test_task_state.py -q
make validate
git diff --check
git add src/forge/controller_protocol.py src/forge/resources/schemas/controller-command-v1alpha1.schema.json src/forge/resources/schemas/controller-response-v1alpha1.schema.json tests/unit/test_controller_protocol.py tests/fixtures/controller
git commit -m "feat: define versioned controller protocol"
```

Expected: strict byte, schema, semantic, identity, redaction, and response tests pass without adding a CLI or transport.

---

### Task 3: Authenticated request-encryption boundary

**Files:**
- Create: `src/forge/request_crypto.py`
- Create: `tests/unit/test_request_crypto.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `KeyHandle`, `EncryptedValue`, `EncryptionError`, `RequestCipher`, `Aes256GcmRequestCipher`, `request_body_aad`, and `state_key_verifier_aad`.
- `RequestCipher.algorithm` is fixed by the implementation before AAD construction.
- `encrypt(plaintext: bytes, associated_data: bytes, key: KeyHandle) -> EncryptedValue` returns only nonce and ciphertext.
- `decrypt(value: EncryptedValue, associated_data: bytes, key: KeyHandle) -> bytes` returns authenticated plaintext or a redacted owned error.
- Consumes: RFC 8785 canonicalization from `forge.canonical`; it does not consume a secret provider or protocol model.

- [ ] **Step 1: Write failing key-record, AAD, and redaction tests**

Create `tests/unit/test_request_crypto.py`. Assert `KeyHandle("key:synthetic", b"K" * 32)` is accepted, while 31/33 bytes, a non-byte key, and an invalid/empty key ID raise `EncryptionError("encryption operation failed")`. Require that none of the following representations contains the key ID, key bytes, nonce, or ciphertext:

```python
key = KeyHandle("key:synthetic", b"K" * 32)
value = EncryptedValue(nonce=b"N" * 12, ciphertext=b"C" * 32)
assert "key:synthetic" not in repr(key)
assert "KKKK" not in repr(key)
assert "NNNN" not in repr(value)
assert "CCCC" not in repr(value)
```

Assert `request_body_aad` equals RFC 8785 bytes for exactly this object:

```python
{
    "domain": "forge.request-body/v1",
    "protocolVersion": "forge.dev/controller/v1alpha1",
    "requestId": "req_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "idempotencyKey": {
        "sourceNamespace": "example-source",
        "sourceEventId": "event:0123",
    },
    "projectRef": "project:example",
    "repositoryRef": "repository:example",
    "bodyDigest": "sha256:" + "b" * 64,
    "securityDigest": "sha256:" + "c" * 64,
    "algorithm": "AES-256-GCM",
    "keyId": "key:synthetic",
}
```

Assert the verifier AAD is exactly the canonical object containing only domain, algorithm, and key ID.

- [ ] **Step 2: Add AES-GCM RED tests**

Require a 32-byte-key round trip, 12-byte nonce, distinct nonce for repeated encryption, and failure for a wrong key, modified AAD, modified nonce, truncated value, or flipped ciphertext bit. Inject a deterministic `nonce_source(size: int) -> bytes` in focused tests and assert it is called with 12. For every expected failure, assert the public string is exactly `encryption operation failed` and excludes all inputs and the underlying cryptography exception text.

Use `caplog` to prove normal operation and expected failure do not log plaintext, AAD, key ID, key bytes, nonce, or ciphertext.

- [ ] **Step 3: Run crypto tests and confirm RED**

```bash
.venv/bin/python -m pytest tests/unit/test_request_crypto.py -q
```

Expected: collection fails because `forge.request_crypto` does not exist.

- [ ] **Step 4: Add the bounded runtime dependency and install it**

Add this line to `[project].dependencies` in `pyproject.toml`:

```toml
"cryptography>=50,<51",
```

Then refresh the editable environment:

```bash
.venv/bin/python -m pip install -e '.[dev]'
```

- [ ] **Step 5: Implement redacted records and exact AAD builders**

Create these records in `src/forge/request_crypto.py`:

```python
@dataclass(frozen=True, slots=True)
class KeyHandle:
    key_id: str = field(repr=False)
    key_bytes: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class EncryptedValue:
    nonce: bytes = field(repr=False)
    ciphertext: bytes = field(repr=False)


class EncryptionError(ValueError):
    def __init__(self) -> None:
        super().__init__("encryption operation failed")
```

`KeyHandle.__post_init__` must accept `type(key_bytes) is bytes`, exactly 32 bytes, and a key ID matching `[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}`; it raises the same parameterless `EncryptionError` for every failure. Build both AAD documents exactly as asserted in Step 1 and return only `canonical_json_bytes`.

- [ ] **Step 6: Implement AES-256-GCM with an injectable nonce source**

Use this concrete public shape:

```python
class RequestCipher(Protocol):
    algorithm: str

    def encrypt(
        self, plaintext: bytes, associated_data: bytes, key: KeyHandle
    ) -> EncryptedValue:
        raise NotImplementedError

    def decrypt(
        self, value: EncryptedValue, associated_data: bytes, key: KeyHandle
    ) -> bytes:
        raise NotImplementedError


class Aes256GcmRequestCipher:
    algorithm = "AES-256-GCM"

    def __init__(
        self, nonce_source: Callable[[int], bytes] = secrets.token_bytes
    ) -> None:
        self._nonce_source = nonce_source
```

The concrete encrypt method validates exact `bytes`, obtains exactly 12 nonce bytes, calls `AESGCM(key.key_bytes).encrypt(nonce, plaintext, associated_data)`, and returns redacted `EncryptedValue`. Decrypt validates nonce length and calls `AESGCM.decrypt`. Normalize expected `InvalidTag`, `TypeError`, `ValueError`, and nonce-source shape failures to a new parameterless `EncryptionError`, chained with `from exc` only for local debugging; never log them.

- [ ] **Step 7: Make Task 3 GREEN and commit**

```bash
.venv/bin/python -m pytest tests/unit/test_request_crypto.py tests/unit/test_controller_protocol.py -q
make validate
git diff --check
git add pyproject.toml src/forge/request_crypto.py tests/unit/test_request_crypto.py
git commit -m "feat: add authenticated request encryption"
```

Expected: key, nonce, round-trip, tamper, AAD, and redaction tests pass on the supported interpreter without contacting a key service.

---

### Task 4: Ledger contracts and in-process controller core

**Files:**
- Create: `src/forge/state_ledger.py`
- Create: `src/forge/controller.py`
- Create: `tests/unit/test_controller.py`

**Interfaces:**
- Produces from `state_ledger.py`: `EncryptedRequestRecord`, `NewTaskRecord`, `NewTaskEvent`, `IngestBundle`, `IngestOutcome`, `TaskSnapshot`, `StateError`, `IdempotencyConflict`, `TaskNotFound`, `StateTransitionConflict`, `ControllerAlreadyRunning`, and `StateLedger`.
- Produces from `controller.py`: `Clock`, `IdSource`, `SystemClock`, `SystemIdSource`, `ControllerError`, `ControllerService`, and `start_controller`.
- Consumes: typed protocol commands/results, request cipher/key, task validators, and the ledger protocol. The core does not import `sqlite3`.

The controller-facing signatures are exactly:

```text
Clock.now() -> datetime
IdSource.new_request_id() -> str
IdSource.new_task_id() -> str
IdSource.new_event_id() -> str
ControllerService.handle(payload: bytes) -> bytes
ControllerService.submit_request(command: SubmitRequestCommand) -> SubmitResult
ControllerService.get_task(command: GetTaskCommand) -> TaskInspectionResult
ControllerService.claim_next_eligible(*, actor_ref: str) -> TaskSnapshot | None
ControllerService.transition_task(*, task_id: str, expected_status: TaskStatus, target_status: TaskStatus, reason_code: str | None, actor_ref: str) -> TaskSnapshot
ControllerService.close() -> None
```

- [ ] **Step 1: Define failing immutable-record and ledger-protocol tests**

In `tests/unit/test_controller.py`, construct records and assert they are frozen, their byte-bearing fields are absent from `repr`, and `TaskSnapshot` is the internal record that may contain project/repository while `TaskInspectionResult` is the public minimized view.

Use these exact storage records in `state_ledger.py`:

```python
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
```

`IngestBundle` contains one of each; `IngestOutcome` contains a `TaskSnapshot` and `created: bool`. `TaskSnapshot` contains request/task/project/repository/mode/status/reason/created/updated and no body, security envelope, or cryptographic material.

Define those result records exactly:

```python
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
```

- [ ] **Step 2: Add a recording fake ledger, cipher, clock, and IDs**

Inside the test module, implement a fake ledger with this exact method surface and call recording:

```text
ingest(bundle: IngestBundle) -> IngestOutcome
get_task(task_id: str) -> TaskSnapshot | None
load_encrypted_request(request_id: str) -> EncryptedRequestRecord | None
assert_encryption_binding(cipher: RequestCipher, key_handle: KeyHandle) -> None
transition(task_id, expected_status, target_status, reason_code, actor_ref, event_id, occurred_at) -> TaskSnapshot
claim_next_eligible(max_concurrency, actor_ref, event_id, occurred_at) -> TaskSnapshot | None
reconcile_running(event_id_factory, actor_ref, occurred_at) -> tuple[TaskSnapshot, ...]
close() -> None
```

The fake cipher records plaintext/AAD/key and returns `EncryptedValue(b"N" * 12, b"C" * 32)`. The fake clock always returns `datetime(2026, 8, 11, 0, 0, 1, tzinfo=timezone.utc)`. The ID source returns these sequences: `req_` + 32 `a`, `tsk_` + 32 `b`, and `evt_` + increasing 32-character lowercase hex.

- [ ] **Step 3: Write startup/readiness RED tests**

Assert `max_concurrency=True`, 0, and -1 fail before ledger access. Assert a valid start first calls `assert_encryption_binding` with the exact controller cipher/key pair, then calls `reconcile_running` once with actor `controller:startup`, the formatted fixed clock time, and the event ID callback, and only then returns a ready service. A binding mismatch must close the ledger, skip reconciliation, and return no service. If binding or reconciliation raises an owned error, assert the ledger closes and public error text excludes the fake sensitive exception. Assert direct handling on an unstarted service returns a redacted `state_error`, and close is idempotent.

- [ ] **Step 4: Write submit and replay RED tests**

Pass the valid submission through `ControllerService.handle`. Assert the cipher receives exact body UTF-8 bytes, canonical request AAD with generated request ID, the injected key handle, and no operation field. Assert the ledger receives one `IngestBundle` with:

- submission/security/body digests from Task 2;
- canonical security-envelope bytes but no plaintext body field;
- fixed cipher algorithm, key ID, nonce, and ciphertext;
- one queued task and an initial `None -> queued` event;
- controller receipt/event/task timestamps from the clock and source-event time unchanged.

For `IngestOutcome(created=True)`, compare the response to the created fixture. For `created=False`, require the existing durable request/task IDs and `replayed` disposition; generated replacement IDs and ciphertext must not appear in the response.

- [ ] **Step 5: Write inspection, transition, claim, and serialization RED tests**

Require `getTask` to return only the minimized result and map missing rows to `task_not_found`. Require `transition_task` to validate expected and target states, reject every target `running` before touching the ledger, pass a generated event ID and stable actor/reason to the ledger, and map ledger compare-and-set conflicts to `invalid_transition`.

Require `claim_next_eligible` to pass the configured N unchanged; a `None` outcome remains `None`, not an error. Use a blocking fake ledger plus two threads to assert controller access never overlaps, proving the service lock serializes all operations over a single ledger connection.

- [ ] **Step 6: Write public error and no-plaintext RED tests**

Parameterize expected mappings:

```python
EXPECTED_CODES = {
    IdempotencyConflict: ErrorCode.IDEMPOTENCY_CONFLICT,
    TaskNotFound: ErrorCode.TASK_NOT_FOUND,
    StateTransitionConflict: ErrorCode.INVALID_TRANSITION,
    ControllerAlreadyRunning: ErrorCode.CONTROLLER_ALREADY_RUNNING,
    StateError: ErrorCode.STATE_ERROR,
    EncryptionError: ErrorCode.ENCRYPTION_ERROR,
}
```

Assert responses contain only the stable code/message and exclude submitted body, security values, key ID, fake ciphertext, path, and raw exception. A malformed request with an already duplicate-safely parsed `submitRequest` or `getTask` discriminator preserves that operation in the error; missing, duplicate, unparseable, or unknown discriminators encode `operation="unknown"`. Expected domain failures use the recognized operation. Assert an unexpected `RuntimeError` from a fake propagates rather than being mislabeled as an expected success/error contract.

- [ ] **Step 7: Run controller tests and confirm RED**

```bash
.venv/bin/python -m pytest tests/unit/test_controller.py -q
```

Expected: collection fails because the ledger and controller modules do not exist.

- [ ] **Step 8: Implement the database-neutral ledger protocol and owned errors**

Define the protocol with these keyword-only mutation signatures:

```python
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
```

Each state exception has one fixed owned message and stores no raw database exception or sensitive value in public attributes.

- [ ] **Step 9: Implement clock, opaque IDs, startup, and readiness**

`SystemClock.now()` returns timezone-aware UTC. `SystemIdSource` uses `secrets.token_hex(16)` and exact `req_`, `tsk_`, or `evt_` prefixes. Validate every injected fake ID against its required pattern before persistence.

Use this startup boundary:

```python
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
```

`_start` formats one clock value, calls the ledger's binding assertion with the same cipher/key that submission will use, performs one locked reconciliation, and sets ready only after both succeed. `handle`, submit, inspect, transition, and claim check readiness. The SQLite adapter's `open` in Task 5 performs ownership/schema/key verification before it is passed to this factory; the second binding assertion prevents a composition caller from opening with key A and starting the controller with key B.

- [ ] **Step 10: Implement submission, minimized reads, and internal operations**

Under one `threading.RLock`, submission obtains one aware clock value and formats it with `format_utc_timestamp`, calculates exact Task 2 digests, generates request/task/event IDs, calls `request_body_aad` with the cipher's fixed algorithm and injected key ID, encrypts exact UTF-8 body bytes, and constructs the records asserted in Step 4. It calls ledger ingestion once and maps `created` to disposition.

Inspection copies only `request_id`, `task_id`, `mode`, `status`, `reason_code`, `created_at`, and `updated_at`. General transition calls `validate_general_transition` before ledger access. Claim generates one event ID and delegates global/repository/FIFO atomicity entirely to the ledger.

`handle` parses once, dispatches the two command types, encodes canonical success, and catches only `ProtocolError`, owned controller/state exceptions, `InvalidTaskTransition`, and `EncryptionError`. Use the eight fixed public messages; do not interpolate exception text. Unexpected exceptions propagate.

- [ ] **Step 11: Make Task 4 GREEN and commit**

```bash
.venv/bin/python -m pytest tests/unit/test_controller.py tests/unit/test_controller_protocol.py tests/unit/test_request_crypto.py tests/unit/test_task_state.py -q
make validate
git diff --check
git add src/forge/state_ledger.py src/forge/controller.py tests/unit/test_controller.py
git commit -m "feat: add in-process controller core"
```

Expected: the core is fully testable with fakes, has no SQLite import or transport, and returns only canonical redacted responses.

---

### Task 5: SQLite schema, ownership, key verification, and restart recovery

**Files:**
- Create: `src/forge/sqlite_state.py`
- Create: `tests/integration/test_sqlite_startup.py`
- Create: `tests/helpers/hold_sqlite_ledger.py`

**Interfaces:**
- Produces: `SqliteStateLedger.open(path: Path, *, cipher: RequestCipher, key_handle: KeyHandle) -> SqliteStateLedger`, context-manager close behavior, `assert_encryption_binding`, `get_task`, and `reconcile_running`.
- Consumes: ledger records/exceptions from Task 4, cipher/key/AAD from Task 3, and task statuses from Task 1.
- Owns: connection lifetime, thread lock, PRAGMA verification, schema transaction, key verifier, error normalization, and reconciliation transaction.

- [ ] **Step 1: Write failing new-database setting and schema tests**

Create `tests/integration/test_sqlite_startup.py` using only `tmp_path / "state.db"`, `Aes256GcmRequestCipher`, and `KeyHandle("key:synthetic", b"K" * 32)`. After `SqliteStateLedger.open`, query through a separate read only after closing the ledger and assert:

- `user_version == 1`;
- application tables are exactly `ledger_metadata`, `requests`, `tasks`, and `task_events`;
- indexes include the idempotency unique constraint, one-request/one-task uniqueness, `ux_tasks_running_repository`, `ix_tasks_queue`, and `ix_task_events_task_sequence`;
- the metadata singleton contains algorithm `AES-256-GCM`, a 12-byte verifier nonce, authenticated ciphertext, and next queue sequence 1;
- WAL remains the persisted journal mode; a recording connection wrapper proves the connection-local foreign-key, busy-timeout, locking, and synchronous settings were set and read back before use; and
- the database remains present after `close()`.

Monkeypatch a connection wrapper in focused tests so a wrong returned value for each required PRAGMA produces only `StateError("state operation failed")`.

- [ ] **Step 2: Add exact schema-version and fingerprint RED tests**

Create databases for these cases and require every open to fail closed without mutation:

1. `user_version=0` with an unexpected table;
2. `user_version=2`;
3. `user_version=1` missing an index;
4. `user_version=1` with a changed column type/nullability;
5. `user_version=1` with a changed foreign key;
6. `user_version=1` with a non-partial running-repository index; and
7. `user_version=1` with extra application objects.

Compare `user_version`, application object definitions, and seeded domain rows before/after each failed open. They must be unchanged; required connection setup may create SQLite-managed WAL sidecars or persist WAL mode, so the test must not mistake those operational files for a schema migration. No migration, repair, drop, or delete is allowed.

- [ ] **Step 3: Add key-verifier RED tests**

Require reopen with the same key to succeed. Require wrong key bytes, wrong key ID, a different cipher algorithm fake, modified verifier nonce, and modified verifier ciphertext to fail with a redacted encryption/state error, close the attempted connection, and preserve every task row. After opening correctly with key A, call `start_controller` with key B using the same key ID and require `assert_encryption_binding` to fail before reconciliation, close the ledger, and leave a seeded running task/event count unchanged. This proves the controller's submission key is the exact pair authenticated by the ledger rather than merely sharing an ID.

Search error strings and captured logs for the key ID, key bytes, nonce, ciphertext, database path, and raw `InvalidTag`/SQLite text; none may appear.

- [ ] **Step 4: Add real cross-process ownership RED tests**

Create `tests/helpers/hold_sqlite_ledger.py` with a fixed synthetic key and this behavior:

```python
from pathlib import Path
import sys

from forge.request_crypto import Aes256GcmRequestCipher, KeyHandle
from forge.sqlite_state import SqliteStateLedger


ledger = SqliteStateLedger.open(
    Path(sys.argv[1]),
    cipher=Aes256GcmRequestCipher(),
    key_handle=KeyHandle("key:synthetic", b"K" * 32),
)
print("ready", flush=True)
sys.stdin.readline()
ledger.close()
```

Launch it with `subprocess.Popen`, use `selectors.DefaultSelector` with a five-second bound before reading the `ready` line, and assert a second open returns `ControllerAlreadyRunning` immediately rather than waiting. Send one newline and wait for clean exit, then require open succeeds. In a separate test terminate only that spawned helper, wait for exit, and require the OS-released lock permits open. Use bounded `wait(timeout=5)`/`communicate(timeout=5)` and clean up only the spawned child in `finally`.

- [ ] **Step 5: Add reconciliation atomicity and preservation RED tests**

Seed synthetic tasks in every state after an initial create/close cycle. On reopen with the correct key, call `reconcile_running` with deterministic unique `evt_` IDs, actor `controller:startup`, and `2026-08-11T00:00:02Z`. Assert:

- every and only `running` task becomes `failed` with `reason_code=controller_restart`;
- each changed row receives one matching `running -> failed` event at the same timestamp;
- queued, waiting, review-ready, and terminal rows and their event counts remain unchanged;
- all changed rows commit together; and
- `start_controller` reports ready only after this method returns.

Inject a duplicate event ID on the second running task and require the entire reconciliation rolls back, leaving both tasks running and adding no event. Assert no automatic retry, executor call, worktree, filesystem reconciliation, or new queued task occurs.

- [ ] **Step 6: Run startup tests and confirm RED**

```bash
.venv/bin/python -m pytest tests/integration/test_sqlite_startup.py -q
```

Expected: collection fails because `forge.sqlite_state` does not exist.

- [ ] **Step 7: Implement the exact schema-v1 DDL**

Keep the DDL as a fixed module constant in `src/forge/sqlite_state.py`; do not add a migration framework or SQL plugin resource:

```sql
CREATE TABLE ledger_metadata (
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
    ON task_events(task_id, event_sequence);
```

The exact application-object set includes the four tables and three explicitly named indexes. SQLite-generated `sqlite_sequence` plus `sqlite_autoindex_*` rows originating from declared primary-key/unique constraints are allowed only when `PRAGMA index_list` reports origin `pk` or `u` and `PRAGMA index_xinfo` matches the declared constrained columns. Their SQL is `NULL`, so do not hard-code generated names as application DDL; reject all other extra internal/application objects. Record `PRAGMA user_version=1` in the same creation transaction.

- [ ] **Step 8: Implement connection setup, ownership, and error normalization**

Open exactly one connection with:

```python
sqlite3.connect(
    path,
    timeout=0.0,
    isolation_level=None,
    check_same_thread=False,
    uri=False,
)
```

Under an adapter-owned `threading.RLock`, set and read back `busy_timeout=0`, `foreign_keys=ON`, `main.locking_mode=EXCLUSIVE`, `main.journal_mode=WAL`, and `main.synchronous=FULL`; require results 0, 1, `exclusive`, `wal`, and 2. Select WAL before DDL. Then execute `BEGIN IMMEDIATE`, which acquires the lock that exclusive mode retains for the connection lifetime.

Detect busy by `(exc.sqlite_errorcode & 0xFF) == sqlite3.SQLITE_BUSY` and translate it only during ownership acquisition to parameterless `ControllerAlreadyRunning`. Translate every other expected database failure to parameterless `StateError`. Always rollback when active and close the connection on failed open. Never include `path` or `str(exc)` in owned errors/logs.

- [ ] **Step 9: Implement new-versus-existing schema validation and key verification**

Treat only `user_version=0` plus zero application objects as new. In the open transaction, create every object, encrypt fixed verifier plaintext `b"forge-state-key-verifier/v1"` with fresh nonce and `state_key_verifier_aad(algorithm, key_id)`, insert singleton metadata with next sequence 1, set user version, and validate the resulting fingerprint.

For existing version 1, compare the exact named application objects and normalized SQL plus `PRAGMA table_xinfo`, `foreign_key_list`, `index_list`, and `index_xinfo` against module constants. Verify SQLite autoindexes by origin, uniqueness, and constrained columns as described in Step 7 rather than treating their generated names/NULL SQL as portable DDL. Reject every mismatch. Select exactly one metadata row; require stored algorithm and key ID to match the injected cipher/key, decrypt with the domain-separated AAD, and use `hmac.compare_digest` against the fixed verifier bytes. Propagate only the owned redacted crypto/state exception. Commit only after all checks pass.

Implement `assert_encryption_binding` by re-reading the immutable verifier metadata under the connection lock and authenticating it with the supplied controller cipher/key. It uses the same fixed plaintext and domain-separated AAD, stores no key fingerprint, and returns only after algorithm, key ID, decryption, and constant-time plaintext comparison succeed.

- [ ] **Step 10: Implement snapshots and atomic restart reconciliation**

Map rows explicitly by named columns to `TaskSnapshot`; never use `SELECT *`. `get_task` holds the connection lock and returns `None` for absence.

`reconcile_running` executes one `BEGIN IMMEDIATE`, selects all running rows ordered by task ID, obtains one validated event ID per row from the callback inside that same transaction, updates each row to `failed/controller_restart`, and inserts its matching event. If any callback, update, or insert fails, rollback all rows/events and raise one owned error. Return immutable snapshots after the updates and commit once. No other status is selected or rewritten.

- [ ] **Step 11: Make Task 5 GREEN and commit**

```bash
.venv/bin/python -m pytest tests/integration/test_sqlite_startup.py tests/unit/test_controller.py tests/unit/test_request_crypto.py -q
make validate
git diff --check
git add src/forge/sqlite_state.py tests/integration/test_sqlite_startup.py tests/helpers/hold_sqlite_ledger.py
git commit -m "feat: add SQLite controller startup recovery"
```

Expected: exact schema/key validation, immediate second-process rejection, clean/crash lock release, and atomic running-only reconciliation all pass on temporary local files.

---

### Task 6: Atomic SQLite ingestion, transitions, scheduling, and vertical integration

**Files:**
- Modify: `src/forge/sqlite_state.py`
- Create: `tests/integration/test_controller_sqlite.py`

**Interfaces:**
- Completes `StateLedger` with `ingest`, `load_encrypted_request`, `transition`, and `claim_next_eligible`.
- Consumes controller-produced immutable records only; SQL rows and raw exceptions never cross the adapter boundary.
- Preserves one adapter-owned connection lock around every read/transaction so direct competing-thread conformance tests cannot use the connection concurrently.

- [ ] **Step 1: Write idempotent-ingestion and rollback RED tests**

Create synthetic `IngestBundle` builders in `tests/integration/test_controller_sqlite.py`. For a new bundle, require one request, one queued task, and one `None -> queued` event after commit, all linked by foreign keys. Require the returned snapshot and `created=True` only after the rows exist.

Submit a second bundle with the same `(source_namespace, source_event_id)` and the same submission digest but different generated request/task/event IDs and ciphertext. Require `created=False`, original durable IDs, original ciphertext, and unchanged row/event counts. Change each immutable submission field in turn through a recomputed digest and require `IdempotencyConflict` with no mutation.

Preinsert the proposed initial event ID for an unrelated task, ingest a new bundle using that duplicate event ID, and require request/task/event inserts all roll back. Repeat with malformed record data that violates a late task/event constraint.

- [ ] **Step 2: Add concurrent replay and encrypted-storage RED tests**

Use a `threading.Barrier` and two threads calling the same ledger. For equivalent bundles with distinct generated IDs, require exactly one created result, one replayed result, and one durable task/event. For conflicting digests, require one created result and one `IdempotencyConflict`.

Use a distinctive body such as `BODY-PLAINTEXT-SENTINEL-7f3c` through the real controller. Assert `load_encrypted_request` returns all fields needed to reconstruct request AAD plus nonce/ciphertext, but no plaintext field or decryption method exists on controller/ledger. Read every existing `state.db`, `state.db-wal`, and `state.db-shm` file as bytes before and after close/checkpoint; the sentinel must not occur. Assert the ciphertext decrypts only when the test reconstructs the exact AAD directly through the cipher boundary.

- [ ] **Step 3: Write atomic transition and requeue RED tests**

For every allowed general transition from Task 1, create the source status, call ledger transition with exact expected status, and assert the task row and one event commit together. For all disallowed pairs, stale expected status, and every attempt to enter `running`, require `StateTransitionConflict` or `InvalidTaskTransition` and no row/event change.

Require transition to `queued` from waiting/review states to allocate a fresh monotonically increasing queue sequence at the tail. Terminal states remain immutable. Inject a duplicate event ID and assert the state, reason, update time, queue counter, and events all roll back. Require missing task to raise `TaskNotFound` without exposing its ID in the exception string.

- [ ] **Step 4: Write N, repository, eligible-FIFO, and overflow RED tests**

Cover `max_concurrency` values 1, 2, and 3 without a module default. For N=2, queue tasks in this order:

```text
sequence 1: repository:a
sequence 2: repository:a
sequence 3: repository:b
sequence 4: repository:c
```

Require claims 1 and 3 while repository A is busy, proving eligible FIFO and that an older blocked repository does not prevent progress elsewhere. A third claim at global capacity returns `None`; sequences 2 and 4 remain queued. After completing the first task, require the oldest newly eligible task to claim. Query the partial unique index defensively by attempting a direct second running row for the same repository and requiring an integrity failure.

Require `True`, zero, and negative N to fail before transaction mutation. No result is marked failed merely because capacity is full.

- [ ] **Step 5: Add competing-claim RED tests**

Queue at least six tasks across three repositories, synchronize four threads with a barrier, and call `claim_next_eligible(max_concurrency=2)` with unique event IDs. Assert exactly two non-`None` claims, global running count 2, distinct repository references, one matching event per claim, and every overflow task still queued. Repeat after freeing capacity to prove later progress.

Use the same test with several tasks from one repository and N greater than one; exactly one may run. The ledger's RLock may serialize connection use, but the test must start calls concurrently so future implementation changes retain both invariants.

- [ ] **Step 6: Write real controller-to-SQLite RED tests**

Open a temporary ledger with the real AES cipher, start a controller with fixed clock/IDs and N=2, then pass raw valid submit bytes through `handle`. Parse the canonical success response, call raw `getTask`, and verify the minimized response. Replay identical bytes and require original IDs plus `replayed`; change only the body and require `idempotency_conflict`.

Claim through the internal in-process method, close, reopen with the same key, start another controller, and require the formerly running task is now `failed/controller_restart` before `getTask` succeeds. Verify queued work survives, no executor is contacted, and no automatic retry occurs.

Scan responses, `repr`, captured logs, and database files for body, raw security envelope values, key material, nonce, private temp path, or raw SQLite/cryptography exceptions according to each boundary's allowed storage; public output/logs contain none, and database storage contains only the explicitly allowed minimized metadata/ciphertext.

- [ ] **Step 7: Run integration tests and confirm RED**

```bash
.venv/bin/python -m pytest tests/integration/test_controller_sqlite.py -q
```

Expected: the startup subset passes, while unimplemented ingestion, transition, claim, and vertical operations fail.

- [ ] **Step 8: Implement transactional ingestion**

Before SQL, validate the immutable record shapes, typed statuses, ID/reference/token/timestamp patterns, digest forms, exact algorithm/key/nonce/ciphertext consistency, and initial event invariants (`previous_status is None`, `next_status is queued`, no reason). Then hold the adapter lock and execute `BEGIN IMMEDIATE`.

Look up the unique source pair first. If present, compare only `submission_digest`; equal returns the original task snapshot without changing ciphertext/counters/events, unequal raises `IdempotencyConflict`. For a new request, allocate a monotonic sequence atomically with:

```sql
UPDATE ledger_metadata
SET next_queue_sequence = next_queue_sequence + 1
WHERE singleton = 1
RETURNING next_queue_sequence - 1;
```

Insert the request, queued task, and initial event in that order, then commit once. Any validation, integrity, callback, or database failure rolls back once and becomes the matching owned exception. The uniqueness constraint remains the defensive final check for a competing idempotency key.

- [ ] **Step 9: Implement encrypted-material loading and atomic general transition**

`load_encrypted_request` selects named columns and reconstructs `EncryptedRequestRecord`; it never decrypts. `transition` starts `BEGIN IMMEDIATE`, selects current status, compares the supplied expected status in the transaction, and calls `validate_general_transition`. When target is queued, allocate a new queue sequence with the metadata counter; otherwise preserve the prior sequence. Update status/reason/time with an expected-status predicate, require row count one, append the event, and commit. Any event failure rolls back the update and counter.

Do not expose a standalone append/update/delete event method. Append-only behavior here is ledger-interface conformance, not a claim that SQLite host permissions prevent direct file mutation.

- [ ] **Step 10: Implement the atomic eligibility claim**

Validate positive non-boolean N and event metadata, then in one `BEGIN IMMEDIATE` transaction count running tasks. Return `None` with a clean commit when at capacity. Otherwise select exactly:

```sql
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
LIMIT 1;
```

If absent, return `None`. Validate the claim-only transition, conditionally update `queued -> running`, clear the current reason, set update time, append one matching event, and commit. Treat the partial unique index as a defensive constraint; the count/selection/update transaction is the global-N guarantee. Do not add priorities, weights, reservations, worker pools, retries, or authorization claims.

- [ ] **Step 11: Make Task 6 GREEN and commit**

```bash
.venv/bin/python -m pytest tests/integration/test_controller_sqlite.py tests/integration/test_sqlite_startup.py -q
.venv/bin/python -m pytest tests/unit -q
make validate
git diff --check
git add src/forge/sqlite_state.py tests/integration/test_controller_sqlite.py
git commit -m "feat: complete SQLite controller ledger"
```

Expected: atomic ingestion/replay, encrypted storage, exhaustive transitions, configurable scheduling, competing claims, and the complete raw-bytes-to-SQLite vertical path pass.

---

### Task 7: Packaged contracts, security/status documentation, and final evidence

**Files:**
- Create: `tests/wheel_controller_smoke.py`
- Modify: `tests/validate-contracts.sh`
- Modify: `.github/workflows/validate.yml`
- Modify: `Makefile`
- Modify: `README.md`
- Modify: `config/README.md`
- Modify: `examples/README.md`
- Modify: `tests/README.md`
- Modify: `SECURITY.md`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/security/threat-model.md`
- Modify: `docs/security/trust-taint-provenance.md`

**Interfaces:**
- Consumes: all Slice 3 modules, schemas, fixtures, tests, approved design, and ADR-0010.
- Produces: installed-wheel evidence for packaged schemas, AES-GCM, and temporary SQLite; accurate public implemented/non-implemented status.
- Does not add a controller CLI command, socket, daemon, deployment profile, executor, workspace integration, secret provider, or reference-deployment mutation.

- [ ] **Step 1: Add failing repository-contract checks for the new public artifacts**

Extend `tests/validate-contracts.sh` to run `python3 -m json.tool` over both controller schemas and all six valid controller fixtures. Add these files to `required_files`:

```text
docs/adr/0010-adopt-a-contract-first-single-node-controller-core.md
docs/superpowers/specs/2026-08-11-controller-state-design.md
docs/superpowers/plans/2026-08-11-controller-state.md
src/forge/resources/schemas/controller-command-v1alpha1.schema.json
src/forge/resources/schemas/controller-response-v1alpha1.schema.json
tests/fixtures/controller/valid-submit.json
tests/fixtures/controller/valid-get-task.json
tests/fixtures/controller/valid-submit-created-response.json
tests/fixtures/controller/valid-submit-replayed-response.json
tests/fixtures/controller/valid-get-task-response.json
tests/fixtures/controller/valid-error-response.json
```

Add grep assertions that architecture names the in-process controller and SQLite as an adapter, roadmap marks Slice 3 implemented, and security status explicitly denies host-enforcement claims.

- [ ] **Step 2: Run contract checks and confirm documentation RED**

```bash
make contracts
```

Expected: new JSON artifacts are valid, while the new implemented-status grep assertions fail against stale public documentation.

- [ ] **Step 3: Create an installed-wheel controller smoke script**

Create `tests/wheel_controller_smoke.py` with no repository-source imports or external access. It must perform these exact operations:

```python
from importlib.resources import files
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonschema import Draft202012Validator

from forge.request_crypto import Aes256GcmRequestCipher, KeyHandle
from forge.sqlite_state import SqliteStateLedger


for schema_name in (
    "controller-command-v1alpha1.schema.json",
    "controller-response-v1alpha1.schema.json",
):
    resource = files("forge").joinpath("resources/schemas", schema_name)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)

key = KeyHandle("key:synthetic", b"K" * 32)
cipher = Aes256GcmRequestCipher()
encrypted = cipher.encrypt(b"synthetic body", b"synthetic aad", key)
assert cipher.decrypt(encrypted, b"synthetic aad", key) == b"synthetic body"

with TemporaryDirectory() as directory:
    path = Path(directory) / "state.db"
    ledger = SqliteStateLedger.open(path, cipher=cipher, key_handle=key)
    ledger.close()
    assert path.is_file()
```

Run this script once from the editable environment and require no output or external side effect.

- [ ] **Step 4: Extend CI without weakening its matrix or permissions**

Keep `contents: read`, Python 3.12/3.14, and the existing validation/build steps. After the existing 3.12 wheel install, add:

```yaml
      - name: Smoke-test installed controller package
        if: matrix.python-version == '3.12'
        run: wheel-smoke/bin/python tests/wheel_controller_smoke.py
```

The normal `make validate` path already discovers all new pytest files. Update only the Make help/validation description so it says contracts, tests, configuration, planning, and controller evidence; do not add package builds to every local validation run.

- [ ] **Step 5: Update architecture, roadmap, and user-facing status accurately**

Update `README.md`, `config/README.md`, `examples/README.md`, `tests/README.md`, `docs/architecture.md`, and `docs/roadmap.md` with this exact distinction:

- implemented: strict in-process controller contract, pure transitions, AES-256-GCM request-body boundary, and first single-node SQLite adapter;
- verified: idempotency, atomic events/transitions, configurable N including N=2 tests, one running task per repository, exclusive ownership, and restart failure reconciliation;
- still absent: socket/daemon/CLI ingress, authentication/authorization, executor, Codex/Hermes integration, workspaces/worktrees, secret-provider delivery, approvals/policy, apply/doctor, host enforcement, deployment, merge, and release; and
- roadmap: Slice 3 implemented; Slice 4 executor/workspace boundary is next, subject to a separate design and approval.

Do not add `maxConcurrency` to the Environment schema in this slice. Explain that it is an injected effective controller setting with no core default; the reference deployment rollout remains 1 until its separate executor/host acceptance and may later target 2 through its own reviewed configuration.

- [ ] **Step 6: Update security status without overclaiming the envelope**

Change `SECURITY.md`, `docs/security/trust-taint-provenance.md`, and `docs/security/threat-model.md` to say:

```text
Slice 3 implements structural validation and lossless preservation of the
minimum forge.dev/security/v1alpha1 envelope embedded in controller requests.
It also encrypts request bodies at the SQLite storage boundary. These checks do
not authenticate callers, validate provenance chains or attestations, increase
trust, remove taint, authorize an effect, deliver or manage keys, isolate code,
or prove runtime, host, network, or external-service enforcement.
```

Keep the broader security schemas, full validators, policy engine, adapter capability enforcement, and host controls described as future work. Preserve the rule that unknown valid taints are forwarded. Do not rewrite historical ADR-0007 or approved design records as though the whole security contract were now implemented.

- [ ] **Step 7: Run focused, full, package, and installed-wheel verification**

Before claiming completion, invoke `superpowers:verification-before-completion` and run fresh evidence:

```bash
.venv/bin/python -m pytest tests/unit/test_task_state.py tests/unit/test_controller_protocol.py tests/unit/test_request_crypto.py tests/unit/test_controller.py -q
.venv/bin/python -m pytest tests/integration/test_sqlite_startup.py tests/integration/test_controller_sqlite.py -q
make validate
make package
python3 -m venv wheel-smoke
wheel-smoke/bin/pip install --force-reinstall dist/forge_control-0.1.0.dev0-py3-none-any.whl
wheel-smoke/bin/python tests/wheel_controller_smoke.py
git diff --check
git status --short
```

Expected: all focused and repository tests pass on synthetic local inputs, source/wheel build succeeds, the installed wheel loads both schemas and exercises AES/SQLite, diff check is clean, and status contains only intentional Slice 3 changes.

- [ ] **Step 8: Review acceptance coverage and security boundaries**

Invoke `superpowers:requesting-code-review`. The reviewer must map each acceptance criterion to fresh evidence:

| Acceptance criterion | Required evidence |
| --- | --- |
| Strict/redacted protocol | protocol unit tests and response-schema fixtures |
| Same replay IDs/conflicting replay failure | controller/SQLite integration tests |
| No body plaintext in SQLite/logs | database/WAL byte scan and caplog assertions |
| Atomic state plus events | injected event-collision rollback tests |
| Global N and repository one | N=2 eligible-FIFO and competing-claim tests |
| Second controller fails | real helper subprocess ownership test |
| Restart fails only running work | key-before-reconcile and state-preservation tests |
| Package works without providers | built-wheel smoke using temporary SQLite |

Address every actionable finding, rerun the smallest affected test, then rerun the full Step 7 evidence. Do not merge, push, deploy, publish, or access a live provider as part of review.

- [ ] **Step 9: Commit public evidence explicitly**

```bash
git add Makefile pyproject.toml tests/validate-contracts.sh tests/wheel_controller_smoke.py .github/workflows/validate.yml README.md config/README.md examples/README.md tests/README.md SECURITY.md docs/architecture.md docs/roadmap.md docs/security/threat-model.md docs/security/trust-taint-provenance.md
git commit -m "docs: publish controller state evidence"
```

Expected: the final implementation history remains seven focused, reviewable commits after this plan commit; no reference deployment, private configuration, runtime database, build environment, or external system is committed.

## Execution handoff

Execute one task at a time in the listed order. Task 1 through Task 4 establish provider-neutral contracts; Task 5 and Task 6 implement the first adapter without leaking it into core; Task 7 updates public claims only after fresh verification. Preserve unrelated user changes and stop for direction if a required action would expand into transport, execution, credential delivery, deployment, publication, or destructive cleanup.
