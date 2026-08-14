# Controller and State Design

## Status

Approved for implementation planning on 2026-08-11. Slice 3 is implemented in
the current source tree. Current delivery status is tracked in the
[roadmap](../../roadmap.md).

This design is Slice 3 of the approved portable Forge MVP. It defines a small,
transport-neutral controller core and its first durable state implementation.
It does not install, deploy, or connect a real gateway, executor, workspace, or
host service.

The durable architecture decision is recorded by
[ADR-0010](../../adr/0010-adopt-a-contract-first-single-node-controller-core.md).

## Context

Slice 1 established the portable configuration contract and offline
validation. Slice 2 added deterministic planning for the exact built-in
`noop+noop` adapter. Forge still has no runtime owner for immutable engineering
requests, task transitions, concurrency, or recovery after a process restart.

Slice 3 must add those contracts without making SQLite, Codex, Hermes,
Discord, Unix sockets, systemd, OCI, or any secret provider a universal Forge
requirement. Repository content, request content, model output, tool output,
and external metadata remain data rather than authority.

## Goals

- Publish a strict, versioned, transport-neutral controller protocol.
- Provide an in-process controller core whose dependencies are injected.
- Persist encrypted request bodies, minimized plaintext metadata, tasks, and
  append-only transition evidence.
- Make request ingestion idempotent and transactional.
- Validate every task-state transition.
- Support configurable global concurrency and one running task per repository.
- Reject a second controller for the same SQLite environment.
- Reconcile interrupted work conservatively before accepting new requests.
- Return stable, redacted errors without exposing sensitive state.

## Non-goals

This slice does not implement:

- a Unix-domain socket, daemon, or systemd service;
- Hermes, Discord, Codex, executor, or workspace integration;
- operating-system sandboxing or host enforcement;
- a secret-provider adapter or operational key delivery;
- approvals, result delivery, artifacts, automatic retry, or priority queues;
- key rotation automation or a multi-key keyring;
- event replay, projections, snapshots, or a general event-sourcing system;
- PostgreSQL, network filesystems, multiple active controllers, or clustering;
- private `forge-ops` configuration, OCI access, deployment, merge, or release.

## Chosen Approach

Use a layered in-process core with injected boundaries:

```text
versioned protocol models and validation
  -> controller application service
       -> pure task transition rules
       -> state-ledger protocol
            -> SQLite state ledger
       -> request-cipher protocol
            -> AES-256-GCM request cipher
```

The controller coordinates policy-neutral application rules. It does not issue
SQL, choose a secret provider, start a process, create a worktree, or claim
host enforcement. The SQLite ledger owns database transactions and the
single-controller lock. The cipher owns authenticated encryption but receives
key material from its caller.

The interfaces remain deliberately narrow. They support only the operations
required by this slice; no registry or generic plugin framework is added.

## Versioned Service Protocol

The first contract version is `forge.dev/controller/v1alpha1`. Protocol values
must be JSON/I-JSON compatible and use the repository's RFC 8785 canonical
JSON profile for identity and digest calculations. Unknown fields, duplicate
keys, unsupported versions, malformed Unicode, non-finite numbers, and
integers outside the interoperable range fail validation.

The initial transport-neutral service supports two client operations:

1. `submitRequest` validates and durably ingests an engineering request.
2. `getTask` returns non-sensitive task identity, state, and timestamps.

Scheduling, transition, cryptographic storage, and startup reconciliation are
internal in-process controller operations. They are not exposed as generic
ingress commands and do not receive authority merely by being internal. A
later Unix-socket adapter may encode the two client operations without changing
their semantics.

The strict parser consumes bounded UTF-8 JSON bytes and detects duplicate
object keys before constructing a model. Future transports provide only
framing, peer authentication, authorization, and delivery. A structurally
valid command is data, not authority to execute code: no real executor may be
connected until a later policy and adapter slice defines and tests admission
enforcement.

### Submit request

A submission contains:

- the controller protocol version;
- a source namespace and opaque source event identifier;
- opaque actor, channel, project, and repository references;
- the requested mode, which is exactly `plan` in this protocol version;
- the exact normalized request body as a string;
- the `forge.dev/security/v1alpha1` contract version, object identifier and
  type, creation time, trust state, taint set, provenance reference, producing
  component class, classification, and retention hint; and
