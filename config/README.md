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
observation. Apply, doctor, controller/state, real adapters, `forge-ops`, OCI
reconciliation, merge, and deployment remain unimplemented or separately
approval-gated.
