# Reference Deployment Roadmap

## Purpose and status

This roadmap preserves the ordered work for the `hermes-discord-codex`
reference deployment. It is not the portable Forge roadmap and does not
authorize host changes. The operator reports an OCI host with Hermes, Discord,
and Codex CLI, but it has not passed this deployment's audit or acceptance
contract.

Each phase requires reviewed documentation, working artifacts, validation, and
a rollback path.

## Phase 0 — Foundation and decisions

Stabilize documents, ADRs, the security-contract/threat-model design, and the
reference deployment shape. Exit only when the deployment's chosen and deferred
components are explicit and security documentation distinguishes design from
adapter or host enforcement.

## Phase 1 — OCI environment audit

Inspect the target before changing it. Capture OS, package, network, privilege,
installed-tool, architecture, NSG/security-list, and host-firewall assumptions
through the [audit procedure](operations/oci-environment-audit.md) and private
inventory. Exit when ARM64 compatibility and all bootstrap assumptions are
documented.

## Phase 2 — Host bootstrap

Create repeatable Ubuntu ARM64 bootstrap steps, prepare `/srv/forge`, and
install Git, GitHub CLI, `jq`, `rsync`, `curl`, `unzip`, and build tools without
changing Hermes. A fresh host must be prepared by reviewable, repeatable steps.

## Phase 3 — Hermes runtime

Install Hermes directly on the host, validate provider setup, record the actual
layout and installed version or source commit, and begin with one assistant
profile and non-sensitive repository. Reconcile every automated command with
the installed CLI and configuration behavior.

## Phase 4 — Private access and dashboard

Establish Tailscale, a loopback dashboard listener, authenticated Tailnet
HTTPS, ACL verification, and service supervision. Exit only when authorized
devices reach the dashboard privately, public exposure is denied, Funnel is
disabled, and reboot behavior is documented.

## Phase 5 — Discord operator interface

Configure the Hermes Discord gateway, minimal bot permissions, allowlist and
mention rules, and desktop/mobile flows. Demonstrate trusted access,
unauthorized denial, deny-all when no allowlist matches, and understood session
and thread behavior.

## Phase 6 — Forum routing and immutable inbox

Keep one assistant profile, register the operator and project Forum channels,
capture source messages before model interpretation, and make one Forum post
one work topic and Codex-session boundary. The initial map is `operator`,
`forum-forge`, `forum-worklog`, and `forum-newsdigest`.

Post creation must not act. `/dev plan` and `/dev run` remain distinct. The
dispatcher verifies the source-message hash, scope splits create linked posts,
unrecognized routing fails closed, and `forge-worker` remains stopped with no
Hermes engineering Kanban card.

## Phase 7 — Repository and workspace automation

Implement registrations, request-driven repository and worklog collection,
bounded scheduled cursors, protected checkouts, Forge-managed worktrees,
cleanup checks, branch naming, and task metadata. Active tasks run only in
isolated worktrees, collection has a documented need and retention/failure
policy, and cleanup preserves unreviewed work.

## Phase 8 — Task ledger and Codex executor

Configure provider fallback, verify the installed Codex command contract,
implement immutable-request ingestion, task envelopes/results, session waits,
and GitHub handoff. Validate all task states, one global executor, process-slot
release for `waiting_user`, distinct recovery for provider and executor failure,
and handoff through a pushed branch and Draft PR.

## Phase 9 — Backups, health checks, and recovery

Add backup, restore, healthcheck, scheduled backup, alerting, dirty-worktree
preservation, pre-upgrade smoke-test, encrypted off-host storage, and
secret-safe logs. A lost host must be recoverable without losing platform
knowledge, and a clean replacement environment must restore the control-plane
state without copied build artifacts.

## Reference Deployment Run Slice and Broader Evolution

This deployment-specific `/dev run` slice is distinct from the portable MVP
acceptance slice, whose engineering-request path is read-only `/dev plan`.

Before adding projects or executor concurrency, demonstrate this path on a
disposable repository: Discord request → Hermes gateway → immutable inbox →
registered Forum post → read-only `/dev plan` → explicit `/dev run` → task
ledger and worktree → Codex validation → pushed checkpoint and Draft PR →
optional direct-Codex handoff → structured result in the same post.

Only after that deployment is stable consider workflow automation, broader
memory/retention, evaluation/observability, multi-repository orchestration,
alternative runtimes, and deeper secret management. Do not automate before a
contract exists, add interfaces before host and runtime stability, add
persistence without lifecycle ownership, or optimize for scale before this
single-host deployment is reliable.

These later candidates are a deferred evolution phase, not part of the first
deployment acceptance contract.
