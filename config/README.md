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
