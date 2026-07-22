# ADR-0001: Use Hermes as the Initial Orchestrator

## Status

Accepted

## Date

2026-07-22

## Context

Forge needs a practical first runtime for an OCI-hosted operator node.

The first deployment needs:

- messaging gateway support
- a remote dashboard
- multiple agent roles
- provider fallback
- task orchestration
- a path to host-installed operation on Linux ARM64

Building all of that from scratch would delay the first useful deployment and
increase design drift before runtime validation.

## Decision Drivers

- Speed to first working OCI deployment
- Existing Hermes support for gateway, dashboard, profiles, and Kanban
- Desire to preserve long-term provider and framework replaceability

## Decision

Forge will use Hermes as its initial orchestrator runtime.

Forge will not define itself as a Hermes wrapper. Hermes is the first runtime
implementation beneath Forge policy, documentation, and workflow conventions.

## Alternatives Considered

- Build a custom orchestrator first
- Use external CLIs as the primary orchestration fabric
- Delay runtime choice until a generic Forge core exists

These were not chosen because they create more design work before the first
deployment proves the operating model.

## Consequences

Benefits:

- immediate access to gateway, dashboard, profiles, Kanban, and fallback
- lower time-to-first-deployment
- less need for speculative orchestration code

Costs:

- first deployment inherits Hermes runtime conventions
- Forge documentation must be explicit about what is Hermes-specific

If Forge later replaces Hermes, that migration must happen through ADRs and
contracted interfaces rather than ad hoc rewrites.
