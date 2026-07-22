# Architecture

## Purpose

This document describes the chosen architecture for Forge's first real
deployment target and the boundaries that should be preserved while
implementation begins.

`FORGE_BOOTSTRAP.md` defines enduring principles.
This document defines the currently chosen system shape.

## Reference Baseline

This architecture was checked on 2026-07-22 against the upstream Hermes
documentation on `main`. That documentation is evidence for direction, not a
stable deployment contract. Implementation must pin and record an installed
release or commit, inspect its `--help` output, and validate the required
behavior on the target host before enabling automation.

Primary references:

-   [Hermes installation](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/getting-started/installation.md)
-   [Profiles](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/profiles.md)
-   [Kanban and workspaces](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/kanban.md)
-   [Discord gateway](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/messaging/discord.md)
-   [Fallback providers](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/fallback-providers.md)
-   [Web dashboard and remote access](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/web-dashboard.md)
-   [Terminal backends and home isolation](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/configuration.md)

## Current State

Implemented today:

-   project constitution
-   AI operating rules
-   architecture and roadmap
-   ADR scaffolding
-   repository scaffolding for future bootstrap, config, scripts, and tests

Not implemented yet:

-   OCI bootstrap scripts
-   Hermes installation automation
-   Discord gateway automation
-   dashboard service management
-   repository and worktree automation
-   backup and observability workflows

The rest of this document describes the target architecture for the first OCI
deployment, not a claim that the runtime already exists.

## Direction Check

The current direction is correct for the first deployment.

The architecture aligns with Hermes' current operating model:

-   Hermes provides a direct Linux installation path, while OCI Ampere provides
    an aarch64 Linux host. Forge still treats the exact ARM64 install as a Phase
    1 validation item rather than assuming every optional dependency works.
-   Hermes profiles isolate state by `HERMES_HOME` while host-installed tools
    still use the real OS home by default.
-   Hermes Kanban is a durable single-host board shared across profiles.
-   Hermes provides a native `worktree` workspace mode for isolated coding
    tasks and preserves those worktrees after task completion.
-   Hermes dashboard guidance explicitly recommends Tailscale or another VPN
    rather than exposing the dashboard to the public internet.
-   Hermes Discord integration is first-class and supports allowlists,
    mentions, threads, files, and slash commands.

Because of that, Forge does not need to invent a custom orchestration model to
reach a useful OCI deployment.

## First Deployment Scope

The first deployment target is a single OCI Ubuntu ARM64 VM running Forge's
initial runtime through Hermes.

That deployment includes:

-   Hermes installed directly on the host
-   Discord as the primary operator interface
-   Hermes dashboard reachable only on the Tailnet
-   Hermes profiles for role separation
-   Hermes Kanban for multi-agent task flow
-   protected Git checkouts plus Hermes-native Git worktrees for code isolation
-   provider fallback for model resilience

The first production-like validation slice is intentionally narrower:

-   one trusted Unix service account
-   one trusted Discord operator
-   one orchestrator profile
-   one Kanban board with automatic decomposition disabled
-   one non-sensitive test repository
-   one coding worker at a time

Coder and reviewer profiles are added only after this slice passes restart,
authorization, workspace-isolation, and recovery checks.

It explicitly does not require, on day one:

-   Dockerized Hermes
-   multi-host orchestration
-   automatic failover between external CLIs
-   a custom web UI beyond Hermes dashboard
-   long-lived shared memory beyond Hermes' default profile state

## Layer Model

Forge should separate durable platform concerns from replaceable runtime
choices.

```text
Human Operator
  -> Interface Layer
  -> Forge Policy and Workflow
  -> Hermes Runtime
  -> Agent Profiles and Kanban
  -> Workspace Manager
  -> Git Repositories and Worktrees
  -> Host Services and Network Boundary
```

## Layer Responsibilities

### Human Operator

Owns intent, approvals, production judgment, and access to secrets.

### Interface Layer

Receives work and returns results.

First chosen interfaces:

-   Discord for day-to-day interaction
-   Hermes dashboard for observability and operator control

### Forge Policy and Workflow

Owns:

-   working rules
-   repository conventions
-   review and rollback expectations
-   documentation requirements

This layer is where Forge keeps its identity independent from Hermes.

### Hermes Runtime

Hermes is the initial runtime implementation for:

-   agent execution
-   messaging gateway
-   dashboard
-   profile management
-   provider fallback
-   Kanban task dispatch

Forge uses Hermes because it already provides the execution surfaces the first
deployment needs.

### Agent Profiles and Kanban

Initial operating model:

-   `orchestrator`
-   `coder`
-   `reviewer`

Optional later:

-   `researcher`
-   `infra`

Kanban is the task coordination plane and remains single-host for the first
deployment. The dispatcher runs inside the gateway by default. A single
installation can host multiple boards, with a separate SQLite database,
workspace area, and logs per board. Forge should begin with one board per
active project or operational domain rather than mixing unrelated projects in
the default board.

