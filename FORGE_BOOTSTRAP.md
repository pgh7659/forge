# FORGE_BOOTSTRAP.md
> Forge Project Constitution v1.0

> **Status:** Ratified
> **Audience:** Humans and AI Agents
> **Purpose:** Define the enduring principles of the Forge platform.

# 1. Purpose

Forge exists to make AI-assisted software engineering safe, repeatable, and
provider-independent.

It is not a coding assistant, chat application, or wrapper around a single LLM.
Forge is a platform project whose responsibility is to define how people, AI
agents, repositories, workflows, documentation, and decisions fit into a
repeatable development system.

Implementations will change.
Models will change.
Workflows will evolve.

The principles in this document should remain stable.

---

# 2. Mission

Forge should enable multiple AI agents to collaborate under one engineering
model.

Success is measured by:

- predictable engineering
- replaceable providers
- reproducible workflows
- documented decisions
- human ownership

The platform values consistency over novelty.

---

# 3. Vision

A repository should eventually become understandable without institutional
knowledge.

A new engineer, or a new AI agent, should be able to understand:

- why the project exists
- how decisions are made
- how work is performed
- how to contribute safely

by reading documentation before reading code.

---

# 4. Core Values

## Provider Independence

No workflow may depend on a specific model.

Providers execute work.

Forge owns orchestration.

## Human Ownership

AI proposes.

Humans approve.

Repositories belong to people.

## Documentation First

Architecture is written before it becomes tribal knowledge.

Important decisions become permanent documentation.

## Git First

Git is the source of truth for code, reviewable configuration, documentation,
and durable engineering decisions.

Runtime state, credentials, conversations, and uncommitted work are not made
safe merely by existing on the Forge host. They require an explicit owner,
retention policy, and backup or disposal rule.

Work that changes a project is not considered durable until its reviewable
result is represented in Git. Operational state that does not belong in Git
must remain reproducible or recoverable by a documented mechanism.

## Infrastructure as Code

Infrastructure should be described, reviewed, and versioned like application
code.

Manual setup may exist during discovery, but durable operations should become
repeatable automation.

## Safe Automation

Automation should make work safer, not less accountable.

High-risk operations require explicit human approval and a clear rollback path.

An agent runtime installed on a dedicated host is not a security boundary.
Filesystem access, shell access, messaging authorization, and model credentials
must each be constrained independently.

## Replaceability

Every component should assume it can be replaced tomorrow.

Interfaces are more important than implementations.

Replaceability does not justify building abstractions before the first runtime
has been operated successfully. Forge first validates native capabilities, then
abstracts only boundaries that have demonstrated a real need to change.

---

# 5. Engineering Principles

- Prefer simple systems over clever systems.
- Optimize maintainability before optimization.
- Small incremental changes beat large rewrites.
- Automation must remain explainable.
- Every change should have a rollback path.
- Architecture should minimize coupling.
- Prefer verified native capabilities over speculative custom infrastructure.
- Record version-dependent behavior before automating it.

---

# 6. AI Principles

Every AI agent is treated as an implementation, not as the platform.

Agents are expected to:

- understand context before coding
- explain decisions
- minimize unnecessary changes
- update documentation when architecture changes
- escalate uncertainty instead of guessing

---

# 7. Architectural Principles

Forge separates concerns into independent layers.

Platform Policy
-> Workflow Orchestration
-> Agent Contracts
-> Provider Adapters
-> Tools and Repositories

Each layer should own a single responsibility and remain replaceable where
practical.

---

# 8. Decision Framework

Before introducing a new capability ask:

1. Does it increase provider lock-in?
2. Can it be replaced?
3. Can it be documented?
4. Can it be tested?
5. Can it be reverted?
6. Does it improve long-term maintainability?

If the answer is mostly "no", reconsider the design.

---

# 9. Documentation Model

README explains the project.

FORGE_BOOTSTRAP defines enduring principles.

AGENTS defines operational rules.

Architecture documents the current system.

ADR records durable architectural decisions.

Roadmap describes intended direction.

No document should duplicate another's responsibility.

---

# 10. Definition of Done

A task is complete only when:

- implementation is finished
- tests pass
- documentation is updated where required
- review is possible
- rollback is possible
- human approval can be given confidently

---

# 11. Evolution Policy

Forge is expected to evolve continuously.

Implementations may change freely.

Constitutional principles should change rarely.

Any modification to these principles requires an Architecture Decision Record.

---

# 12. Non-goals

Forge is not:

- an IDE
- a chatbot
- a Claude wrapper
- a Codex wrapper
- a prompt collection
- an autonomous software company
- a promise of unattended production changes
- a substitute for backups, access control, or engineering review

Forge is infrastructure for AI engineering.

---

# 13. Closing

Technology changes quickly.

Engineering principles should not.

Forge chooses to invest in durable principles instead of temporary tools.

Every future implementation should be judged against this constitution before it
is judged by convenience or popularity.
