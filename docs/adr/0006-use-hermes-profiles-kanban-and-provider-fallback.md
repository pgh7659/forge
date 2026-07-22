# ADR-0006: Use Hermes Profiles, Kanban, and Provider Fallback

## Status

Accepted

## Date

2026-07-22

## Context

Forge needs a practical first multi-agent execution model that works on one OCI
host, tolerates provider failures, and avoids premature invention of custom
cross-CLI orchestration.

Hermes already provides:

- profile-scoped state via `HERMES_HOME`
- a gateway-embedded Kanban dispatcher
- provider fallback chains

## Decision Drivers

- Need for role separation
- Need for durable single-host task coordination
- Need for graceful handling of provider outages or limits

## Decision

Forge will use Hermes profiles for initial role separation, Hermes Kanban for
task coordination, and Hermes provider fallback for runtime resilience.

Initial profiles:

- orchestrator
- coder
- reviewer

Deployment starts with the orchestrator profile only. Coder and reviewer are
enabled after the single-profile vertical slice validates access controls,
workspace isolation, restart behavior, and recovery.

The first deployment uses one Discord-connected orchestrator gateway. Worker
profiles are launched by the gateway-embedded dispatcher. Unrelated projects
or operational domains should use separate Kanban boards.

External CLIs such as Codex CLI, Claude Code, and Gemini CLI are optional
specialist tools, not the primary task handoff mechanism.

## Alternatives Considered

- Use external CLIs as equal peer agents from day one
- Build a custom task queue and dispatcher first
- Run all work through a single Hermes profile

These were not chosen because they either overcomplicate the first deployment
or give up useful runtime boundaries that Hermes already provides.

## Consequences

Benefits:

- native single-host multi-agent flow
- built-in provider resilience
- less custom orchestration code early on

Costs:

- Kanban is single-host and must be treated that way
- profile and fallback configuration become operationally important
- boards, workspaces, and concurrency require explicit lifecycle policies
- profiles share the host user's normal CLI credentials by default and are not
  security sandboxes

Initial safety defaults:

- no more than two in-progress tasks across the board
- automatic triage decomposition disabled until manual task flow is proven
- provider fallback used for Hermes API calls, not advertised as transparent
  continuation across external CLI sessions

If Forge later needs multi-host task routing or richer handoff contracts, that
should be added above or beside this runtime model rather than hidden inside
provider-specific tooling.
