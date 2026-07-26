# Security Policy

## Project Maturity

Forge is currently in its documentation and contract phase. The repository
contains architectural choices and proposed controls, but it does not yet ship
a hardened runtime or claim to enforce host isolation.

The security contracts adopted by
[ADR-0007](docs/adr/0007-adopt-runtime-neutral-security-contracts.md) are the
chosen design. Their schemas, validators, policy engine, runtime adapters, and
host enforcement are proposed work unless a later document links to tested
implementation evidence.

## Supported Versions

Forge has not published a supported release. Security fixes are made on the
default branch while the project is pre-release.

| Version | Supported |
| --- | --- |
| Default branch | Yes, best effort |
| Tagged releases | None published |

## Reporting a Vulnerability

Do not open a public issue for a suspected vulnerability or include secrets,
private repository content, exploit details, or personal data in a public
thread.

Use the repository's **Security** tab to submit a private vulnerability report
through GitHub's private vulnerability reporting flow. If that flow is not
available, open a minimal public issue that asks the maintainer to provide a
private reporting channel; do not disclose the vulnerability itself.

A useful private report includes:

- the affected document, contract, or future implementation surface;
- the expected and observed behavior;
- reproducible steps using non-sensitive test data;
- the likely impact and preconditions; and
- a safe remediation idea, if known.

Maintainers should acknowledge a report before discussing disclosure timing.
No response-time or remediation-time service level is promised during the
pre-release phase.

## Security Scope

Security-sensitive surfaces include:

- trust, taint, provenance, policy, and approval contracts;
- runtime and provider adapters;
- command, filesystem, network, credential, messaging, and deployment sinks;
- logs, artifacts, task metadata, backups, and review output; and
- documentation that could cause an operator to overestimate enforcement.

See the [threat model](docs/security/threat-model.md) and the
[security contracts](docs/security/trust-taint-provenance.md).

## Deployment Responsibility

Forge core is intended to declare and validate runtime-neutral contracts. A
host or runtime adapter is responsible for translating an allowed action into
real enforcement. Contract validation is not a sandbox, an authorization
boundary, or proof that an operating system, network, credential broker, or
external service enforced the decision.

Operators remain responsible for least privilege, secret management, network
boundaries, backups, monitoring, and tested recovery. Profiles, branches, and
Git worktrees improve workflow isolation but do not contain hostile code.
