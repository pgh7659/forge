# Hermes, Discord, and Codex Reference Deployment Rules

These rules apply only to the `hermes-discord-codex` reference deployment.
They supplement the portable repository policy; they do not define Forge core
requirements.

## Selected deployment rules

- Treat OCI as this deployment's first host, not the platform identity.
- Keep Hermes profile state under `~/.hermes` and Forge operational assets under
  `/srv/forge` unless this reference deployment records a replacement decision.
- Use Discord as this deployment's operator interface. A project Forum channel
  maps to exactly one registered repository, and a Forum post maps to one work
  topic and primary Codex session.
- Post creation does not execute code. `/dev plan` is read-only; `/dev run`
  explicitly authorizes implementation within the declared task boundary.
- Keep the Hermes dashboard private through this deployment's selected network
  controls and dashboard authentication. Do not document unrestricted public
  dashboard exposure as the default.
- Hermes owns personal conversation, reminders, factual status, routing
  confirmation, and delivery of Codex questions and results. The gateway
  captures the original message before model interpretation and dispatches an
  opaque request ID and mode, never a generated summary.
- Codex is this deployment's engineering executor. It works only in a
  task-local worktree and returns reviewable Git and validation evidence.
- No two executors may own the same task branch concurrently. This reference
  deployment starts with one running Codex process globally.
- The selected host services may use systemd. Before automating a Hermes or
  Codex command, verify it against the installed version's `--help` output and
  record the observed version or commit.

## Approval boundary

Merge, deployment, migration, credential use, publication, destructive
operations, and infrastructure mutation require scoped human approval.
