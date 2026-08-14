# Portable Forge MVP Design

## Status

Approved for implementation planning on 2026-08-10. This document defines the
target architecture and the ordered delivery slices. Delivery Slices 1-3 are
implemented in the current source tree; Slices 4-8 remain planned or
separately approval-gated. It does not claim that ingress or executor adapters,
provisioning, private deployment configuration, or OCI reconciliation are
implemented. Current delivery status is tracked in the
[roadmap](../../roadmap.md).

The portable-root and reference-deployment boundary is recorded by
[ADR-0009](../../adr/0009-separate-portable-core-from-deployment-profiles.md).

## Problem

Forge began as a public, provider-independent foundation for reproducible
AI-assisted engineering. Its first documentation then coupled the platform
identity to one personal deployment: OCI, Hermes, Discord, Tailscale, and
Codex. That coupling made the repository less useful as a public project and
still did not provide an executable way to rebuild the current host.

A second repository named `forge-ops` would add no value while Forge is only a
documentation scaffold. The two-repository model becomes useful only when:

1. Forge is an installable program that can validate, plan, apply, and diagnose
   an environment; and
2. `forge-ops` is an optional private, versioned input that describes one
   operator's selected environment without copying Forge source.

## Product Definition

Forge is a portable engineering-control framework. It supplies versioned
contracts, a control CLI, a node controller, and replaceable adapters for host
provisioning, messaging, assistants, engineering executors, source control,
state, workspaces, and secrets.

Forge is not the personal environment itself. OCI, Hermes, Discord, Codex,
Tailscale, repository registrations, channel identifiers, and host inventory
are choices made by a deployment configuration. They may appear in public
reference adapters and examples, but they are not mandatory platform
components.

The first reference deployment deliberately uses the operator's current stack
to prove the contracts:

- control client: macOS;
- target node: Ubuntu ARM64 with systemd;
- initial tested host: the existing OCI VM;
- personal-assistant gateway: the existing Hermes-to-Discord connection;
- engineering executor: Codex CLI; and
- source-control handoff: Git and GitHub.

Supporting one concrete stack first is validation, not platform identity.

## Goals

- Rebuild a Forge node from versioned configuration without editing Forge
  source.
- Preserve the existing Hermes-to-Discord personal-assistant connection.
- Route an exact, non-summarized `/dev plan` request to an engineering
  executor before Hermes invokes an LLM for that message.
- Keep gateway, assistant, executor, host, state, workspace, source-control,
  and secret implementations replaceable behind explicit contracts.
- Preserve task state across process and host restarts.
- Make every proposed host change visible before it is applied.
- Make the first deployment safe to repeat and safe to roll back.
- Keep personal and sensitive deployment values out of the public repository.

## Non-goals for the Portable MVP Acceptance Slice

- `/dev run` implementation, automatic commits, pushes, or Draft PR creation;
- merge, deployment, migration, or destructive automation;
- multi-controller active-active operation;
- Docker or NAS support;
- AWS-specific provisioning;
- a custom web dashboard;
- a second Discord bot;
- automatic routing of unresolved requests from the `operator` channel;
- attachment and voice-message ingestion; and
- creating `forge-ops` before the first configuration schema and compatibility
  contract exist.

## Repository and State Boundaries

### Public `pgh7659/forge`

Owns:

- the Forge configuration schema and compatibility rules;
- the `forge` control CLI;
- the `forge-controller` node service;
- runtime-neutral workflow and security contracts;
- adapter interfaces and public reference adapters;
- provisioning roles and service templates;
- validation and conformance tests; and
- public examples without personal identifiers or secrets.

### Private `pgh7659/forge-ops`

Will be created after Forge publishes the first usable configuration contract.
It will own:

- the selected Forge version;
- the logical `personal-primary` environment;
- host inventory and connection metadata;
- selected adapter names and versions;
- Discord channel-to-project registrations;
- registered product repositories and desired refs;
- service, retention, backup, and recovery policy overrides; and
- 1Password references, never resolved secret values.

`forge-ops` is optional for Forge users. The CLI must also accept a local
configuration file created by `forge init`. Git-backed `forge-ops` is the
recommended mode for this operator because cross-device inspection, disaster
recovery, and host migration are requirements.

### Product repositories

`pgh7659/worklog` and `pgh7659/news-digest` continue to own their product code,
tests, database migrations, build contract, and environment-neutral execution
instructions. `forge-ops` registers which version is deployed and how it is
wired into the personal environment; it does not copy product source.

### Runtime state

