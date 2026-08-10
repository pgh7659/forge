# Roadmap

## Purpose

This roadmap turns Forge from a documentation scaffold into a working OCI-hosted
Hermes operator node without collapsing its long-term portability.

The roadmap is ordered.
Each phase should leave behind:

-   reviewed documentation
-   working artifacts
-   a validation path
-   a rollback path

## Current Status

Repository foundation is in progress. The operator reports an active OCI host
with Hermes, Discord, and Codex CLI, but that deployment has not yet passed the
repository's audit and acceptance contract.

The direction is now explicit:

-   first host: OCI Ubuntu ARM64
-   first personal-assistant runtime: Hermes
-   first operator interface: Discord
-   first private access layer: Tailscale
-   first workspace model: protected checkout plus Forge-managed worktree
-   personal-assistant gateway: Hermes and Discord
-   engineering decision surface: direct Codex or Discord-routed Codex
-   engineering state: Forge inbox and task ledger, not Hermes Kanban
-   first engineering executor: version-verified Codex CLI adapter
-   security baseline: runtime-neutral trust, taint, provenance, policy, and
    sink contracts, with enforcement deferred to tested adapters

## Phase 0 - Foundation and Decisions

Goals:

-   stabilize the core documents
-   create initial ADRs
-   adopt the FGE-SEC-01 security contracts and threat model
-   clarify the first deployment shape
-   avoid premature implementation drift

Exit criteria:

-   README, bootstrap, agents, architecture, and roadmap agree with each other
-   initial ADRs exist for Hermes, Discord, Tailscale, host install, and
    protected-worktree strategy, with superseded assumptions identified
-   security contracts distinguish documented design, proposed implementation,
    and adapter or host enforcement
-   the repository states what is chosen versus what is only deferred

## Phase 1 - OCI Environment Audit

Goals:

-   inspect the target OCI host before changing it
-   capture OS, package, network, and privilege assumptions
-   identify gaps in the current documentation

Deliverables:

-   environment audit script
-   private environment audit report
-   explicit bootstrap prerequisites
-   installed-tool and architecture compatibility matrix
-   current OCI NSG/security-list and host-firewall inventory

Exit criteria:

-   Forge can describe the actual OCI host it is targeting
-   package, user, and network assumptions are documented before automation
    begins
-   ARM64 compatibility of the selected Hermes version and required extras is
    demonstrated on the target host

## Phase 2 - Host Bootstrap

Goals:

-   create repeatable bootstrap scripts for OCI Ubuntu ARM64
-   prepare `/srv/forge`
-   install foundational operator tooling without touching Hermes yet

Expected scope:

-   Git and GitHub CLI
-   `jq`, `rsync`, `curl`, `unzip`, build tools
-   optional Docker installation for future workload isolation
-   directory creation and permissions

Exit criteria:

-   a fresh OCI host can be prepared through documented, reviewable steps
-   bootstrap scripts are safe to rerun where practical

## Phase 3 - Hermes Runtime

Goals:

-   install Hermes directly on the host
-   validate provider setup
-   document the real install layout and service boundaries
-   record the installed Hermes version or source commit
-   begin with a single assistant profile and a non-sensitive test
    repository

Expected scope:

-   Hermes install
-   baseline provider setup
-   dashboard prerequisites
-   gateway service model

Exit criteria:

-   Hermes runs successfully on the OCI host
-   its runtime paths and profile model are documented
-   no unsupported assumptions remain in Forge docs
-   upstream `main` documentation has been reconciled with the installed
    version's actual CLI and configuration behavior

## Phase 4 - Private Access and Dashboard

Goals:

-   establish Tailscale on the host
-   keep the dashboard private
-   add authentication and service supervision

Expected scope:

-   Tailscale join flow
-   loopback-only dashboard listener
-   Tailscale Serve over Tailnet HTTPS
-   Tailnet identity and ACL verification
-   systemd or equivalent background service management

Exit criteria:

-   dashboard is reachable from authorized devices on the Tailnet
-   dashboard is not exposed to the public internet
-   Tailscale Funnel is disabled
-   restart and reboot behavior are documented

## Phase 5 - Discord Operator Interface

Goals:

-   bring up the Hermes Discord gateway
-   restrict access correctly
-   validate desktop and mobile operator flows

Expected scope:

-   Discord bot creation checklist
-   gateway configuration
-   allowlist and mention rules
-   home channel and proactive reporting decisions

Exit criteria:

-   authorized users can interact with Forge through Discord
-   unauthorized users are denied by policy
-   thread and session behavior is understood and documented
-   deny-all behavior is confirmed when no allowlist matches
-   bot permissions are minimal and an unauthorized-user test is recorded

