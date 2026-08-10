# Architecture Decision Records

Record durable architecture decisions here.

Create an ADR when a change introduces a new layer, expensive-to-replace
dependency, provider contract, infrastructure pattern, or long-lived workflow
rule.

## Current ADR Index

-   `0000-template.md` - template for new decisions
-   `0001-use-hermes-as-initial-orchestrator.md` - engineering-orchestrator portion
    superseded by ADR-0008
-   `0002-use-host-install-on-oci-for-first-deployment.md`
-   `0003-use-discord-as-primary-operator-interface.md` - worker/Kanban topology
    superseded by ADR-0008
-   `0004-use-tailscale-for-private-dashboard-access.md`
-   `0005-use-protected-checkouts-and-hermes-worktrees.md` - protected checkout
    decision retained; worktree owner superseded by ADR-0008
-   `0006-use-hermes-profiles-kanban-and-provider-fallback.md` - profile/Kanban
    topology superseded by ADR-0008; provider fallback retained
-   `0007-adopt-runtime-neutral-security-contracts.md` - trust, taint,
    provenance, policy-decision, and sink contracts
-   `0008-separate-assistant-control-plane-from-engineering-execution.md` -
    Hermes personal assistant, Discord Forum routing, Forge task ledger, Codex
    executor, and Git-based handoff