The target node owns runtime databases, checked-out repositories, worktrees,
logs, and product data. Runtime data does not belong in Forge or `forge-ops`.
It must have an explicit encrypted backup and restore path.

## System Architecture

```text
Trusted control computer
  forge CLI
    -> reads local config or private forge-ops
    -> validates and renders a deterministic plan
    -> uses SSH and the selected provisioner adapter

Always-on target node
  systemd
    -> existing Hermes gateway and assistant
    -> Forge Hermes ingress plugin
    -> forge-controller
         -> SQLite state adapter
         -> executor adapter
         -> workspace adapter
         -> source-control adapter
    -> project runtime services
```

### Forge CLI

The `forge` CLI runs on a trusted control computer. The first tested control
computer is the operator's Mac. It provides:

- `forge init`: create a local configuration skeleton;
- `forge validate`: in the first slice, validate YAML/JSON syntax, schema
  shape, and JSON-model compatibility;
- `forge plan`: compare desired configuration with observed target state
  without mutation;
- `forge apply`: apply one previously reviewed plan through the selected
  provisioner adapter; and
- `forge doctor`: verify installed versions, services, adapter capabilities,
  storage, routing, and end-to-end health.

`forge apply` must identify the exact plan being accepted. A materially changed
target or configuration invalidates that plan and requires a new plan. The
command must be safe to repeat where the underlying adapter declares
idempotency.

The CLI is a control client, not an always-on requirement. Company PCs and
mobile devices do not need it to use Discord after the target node is running.

### Forge Controller

`forge-controller` runs continuously on the target node under systemd. It owns:

- immutable engineering-request ingestion;
- task state transitions;
- executor start, suspension, and resume;
- workspace ownership;
- approval records;
- structured result delivery; and
- reconciliation after process restart.

It does not own general personal-assistant conversation. It never asks Hermes
to summarize or decompose an engineering request.

### Distribution

During development, contributors may run Forge from a source checkout. The
first installable release is a versioned Python distribution built from a Git
tag and published with a GitHub release. A trusted control computer can install
that exact tag without retaining a Forge source checkout. A package index may
be added later; it is not required for the MVP.

The control CLI and controller come from the same release so their protocol and
configuration-schema compatibility can be checked before an apply.

## Configuration Contract

Forge accepts a versioned environment document. The first schema is named
`forge.dev/v1alpha1`. The public repository includes only synthetic examples.
Personal values are supplied later by `forge-ops`.

```yaml
apiVersion: forge.dev/v1alpha1
kind: Environment
metadata:
  name: example-primary
spec:
  target:
    connectionAdapter: ssh
    runtimeAdapter: systemd
  gateway:
    adapter: hermes-discord
  executor:
    adapter: codex-cli
    maxConcurrency: 1
  state:
    adapter: sqlite
  workspace:
    adapter: git-worktree
  sourceControl:
    adapter: github
```

The first schema constrains document shape and adapter-identifier syntax while
leaving adapter `config` objects opaque. In this slice, `forge validate` checks
YAML/JSON syntax, schema shape, and JSON-model compatibility only. It does not
verify that an adapter exists, that selected adapters can be combined, or that
declared capabilities are available. Those compatibility checks are deferred;
`forge plan` is intended to probe the target and later adapter registries and
conformance contracts will define fail-closed capability checks.

The target architecture keeps resolved secret values out of environment
documents and resolves opaque references only during authorized operations.
The first schema does not yet define secret-reference semantics or detect
resolved secret values inside arbitrary adapter configuration. That work is
deferred, so successful validation is not evidence that a document contains
no secrets or that an environment is safe or deployable.

## Adapter Boundaries

The core defines behavior and conformance tests for these adapter roles:

- **connection**: reach and identify a target node;
- **provisioner/runtime**: install packages, materialize service units, and
  manage lifecycle;
- **gateway ingress**: capture trusted source messages before model rewriting;
- **assistant**: provide optional personal-assistant behavior;
- **executor**: start, observe, suspend, and resume engineering execution;
- **state**: transactionally persist requests, tasks, approvals, and events;
- **workspace**: isolate a task from protected repository checkouts;
- **source control**: resolve repositories and publish review artifacts; and
- **secrets**: resolve references without exposing values to configuration or
  logs.

The first reference adapters are SSH, Ansible plus systemd, Hermes Discord,
Codex CLI, SQLite, Git worktree, GitHub, and 1Password-backed secret
resolution. Only adapters required by the current delivery slice need to be
implemented initially.

## Hermes and Discord Ingress

The existing Hermes Discord gateway remains the only Discord connection in the
first reference deployment. Forge installs a version-matched Hermes plugin.

