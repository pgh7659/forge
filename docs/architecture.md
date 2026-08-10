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
-   runtime-neutral security contract and threat model documentation
-   assistant-control-plane and engineering-executor responsibility contract
-   read-only OCI audit and Git-based handoff templates
-   repository scaffolding for future bootstrap, config, scripts, and tests

Reported by the operator but not yet reconciled through Forge acceptance
evidence:

-   OCI-hosted Hermes, Discord, and Codex CLI operation

Not implemented or not yet evidenced in this repository:

-   OCI bootstrap scripts
-   Hermes installation automation
-   Discord gateway automation
-   dashboard service management
-   repository and worktree automation
-   backup and observability workflows
-   security contract schemas, validators, policy evaluation, runtime adapters,
    and host enforcement

The rest of this document describes the chosen architecture and reconciliation
target. It is not evidence that the reported OCI runtime is reproducible,
recoverable, or compliant until the environment audit and acceptance contract
pass.

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
-   Codex CLI supports non-interactive execution and resumable task sessions in
    the currently inspected client, but the OCI-installed version and help
    output must be captured before its adapter is automated.

Because of that, Forge does not need to invent a custom orchestration model to
reach a useful OCI deployment.

## First Deployment Scope

The first deployment target is a single OCI Ubuntu ARM64 VM running Forge's
initial runtime through Hermes.

That deployment includes:

-   Hermes installed directly on the host
-   Discord and Hermes as the personal-assistant and operations interface
-   Hermes dashboard reachable only on the Tailnet
-   an assistant profile and an optional operations profile
-   Hermes Kanban for durable task, approval, and handoff state
-   Codex as the first engineering executor
-   protected Git checkouts plus Hermes-native Git worktrees for code isolation
-   provider fallback for model resilience

The first production-like validation slice is intentionally narrower:

-   one trusted Unix service account
-   one trusted Discord operator
-   one assistant profile
-   one Kanban board with automatic decomposition disabled
-   one non-sensitive test repository
-   one Codex engineering executor at a time

The optional operations and reviewer profiles are added only after this slice
passes restart, authorization, workspace-isolation, and recovery checks.

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
  -> Direct Codex Decision Surface | Discord Assistant Surface
  -> Forge Policy, Task Contract, and Approval Boundary
  -> Hermes Assistant Control Plane
  -> Codex Engineering Executor
  -> Workspace Manager and GitHub Handoff
  -> Protected Runtime and Data Plane
```

## Layer Responsibilities

### Human Operator

Owns intent, approvals, production judgment, and access to secrets.

### Interface Layer

Receives work and returns results.

First chosen interfaces:

-   direct Codex for product, architecture, roadmap, and interactive engineering
-   Discord for personal assistance, operations, task capture, and reporting
-   Hermes dashboard for observability and operator control

### Forge Policy and Workflow

Owns:

-   working rules
-   repository conventions
-   review and rollback expectations
-   documentation requirements

This layer is where Forge keeps its identity independent from Hermes.

### Hermes Runtime

Hermes is the initial assistant control-plane runtime for:

-   messaging gateway
-   dashboard
-   profile management
-   provider fallback
-   Kanban task, approval, and dispatch state
-   reminders, scheduled reports, factual status, and registered runbooks

Hermes must preserve the operator's raw request and must route ambiguous design
work to direct Codex rather than silently inventing an engineering contract.

Status collection is on-demand by default. When a daily brief is useful, the
collector advances an incremental cursor and caches only the bounded state
needed for the report. OCI utilization is an observation, not a reason to run
full-history scans or invent background work.

### Assistant Profiles and Kanban

Initial operating model:

-   `assistant`: the only Discord-connected gateway; owns capture, status,
    reminders, approvals, and dispatch
-   `ops`: optional worker for registered read-only or reversible runbooks

Optional later:

-   `reviewer`: independent read-only verification
-   other named specialists justified by observed demand

Kanban is the task coordination plane and remains single-host for the first
deployment. The dispatcher runs inside the gateway by default. A single
installation can host multiple boards, with a separate SQLite database,
workspace area, and logs per board. Forge should begin with one board per
active project or operational domain rather than mixing unrelated projects in
the default board.

Only the assistant profile needs the Discord-connected gateway. Codex is
invoked through a version-verified executor adapter rather than represented as
a Hermes coding personality. Giving every profile its own bot token and gateway
would add operational complexity without improving the workflow.

Profiles isolate Hermes state through `HERMES_HOME`; they do not automatically
isolate the host user's SSH keys, GitHub credentials, external CLI sessions, or
filesystem permissions. The initial profiles therefore share one trust domain.
Stronger identity separation requires separate Unix users, containers, or a
later isolation design.

### Codex Engineering Executor

Codex is the first implementation executor for accepted engineering tasks. The
adapter may start or resume a Codex CLI session only after the installed OCI
version and command contract have been captured. It receives the operator's raw
request plus a versioned task envelope and runs in the task-local worktree.

The adapter returns structured status, validation evidence, the last pushed
commit, Draft PR, risks, blockers, and any action requiring approval. It does
not merge, deploy, migrate, publish, use credentials outside the declared
scope, or perform destructive cleanup without fresh human approval.

Direct Codex and OCI Codex sessions do not share hidden conversation state.
Handoff across devices or runtimes uses pushed Git refs, Draft PRs, and the
procedure in `docs/operations/assistant-codex-handoff.md`.

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

This public Forge repository owns reusable templates, contracts, scripts, and
runbooks. Host-specific inventory, repository registrations, opaque service
identifiers, audit reports, and accepted version locks belong in a separate
private operations repository mounted or checked out at `/srv/forge/ops`.
Credentials remain outside both repositories in a host or external secret
store. Introducing the private operations repository is a deployment action and
requires explicit approval.

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

Discord is the primary assistant and operations interface, not the sole surface
for product strategy or interactive engineering. Design requests are recorded
and routed to direct Codex; implementation requests preserve the raw Discord
message in private task state.

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

Codex CLI is the first engineering executor beneath the Forge task contract.
It is not the primary orchestration fabric: Hermes and Kanban own durable task
state, while GitHub owns durable engineering handoff. Other CLIs remain optional
adapters.

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

Forge has chosen runtime-neutral trust, taint, provenance, policy-decision, and
sink contracts in
[`docs/security/trust-taint-provenance.md`](security/trust-taint-provenance.md).
The generalized threat model is
[`docs/security/threat-model.md`](security/threat-model.md). Those documents are
implemented as design contracts only. Forge core will declare and validate the
contracts; runtime and host adapters must separately implement and demonstrate
enforcement. No current document should be read as evidence of sandboxing or
host-level enforcement.

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
