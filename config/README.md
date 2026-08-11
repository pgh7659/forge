# Config

Non-secret configuration examples live here.

Secrets belong in local environment files or external secret storage, never in
Git.

This public repository must contain reusable templates only. Deployment audit
reports, repository registrations, host identifiers, profile overrides, and
accepted version locks belong in the private operations inventory. Tokens,
private keys, message contents, model auth, and raw personal or company data do
not belong in either repository.

Real environment configuration belongs in a private deployment repository.
The current validator checks YAML/JSON syntax, schema shape, and JSON-model
compatibility. It does not verify adapter existence or combinations, define
secret-reference semantics, or inspect arbitrary adapter configuration for
resolved secret values. Passing validation is therefore not evidence that a
configuration is safe or compatible with a deployment.

The only built-in planning registration is the exact `noop+noop` pair.
`ssh+systemd` is schema-valid but planning-unavailable until a later reviewed
adapter slice. `forge plan --config examples/environments/noop.yaml` makes no
target access or mutation, and its Plan is private review/audit data by default
rather than proof of deployability, safety, secret absence, or real target
observation.

Slice 3 adds a strict in-process controller contract, pure task transitions,
an AES-256-GCM request-body storage boundary, and a first single-node SQLite
state adapter. Tests verify idempotency, atomic task events and transitions,
configurable injected concurrency including N=2, one running task per
repository, exclusive ownership, and restart reconciliation from `running` to
`failed(controller_restart)`.

The Environment schema already carries `spec.executor.maxConcurrency` as an
executor selection. Slice 3 adds no Environment field and does not wire
Environment loading into the controller; callers inject the required positive
effective value, for which the core supplies no default. The first reference
deployment remains at its separately approved rollout value of 1 pending
executor and host acceptance, and any later target of 2 requires a separately
reviewed configuration change. Socket, daemon, or CLI ingress; authentication
and authorization; executors; Codex or Hermes integration; workspaces or
worktrees; secret-provider key delivery; approvals and policy; apply and
doctor; host enforcement; deployment; merge; and release remain absent or
separately approval-gated.
