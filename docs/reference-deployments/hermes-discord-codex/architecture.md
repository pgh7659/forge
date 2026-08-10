# Reference Deployment Architecture

## Scope and evidence

This document preserves the selected architecture for the
`hermes-discord-codex` reference deployment. It is evidence and a reconciliation
target, not a Forge core default or proof that a live host is compliant. Before
automation, record the installed release or commit, inspect its `--help`
output, and validate the needed behavior on the target host.

## Current state

The reference design includes a single OCI Ubuntu ARM64 host, a host-installed
Hermes runtime, Discord as the personal-assistant gateway, a private dashboard,
an immutable Forge inbox and task ledger, protected Git checkouts with
task-local worktrees, and Codex as the first engineering executor. It retains
one trusted service account, one trusted Discord operator, one assistant
profile, one non-sensitive repository, and one running Codex executor for the
first production-like validation. The stopped legacy `forge-worker` profile
and its Kanban data are rollback material during acceptance, not an active or
fallback execution path.

The repository documents this architecture, security contracts, an audit
script, routing, handoff, and service templates. It does not evidence host
bootstrap, installation automation, gateway automation, dashboard supervision,
workspace automation, backups, or host enforcement.

## Layer model and responsibilities

```text
Human Operator
  -> Direct Codex Surface | Discord Operator and Project Forum Surfaces
  -> Hermes Personal Assistant and Gateway
  -> Forge Immutable Inbox, Task Ledger, and Approval Boundary
  -> Forge Dispatcher and Codex Engineering Executor
  -> Workspace Manager and GitHub Handoff
  -> Protected Runtime and Data Plane
```

The operator owns intent, approvals, production judgment, and secrets. Hermes
owns personal conversation, reminders, factual status, routing confirmation,
provider fallback, and delivery of engineering questions and results. It
captures the raw request before model interpretation and dispatches only an
opaque request ID and mode; it does not edit repositories, create engineering
Kanban cards, or run a general-purpose shell.

Each registered Discord Forum channel maps to one repository and each post to
one work topic and primary Codex session. Post creation performs no execution;
`/dev plan` is read-only and `/dev run` is the explicit implementation gate.
Forge, not Hermes Kanban, owns `queued`, `running`, `waiting_user`,
`waiting_approval`, `review_ready`, `failed`, `cancelled`, and `completed`
state. A normal input wait releases the process and executor slot while
preserving the session and worktree.

Codex receives a verified immutable request and versioned task envelope in its
task-local worktree. It returns structured state, validation evidence, a
pushed commit, Draft PR, risks, issues, and approval requests. It cannot merge,
deploy, migrate, publish, broaden credential use, or destructively clean up
without fresh scoped approval. Cross-device handoff uses pushed Git refs, Draft
PRs, and [the handoff procedure](operations/assistant-codex-handoff.md), not
private session continuity.

## Filesystem and workspace layout

Hermes-owned state remains under `~/.hermes`, including configuration,
environment, profiles, historical Kanban, and rollback material. Forge-owned
host assets use `/srv/forge`:

```text
/srv/forge/
  ops/
  repos/<project>/.worktrees/<task-id>/
  state/{tasks.db,inbox}/
  backups/
  logs/
  tmp/
```

`ops/` carries version-controlled host operational material; `state/` is
private runtime data and is not committed. Real inventory, registrations,
service identifiers, audit reports, and accepted version locks belong in a
private operations repository. Credentials remain outside both repositories.
Pushed refs are authoritative; health and backup policy must detect and
preserve dirty or unpushed worktrees.

## Host, interface, and network design

This reference host is a dedicated OCI VM. Hermes runs directly on the host to
use host tooling and user credentials naturally; this is packaging and
operability, not sandboxing. The service account receives least-privilege tools
and a non-sensitive repository before broader access.

Discord access uses an explicit user or role allowlist, a restricted guild and
channel scope, mention-gated shared channels unless explicitly free-response,
per-user session isolation, and no administrator permission. The gateway
records raw messages before interpretation; the full protocol is in
[routing](operations/discord-forum-codex-routing.md).

The dashboard is never public. Hermes binds to `127.0.0.1`; Tailscale Serve
publishes authenticated Tailnet HTTPS only. For the recorded Hermes version, a
loopback Caddy listener at `127.0.0.1:9120` normalizes the required upstream
Host header before forwarding to the dashboard at `127.0.0.1:9119`. Caddy does
not bind a public or Tailnet address, Tailscale Funnel is forbidden, and public
security rules do not expose dashboard ports. The selected Caddy and systemd
assets are under [assets](assets/).

## Provider, security, and approval boundaries

Hermes provider fallback handles eligible API failures inside the assistant
conversation. It does not resume an external coding CLI's private state. The
Forge ledger owns task state and GitHub carries durable engineering handoff;
Hermes Kanban is not in the engineering path.

Runtime-neutral [trust, taint, provenance, policy-decision, and sink
contracts](../../security/trust-taint-provenance.md) and the portable [threat
model](../../security/threat-model.md) remain authoritative for implementation
semantics. This reference deployment adds: no open dashboard, no unrestricted
Discord access, no secrets in Git, no root runtime, explicit approvals for
infrastructure or destructive actions, and one global Codex process. Worktrees
are workflow isolation, not hostile-code containment. Runtime secrets use mode
`0600`, public examples use placeholders, and logs, task metadata, comments,
and backups must not reveal secret values. Discord messages, repository
content, issues, pull requests, web pages, and downloaded files remain
untrusted input; authorization never implicitly permits secret disclosure,
privilege escalation, deployment, or destructive cleanup.

## Operations, recovery, and acceptance

Record the installed Hermes version or commit and never perform unattended
upgrades. Before an upgrade, back up Hermes configuration, memories, skills,
sessions, historical profile and Kanban data; the Forge inbox, ledger,
registrations, and retained session metadata; operational definitions; and all
unpushed or dirty worktrees. Encrypt off-host copies and exercise a restore
into a temporary location or replacement host.

Acceptance requires recorded installed versions and paths; successful
`hermes doctor` and a basic model call; gateway and dashboard survival across
logout and reboot; public-IP dashboard denial and authenticated Tailnet access;
authorized and unauthorized Discord tests; no execution when a Forum post is
created; read-only `/dev plan`; original-message verification for `/dev run`;
task-local-only edits; `waiting_user` process release and resume; understood
provider failure; tested backup creation, encrypted off-host copy, and restore;
and no secrets in Git or verification logs. Detailed audit, migration,
incident, and handoff procedures are under [operations](operations/).

## Deferred concerns and decision gates

Dockerized deployment, multi-host orchestration, a custom dashboard,
large-scale repository onboarding, external secret-manager integration, custom
memory abstractions, and automated cross-provider CLI handoff are deferred.
Record a new deployment decision before changing the OCI model, the
`~/.hermes`/`/srv/forge` boundary, operator interface, public network exposure,
or persistent store.
