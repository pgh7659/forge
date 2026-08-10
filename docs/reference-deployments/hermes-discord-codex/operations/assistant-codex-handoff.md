# Assistant and Codex Handoff Runbook

## Purpose

This runbook defines how the Hermes personal assistant, Forge dispatcher, OCI
Codex worker, and a direct Codex surface share engineering state without Hermes
Kanban or directory synchronization.

GitHub refs, Draft PRs, checks, and the private Forge task ledger are durable.
Model session state and dirty worktrees require explicit preservation.

## Roles

- The operator owns product direction, priorities, and privileged approvals.
- The Discord gateway captures an immutable source message before model use.
- Hermes confirms routing and delivers observed questions and results.
- Forge validates the request ID, manages state and worktrees, and invokes
  Codex.
- Codex plans or implements in the registered project boundary.
- CI verifies deterministic requirements.

## Source Boundary

Each project Forum channel maps to exactly one private project registration.
Each Forum post maps to one work topic and primary Codex session. Post creation
does not start execution.

The source record contains an opaque request ID, Discord channel/post/message
references, raw message, content hash, trusted author, project, requested mode,
and receive time. Hermes dispatches the ID, not a summary.

## Required Task Record

Each engineering task records:

- task, request, project-channel, Forum-post, and source-message identifiers;
- raw operator request and verified hash in private state;
- mode (`plan` or `run`);
- repository and resolved base ref;
- task branch and worktree;
- allowed actions and approval requirements;
- Codex session identifier when one exists;
- last pushed commit, Draft PR, validation, and ledger state; and
- any exact pending question or approval request.

Do not include private Discord bodies, credentials, private source, or personal
data in public audit records.

## `/dev plan` Preconditions

1. Resolve the project only from the registered Forum channel or confirmed
   operator-channel routing.
2. Verify the immutable source-message hash.
3. Resolve the allowlisted repository and base ref.
4. Start or resume Codex with read-only repository authority; and
5. record questions, risks, and the proposed plan without modifying files.

## `/dev run` Preconditions

1. Confirm explicit run intent in the source Forum post.
2. Resolve and record the current base commit.
3. Create a dedicated branch and Forge-managed worktree.
4. Confirm the protected checkout is clean and is not the task workspace.
5. Verify the exact source request and every accepted continuation message.
6. Record actions that still require approval.
7. Enforce a single active Codex process for the initial deployment.

Do not automate a Hermes or Codex command until the installed OCI version and
its `--help` output have been captured by the private deployment audit.

## Waiting and Resume

When Codex needs operator input, Forge records `waiting_user`, the exact
question, session ID, worktree, branch, and last event, then exits the worker
process. The task holds no executor slot.

The trusted operator's next reply in the same Forum post may act as
`/dev continue`. The gateway captures that reply as a new immutable message,
and Forge resumes the same Codex session after verifying the task state.

Privileged actions use `waiting_approval`. A prior or general approval cannot
authorize a new target or action.

## Handoff Between Environments

The current owner must:

1. run the relevant validation;
2. commit the smallest recoverable checkpoint;
3. push the task branch;
4. create or update a Draft PR;
5. record completed work, test evidence, remaining work, and issues; and
6. release ownership in the private ledger.

The next owner fetches the pushed ref, verifies the commit, creates its own
worktree, and resumes from the explicit handoff. Two executors never edit the
same branch concurrently. Unpushed work is not a cross-device handoff.

## Completion

A run is review-ready only when:

- the branch and Draft PR exist;
- declared checks pass or failures are reported accurately;
- changed files, risks, rollback, and remaining work are recorded;
- no production checkout or runtime data was modified; and
- privileged follow-up remains pending human approval.

## Failure and Recovery

- Preserve a dirty worktree; never clean it automatically.
- Record a crash or timeout as `failed`, retain its session ID, and release the
  executor slot.
- Resume only when the installed CLI supports it and the task still targets the
  same repository and branch.
- Recreate clean worktrees from GitHub and back up unpushed work before host or
  runtime maintenance.
