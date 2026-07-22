# ADR-0003: Use Discord as the Primary Operator Interface

## Status

Accepted

## Date

2026-07-22

## Context

Forge needs a primary operator interface that works well on desktop and mobile,
supports threads, file delivery, and controlled access, and fits Hermes'
existing gateway features.

Telegram and Discord were both viable options.

## Decision Drivers

- Desktop and mobile operator experience
- Thread-oriented task discussion
- Hermes' mature Discord gateway support
- Ability to restrict access with user and role allowlists

## Decision

Forge will use Discord as the first primary operator interface.

Discord is the day-to-day command and reporting surface for the first
deployment. Hermes dashboard remains the operator control and observability
surface rather than the main conversational interface.

The initial topology uses one Discord-connected gateway for the orchestrator
profile. Worker profiles are launched by the Kanban dispatcher and do not need
their own Discord bots.

## Alternatives Considered

- Telegram as the primary interface
- CLI-only operation
- Custom web UI first

Telegram remained a viable future option, but Discord was chosen because it
better supports thread-based task separation and richer operator workflows.

## Consequences

Benefits:

- strong desktop and mobile experience
- task-level discussion via threads
- natural support for attachments and status reports
- allowlist and mention-based safety controls

Costs:

- Discord bot setup and permissions must be managed carefully
- gateway access must be locked down to trusted users or roles

Discord does not replace Git or documentation. It is the control plane, not
the source of truth.
