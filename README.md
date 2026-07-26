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
the initial orchestrator, not the identity of the platform.

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
- Discord as the primary operator interface
- Tailscale-only access for the Hermes dashboard
- Hermes profiles plus Kanban for multi-agent execution
- protected Git checkouts plus Hermes-native task worktrees for code isolation
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

## Current status

Forge is in the documentation and contract phase.

Implemented today:

- constitution and operating rules
- architecture and roadmap
- initial ADRs
- runtime-neutral security contracts and threat model documentation
- repository scaffold

Not implemented yet:

- OCI bootstrap scripts
- Hermes installation automation
- Discord gateway setup
- dashboard service management
- repository and worktree automation
- backup and observability workflows

No document in this repository should be read as evidence that an OCI host is
already configured. Until the relevant phase is implemented and its acceptance
checks pass, it is a chosen design rather than an operating capability.

## Security

Read [`SECURITY.md`](SECURITY.md) before reporting a vulnerability or making a
security-sensitive change. Forge has chosen generalized trust, taint,
provenance, policy-decision, and sink contracts, documented under
[`docs/security/`](docs/security/). Their schemas, validators, adapters, and
host enforcement are proposed work, not current runtime capabilities.

## Validated design stance

The first deployment deliberately uses Hermes features before adding Forge
abstractions:

- one Discord-connected orchestrator gateway
- named Hermes profiles as workers
- Kanban boards and the gateway-embedded dispatcher
- native `worktree` workspaces for coding tasks
- Hermes provider fallback for API-level resilience

External coding CLIs remain optional tools. Forge does not assume that a
Claude Code, Gemini CLI, or Codex CLI session can transparently continue
another CLI's interrupted session.

## Working stance

Forge prefers documented constraints over premature automation.

Before adding code, scripts, or services, define:

- what the component owns
- what it is allowed to change
- how it is rolled back
- what documentation must move with it

The first useful milestone is deliberately smaller than the long-term vision:
one OCI host, one trusted operator, one Discord-connected orchestrator, one
Kanban board, and one test repository. Multi-project and multi-agent expansion
follows only after this vertical slice survives restart, recovery, and access
control tests.
