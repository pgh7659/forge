# ADR-0010: Adopt a Contract-First Single-Node Controller Core

## Status

Accepted

## Date

2026-08-11

## Context

Forge needs durable request ingestion, task transitions, bounded scheduling,
and restart recovery before deployment-specific ingress and executor adapters
can be added. Implementing the first controller as a Hermes, Codex, systemd,
or SQLite-specific monolith would make one reference deployment appear to be a
portable core requirement. Implementing a daemon, runtime integration, and
state layer in one slice would also make the change difficult to review and
roll back.

Request bodies may be sensitive, message delivery may be repeated, processes
may restart, and multiple tasks may target the same repository. The first
runtime state implementation is single-node SQLite, but the public controller
contract must not depend on a network database or a selected agent runtime.

## Decision Drivers

- Preserve the portable core and adapter boundary adopted by ADR-0009.
- Preserve trust, taint, provenance, and fail-closed semantics from ADR-0007.
- Make duplicate delivery and state transitions deterministic and atomic.
- Keep plaintext request bodies out of the durable ledger and normal logs.
- Support useful cross-repository concurrency without same-repository races.
- Recover conservatively rather than duplicating an interrupted effect.
- Keep Slice 3 independently reviewable, testable, and reversible.

## Decision

Forge will add a transport-neutral, versioned controller protocol and an
in-process application service. The service depends on narrow injected
protocols for state and authenticated encryption. Actual ingress, executor,
workspace, source-control, secret-provider, daemon, and host-service adapters
remain separate slices.

Submissions carry the minimal versioned trust, taint, provenance,
classification, and retention envelope required by ADR-0007. The controller
validates and preserves that metadata but does not convert it into authority,
issue policy decisions, or claim enforcement.

The first state implementation is a local SQLite ledger with:

- encrypted immutable request bodies with minimized plaintext metadata;
- current task rows;
- append-only task-transition events;
- atomic ingestion, transition, claim, and reconciliation transactions;
- WAL with full synchronous durability and foreign keys; and
- exclusive single-controller ownership.

The first cipher is AES-256-GCM with a fresh 96-bit nonce and canonical
immutable request metadata as associated data. The key is supplied by the
caller and is never stored in SQLite, Git, or normal logs. Operational key
delivery and rotation automation are not part of this decision.

Scheduling uses a required, configurable positive global `maxConcurrency` and
permits at most one running task for a repository. The core has no implicit
default or public maximum and its conformance tests cover N=2. The first
reference deployment retains its approved rollout value of 1 until its later
executor and host acceptance gate passes; a separately reviewed deployment
change may then raise it to the target value of 2. Excess work remains queued.

Only one controller may own a SQLite environment. At startup it acquires
exclusive ownership and reconciles state before readiness. Every task found in
`running` becomes `failed` with reason `controller_restart`; it is not retried
automatically. Other states remain unchanged.

The complete Slice 3 contract and verification requirements are defined in the
[controller and state design](../superpowers/specs/2026-08-11-controller-state-design.md).

## Alternatives Considered

### Implement the Unix-socket daemon and real adapters now

Rejected because it combines the controller, transport, executor, workspace,
and host lifecycle boundaries. That would couple the core to the first
reference deployment and enlarge the failure and rollback surface.

### Put all controller behavior in the SQLite implementation

Rejected because task semantics, protocol validation, and cryptographic
boundaries would become database-specific and harder to test independently.

### Implement only the database schema

Rejected because it would not prove idempotent ingestion, state-transition,
scheduling, compatibility, or restart contracts needed by later adapters.

### Use full event sourcing

Rejected because projections, replay compatibility, snapshots, and event
schema evolution are unnecessary for the single-node MVP. Append-only
transition evidence plus a transactional current-state row is sufficient.

## Consequences

Benefits:

- later ingress and executor adapters can bind to one tested application
  contract;
- sensitive request bodies remain encrypted at rest in the ledger;
- retries, concurrent claims, and restart recovery have deterministic rules;
- different repositories may make progress concurrently while same-repository
  work is serialized; and
- SQLite can be replaced behind an explicit boundary if a demonstrated
  multi-node need appears.

Costs and limitations:

- transaction boundaries and state transitions require more tests than a
  database-only prototype;
- AES-GCM requires a maintained cryptographic dependency and safe external key
  delivery before deployment;
- exclusive ownership intentionally prevents active-active controllers; and
- the in-process core alone does not provide a daemon, sandbox, executor,
  workspace, message delivery, or host enforcement.

Rollback supersedes this ADR and removes the controller contract before a
release depends on it. Runtime databases are preserved rather than deleted
automatically. A future incompatible protocol, transition, encryption, or
state-adapter change requires explicit versioning and a superseding decision.
