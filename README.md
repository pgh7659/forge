# Forge

Forge is being built as a personal AI Engineering Platform for coordinating
AI-assisted software engineering under one engineering model.

## What is Forge?

Forge is intended to coordinate people, AI agents, repositories, workflows,
documentation, and infrastructure while remaining independent of any single AI
provider.

The project is not a wrapper around one model. Its design center is durable
engineering practice: providers should be replaceable, work should be
reviewable, and Git should remain the source of truth.

## Philosophy

-   Documentation First
-   Git First
-   Provider Independence
-   Infrastructure as Code
-   Human in the Loop
-   Safe Automation

## Documentation

Read these documents before exploring implementation details:

-   FORGE_BOOTSTRAP.md - project constitution and enduring principles
-   AGENTS.md - operating rules for AI agents
-   docs/architecture.md - current architecture and boundaries
-   docs/roadmap.md - planned direction and milestones
-   docs/adr/ - architecture decision records

## Repository Layout

-   bootstrap/ - host and repository bootstrap assets
-   scripts/ - repeatable local automation
-   templates/ - reusable project and workflow templates
-   systemd/ - service units and timers for Linux hosts
-   config/ - non-secret configuration examples
-   tests/ - validation and regression checks
-   examples/ - runnable examples and reference scenarios
-   prompts/ - reusable agent prompts and operating playbooks
-   docs/ - architecture, roadmap, and ADRs

## Current Scope

The repository is currently a documentation-first scaffold. It does not yet
contain a runtime orchestrator, provider adapter, Discord bot, host bootstrap,
or workspace automation.

Those capabilities should be added incrementally after their contracts and
operational boundaries are documented.

## Status

Bootstrap / Genesis.

The repository contains the constitution, operating rules, initial
documentation, and project scaffold.