- the source event time copied from the originating system.

Adapters must supply opaque references rather than credentials, raw sensitive
values, private filesystem locations, or deployment-specific secrets. The
controller enforces reference syntax and length but does not claim it can
recognize every secret embedded in an otherwise valid string. It checks the
security-envelope structure and preserves its values. This slice does not
issue trust attestations, remove taint, make approval decisions, or implement a
policy engine.

On success the response returns the protocol version, durable request ID,
durable task ID, current task status, and whether the call created or replayed
the record. It never returns plaintext, ciphertext, a nonce, key material, raw
provenance content, or an internal database error.

### Task inspection

Task inspection returns only the opaque task and request IDs, mode, current
state, stable reason code when present, and controller-generated timestamps.
Project and repository references, request bodies, security metadata, and
cryptographic fields are unavailable through this operation. A future
transport or policy adapter must authenticate and authorize its caller before
invoking even this minimized read; this core does not claim that enforcement.

### Compatibility

The controller accepts only explicitly supported protocol versions. It does
not silently downgrade, infer a version, ignore unknown fields, or reinterpret
an invalid request. A future incompatible change requires a new protocol
version and compatibility tests.

### Normative message shape and bounds

The packaged v1alpha1 schemas use `additionalProperties: false` at every
object boundary. A submission has this exact shape:

```json
{
  "protocolVersion": "forge.dev/controller/v1alpha1",
  "operation": "submitRequest",
  "request": {
    "sourceNamespace": "example-source",
    "sourceEventId": "event:0123",
    "sourceEventTime": "2026-08-11T00:00:00Z",
    "actorRef": "actor:example",
    "channelRef": "channel:example",
    "projectRef": "project:example",
    "repositoryRef": "repository:example",
    "mode": "plan",
    "body": "Review the synthetic change and produce a plan.",
    "security": {
      "contractVersion": "forge.dev/security/v1alpha1",
      "objectId": "object:example",
      "objectType": "engineering-request",
      "createdAt": "2026-08-11T00:00:00Z",
      "trust": "unknown",
      "taint": ["external-input", "user-supplied"],
      "provenanceRef": "provenance:example",
      "producerClass": "gateway-adapter",
      "classification": "private",
      "retentionHint": "task-lifecycle"
    }
  }
}
```

Task inspection has exactly `protocolVersion`, `operation: "getTask"`, and a
controller-generated `taskId`. A successful response has
`protocolVersion`, the recognized `operation`, `ok: true`, and `result`.
Submission results contain `requestId`, `taskId`, `status`, and
`disposition: "created" | "replayed"`. Inspection results contain
`requestId`, `taskId`, `mode`, `status`, optional stable `reasonCode`,
`createdAt`, and `updatedAt`. An error response has `protocolVersion`, the
recognized operation or `unknown`, `ok: false`, and only
`error: {"code": ..., "message": ...}`; it has no arbitrary details member.

The parser enforces these bounds before model construction:

- at most 256 KiB of UTF-8 JSON for one command;
- 1 through 65,536 Unicode scalar values in `body`;
- opaque references matching
  `[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}` exactly;
- namespaces, classifications, retention hints, producer classes, taints, and
  reason codes matching `[a-z][a-z0-9._:-]{0,127}` exactly;
- unique, lexicographically sorted taint values so set identity is stable;
- valid UTC RFC 3339 timestamps ending in `Z`, with no more than six
  fractional-second digits; and
- controller IDs with 128 random bits encoded as lowercase hexadecimal and
  prefixed by `req_`, `tsk_`, or `evt_` for their type.

The idempotency digest projection is exactly the canonical object containing
`protocolVersion` and `request` from a validated `submitRequest`; it excludes
the fixed operation discriminator and every controller-generated field. The
controller does not perform Unicode normalization or rewrite `body` after
validation.

## Core Components

### Protocol models and validator

Immutable protocol models are constructed only from schema-valid input. Raw
dictionaries do not cross into controller operations as trusted values. The
validator normalizes failures to stable public error codes.

### Controller application service

The service coordinates:

- request ingestion and idempotent replay;
- retrieval of non-sensitive task state;
- claiming the next eligible queued task;
- validated state transitions;
- startup reconciliation before readiness.

