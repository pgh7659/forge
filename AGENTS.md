# AGENTS.md

> Operational rules for every AI agent working inside Forge.

## Purpose

This document defines how AI agents operate within Forge.

Every task should leave the repository easier to understand, safer to change,
and closer to the architecture described in the project documents.

## Read Order

1.  FORGE_BOOTSTRAP.md
2.  AGENTS.md
3.  docs/architecture.md
4.  docs/roadmap.md
5.  Relevant ADRs
6.  Related source code

## Operating Principles

-   Understand context before acting.
-   Prefer planning before implementation when the work is ambiguous.
-   Keep changes minimal, reversible, and explainable.
-   Explain architectural decisions.
-   Update documentation when behavior or architecture changes.
-   Respect existing architecture.
-   Escalate uncertainty instead of guessing.

## Agent Lifecycle

1.  Load the required project context.
2.  Inspect the relevant files and Git state.
3.  Build a small plan when the task has multiple steps.
4.  Request human approval for high-impact operations.
5.  Execute the smallest useful change.
6.  Validate with tests, checks, or direct inspection.
7.  Update documentation or ADRs when required.
8.  Summarize what changed and what remains.

## Human Approval

High-impact operations require explicit human approval:

-   deleting code or data
-   changing architecture
-   modifying infrastructure
-   releasing software
-   rewriting history
-   pushing directly to protected branches

## Always

-   Explain architectural decisions.
-   Prefer incremental commits when committing.
-   Update documentation with code.
-   Keep commits focused.
-   Preserve user changes unless explicitly told otherwise.

## Never

-   Push directly to main.
-   Commit secrets.
-   Invent APIs, workflows, or CLI commands.
-   Execute destructive actions without approval.
-   Hide uncertainty behind confident guesses.

## Definition of Done

-   Implementation is complete.
-   Tests or relevant checks pass.
-   Documentation is updated where required.
-   ADR is added or updated if architecture changed.
-   The change is reviewable and reversible.
