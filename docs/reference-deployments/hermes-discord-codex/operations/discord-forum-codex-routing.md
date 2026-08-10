# Discord Forum and Codex Routing Contract

## Purpose

This contract defines how one Discord assistant gateway routes personal
conversation and exact engineering requests without using Hermes Kanban or a
Hermes coding profile.

Deployment-specific Discord IDs, user IDs, repository credentials, and private
message bodies belong only in the private Forge operations state.

## Channel Map

The initial logical map is:

| Discord surface | Responsibility |
| --- | --- |
| `operator` | Personal-assistant conversation and unresolved project requests |
| `forum-forge` | Forge project topics |
| `forum-worklog` | Worklog project topics |
| `forum-newsdigest` | News Digest project topics |

The private registration binds each Forum channel ID to exactly one repository,
default branch, and permission policy. A model never guesses or rewrites that
mapping.

## Post and Session Boundary

- One Forum channel represents one project.
- One Forum post represents one work topic and one primary Codex session.
- Creating a post records discussion only; it does not execute code.
- Planning, questions, implementation, and review remain in the same post.
- An independently reviewable scope creates a new post with source-message
  links.
- Discord does not support or require a nested engineering thread below the
  Forum post; the post is already the thread.

## Commands

### `/dev plan`

Start or resume Codex in planning mode. Codex may inspect the registered
repository and return questions, risks, and a proposed plan. It may not modify
files, commit, push, or create a PR.

### `/dev run`

Start implementation using the exact accepted request and conversation record.
Codex may edit its worktree, validate, commit, push its task branch, and create
or update a Draft PR.

### `/dev status`

Return observed ledger, process, session, branch, PR, and validation state. Do
not generate optimistic progress prose.

### `/dev continue`

Resume a `waiting_user` or `waiting_approval` task. The new operator reply is
captured as a separate exact message; it does not replace the initial request.
When a Codex question is pending, the trusted operator's next post reply may be
treated as `/dev continue` after the adapter verifies the task state.

### `/dev cancel`

Stop or prevent further executor work. Preserve the session, task branch, and
dirty worktree until an explicitly approved cleanup.

### `/dev handoff`

Report the pushed commit, Draft PR, validation, remaining work, and the exact
state another Codex surface needs to continue.

## Operator-Channel Routing

When a development request begins in `operator`, Hermes proposes a project and
mode but does not dispatch automatically. After confirmation it creates a post
in the selected project Forum, copies the original message without rewriting
it, includes a source link, and dispatches its immutable request identifier.

If no project can be resolved safely, Hermes asks one concise question. It does
not create a repository, choose a similar project, or broaden repository access.

## Immutable Inbox

The gateway captures source data before model interpretation:

- request identifier;
- Discord guild, channel, Forum post, and message references;
- trusted author reference;
- raw message bytes and content hash;
- registered project and requested mode;
- receive time and retention class.

Hermes calls the dispatcher with `request_id` and `mode`. The dispatcher loads
and verifies the raw message itself. A generated summary, title, tag, or status
message is never executor input.

## User-Visible State

Recommended Forum state tags are `planning`, `queued`, `running`, `waiting`,
`review`, `done`, and `cancelled`. They are a projection of the Forge task
ledger, not the source of truth.

Initial ledger states:

| State | Meaning |
| --- | --- |
| `queued` | Accepted and waiting for the single executor slot |
| `running` | A bounded Codex process is active |
| `waiting_user` | Codex asked a question; no process slot is held |
| `waiting_approval` | A privileged action awaits scoped approval |
| `review_ready` | A Draft PR and validation report are available |
| `failed` | Execution failed and recoverable state is retained |
| `cancelled` | The operator stopped further execution |
| `completed` | The accepted non-privileged scope is complete |

The ledger does not model normal input waits as a Kanban block.

## Result Delivery

Codex questions and structured results are posted back to the source Forum post.
Hermes may introduce the event, but it must not rewrite engineering content.
Project notifications remain in their post; only cross-project incidents or
explicit summaries belong in `operator`.

## Approval Boundary

Planning is read-only. An accepted run may commit, push its branch, and create a
Draft PR. Merge, deploy, migration, release, public exposure, credential or
permission changes, host configuration, and destructive cleanup always require
fresh human approval.
