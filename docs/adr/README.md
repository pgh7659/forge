# Architecture Decision Records

This directory records durable decisions for the portable Forge core. Create an
ADR for a public contract, interface, compatibility rule, or architecture
boundary that is costly to change.

## Current index

- `0000-template.md` — template for new decisions.
- `0007-adopt-runtime-neutral-security-contracts.md` — runtime-neutral trust,
  taint, provenance, policy-decision, and sink contracts.
- `0009-separate-portable-core-from-deployment-profiles.md` — public core,
  private deployment configuration, and public reference-deployment boundary.
- `0010-adopt-a-contract-first-single-node-controller-core.md` — versioned
  in-process controller, encrypted request bodies in SQLite, bounded
  scheduling, and conservative restart recovery.

Historical decisions for the first stack live with the [Hermes, Discord, and
Codex reference deployment](../reference-deployments/hermes-discord-codex/decisions/).
They retain their original rationale but govern that deployment only.
