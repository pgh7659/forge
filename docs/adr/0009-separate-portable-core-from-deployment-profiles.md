# ADR-0009: Separate Portable Core from Deployment Profiles

## Status

Accepted

## Date

2026-08-10

## Context

Forge's public documentation previously described one selected deployment as
if it were the platform. That obscured the portable interfaces that users need
to select their own environment and made the first deployment's operational
material appear mandatory.

## Decision

Public Forge owns executable contracts and adapter interfaces. Private
deployment repositories own selected versions and real inventory. Named public
reference deployments provide conformance evidence without becoming core
defaults.

The first public reference deployment keeps its selected operations, decisions,
assets, prompts, scripts, and example envelopes under
`docs/reference-deployments/hermes-discord-codex/`.

## Consequences

Portable root policy can evolve independently of selected infrastructure and
provider choices. Reference deployments remain reviewable examples and may
document their own operational constraints through nested guidance. Future
private deployment configuration begins only after a published configuration
contract, and does not copy Forge source or resolved secret values.
