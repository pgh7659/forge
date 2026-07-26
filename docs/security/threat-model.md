# Forge Threat Model

## Status and Scope

This document is the chosen threat model for Forge's reusable security
contracts. It documents design obligations; it does not claim that runtime or
host controls are implemented.

The model covers data and actions moving among operators, agents, models,
runtimes, tools, repositories, external services, and host adapters. It is
runtime-neutral. Deployment-specific controls may strengthen this baseline but
must not weaken its fail-closed semantics.

## Security Objectives

Forge should:

- preserve explicit trust, taint, and provenance across boundaries;
- prevent data from being interpreted as authority merely because an agent or
  trusted workflow repeated it;
- require policy decisions before security-relevant effects;
- minimize secrets and sensitive content in logs and durable metadata;
- keep high-impact actions attributable and reviewable; and
- distinguish contract validation from real enforcement.

## Protected Assets

- source code, review history, and repository integrity;
- credentials, tokens, signing material, and delegated authority;
- operator identity, intent, approvals, and private data;
- host filesystem, processes, services, and network position;
- workflow state, artifacts, logs, provenance, and backups;
- policy definitions, contract versions, and validation evidence; and
- release, publication, deployment, and destructive capabilities.

## Actors and Trust Assumptions

### Human operator

The authenticated operator can express intent and grant scoped approval. An
operator message is not blanket authorization to disclose secrets, escalate
privilege, deploy, publish, or destroy data. Identity and approval freshness
must be verified by the enforcing environment.

### Agent and model

Agents and models are fallible processors, not trusted principals and not
security boundaries. Their output begins tainted as model-derived. Confidence,
helpful tone, or repeated agreement does not upgrade trust.

### Runtime, tool, and provider

A runtime or provider may transport requests and results, but its presence does
not prove policy compliance. Runtime adapters must preserve contract metadata;
host adapters must enforce decisions using capabilities actually available to
them.

### External content

Repository files, issues, pull requests, chat messages, websites, downloads,
tool output, and generated artifacts may be adversarial. They are data even
when they contain imperative language.

## Trust Boundaries

1. operator or external source to interface;
2. interface to runtime and model context;
3. model output to tool request;
4. runtime to tool, provider, or host adapter;
5. repository or downloaded content to parser and workflow;
6. policy decision to security-relevant sink;
7. runtime state to logs, artifacts, backups, or publication; and
8. one runtime or provider adapter to another.

Every crossing must preserve source identity by reference, taint, contract
version, and relevant decision evidence. Missing metadata is `unknown`, not
trusted.

## Threats and Required Responses

### Prompt injection and confused-deputy use

A document may ask an agent to ignore policy, or a low-authority source may
trigger a privileged tool. Keep the content as untrusted data. Bind authority
to the subject, action, resolved resource, and fresh approval.

### Taint laundering and provenance loss

A model may paraphrase untrusted instructions, or content may be copied between
tools without its origin. Union taint through transformations; sanitization
does not imply trust. Reject privileged use when required provenance is absent
or invalid.

### Approval replay and contract downgrade

A prior approval may be reused for a different action, or an adapter may emit
an older, weaker contract. Scope and expire approvals. Validate supported
versions and fail closed on incompatible semantics.

### Secret disclosure and audit leakage

Sensitive values may enter model context, logs, or provenance. Minimize and
redact data, use indirect references, deny unauthorized sinks, and record
classifications or digests rather than sensitive values.

### Compromised tools and forged metadata

A tool may return malicious output, or untrusted input may claim a trusted
label. Mark tool output tainted and verify integrity evidence where policy
requires it. Only authorized policy components may attest or declassify
metadata.

### Resource confusion and network exfiltration

A safe-looking identifier may resolve to another target, or data may be sent to
an unapproved endpoint. Canonicalize resources at the enforcing boundary and
bind decisions to resolved targets. Require typed network-sink policy and
host-level destination controls.

### Unauthorized publication and destructive action

Draft output may be published as final, or cleanup may remove unreviewed work.
Separate generation from publication. Require scoped authority, bounded
targets, verified preconditions, and rollback evidence.

## Security-Relevant Sinks

At minimum, policy must type and evaluate:

- command or code execution;
- filesystem reads, writes, permission changes, and deletion;
- network requests and external data transfer;
- credential, key, token, or delegated identity use;
- messages, comments, commits, pushes, and publication;
- infrastructure, deployment, release, and service changes;
- changes to policy, authentication, or audit records; and
- log, artifact, backup, and memory persistence.

Privileged sinks default to deny when a required contract, policy version,
provenance record, or approval is missing, malformed, stale, or incompatible.
The host adapter must separately prove whether it can enforce the decision.

## Out of Scope for the Documentation Baseline

This document does not provide:

- hostile-code containment;
- operating-system, container, or network isolation;
- identity-provider assurance;
- secure credential storage;
- supply-chain verification; or
- incident monitoring and response automation.

Those controls belong to implementation and deployment work. A future claim
that one is implemented must identify its owner, enforcement point, tests,
failure mode, and residual risk.

## Validation Plan

Proposed implementation work should add:

- schema-valid and schema-invalid fixtures;
- trust-upgrade and taint-laundering negative tests;
- provenance truncation, redaction, and chain-integrity tests;
- approval scope, freshness, replay, and revocation tests;
- adapter contract-downgrade and metadata-loss tests;
- deny-by-default sink tests; and
- public-artifact hygiene scans.

Until that evidence exists, only the threat model and contract design are
implemented as documentation.