## Phase 6 - Discord Forum Routing and Immutable Inbox

Goals:

-   keep one Hermes personal-assistant profile
-   register the operator channel and project Forum channels
-   capture source messages before model interpretation
-   validate one Forum post as one work topic and Codex-session boundary

Expected initial Discord map:

-   `operator`: personal-assistant and unresolved-project conversation
-   `forum-forge`: Forge
-   `forum-worklog`: Worklog
-   `forum-newsdigest`: News Digest

Exit criteria:

-   post creation performs no engineering action
-   `/dev plan` and `/dev run` are explicit, distinct modes
-   the dispatcher retrieves the original message by request ID and verifies
    its hash
-   a scope split creates a linked Forum post instead of silently expanding the
    task
-   unauthorized channels, users, and project mappings fail closed
-   `forge-worker` remains stopped and no Hermes engineering Kanban card is
    created

## Phase 7 - Repository and Workspace Automation

Goals:

-   codify the protected checkout and worktree strategy
-   automate safe setup and cleanup
-   make task-local execution reproducible

Expected scope:

-   repository registration
-   request-driven repository and worklog collection
-   incremental cursors for explicitly scheduled briefs
-   protected checkout setup
-   Forge-managed worktree creation
-   worktree cleanup checks
-   branch naming and task metadata conventions

Exit criteria:

-   active tasks run only in isolated worktrees
-   scheduled collection has a documented operator need, bounded query window,
    retention, and failure signal
-   project checkouts are protected from task edits
-   cleanup does not destroy unreviewed work

## Phase 8 - Forge Task Ledger and Codex Executor

Goals:

-   configure Hermes provider fallback
-   record the installed OCI Codex version and command contract
-   implement the private task ledger and immutable request adapter
-   implement task-envelope and structured-result validation
-   implement Codex session, waiting, and GitHub handoff state
-   configure Hermes provider fallback without treating it as Codex session
    failover

Expected scope:

-   fallback provider policy
-   version-verified Codex non-interactive execution and resume behavior
-   `queued`, `running`, `waiting_user`, `waiting_approval`, `review_ready`,
    `failed`, `cancelled`, and `completed` transitions
-   branch, Draft PR, validation, and approval result contract
-   optional adapters for other CLIs only after the Codex path is stable

Exit criteria:

-   provider failures degrade gracefully
-   Hermes provider failure and Codex executor-session failure have distinct,
    observable recovery paths
-   `waiting_user` exits the Codex process, releases the executor slot, and
    resumes from the same Forum post
-   initial global Codex concurrency is one
-   one accepted task can be dispatched to Codex in a worktree and handed to a
    direct Codex session through GitHub without directory synchronization

## Phase 9 - Backups, Health Checks, and Recovery

Goals:

-   back up Hermes state and Forge host ops artifacts
-   verify that recovery can be practiced
-   make operational failures visible

Expected scope:

-   backup scripts
-   restore scripts
-   healthcheck script
-   scheduled backups
-   operator alerting
-   detection and preservation of unpushed worktree state
-   pre-upgrade backup and smoke-test procedure
-   encrypted off-host storage and secret-safe logs

Exit criteria:

-   the OCI host can be lost without losing unrecoverable platform knowledge
-   backup and restore steps are tested and documented
-   a clean replacement environment can recover the control-plane state without
    copying repository build artifacts

## First Vertical Slice

Before adding more projects or executor concurrency, Forge must complete one
end-to-end task through this path:

```text
Discord request
  -> Hermes gateway
  -> immutable inbox capture before model interpretation
  -> registered project Forum post
  -> /dev plan with no repository writes
  -> explicit /dev run
  -> Forge task ledger and one task worktree
  -> Codex implementation and validation
  -> pushed Git checkpoint and Draft PR
  -> optional handoff to direct Codex on another device
  -> structured result in the same Forum post
```

The slice uses a disposable or non-sensitive repository. Its purpose is to
validate the real security and lifecycle boundaries, not to demonstrate maximum
agent autonomy.

## Phase 10 - Broader Platform Evolution

This phase starts only after the first deployment is stable.

Candidates:

-   GitHub workflow automation
-   memory and retention policy beyond defaults
-   evaluation and observability
-   multi-repository orchestration
-   alternative runtime frameworks
-   deeper secret management

## Roadmap Rules

-   Do not skip directly to automation before the relevant contract exists.
-   Do not add interfaces before the host and runtime are stable.
-   Do not add persistence without lifecycle and ownership rules.
-   Do not optimize for scale before the single-host deployment is reliable.
