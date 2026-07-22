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

Repository foundation is in progress.

The direction is now explicit:

-   first host: OCI Ubuntu ARM64
-   first orchestrator runtime: Hermes
-   first operator interface: Discord
-   first private access layer: Tailscale
-   first workspace model: protected checkout plus Hermes-native worktree

## Phase 0 - Foundation and Decisions

Goals:

-   stabilize the core documents
-   create initial ADRs
-   clarify the first deployment shape
-   avoid premature implementation drift

Exit criteria:

-   README, bootstrap, agents, architecture, and roadmap agree with each other
-   initial ADRs exist for Hermes, Discord, Tailscale, host install, and native
    worktree strategy
-   the repository states what is chosen versus what is only deferred

## Phase 1 - OCI Environment Audit

Goals:

-   inspect the target OCI host before changing it
-   capture OS, package, network, and privilege assumptions
-   identify gaps in the current documentation

Deliverables:

-   environment audit script
-   environment audit report
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
-   begin with a single default/orchestrator profile and a non-sensitive test
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

## Phase 6 - Profiles, Kanban, and Workflow Roles

Goals:

-   define initial profiles
-   initialize Kanban
-   validate the first multi-agent loop
-   create a separate board for the first project or operational domain

Expected profiles after the single-profile vertical slice succeeds:

-   orchestrator
-   coder
-   reviewer

Exit criteria:

-   a task can be created, assigned, run, and completed through Hermes Kanban
-   role boundaries are documented
-   concurrency limits are conservative and explicit
-   automatic triage decomposition remains off until manually reviewed task
    flow is stable
-   profile boundaries are not presented as host credential or filesystem
    isolation

## Phase 7 - Repository and Workspace Automation

Goals:

-   codify the protected checkout and worktree strategy
-   automate safe setup and cleanup
-   make task-local execution reproducible

Expected scope:

-   repository registration
-   protected checkout setup
-   Hermes-native worktree creation
-   worktree cleanup checks
-   branch naming and task metadata conventions

Exit criteria:

-   active tasks run only in isolated worktrees
-   project checkouts are protected from task edits
-   cleanup does not destroy unreviewed work

## Phase 8 - Provider Resilience and Specialist Tools

Goals:

-   configure Hermes provider fallback
-   define when external specialist CLIs are used
-   avoid inventing fragile cross-CLI orchestration too early

Expected scope:

-   fallback provider policy
-   role-based provider aliases
-   documented optional use of Codex CLI, Claude Code, and Gemini CLI

Exit criteria:

-   provider failures degrade gracefully
-   Forge relies on Hermes-native resilience before custom handoff logic

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

Before expanding to multiple profiles or projects, Forge must complete one
end-to-end task through this path:

```text
Discord request
  -> Hermes gateway
  -> manually reviewed Kanban task
  -> one task worktree
  -> test change and validation
  -> Git commit or explicit discard
  -> Discord completion report
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
