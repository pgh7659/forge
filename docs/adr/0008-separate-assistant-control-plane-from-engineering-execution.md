# ADR-0008: Separate Assistant Control Plane from Engineering Execution

## Status

Accepted

## Date

2026-08-10

## Context

Forge's first OCI deployment proved that Discord and Hermes are useful as an
always-available personal operator surface. It also exposed a quality boundary:
when Hermes interprets an ambiguous product request and then relays a rewritten
version to a coding agent, intent, conversational context, progress, and review
feedback are lost.

The operator also develops directly through Codex on local or hosted workspaces.
Those workspaces must interoperate with OCI without copying directories or
sharing an uncommitted checkout.

ADR-0006 chose Hermes profiles and Kanban as the initial multi-agent execution
model and treated external coding CLIs as optional specialist tools. That remains
appropriate for durable task coordination, but it is too broad for engineering
execution after operating experience showed that direct Codex collaboration is
materially more effective for design and implementation.

## Decision Drivers

- Preserve the operator's original request and direct engineering feedback loop.
- Keep Discord useful as a mobile personal-assistant and operations interface.
- Make GitHub refs and pull requests the handoff boundary across devices.
- Reuse Hermes' gateway, profiles, Kanban, cron, and worktree capabilities.
- Avoid filesystem synchronization and edits in production checkouts.
- Keep merge, deployment, migration, secrets, and destructive operations under
  explicit human approval.

## Decision

Forge separates the assistant control plane from engineering execution.

### Human and direct Codex

The human operator owns product direction, priorities, approvals, and production
judgment. Direct Codex conversations are the preferred surface for ambiguous
requirements, architecture, roadmap decisions, interactive implementation, and
final review.

### Hermes assistant control plane

The Discord-connected Hermes profile is named `assistant`. It owns request
capture, reminders, factual status summaries, scheduled reports, approval
routing, Kanban state, and dispatch. It may execute explicitly registered
operations runbooks.

Repository and worklog collection is request-driven by default. Scheduled
briefs may use a cached incremental cursor, but Forge does not repeatedly scan
all history merely to keep the OCI host busy. A schedule must have an operator
need, bounded cost, retention policy, and failure notification.

Hermes must preserve the operator's raw request. It may append resolved facts
such as repository, base ref, task identifier, and acceptance criteria, but it
must not silently replace the raw request with a summary.

### Engineering executor

Codex is the first engineering executor. A version-verified adapter may start or
resume Codex CLI sessions in a task-local worktree and consume machine-readable
events and a structured final result. The adapter is an implementation detail;
the durable handoff is the Git branch, commit, Draft PR, tests, and task record.

Forge does not promise that a Hermes conversation, direct Codex conversation,
or another CLI can share private model-session state. Continuation across
surfaces uses GitHub plus an explicit handoff record.

### Operations profile

An optional `ops` profile runs only registered read-only or reversible runbooks,
such as status collection, incremental synchronization, health checks, and
backup verification. Infrastructure mutation, deployment, migration, credential
use, and destructive actions require scoped human approval.

### Reviewer

Review is an independent verification pass, not an autonomous product decision.
CI provides deterministic checks. A reviewer profile or Codex review session may
inspect the diff read-only, but the human remains the final approval authority.

### Repository and deployment boundary

Every coding task uses a branch and task-local worktree. Local, cloud, and OCI
workers synchronize through pushed Git refs and Draft PRs, never through
filesystem mirroring. The protected checkout and production release are not
agent workspaces. Production consumes only an approved commit from the protected
branch.

## Task Classification

- `status`: Hermes answers from observed state without proposing roadmap work.
- `ops`: Hermes runs a registered runbook within its declared authority.
- `implement`: Hermes dispatches the raw request and task envelope to Codex.
- `design`: Hermes records context and routes the operator to direct Codex.
- `privileged`: Hermes records the request and waits for explicit approval.

Ambiguous requests fail toward `design`, not unattended implementation.

## Relationship to Previous Decisions

- ADR-0001 remains valid: Hermes is the initial orchestration runtime.
- ADR-0003 remains valid: Discord is the primary assistant and operations
  interface, but it is not the source of engineering truth.
- ADR-0005 remains valid: coding runs in task-local worktrees.
- This ADR supersedes the part of ADR-0006 that treats external coding CLIs as
  merely optional specialists. Codex is now the first engineering executor;
  Hermes Kanban remains the durable single-host coordination plane.
- ADR-0007 applies to task envelopes, approvals, tool output, and executor
  adapters. A contract decision is not proof of host enforcement.

## Consequences

Benefits:

- better fidelity for product and engineering work;
- a useful always-on personal assistant without making it the coding brain;
- explicit handoff across local, cloud, and OCI environments;
- smaller, testable adapter and approval boundaries.

Costs:

- Forge must maintain a Codex execution adapter and session/task mapping;
- direct and Discord conversations do not share hidden session context;
- OCI needs a private deployment inventory and tested recovery path;
- tasks require checkpoints in Git before ownership moves between environments.

## Rollback

Disable the Codex adapter and return engineering tasks to manually operated
worktrees. Hermes' assistant, Kanban, Discord, and operations functions remain
usable. Superseding this decision requires a new ADR and must preserve Git-based
handoff and human approval boundaries.
