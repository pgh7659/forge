# ADR-0007: Adopt Runtime-Neutral Security Contracts

## Status

Accepted

## Date

2026-07-26

## Context

Forge needs a reusable way to describe security decisions across agent
runtimes, model providers, tools, repositories, and hosts. Prompt wording and
runtime-specific configuration alone cannot provide a stable platform
boundary. They also make it easy to confuse a declared policy with enforcement
performed by an operating system or external service.

Forge is still in its documentation and contract phase. This decision defines
the durable contract shape before schemas, validators, policy evaluation, or
runtime adapters are implemented.

## Decision Drivers

- Keep Forge independent from any single runtime or provider.
- Preserve the origin and handling history of security-relevant data.
- Prevent untrusted data from silently becoming trusted instructions.
- Make privileged sinks deny by default when evidence is absent or invalid.
- State exactly which layer declares, validates, decides, and enforces.
- Keep public artifacts free of secrets and deployment-specific internals.

## Decision

Forge adopts runtime-neutral contracts for:

1. **Trust**: an explicit label describing how a principal or datum may be used,
   never an inference from presentation, location, or model confidence.
2. **Taint**: a monotonic set of risk markers carried through derivations,
   combinations, and tool boundaries unless an explicit policy authorizes a
   narrowly scoped declassification.
3. **Provenance**: a structured, redacted record of origin, transformations,
   policy decisions, and integrity evidence without embedding secret or raw
   sensitive values.
4. **Policy decisions**: allow, deny, or require-approval results tied to a
   named action, subject, resource class, evidence, policy version, and reason.
5. **Sinks**: typed security-relevant effects such as command execution,
   filesystem writes, network access, credential use, publication, deployment,
   or destructive operations.

The normative documentation is the
[security contract](../security/trust-taint-provenance.md).
The threat boundaries and abuse cases are documented in
[`docs/security/threat-model.md`](../security/threat-model.md).

Forge core will own generalized contract definitions and validation rules. A
policy layer will decide whether a typed action is allowed. Runtime adapters
will map runtime events into these contracts. Host adapters and external
services will perform actual enforcement where the platform can support it.

A valid contract or an `allow` decision is not evidence that enforcement
occurred. Enforcement claims require adapter-specific, tested evidence.
Unknown, missing, stale, malformed, or incompatible security metadata must not
be interpreted as trusted or allowed at a privileged sink.

### Decision State

- **Chosen and documented now:** the contract vocabulary, invariants, ownership
  boundaries, threat model, and fail-closed interpretation.
- **Proposed next:** versioned schemas, validators, policy evaluation, adapter
  interfaces, conformance fixtures, and red-team tests.
- **Not implemented by this ADR:** runtime interception, operating-system
  sandboxing, network controls, credential brokerage, or host enforcement.

## Alternatives Considered

### Runtime-specific policy only

Rejected because it couples Forge's security model to one implementation and
cannot preserve a stable contract across replacement runtimes.

### Prompt instructions as the primary control

Rejected because prompts guide behavior but do not create an authorization or
host-enforcement boundary.

### Binary trusted/untrusted flag without provenance

Rejected because it loses transformation history, cannot represent unknown
state safely, and encourages unsafe trust upgrades.

### Build a complete policy engine before defining contracts

Rejected because implementation would harden accidental assumptions before
the portable boundary is reviewable.

## Consequences

Benefits:

- security metadata can cross runtime and provider boundaries consistently;
- policy and enforcement responsibilities are reviewable;
- unsafe trust upgrades and missing provenance can be rejected explicitly; and
- future adapters can be tested against shared conformance cases.

Costs:

- adapters must preserve and validate metadata instead of passing opaque text;
- provenance must balance auditability with data minimization;
- contract versions and compatibility require lifecycle management; and
- controls remain documentary until validators and enforcing adapters exist.

Rollback consists of superseding this ADR and its normative contracts with a
new ADR. Existing documents must not be relabeled as implemented enforcement
without linked test evidence.
