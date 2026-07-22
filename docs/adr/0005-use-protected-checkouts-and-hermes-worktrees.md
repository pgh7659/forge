# ADR-0005: Use Protected Checkouts and Hermes-Native Git Worktrees

## Status

Accepted

## Date

2026-07-22

## Context

Forge must support repeated task execution against repositories without letting
agents casually edit the durable mirror of those repositories.

Hermes sessions operate from the current working directory, which makes
workspace boundaries important when multiple tasks or agents are active.

## Decision Drivers

- Isolation of active task work
- Safer parallel execution
- Cleaner cleanup and rollback

## Decision

Forge will keep a normal, protected checkout for each project under
`/srv/forge/repos/<project>` and use Hermes Kanban's native `worktree`
workspace mode for coding tasks. By default, Hermes creates these worktrees
under `<project>/.worktrees/<task-id>`.

Agents operate in task worktrees rather than in the protected project
checkout.

## Alternatives Considered

- Standard cloned repositories edited in place
- Per-task full repository clones
- A custom bare-repository mirror plus external worktree manager

Editing the protected checkout in place mixes stable project state with task
work. Full clones waste space. A custom bare-repository manager duplicates
Hermes' native workspace lifecycle and adds ref-management complexity before
the built-in workflow has been validated.

## Consequences

Benefits:

- explicit separation between protected checkout and active work
- safer concurrent task execution
- lower disk usage than repeated full clones
- less custom Forge automation in the first deployment

Costs:

- the protected checkout remains present and must be guarded by policy
- worktree cleanup must be cautious around uncommitted changes

This decision raises the bar for workspace tooling, but it gives Forge a safer
default operational model.