It depends on a state ledger, request cipher, clock, opaque-ID source, and
effective concurrency configuration. It serializes state-changing operations
before using the ledger's single connection; task concurrency does not imply
concurrent unsynchronized database access. Tests can replace each boundary
with a small in-memory fake. This slice provides no production executor fake
or runtime adapter.

### Task transition rules

Task-state validation is pure logic with no database, clock, or adapter
dependency. The initial states are:

- `queued`
- `running`
- `waiting_user`
- `waiting_approval`
- `review_ready`
- `completed`
- `failed`
- `cancelled`

The last three are terminal. `waiting_approval` and `review_ready` preserve the
approved MVP vocabulary, but this slice does not implement approval or review
features.

Allowed transitions are:

| From | To |
| --- | --- |
| new task | `queued` |
| `queued` | `running`, `failed`, `cancelled` |
| `running` | `waiting_user`, `waiting_approval`, `review_ready`, `completed`, `failed`, `cancelled` |
| `waiting_user` | `queued`, `failed`, `cancelled` |
| `waiting_approval` | `queued`, `failed`, `cancelled` |
| `review_ready` | `queued`, `completed`, `failed`, `cancelled` |

A user reply, approval, or requested revision returns the task to `queued`
rather than bypassing scheduler limits. Terminal states have no outgoing
transition. `queued` to `running` is available only through the atomic
`claimNextEligible` operation; the general transition operation rejects every
attempt to enter `running`. Invalid transitions do not change persistent state.

### State ledger protocol

The controller uses a narrow ledger protocol for:

- idempotent request ingestion;
- non-sensitive task reads;
- atomic state transition plus event append;
- atomic claim of the next eligible task;
- startup reconciliation; and
- loading encrypted request material by durable ID.

Transaction ownership belongs to the ledger implementation. The application
service must not simulate atomicity with several independent ledger calls. A
transition supplies its expected current state, and the ledger rechecks that
state in the same transaction before updating the row and appending the event.

### Request cipher protocol

The cipher accepts plaintext bytes, canonical authenticated metadata, and
caller-supplied `KeyHandle` containing an opaque key ID and key bytes. The
algorithm is fixed by the cipher implementation before associated data is
constructed. Encryption returns only a fresh nonce and ciphertext; the
controller stores them with the input key ID and algorithm identifier.
Decryption requires the same authenticated metadata and key handle.

The first implementation uses AES-256-GCM through a maintained cryptographic
library. It accepts exactly 32-byte keys and generates a fresh 96-bit random
nonce for each encryption. It does not derive keys from passwords, reuse a
nonce, log inputs, or store keys.

The cipher provides decryption for authenticated round-trip validation and the
database key verifier. The controller exposes no generic plaintext-read
operation in this slice. Connecting decrypted content to an executor requires
a later, separately authorized, taint-preserving boundary.

## SQLite State Ledger

SQLite is the first single-node state adapter, not a portable core
requirement. The database path is injected and must resolve to a local
filesystem selected by the deployment.

The first schema contains only operational metadata plus these domain tables:

Operational metadata includes an encrypted, domain-separated key verifier for
the one active key handle. A new database encrypts a fixed verifier value with
a fresh nonce. Startup must decrypt and compare it before reconciliation; key
ID or key-length checks alone are insufficient. Automated key replacement and
multi-key reads remain out of scope.

### `requests`

- opaque request ID;
- source namespace and source event ID;
- project, repository, mode, and minimized security metadata;
- body and security-envelope digests;
- encryption algorithm, opaque key ID, nonce, and ciphertext; and
- source event and controller receipt timestamps.

The pair `(source_namespace, source_event_id)` is unique.

### `tasks`

- opaque task ID and request reference;
- project and repository references;
- mode and current state;
- stable current reason code when present;
- monotonic queue sequence; and
- creation and update timestamps.

One task is created for each accepted request in this slice.
SQLite adds a partial unique index on repository reference for rows whose state
is `running`, providing a defensive database constraint in addition to the
claim transaction. The serialized controller transaction enforces the global
N limit, which cannot be expressed by that index.

### `task_events`

- monotonic event sequence and opaque event ID;
- task reference;
- previous and next state;
- stable reason code;
- minimized actor or component reference; and
- event timestamp.

Events are append-only through the ledger interface. SQLite triggers or
permissions are not represented as host enforcement; conformance is provided
by the implementation and tests.

