# Assistant and Codex Handoff Runbook

## Purpose

This runbook defines how the Hermes assistant, an OCI Codex worker, and direct
Codex work on another device share engineering state without synchronizing
directories.

GitHub refs, Draft PRs, checks, and task comments are durable. Model session
state and dirty worktrees are not.

## Roles

- The operator and direct Codex decide product direction and architecture.
- Hermes records the raw request, reports observed status, routes approvals,
  and dispatches only classified work.
- Codex implements an accepted task in a task-local worktree.
- CI verifies deterministic requirements.
- The operator approves merge, deployment, migration, and destructive actions.

## Required Task Record

Each engineering task records:

- task and source-thread identifiers;
- raw operator request;
- classification (`status`, `ops`, `design`, `implement`, or `privileged`);
- repository and resolved base ref;
- task branch and workspace kind;
- acceptance criteria and validation commands;
- allowed actions and approval requirements;
- executor owner (`local`, `oci`, or `cloud`);
- Codex session identifier when one exists;
- last pushed commit, Draft PR, status, and blockers.

Do not include message bodies, credentials, private source, or personal data in
public audit records. Store deployment-specific task state in the private
operations inventory.

## Dispatch Preconditions

Before an implementation task starts:

1. Resolve the repository from an allowlist.
2. Fetch the declared base ref and record its commit.
3. Create a dedicated branch and Hermes-native `worktree` workspace.
4. Confirm that the protected checkout is clean and is not the task workspace.
5. Preserve the raw request in the task envelope.
6. Resolve ambiguous requirements through direct Codex before execution.
7. Record actions that require approval.

Do not automate a Hermes or Codex CLI command until the installed OCI version
and its `--help` output have been captured by the private deployment audit.

## Handoff Between Environments

The current owner must:

1. run the relevant validation;
2. commit the smallest recoverable checkpoint;
3. push the task branch;
4. create or update a Draft PR;
5. record completed work, test evidence, remaining work, and blockers;
6. release ownership in the task record.

The next owner fetches the pushed ref, verifies the recorded commit, creates its
own worktree, and then resumes. Two executors must not edit the same branch at
the same time.

Incomplete commits are acceptable on a task branch when the PR will be squash
merged. Unpushed work is not a valid handoff.

## Completion

An implementation task is complete only when:

- the branch and Draft PR exist;
- declared checks pass or failures are reported accurately;
- changed files, risks, rollback, and remaining work are recorded;
- no production checkout or runtime data was modified; and
- privileged follow-up actions remain pending human approval.

## Failure and Recovery

- Preserve a dirty worktree; never clean it automatically.
- Mark a crashed or timed-out executor as blocked and retain its session ID.
- Resume the same Codex session only when the installed CLI supports it and the
  task still targets the same repository and branch.
- Recreate clean worktrees from GitHub. Back up unpushed work before host or
  runtime maintenance.