Only the orchestrator profile needs the Discord-connected gateway initially.
Coder and reviewer profiles are dispatcher-spawned workers; giving every
profile its own bot token and gateway would add operational complexity without
improving the first workflow.

Profiles isolate Hermes state through `HERMES_HOME`; they do not automatically
isolate the host user's SSH keys, GitHub credentials, external CLI sessions, or
filesystem permissions. The initial profiles therefore share one trust domain.
Stronger identity separation requires separate Unix users, containers, or a
later isolation design.

### Workspace Manager

Forge keeps a normal, protected Git checkout for each project and uses Hermes'
native task-local worktrees so agent sessions do not edit that checkout
directly.

Coding tasks use Kanban workspace type `worktree` (or an explicit
`worktree:<path>` only when needed). Hermes creates the task workspace under
the repository's `.worktrees/<task-id>/` directory by default and passes that
workspace to the worker.

### Git Repositories and Worktrees

Protected project checkouts live under `/srv/forge/repos`.
Active task workspaces normally live inside each checkout's `.worktrees/`
directory, following Hermes' native workspace lifecycle.

This gives each task:

-   its own branch
-   its own filesystem state
-   clearer rollback and cleanup
-   safer parallel execution

### Host Services and Network Boundary

The first host is a dedicated OCI VM.

Hermes runs directly on that host rather than inside a container for the first
deployment so it can use:

-   real user-level CLI credentials
-   Git and SSH naturally
-   `gh`, Codex, Claude Code, and Gemini CLI without container plumbing
-   systemd user services with fewer moving parts

Host installation is a packaging and operability choice, not sandboxing. The
Hermes service account can do whatever its Unix permissions and enabled tools
allow. Forge therefore starts with least-privilege tool configuration and a
non-sensitive repository before granting access to personal or private code.

## Filesystem Layout

### Hermes-owned state

Hermes keeps its own state under `~/.hermes`.

Important paths include:

-   `~/.hermes/config.yaml`
-   `~/.hermes/.env`
-   `~/.hermes/kanban.db`
-   `~/.hermes/profiles/<name>/`

That boundary matters. Forge should not invent a parallel location for Hermes'
native state unless a later ADR justifies it.

### Forge-owned operational assets

Forge-owned host assets should live under `/srv/forge`.

Target layout:

```text
/srv/forge/
  ops/
  repos/
    <project>/
      .git/
      .worktrees/
        <task-id>/
  backups/
  logs/
  tmp/
```

`ops/` is version-controlled operational material for the host.
`repos/` contains protected project checkouts. Each checkout is the anchor for
the task worktrees Hermes creates below `.worktrees/`.

The checkout is operational state, not the source of truth: pushed Git refs
remain authoritative. Uncommitted or unpushed worktrees must be detected by
health checks and backup policy because GitHub cannot restore them.

The `/srv/forge/repos` layout is a Forge convention, not a Hermes requirement.
Each registered checkout must have an explicit remote and default branch and is
protected by policy and validation. Forge does not add a custom bare-repository
manager until native worktrees have been exercised and shown insufficient.

## Interfaces

### Discord

Discord is the first operator interface because it fits:

-   mobile and desktop use
-   threads for task-level discussion
-   file delivery
-   mention-gated channel interaction
-   fine-grained allowlists

Default security stance:

-   restricted user allowlist or role allowlist
-   mention required in shared channels unless a channel is explicitly marked
    free-response
-   per-user session isolation enabled
-   one explicit guild and channel scope
-   no administrator permission for the bot
-   no public or untrusted users

### Dashboard

Hermes dashboard is the operator UI for:

-   session inspection
-   gateway monitoring
-   Kanban visibility
-   remote control where appropriate

Default exposure rule:

-   never public internet
-   bind Hermes itself to `127.0.0.1`
-   publish the loopback service only through Tailscale Serve
-   rely on authenticated Tailnet membership and ACLs as the initial access
    boundary

Hermes 0.19.0 engages its OAuth gate for non-loopback binds and refuses to
start without a registered dashboard auth provider. The bundled provider
requires a Nous-provisioned OAuth client ID; OpenAI Codex inference OAuth does
not provide one. Forge therefore does not bind the dashboard directly to the
Tailnet address and does not pass `--insecure` to bypass the gate.

The dashboard runs as a supervised user service on `127.0.0.1:9119`.
Hermes 0.19.0 also rejects a proxied request when its external `Host` header
does not match the loopback bind. A minimal Caddy listener on
`127.0.0.1:9120` normalizes that header and proxies to Hermes. Tailscale Serve
terminates Tailnet HTTPS and forwards only authenticated Tailnet traffic to
the compatibility listener. Caddy does not listen on a public or Tailnet
address. Tailscale Funnel is forbidden.
Stronger application-layer authentication may be added later through a
supported Hermes dashboard auth provider and must be recorded before the
dashboard is exposed beyond the Tailnet.

