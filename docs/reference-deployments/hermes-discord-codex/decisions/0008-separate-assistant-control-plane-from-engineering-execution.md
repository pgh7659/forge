# ADR-0008: Use Hermes as a Personal Assistant and Forge as the Codex Dispatcher

## Status

Accepted

## Date

2026-08-10

## Scope

This historical decision governs only the `hermes-discord-codex` reference
deployment. It is not a portable Forge core requirement.

## Context

The first OCI deployment connected one Hermes default profile to Discord and
used a separate `forge-worker` Hermes profile plus Kanban for engineering work.
Operating experience showed that the extra agent and Kanban blocking lifecycle
lost request fidelity, produced weaker engineering results, and repeatedly left
work waiting in a blocked board state.

The operator needs Discord as an always-available mobile interface, but wants
Codex to own engineering discussion and implementation. Hermes must not shorten,
reinterpret, or replace the original development request before Codex receives
it.

Discord is already organized as one general `operator` channel and one Forum
channel per project. Each Forum post is a Discord thread and provides a natural
boundary for one work topic.

## Decision Drivers

- Preserve the exact Discord request and its provenance.
- Keep the existing Hermes and Discord gateway connection available.
- Remove Hermes Kanban and Hermes coding profiles from engineering execution.
- Let the operator plan, run, answer, and review from the same Forum post.
- Make Git branches and Draft PRs the durable cross-device engineering state.
- Keep merge, deployment, migration, credential, and infrastructure changes
  under explicit human approval.

## Decision

### Hermes is a personal assistant

The existing Discord-connected Hermes default profile remains physically in
place during migration and takes the logical role `assistant`. It owns general
conversation, reminders, factual status, routing confirmation, and delivery of
Codex questions and results.

Hermes does not edit repositories, decompose engineering work, create
engineering Kanban cards, manufacture acceptance criteria, or summarize a raw
development request for the executor. The stopped `forge-worker` profile is
retained only for rollback until the new path is accepted, then retired.

No additional Hermes `ops`, coder, or reviewer profile is part of the initial
target. Registered operational procedures are deterministic Forge runbooks with
their own approval gates, not autonomous Hermes roles.

### Discord project and work boundaries

The Discord routing contract is deterministic:

- `operator` receives personal-assistant conversation and requests with no
  resolved project;
- `forum-forge` maps to the Forge project;
- `forum-worklog` maps to the Worklog project;
- `forum-newsdigest` maps to the News Digest project; and
- new project Forum channels require an explicit private registration.

A Forum channel represents one project. A Forum post represents one work topic
and one primary Codex session. Creating a post does not start execution. If the
scope splits into an independently reviewable outcome, the assistant proposes a
new post and links the original messages without replacing them with a summary.

The default command is `/dev plan`, which permits repository inspection and a
Codex plan or questions but no code modification. `/dev run` explicitly permits
implementation. Commit, task-branch push, validation, and Draft PR creation are
allowed during an accepted run. Merge and deployment remain approval-gated.

### Immutable request inbox

The Discord gateway records the source message before model interpretation and
assigns an opaque request identifier. Private Forge state stores the exact raw
message, Discord message and thread references, author, project registration,
receive time, and a content hash.

Hermes dispatches only the opaque request identifier and requested mode. The
dispatcher reloads and verifies the original message independently. Any
assistant summary is display-only and can never become the executor request.

### Forge task ledger replaces Hermes Kanban

Forge owns a small durable task ledger independent from Hermes. Initial states
are `queued`, `running`, `waiting_user`, `waiting_approval`, `review_ready`,
`failed`, `cancelled`, and `completed`.

`waiting_user` is a normal suspended state, not a Kanban block. The Codex
process exits, while its session identifier, worktree, branch, and exact pending
question remain durable. A reply in the same Forum post resumes that session.
A waiting task consumes no executor slot.

The initial deployment runs at most one Codex executor process at a time.

### Codex is the only engineering executor

Forge starts or resumes a version-verified Codex CLI session in a dedicated Git
worktree. It provides trusted repository and permission metadata around the
unchanged raw request, consumes machine-readable events, and records a
structured result.

Codex may inspect, plan, implement, test, commit, push only its task branch, and
create or update a Draft PR within the accepted mode. It may not merge, deploy,
migrate, publish, expand credentials, modify host access, or destroy retained
work without fresh approval.

Direct Codex and OCI Codex sessions do not share hidden conversation state.
Git refs, Draft PRs, validation evidence, and explicit handoff records are the
durable cross-device boundary.

### Repository and deployment boundary

Every run uses a protected checkout plus a task-local worktree managed by
Forge. The implementation does not depend on Hermes Kanban workspace lifecycle.
Production checkouts, runtime databases, secrets, and releases are never task
workspaces.

## Relationship to Previous Decisions

- ADR-0001 is superseded where it names Hermes as the engineering orchestrator;
  Hermes remains the initial personal-assistant runtime and Discord gateway.
- ADR-0003 remains valid for Discord, but its worker-profile and Kanban topology
  is superseded by Forum routing and the Forge dispatcher.
- ADR-0005 remains valid for protected checkouts and worktree isolation, but
  Forge rather than Hermes Kanban owns worktree lifecycle.
- [ADR-0006](0006-use-hermes-profiles-kanban-and-provider-fallback.md) is
  superseded for profiles and Kanban. Provider fallback remains a Hermes
  conversational concern and is independent from Codex session recovery.
- ADR-0007 applies to the inbox, task ledger, executor, approvals, and results.

## Consequences

Benefits:

- the request sent to Codex is independently verifiable and unchanged;
- Discord Forum posts provide project and session boundaries without Kanban;
- questions suspend cleanly without occupying an executor or blocked card;
- Hermes stays useful without acting as a weaker engineering intermediary;
- GitHub remains the recoverable and device-independent engineering boundary.

Costs:

- Forge must implement an inbox, dispatcher, task ledger, Discord routing
  adapter, worktree manager, and Codex session adapter;
- the existing Hermes coding profile and Kanban history require archival;
- Discord message retention and private task retention need explicit policy;
- local and OCI Codex conversations still require Git-based handoff.

## Rollback

Stop the Forge dispatcher and restore the backed-up Hermes identity and gateway
configuration. Keep every dirty worktree and pushed task branch. The old
`forge-worker` profile remains stopped and available only during the acceptance
window; rollback does not authorize new Kanban engineering work without an
explicit operator decision.