SQLite uses `foreign_keys=ON`, WAL journal mode, and `synchronous=FULL`.
Startup verifies the value SQLite returns for each required setting rather
than assuming an unknown or ignored pragma succeeded. Application schema
version 1 is recorded with `PRAGMA user_version=1`; SQLite's internal
`schema_version` is not an application migration field.

WAL is selected and verified before schema DDL begins. A new database then
uses `BEGIN IMMEDIATE` to create all tables and indexes, write the encrypted key
verifier, and set `user_version` in one commit. An unsupported newer, older, or
malformed schema fails startup. No general migration framework is introduced
in this slice.

## Idempotent Ingestion

The idempotency key is `(source_namespace, source_event_id)`. The request
digest covers the canonical immutable submission, including the body, stable
source event time, and all security-relevant metadata. The controller receipt
time is generated separately and is excluded so a replay does not change
identity. Digests are private ledger metadata: they are not returned, logged,
published, or treated as confidentiality protection.

Ingestion performs this sequence:

1. validate the versioned request and security metadata;
2. canonicalize the immutable submission and calculate its SHA-256 digest;
3. generate opaque request, task, and initial-event IDs;
4. encrypt the request body with authenticated immutable metadata;
5. in one database transaction, insert the request, `queued` task, and initial
   task event; and
6. return durable IDs only after commit.

If the idempotency key already exists with the same digest, ingestion returns
the original request and task IDs and creates no new event. If the body,
identity reference, project, repository, mode, trust, taint, provenance, or
other immutable security metadata differs, ingestion fails with
`idempotency_conflict`. Concurrent submissions obey the same result through
the database uniqueness constraint and transactional comparison.

Before encryption, the controller builds canonical associated data containing
the domain `forge.request-body/v1`, protocol version, request ID, idempotency
key, project and repository references, body digest, security-envelope digest,
the cipher's fixed algorithm identifier, and the input key handle's opaque key
ID. The cipher then generates only the nonce and ciphertext. Changing any
bound field makes decryption fail. The key verifier uses the separate domain
`forge.state-key-verifier/v1` and never reuses a request nonce.

## Scheduling and Concurrency

`maxConcurrency` is required configuration, not a hard-coded architectural
ceiling, and the portable core supplies no implicit default. Slice 3 tests the
algorithm with an effective value of `2`. The first reference deployment keeps
its already-approved rollout value of `1` until its later executor and host
acceptance gate passes; it may then be raised to the target value of `2` by a
separately reviewed deployment configuration change. Another deployment may
choose another positive value after its own capacity testing.

The scheduler enforces:

- fewer than `maxConcurrency` tasks may be `running` globally; and
- at most one task may be `running` for a repository reference.

Claiming is a single ledger transaction. It counts current running tasks,
finds the oldest eligible queued task by monotonic queue sequence, appends the
transition event, changes `queued` to `running`, and returns the claimed task.
If capacity is full or no repository is eligible, it returns no task; queued
work is not treated as an error.

A busy repository does not block an older eligible task for another
repository. No priorities, weights, reservations, adaptive limits, or worker
pool are added. The controller core exposes the claim operation so a future
executor adapter can drive it. A successful claim records scheduling
ownership; it is not an authorization decision or proof of host enforcement.

## Single Controller and Startup Reconciliation

The SQLite implementation opens one long-lived, controller-serialized
connection with a zero busy timeout and requests
`main.locking_mode=EXCLUSIVE`. Before readiness it starts an immediate write
transaction and commits initialization or reconciliation. In exclusive
locking mode the connection retains the resulting file locks for its lifetime.
A lock-acquisition `SQLITE_BUSY` is normalized to
`controller_already_running`; the controller does not wait or attempt shared
leadership. Other database failures remain `state_error`. Closing or crashing
the process releases the SQLite file locks.

Startup proceeds in this order:

1. open SQLite, select and verify required database settings, and acquire
   exclusive ownership;
2. create or validate `PRAGMA user_version=1` and the exact schema;
3. verify the configured key handle by decrypting the stored key verifier;
4. in one transaction, change every `running` task to `failed` with reason
   `controller_restart` and append matching events;
5. preserve `queued`, waiting, review-ready, and terminal tasks; and
6. report readiness only after reconciliation commits.