OCI network policy remains defense in depth: port `9119` is not opened in the
public NSG or security list, no Forge web process listens on the public
interface, and the Tailscale Serve configuration is checked before remote use
is accepted. Legacy OCI ingress rules for TCP 80 and 443 are removed after the
private migration is accepted from a second Tailnet device.

## Provider Strategy

Forge keeps provider choice below the workflow layer.

Initial resilience strategy:

-   Hermes primary provider configuration
-   Hermes `fallback_providers`
-   auxiliary task fallback where needed

Provider fallback preserves the Hermes conversation when an API provider hits
a rate limit, authentication failure, overload, or connection error. It does
not preserve the private session state of an external coding CLI.

Optional specialist CLIs such as Codex CLI, Claude Code, and Gemini CLI are
secondary tools, not the primary orchestration fabric.

That means Forge should avoid assuming:

-   cross-CLI session continuity
-   automatic handoff between external CLIs
-   provider-specific prompt contracts in core workflow logic

Fallback handles eligible provider/API failures inside Hermes. It is not a cost
control system, a guarantee that every error is retryable, or a mechanism for
resuming the private session state of another CLI. Initial deployment records
provider budgets and keeps worker concurrency conservative.

## Security Boundaries

The first deployment assumes a personal but still security-conscious operator
node.

Rules:

-   no dashboard exposure to the open internet
-   no unrestricted Discord access
-   no secret material in Git
-   no root runtime for Hermes day-to-day execution
-   explicit approval gates for destructive or infrastructure-changing actions
-   Hermes runs with the filesystem and command privileges of its Unix user;
    host installation is packaging, not a security sandbox
-   Discord authorization grants access to a tool-capable agent, so user or
    role allowlists are mandatory and deny-all is the expected fallback
-   start with conservative Kanban concurrency (`max_in_progress: 2` or lower)
    and disable automatic triage fan-out until costs and behavior are observed

Threat model for the first deployment:

-   Discord messages, repository content, issues, PR bodies, web pages, and
    downloaded files are untrusted input and may contain prompt injection.
-   The trusted operator may authorize work but does not implicitly authorize
    secret disclosure, privilege escalation, deployment, or destructive cleanup.
-   The OCI host and its service account are inside one trust domain; profiles
    and worktrees provide workflow isolation, not hostile-code containment.
-   A compromised provider token, Discord bot token, SSH key, or dashboard
    credential must be independently revocable.

Initial secret policy:

-   runtime secrets live outside Git with mode `0600`
-   config examples contain names and placeholders only
-   logs, task metadata, comments, and backups must not echo secret values
-   backup archives containing Hermes state are encrypted before leaving the host

## Operations and Recovery

The deployment records the installed Hermes version or source commit and never
performs unattended Hermes upgrades. Before an upgrade, Forge backs up Hermes
state and validates the new release against a smoke-test checklist.

Backup scope includes:

-   Hermes configuration, profiles, memories, skills, sessions, boards, and
    Kanban databases under `~/.hermes`
-   Forge operations configuration and scripts
-   any worktree with uncommitted or unpushed changes

Repository checkouts and clean worktrees may be recreated from Git. Backups
must be copied off the OCI instance and restoration must be tested, not merely
documented.

Minimum recovery objectives for the first deployment:

-   pushed project history is restored from GitHub
-   Forge operational definitions are restored from this repository
-   Hermes state is restored from an encrypted off-host backup
-   clean checkouts and worktrees may be recreated
-   unpushed or dirty worktrees are detected and preserved before cleanup

Recovery is not accepted until a restore is exercised into a temporary location
or replacement test host.

## First Deployment Acceptance Contract

The OCI deployment is considered usable only when all of the following are
demonstrated and recorded:

-   installed versions and binary paths are captured
-   `hermes doctor` and a basic model call succeed
-   gateway and dashboard survive logout and host reboot
-   the dashboard is unreachable through the public IP and authenticated over
    Tailscale
-   Discord accepts the trusted operator and rejects an unauthorized identity
-   a task modifies only its worktree, not the protected checkout
-   provider failure produces an understood fallback or bounded failure
-   backup creation, off-host copy, and restore verification succeed
-   no secret appears in Git history or verification logs

## Deferred Concerns

These are intentionally deferred until the first deployment works:

-   Dockerized Hermes
-   multi-host orchestration
-   custom dashboard beyond Hermes
-   automatic repository onboarding across many repos
-   external secret manager integration
-   custom memory abstractions on top of Hermes
-   automated cross-provider CLI handoff

## Decision Gates

Add or update an ADR before introducing:

-   a new long-lived integration
-   a change to the OCI deployment model
-   a change to the `~/.hermes` and `/srv/forge` boundary
-   a different operator interface
-   public network exposure of any control surface
-   a new persistent data store
