# Forge

Forge is a personal AI engineering platform for running long-lived software
workflows on infrastructure you control.

The first delivery target is concrete: an OCI-hosted Hermes node that can
receive work through Discord, protect its dashboard behind Tailscale, manage
repositories through Git worktrees, and stay understandable through
documentation and review.

## What Forge is

Forge coordinates:

- people and approvals
- AI agents and their execution rules
- repositories and workspaces
- workflows, documentation, and operational decisions
- infrastructure required to run the system repeatedly

Forge is not a thin wrapper around one model or one agent runtime. Hermes is
the initial personal-assistant gateway, not the engineering orchestrator or the
identity of the platform.

## Why this repository exists

This repository exists to prevent the OCI Hermes setup from becoming tribal
knowledge or a pile of ad hoc shell history.

The goal is to make the first deployment:

- repeatable
- reviewable
- reversible
- secure enough for a personal operator node
- replaceable when providers, frameworks, or hosts change

## First implementation direction

The current direction, intentionally, is:

- OCI Ubuntu ARM64 as the first host
- Hermes installed directly on the host for the first deployment
- Discord and one Hermes profile as the personal-assistant gateway
- Tailscale-only access for the Hermes dashboard
- direct or Discord-routed Codex for product, architecture, and engineering
- a Forge immutable inbox and task ledger for Discord engineering requests
- Codex CLI as the first version-verified engineering executor
- protected Git checkouts plus Forge-managed task worktrees for code isolation
- provider fallback for resilience before custom multi-CLI handoff logic

The design has been checked against current upstream Hermes documentation, but
Forge does not treat upstream `main` as a deployment contract. Every real host
records and validates the installed Hermes release or commit before automation
is enabled.

This is a host-specific implementation choice, not a permanent platform
requirement. Forge keeps the orchestration contract above any single runtime.

## Read this first

If you are new to the repository, read in this order:

1. `FORGE_BOOTSTRAP.md`
2. `AGENTS.md`
3. `docs/architecture.md`
4. `docs/roadmap.md`
5. `SECURITY.md` and `docs/security/` for security-sensitive work
6. relevant files in `docs/adr/`

## Repository layout

- `docs/` holds architecture, roadmap, security contracts, threat models, and
  architectural decisions.
- `bootstrap/` will hold first-run and host bootstrap assets.
- `scripts/` will hold repeatable automation for repository and operator tasks.
- `systemd/` will hold Linux service units and timers.
- `config/` will hold non-secret config examples and templates.
- `templates/` will hold reusable scaffolds and config templates.
- `prompts/` will hold structured prompts and operator playbooks.
- `tests/` will hold validation for contracts, safety rules, and workflows.
- `examples/` will hold small, inspectable scenarios.

Host-specific inventory and audit evidence belong in a separate private
operations repository. Secrets remain outside Git entirely.

## Current status

Forge is moving from documentation and contracts into reconciliation with its
first manually configured OCI host.

Implemented today:

- constitution and operating rules
- architecture and roadmap
- initial ADRs
- runtime-neutral security contracts and threat model documentation
- personal-assistant gateway and engineering-executor responsibility contract
- Discord Forum routing, read-only OCI audit, and task-handoff templates
- repository scaffold

Reported outside this repository but not yet accepted as verified Forge
capability:

- OCI-hosted Hermes, Discord, and Codex CLI operation

Not implemented or not yet evidenced in this repository:

- OCI bootstrap scripts
- Hermes installation automation
- Discord gateway setup
- dashboard service management
- repository and worktree automation
- backup and observability workflows

The operator reports that an OCI host is configured, but its version, service,
workspace, access, backup, and recovery evidence has not been reconciled with
this repository. Until the read-only audit and acceptance checks pass, treat
that host as observed external state rather than a reproducible Forge release.

## Security

Read [`SECURITY.md`](SECURITY.md) before reporting a vulnerability or making a
security-sensitive change. Forge has chosen generalized trust, taint,
provenance, policy-decision, and sink contracts, documented under
[`docs/security/`](docs/security/). Their schemas, validators, adapters, and
host enforcement are proposed work, not current runtime capabilities.

## Validated design stance

The first deployment keeps Hermes deliberately narrow:

- one Discord-connected assistant gateway
- one general operator channel and one Forum channel per registered project
- one Forum post per work topic and primary Codex session
- no Hermes Kanban or Hermes coding profile in the engineering path
- a Forge inbox that retrieves the original Discord message by opaque ID
- a Forge ledger and dispatcher with Forge-managed `worktree` workspaces
- Hermes provider fallback for API-level resilience
- a version-verified Codex adapter for engineering execution

Codex is the first engineering executor, not the Forge platform identity.
Forge does not assume that Hermes, direct Codex, Codex CLI, Claude Code, or
Gemini CLI can transparently continue another runtime's private session.
Durable continuation uses Git refs, Draft PRs, validation evidence, and an
explicit handoff record.

## Working stance

Forge prefers documented constraints over premature automation.

Before adding code, scripts, or services, define:

- what the component owns
- what it is allowed to change
- how it is rolled back
- what documentation must move with it

The next useful milestone is deliberately smaller than the long-term vision:
audit the existing OCI host, run one trusted Discord assistant, dispatch one
`/dev plan` and one accepted `/dev run` through Codex into an isolated worktree
and Draft PR, and prove
restart, recovery, access control, and handoff to a second device.
