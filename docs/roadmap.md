# Roadmap

## Vision

Incrementally evolve Forge into an operable AI Engineering Platform rather than
a collection of one-off AI scripts.

The roadmap is directional. Each phase should produce reviewable documentation,
small implementation steps, and a clear rollback path.

## Phase 0 - Repository Foundation

Status: in progress.

-   Establish the project constitution.
-   Define AI agent operating rules.
-   Create architecture and roadmap documents.
-   Create the initial repository scaffold.
-   Add safe local defaults for editor, ignore, environment, and Makefile
    behavior.

Exit criteria:

-   The repository explains what Forge is and what it is not.
-   Empty scaffold directories have documented responsibilities.
-   Future implementation work has a clear read order.

## Phase 1 - Contracts Before Code

-   Define the task lifecycle.
-   Define the agent contract.
-   Define the provider adapter contract.
-   Define tool and workspace boundaries.
-   Add ADRs for durable architectural choices.

Exit criteria:

-   An implementation can begin without inventing core concepts in code.
-   Tests can be planned against documented contracts.

## Phase 2 - Bootstrap Automation

-   Convert known manual setup steps into repeatable scripts.
-   Add validation checks for repository and host assumptions.
-   Document rollback and recovery behavior.
-   Keep bootstrap scripts idempotent where practical.

Exit criteria:

-   A new environment can be prepared from documented steps.
-   Failed bootstrap operations are understandable and recoverable.

## Phase 3 - First Workflow Runner

-   Select or build the first workflow runner.
-   Represent task state in a reviewable format.
-   Add approval gates for high-impact operations.
-   Keep the runner replaceable.

Exit criteria:

-   A simple task can move through plan, execute, validate, and summarize.
-   Human approval points are explicit.

## Phase 4 - Human and Repository Interfaces

-   Add one human-facing interface, such as Discord or CLI.
-   Add one repository-facing interface, such as GitHub.
-   Keep interface-specific code outside Forge Core.
-   Document integration failure modes.

Exit criteria:

-   Forge can receive a task and report status through bounded interfaces.
-   Repository changes remain reviewable through Git.

## Phase 5 - Workspace Management

-   Create isolated task workspaces.
-   Automate Git worktree setup when appropriate.
-   Add cleanup and recovery workflows.
-   Track workspace assumptions in documentation.

Exit criteria:

-   Concurrent tasks can avoid stepping on each other's files.
-   Workspace cleanup is safe and inspectable.

## Phase 6 - Provider Adapters

-   Implement the first provider adapter.
-   Add additional adapters only after the contract stabilizes.
-   Normalize inputs, outputs, errors, and lifecycle events.
-   Add tests for provider contract behavior.

Exit criteria:

-   At least two providers can be swapped without changing workflow semantics.
-   Provider-specific failures are surfaced clearly.

## Phase 7 - Memory, Evaluation, and Observability

-   Add memory only after ownership, retention, and deletion rules are written.
-   Add evaluation workflows for agent output quality.
-   Add observability for tasks, tools, approvals, and failures.
-   Explore multi-repository orchestration after single-repository workflows are
    reliable.

Exit criteria:

-   Operators can understand what happened, why it happened, and how to recover.
-   Persistent data has explicit ownership and lifecycle rules.

## Long-Term Direction

Forge should outlive individual AI models and orchestration frameworks. Each
phase should make the platform more understandable, replaceable, and safe to
operate.