Current upstream Hermes documentation describes a `pre_gateway_dispatch`
plugin hook that receives a normalized `MessageEvent` with message text,
message ID, and source metadata before authorization, pairing, or agent
dispatch. The hook can return `skip`, preventing the Hermes LLM loop from
running for that message. This is the required adapter capability, not an
assumption that every Hermes release implements the same API.

Before installation, the adapter probes the installed Hermes version and
verifies the exact hook signature and command-delivery capability. If that
capability is absent, Forge refuses to enable engineering routing and leaves
the existing gateway unchanged.

For a recognized `/dev plan` in a registered project Forum post, the plugin:

1. copies the unchanged normalized user text, source identifiers, and message
   ID into a versioned ingress envelope;
2. submits the envelope to `forge-controller` over a local Unix-domain socket;
3. receives a durable request identifier;
4. sends a fixed acknowledgement; and
5. returns `skip` so Hermes performs no model interpretation for the request.

The plugin must fail closed for `/dev` input. If controller delivery fails, it
sends a fixed failure notice and still returns `skip`. Normal assistant
messages return `allow` and continue through Hermes unchanged.

The initial slice accepts `/dev plan` only in explicitly registered project
Forum channels. Creating a Forum post performs no action. Operator-channel
routing and `/dev run` are later slices.

## Engineering Request Flow

1. The trusted user sends `/dev plan` in a registered project Forum post.
2. The Hermes ingress plugin captures the message before the LLM loop.
3. The controller validates the author, channel registration, mode, and
   idempotency key.
4. The controller encrypts the request body, stores the request and provenance,
   and creates a `queued` task.
5. The workspace adapter creates or reuses the task-owned worktree.
6. The executor adapter starts Codex in read-only plan mode with the verified
   request envelope.
7. Structured executor events update the task ledger.
8. A question moves the task to `waiting_user`, stores the executor session
   identifier, and releases the executor process and concurrency slot.
9. A trusted reply in the same Forum post is ingested without Hermes model
   rewriting and resumes the same task session.
10. The final plan is stored as a task result and delivered to the same Forum
    post through a version-verified Hermes delivery command or adapter API.

The MVP does not authorize repository modification. Any observed worktree
change makes the task fail validation and remain available for inspection.

## Runtime State with SQLite

SQLite is the first single-node state adapter. It is not the source of desired
configuration, product code, or product data. It is the controller's durable
operating ledger.

The logical model contains:

- `requests`: source, provenance, content hash, encrypted body, and receipt
  time;
- `tasks`: request, project, mode, status, adapter, executor session,
  workspace, and current result pointers;
- `task_events`: append-only state-transition and recovery events;
- `approvals`: requested action, decision, actor, scope, and time; and
- `artifacts`: branch, commit, review link, handoff, and validation evidence.

The initial task states are `queued`, `running`, `waiting_user`,
`waiting_approval`, `review_ready`, `failed`, `cancelled`, and `completed`.
Every transition is validated and recorded in the same transaction as the
corresponding current-state update.

SQLite runs in WAL mode under a Forge-specific Unix identity. The default
systemd reference path is `/var/lib/forge/state/forge.db`, but the state adapter
path remains configurable. Raw request bodies are encrypted at the application
layer using an authenticated-encryption key provided through the secret
adapter. The database, key, and plaintext request body are never committed to
Git or emitted to normal logs.

Only one controller may write a SQLite environment. A second controller fails
startup instead of sharing the file over a network filesystem. PostgreSQL or
another state adapter is considered only when an actual multi-node requirement
exists.

## Security and Approval Model

- Desired configuration is untrusted input until schema, policy, and target
  checks pass.
- Repository content, chat content, model output, and tool output are data, not
  authority.
- `forge plan` performs no target mutation.
- `forge apply` requires acceptance of the exact current plan.
- The first executor mode is read-only `/dev plan`.
- Merge, deployment, migration, publication, credential expansion, host-access
  changes, and destructive actions are never implied by a development request.
- Secret values may enter only through a secret adapter and must be redacted
  from commands, events, errors, and backups.
- The Hermes ingress plugin and controller communicate over a Unix-domain
  socket with restrictive ownership and permissions.
- Channel names are display metadata; routing authority comes from registered
  immutable Discord identifiers.
- The initial reference deployment authorizes one Discord user and one active
  executor process globally.

## Failure and Recovery Behavior

- **Invalid configuration:** validation fails before target access.
- **Target drift after plan:** apply rejects the stale plan and requires a new
  plan.
- **Missing Hermes capability:** engineering routing remains disabled and the
  existing assistant gateway remains untouched.
