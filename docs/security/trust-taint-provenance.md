# Trust, Taint, and Provenance Contracts

## Status

This document defines the chosen, runtime-neutral contract semantics adopted by
ADR-0007. The semantics are normative for future Forge implementation.
Versioned schemas, validators, policy engines, adapters, and host enforcement
are proposed and are not implemented by this documentation change.

## Contract Ownership

- **Forge core** declares contract types, invariants, versions, and validation
  rules. This does not prove that a host blocked or performed an effect.
- **Policy layer** returns allow, deny, or require-approval for a typed action.
  This does not prove that an adapter enforced the decision.
- **Runtime adapter** translates runtime events and preserves metadata. This
  does not provide operating-system or external-service isolation.
- **Host or service adapter** resolves resources and enforces the decisions it
  supports. Its assurance ends at its tested capability.
- **Audit pipeline** records minimized decision and provenance evidence. A
  record's existence does not prove its correctness.

An implementation must not collapse these responsibilities into an ambiguous
claim that "Forge enforced" an action.

## Common Envelope

Every security-relevant datum or action must carry a versioned envelope with
at least:

- a stable contract version;
- an opaque event or object identifier;
- a type and creation time;
- trust state and taint set;
- a provenance reference;
- the producing component class;
- data classification and retention hints; and
- integrity evidence when required by policy.

Identifiers and references must not embed credentials, raw sensitive content,
private filesystem locations, or deployment-specific identities. Unknown or
unparseable values fail validation rather than receiving a permissive default.

## Trust Contract

### States

- `trusted`: attested for a specific use by an authorized policy component.
- `untrusted`: known to originate outside the authority required for that use.
- `unknown`: origin, attestation, freshness, or compatibility is insufficient.

Trust is scoped. A datum trusted as operator-authored text is not automatically
trusted as permission to use credentials or publish a release.

### Invariants

1. New external, repository, tool, and model content is `untrusted` or
   `unknown` unless an explicit attestation rule applies.
2. Trust does not increase through copying, summarizing, formatting, model
   generation, or successful parsing.
3. Only an authorized policy component may issue a scoped trust attestation.
4. An attestation names its subject, permitted purpose, issuer class, policy
   version, issue time, expiry or freshness rule, and evidence reference.
5. Missing, expired, revoked, incompatible, or unverifiable attestation yields
   `unknown` at evaluation time.
6. `unknown` never aliases `trusted`.

## Taint Contract

Taint records relevant risk lineage. The initial vocabulary is intentionally
general:

- `external-input`;
- `repository-content`;
- `tool-output`;
- `model-derived`;
- `user-supplied`;
- `secret-derived`;
- `personal-data`;
- `unverified-integrity`; and
- `policy-exception`.

Implementations may add namespaced values without redefining existing ones.
Unknown taint values must be preserved when forwarding, not dropped.

### Propagation

- Derivation produces the union of all input taints plus any taint introduced
  by the transformation.
- Combining trusted and untrusted inputs does not make the result trusted.
- Parsing, escaping, validation, malware scanning, or schema conformance may
  add evidence but does not by itself remove taint or confer authority.
- Redaction can produce a less sensitive representation while provenance still
  records that the value was derived from sensitive input.
- Crossing a runtime or provider boundary preserves taint; adapters may add
  taint when fidelity or integrity is uncertain.

### Declassification

Taint may be removed only by an explicit, narrowly scoped policy decision. The
decision records the removed marker, purpose, transformation, issuer class,
evidence, policy version, and expiry where relevant. Declassification does not
grant unrelated authority and must not erase the historical provenance chain.

`secret-derived` and `personal-data` require purpose-specific policy and a sink
classification. A generic "sanitized" flag is insufficient.

## Provenance Contract

A provenance record should describe:

- source class and opaque source reference;
- acquisition time and acquiring component class;
- parent provenance references for derived data;
- ordered transformation classes and tool identity references;
- trust attestations and declassification decision references;
- content classification, redaction state, and retention class;
- integrity algorithm and digest where safe and useful; and
- contract and policy versions used for evaluation.

### Data Minimization

Provenance is metadata, not a copy of the payload. It must not contain raw
secrets, authentication material, private message bodies, private source code,
or unnecessary personal data. Prefer opaque references, bounded classifications,
and digests. A digest is integrity evidence, not proof that content is benign
or authorized.

### Chain Rules

1. Derived records reference every security-relevant parent.
2. Transformation order is append-only from the perspective of consumers.
3. Redaction and declassification add records; they do not rewrite history.
4. Truncation is explicit, bounded by policy, and leaves a continuity marker.
5. Broken, cyclic, forged, or unsupported chains are invalid for privileged
   decisions.
6. Adapters report metadata loss instead of synthesizing false provenance.

## Policy Decision Contract

A decision is one of `allow`, `deny`, or `require-approval` and includes:

- decision identifier and time;
- policy name and version;
- subject and authority reference;
- typed action and resolved resource class;
- relevant trust, taint, provenance, and approval references;
- reason code and human-readable explanation;
- expiry or one-time-use constraint; and
- enforcement requirements expected from the adapter.

A decision applies only to the exact scoped action. It cannot be replayed for a
different target, transformed request, credential, publication, or deployment.
Adapters deny unsupported enforcement requirements rather than silently
approximating them.

## Validation and Failure Semantics

Future validators must check structure, supported versions, required fields,
state transitions, provenance continuity, attestation authority, decision
scope, and freshness. Validation errors use stable reason codes and do not
include sensitive payloads.

For a privileged sink:

- malformed contract: deny;
- unsupported or downgraded version: deny;
- absent required provenance: deny;
- `unknown` trust where trust is required: deny or require fresh approval;
- stale or mismatched approval: deny; and
- adapter cannot enforce a required condition: deny.

Read-only processing may use a policy-defined quarantine path, but quarantine
must preserve taint and cannot authorize later effects.

## Illustrative Flow

```text
external datum
  -> envelope(untrusted, external-input, provenance=P1)
  -> model transformation
  -> envelope(untrusted, external-input + model-derived, provenance=P2 <- P1)
  -> typed effect request
  -> policy decision(deny | require-approval | allow)
  -> capable host adapter enforcement
  -> minimized audit evidence
```

The arrow from policy decision to host adapter is an interface boundary, not a
claim that enforcement already exists.

## Proposed Implementation Sequence

1. Publish machine-readable version 1 schemas and reason-code registry.
2. Implement pure contract validators and negative fixtures.
3. Implement policy evaluation without side effects.
4. Define adapter capability negotiation and deny-on-gap behavior.
5. Add one non-privileged reference adapter and conformance suite.
6. Add privileged adapters only with enforcement and failure-mode tests.
7. Link every "implemented" claim to test and release evidence.
