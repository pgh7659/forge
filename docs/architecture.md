# Architecture

## Responsibility

This document describes Forge's current architecture and the boundaries the
project should preserve as implementation begins.

FORGE_BOOTSTRAP defines enduring principles. This document should stay closer
to implementation reality: what exists, what is only proposed, and what must be
decided before code is added.

## Current Implementation

Forge is currently a repository scaffold.

Implemented today:

-   project constitution
-   AI agent operating rules
-   architecture and roadmap documents
-   ADR directory
-   placeholder directories for bootstrap, scripts, templates, systemd,
    config, tests, examples, and prompts

Not implemented yet:

-   runtime orchestrator
-   provider adapter interface
-   Discord, GitHub, or CLI integration layer
-   workspace manager
-   host bootstrap automation
-   memory, evaluation, or observability system

This distinction matters. Future-facing diagrams in this file are design
targets, not claims about working software.

## Target Layer Model

Forge should separate platform responsibilities from replaceable
implementations.

```text
Human
  -> Interface Layer
  -> Forge Core
  -> Workflow Engine
  -> Agent Contract
  -> Provider Adapter
  -> Tool Boundary
  -> Workspace
  -> Git Repository
  -> Infrastructure
```

## Intended Responsibilities

-   Human: owns intent, approval, and final accountability.
-   Interface Layer: exposes Forge through Discord, GitHub, CLI, or other
    human-facing entry points.
-   Forge Core: owns platform concepts, task state, and policy.
-   Workflow Engine: coordinates task lifecycle, approvals, validation, and
    rollback expectations.
-   Agent Contract: defines how agents receive context, act, report, and stop.
-   Provider Adapter: isolates model-specific execution behind a replaceable
    interface.
-   Tool Boundary: exposes limited, auditable capabilities to agents.
-   Workspace: prepares repositories, worktrees, and task-local files.
-   Git Repository: stores code, documentation, decisions, and review history.
-   Infrastructure: runs Forge services through versioned configuration.

## Candidate Integrations

These tools are candidates for early implementation, not permanent
dependencies:

-   GitHub for repository and review workflows
-   Discord for human interaction
-   Tailscale for private host access
-   OCI Ubuntu ARM64 for an initial host
-   Hermes as a possible first orchestrator
-   Codex CLI, Claude Code, and Gemini CLI as possible provider backends

Provider independence means each candidate must be replaceable without
rewriting Forge's core workflow semantics.

## Design Rules

-   Document contracts before implementing adapters.
-   Keep providers stateless unless state ownership is explicitly designed.
-   Treat Git as the source of truth for durable work.
-   Prefer replaceable integrations over direct coupling.
-   Require human approval for high-risk operations.
-   Make every automation path explainable and reversible.

## Decision Gates

Add or update an ADR before introducing:

-   a new architectural layer
-   a long-lived provider contract
-   host or infrastructure assumptions
-   persistent memory
-   release automation
-   a dependency that would be expensive to replace