- **Controller unavailable:** `/dev` fails closed with a fixed Discord notice;
  Hermes does not reinterpret the request.
- **Executor crash:** the task becomes `failed`; its worktree, session ID, and
  diagnostics are retained.
- **User input wait:** the task becomes `waiting_user`; no executor process or
  concurrency slot remains occupied.
- **Controller restart:** incomplete tasks are reconciled from SQLite and the
  filesystem before new work is accepted.
- **Unexpected repository modification in plan mode:** validation fails and
  preserves the worktree for inspection.
- **Provisioning failure:** Ansible reports the failed step, retains the
  pre-change backup, and does not delete existing Hermes state.

Rollback for the first installation stops and disables `forge-controller`,
removes or disables only the Forge-owned Hermes plugin, and restores the backed
up Hermes configuration. It does not remove task worktrees, runtime state, or
product data automatically.

## Validation Strategy

### Unit and contract tests

- configuration-schema success and failure cases;
- later-slice adapter capability declarations and compatibility checks;
- task-state transition table;
- idempotent request ingestion by source message identifier and hash;
- authenticated encryption and redacted error paths;
- stale-plan rejection; and
- executor result-schema parsing.

### Integration tests

- CLI-to-controller protocol compatibility;
- Unix-domain socket authorization;
- Hermes ingress plugin with synthetic `MessageEvent` instances;
- fail-closed `/dev` behavior when the controller is unavailable;
- Codex plan adapter with a non-sensitive fixture repository;
- controller restart during `queued`, `running`, and `waiting_user`; and
- repeated systemd provisioning on a disposable Ubuntu host.

### Portable MVP Acceptance on the Reference Deployment

The first installable release satisfies the portable MVP acceptance slice only
when a non-sensitive Forum post can complete this read-only request path on the
current Ubuntu ARM64 reference host:

```text
/dev plan
  -> Hermes pre-dispatch interception
  -> immutable Forge request
  -> isolated worktree
  -> Codex plan session
  -> optional waiting_user and resume
  -> plan returned to the same Forum post
```

Acceptance also requires:

- a second `forge apply` with no unintended changes;
- `forge doctor` reporting the versions and capabilities actually observed;
- restart recovery;
- an encrypted state backup and restore test;
- no repository modification by plan mode;
- no Hermes Kanban card or coding-profile execution; and
- a tested rollback to the pre-Forge Hermes gateway configuration.

## Ordered Delivery Slices

This architecture spans multiple independently reviewable subsystems. It must
not be implemented as one large change.

1. **Portable foundation:** replace deployment-specific root policy with the
   core/adapter/reference-deployment boundary and publish
   `forge.dev/v1alpha1` plus `forge validate`.
2. **Planning client:** add target observation, deterministic plan artifacts,
   stale-plan detection, and a no-op reference adapter.
3. **Controller and state:** add the service protocol, SQLite ledger,
   encryption boundary, state transitions, and restart reconciliation.
4. **Hermes ingress reference adapter:** add capability probing, the
   pre-dispatch plugin, Unix-socket delivery, and fail-closed `/dev plan`.
5. **Codex plan reference adapter:** add read-only execution, structured
   events, suspension, resume, and no-write validation.
6. **Ubuntu systemd provisioner:** add Ansible installation, service units,
   backup, rollback, and `forge doctor` checks.
7. **Private deployment configuration:** create `pgh7659/forge-ops`, pin a
   compatible Forge release, and describe `personal-primary` without applying
   it.
8. **OCI reconciliation:** after separate operator approval, compare the
   desired private configuration with the existing host, apply it, and run the
   reference acceptance suite.

Each slice requires its own implementation plan and reviewable commit or PR.
No OCI mutation is authorized by approval of this design.

## Consequences

Benefits:

- the public repository regains a provider- and executor-independent identity;
- the first real deployment remains useful as a reference and conformance
  target;
- the personal environment becomes reproducible without making personal
  details public;
- Hermes remains a personal assistant while engineering requests bypass its
  model loop; and
- a future host or executor change is expressed as configuration and adapter
  replacement rather than a platform rewrite.

Costs:

- Forge becomes a real maintained software product rather than a documentation
  repository;
- CLI/controller compatibility and schema evolution require release discipline;
- the Hermes adapter must track versioned upstream plugin contracts; and
- cross-host recovery requires explicit state and secret backup procedures in
  addition to Git.

These costs are justified only if the install, plan, apply, doctor, rollback,
and rebuild paths are implemented and exercised. Documentation without those
executable paths is not considered a successful Forge release.