There is no automatic retry or attempt to reconnect to an executor. An
operator or a later approved workflow may inspect and explicitly resubmit
failed work. Filesystem and worktree reconciliation belongs to the later
workspace-adapter slice.

## Error and Redaction Contract

Public failures use stable codes with bounded, non-sensitive messages. The
initial codes are:

- `unsupported_protocol`
- `invalid_request`
- `idempotency_conflict`
- `task_not_found`
- `invalid_transition`
- `controller_already_running`
- `state_error`
- `encryption_error`

Capacity exhaustion is a normal empty-claim result, not an error. Internal
exceptions may be chained for local debugging, but public responses and normal
logs must not include request plaintext, ciphertext, nonce, key ID, key bytes,
private paths, raw SQLite messages, raw cryptographic exceptions, or raw
security metadata. Logs use opaque request/task IDs and stable reason codes.

Malformed, unsupported, missing, or downgraded security metadata fails closed.
Successful schema validation proves only contract shape; it does not claim
that a runtime, host, or external service enforced the metadata.

## Verification Strategy

### Protocol and contract tests

- valid submission and task-inspection fixtures;
- unsupported version, unknown fields, duplicate keys, malformed Unicode,
  non-I-JSON values, and missing security metadata;
- canonical identity stability and normalized, redacted errors; and
- responses that never expose request or cryptographic material.

### State-machine tests

- every allowed transition;
- every disallowed transition;
- terminal-state immutability; and
- waiting and review states returning through `queued`.

### Cryptographic tests

- AES-256-GCM round trip;
- key-length validation and fresh nonce behavior;
- wrong key, changed authenticated metadata, and tampered ciphertext failure;
- no plaintext or cryptographic material in errors and logs; and
- cipher boundary tests that do not require a real secret provider.

### SQLite and ingestion tests

- new-schema creation, foreign keys, WAL, and schema validation;
- atomic request, task, and initial-event creation;
- rollback when any part of ingestion fails;
- identical replay, conflicting replay, and concurrent duplicate submissions;
- state/event transaction atomicity and append-only behavior; and
- package operation with temporary local database paths only.

### Scheduling and recovery tests

- configurable global concurrency values;
- one running task per repository;
- FIFO among eligible work and progress for a different repository;
- full capacity leaving overflow queued;
- concurrent claims never exceeding either limit;
- second-process controller lock rejection and lock release after exit;
- `running` becoming `failed(controller_restart)` on startup; and
- queued, waiting, review-ready, and terminal states remaining unchanged.

The existing `make validate` suite must remain green on the supported Python
versions. CI adds the controller tests to the same validation path and retains
package-build and installed-wheel smoke evidence. Tests use synthetic
identifiers, content, repositories, keys, and paths; they perform no network,
OCI, Hermes, Discord, Codex, systemd, credential, publication, or deployment
operation.

## Documentation and Compatibility Impact

Implementation will update the architecture and roadmap to distinguish the
implemented in-process core from the still-proposed transport, executor,
workspace, and host adapters. Public examples and fixtures remain synthetic.

The service protocol, state vocabulary, transition rules, encryption record
shape, idempotency semantics, and state-adapter boundary are public contracts.
Changes that alter their meaning require explicit versioning and, when
durable, a superseding ADR. SQLite schema changes require an explicit,
transactional migration design before code is changed.

## Rollback

This slice creates no deployment and mutates no external system. Code rollback
removes the new in-process controller modules, schemas, dependency, and tests.
Runtime database rollback never deletes a database automatically. A database
created by development or tests remains inspection evidence unless its exact
temporary path is explicitly removed.

## Acceptance Criteria

- The controller protocol rejects malformed and unsupported input without
  leaking sensitive data.
- Identical submissions return the same durable IDs; conflicting replays fail.
- Plaintext request bodies are absent from SQLite and normal logs.
- State updates and append-only events are atomic.
- Global N and per-repository-one scheduling limits hold under competing
  claims; N=2 is covered without creating a hard-coded ceiling, while the
  reference rollout remains 1 until its later acceptance gate.
- A second SQLite controller fails startup.
- Startup converts only `running` tasks to
  `failed(controller_restart)` before readiness and never retries them.
- The full repository validation and package checks pass without contacting a
  real provider, host, runtime, or secret service.
