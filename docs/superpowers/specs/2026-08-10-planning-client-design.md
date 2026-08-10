# Planning Client Design

## Status and scope

Approved Slice 2 design for one implementation plan. This slice adds an
offline-capable planning client, deterministic plan artifacts, stale-plan
detection, and one non-privileged reference adapter. It extends the portable
foundation and deliberately tightens its pre-release compatibility contract:
`forge validate` now rejects values that are valid JSON-model values but are
outside RFC 8785/I-JSON's interoperable numeric domain. These failures remain
owned validation issues with stable pointers rather than serializer errors.

The only built-in planning adapter registration is `noop+noop`. It observes
nothing and proposes no operations. Any other adapter pair may be supplied by
an explicit in-process injection in a future integration or test, but this
slice has no discovery, loading, or built-in registration for it.

This is a portable core contract. It makes no SSH, systemd, OCI, Hermes, Codex,
or provider assumption.

## Goals

- Add `forge plan --config PATH`, which validates the environment before any
  planning-adapter lookup or observation.
- Publish a public `forge.dev/v1alpha1` `Plan` JSON artifact contract with a
  stable, content-derived ID. Individual artifacts are private review/audit
  data by default, not automatically publish-safe evidence.
- Bind every plan to exactly one environment digest, planning-adapter tuple, and
  observation digest, then provide a pure stale predicate over those values.
- Provide a no-op adapter that is safe to run without a target, credentials,
  subprocesses, network access, or target filesystem access.
- Preserve the foundation exit-code contract and make planning unavailable
  explicit rather than silently choosing another adapter.

## Non-goals and explicit deferrals

This slice does not implement SSH, systemd, OCI, Hermes, Codex, `forge apply`,
`forge doctor`, the controller, SQLite, secrets, plugin discovery, capability
probing, provisioning, target mutation, or an adapter registry backed by entry
points, files, or a network service. It also does not add private deployment
configuration or interpret arbitrary adapter configuration as secret-safe.

`Plan` is an output contract only in this slice. No command consumes a plan to
perform an effect. Apply-time approval, target re-observation, capability
enforcement, and operation execution are later slices.

## Public interfaces

### Configuration and adapter resolution

`forge plan --config PATH` uses the same loader and validator as `forge
validate`. A valid environment provides these two exact strings:

```text
connectionAdapter = environment.spec.target.connectionAdapter
runtimeAdapter    = environment.spec.target.runtimeAdapter
planningAdapterKey = connectionAdapter + "+" + runtimeAdapter
```

No normalization, aliasing, guessed pair, fallback, or compatibility search is
permitted. For example, `noop` and `noop` resolve only to `noop+noop`; `ssh`
and `systemd` resolve only to `ssh+systemd`. A registry miss is planning
unavailable, even if another injected adapter could have produced a plan.

The planning client receives its registry as an injected mapping from exact
`(connectionAdapter, runtimeAdapter)` tuple to `PlanningAdapter`. The CLI
composition registers exactly this mapping:

```text
("noop", "noop") -> NoopPlanningAdapter
```

The injection point makes the boundary testable and replaceable without
inventing plugin discovery. Registry construction rejects duplicate
registrations; the CLI must not let an injected adapter override the built-in
pair.

The adapter contract is deliberately narrow:

```text
observe(validated_environment) -> Observation
plan(validated_environment, observation) -> sequence[Operation]
```

Core validates that returned values are JSON-model-compatible, materializes
the artifact, validates it against the packaged plan schema, and computes the
ID. An adapter does not format CLI output, select a different adapter, access
the complete artifact after its ID is assigned, or decide whether a plan is
stale.

### `noop+noop` reference adapter

`NoopPlanningAdapter` is the sole built-in implementation. Its `observe`
method returns the canonical empty observation document `{}`. Its `plan`
method returns `[]`.

It must not make network requests; launch subprocesses; read, write, stat, or
enumerate a target filesystem; resolve credentials; use target connection
configuration; or mutate any local or target state. It consumes only the
validated environment identity needed by the common interface and does not
emit configuration data. Its behavior is entirely in-memory and deterministic.

The exact SHA-256 digest of its observation document is:

```text
sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a
```

That value is derived from the two UTF-8 bytes `{}` under the canonicalization
rule below; implementations compute it rather than treat a fixture literal as
an authority.

### Plan artifact

The public artifact has `apiVersion: "forge.dev/v1alpha1"` and `kind: "Plan"`.
Its complete logical shape is:

```json
{
  "apiVersion": "forge.dev/v1alpha1",
  "kind": "Plan",
  "metadata": {
    "id": "sha256:<64 lowercase hexadecimal characters>"
  },
  "spec": {
    "environment": {
      "name": "<validated metadata.name>",
      "configDigest": "sha256:<64 lowercase hexadecimal characters>"
    },
    "planningAdapter": {
      "contractVersion": "forge.dev/planning/v1alpha1",
      "connectionAdapter": "<exact connectionAdapter>",
      "runtimeAdapter": "<exact runtimeAdapter>"
    },
    "observation": {
      "document": {},
      "digest": "sha256:<64 lowercase hexadecimal characters>"
    },
    "operations": []
  }
}
```

`configDigest` is the validated-environment digest rendered with a `sha256:`
prefix. Slice 2 migrates that digest to the same RFC 8785 canonicalization used
by plan artifacts; this is an intentional pre-release contract correction.
`observation.digest` is the SHA-256 digest of the canonical JSON bytes of
`observation.document`. `contractVersion` binds the artifact to the exact
planning and operation semantics. `operations` contains zero or more ordered
operation records. The initial no-op plan always contains `[]`.

An operation record is a strict object with `id`, `action`, `resource`, and
`details`. `id` matches `op-` followed by a positive decimal integer and is
unique within one plan. `action` is one of `create`, `update`, `replace`, or
`delete`. `resource` is a strict object containing non-empty `kind` and `id`
strings. `details` is a JSON object containing an adapter-produced,
data-minimized explanation of the proposed change. No operation has a
timestamp, host path, credential, raw secret, or complete environment document.

The packaged schema lives at
`src/forge/resources/schemas/plan-v1alpha1.schema.json`. It uses JSON Schema
Draft 2020-12, requires every field shown above, and sets
`additionalProperties: false` on every Forge-owned object. It enforces the
API version, kind, SHA-256 representation, adapter-key syntax, operation ID
and action, and JSON-object observation/details boundaries. The core separately
rejects non-JSON values and recursive values before schema validation, and
rejects duplicate operation IDs after schema validation. Adapter-owned
observation and detail members are
intentionally data fields rather than unvalidated Forge-owned keys; their
semantic schemas are a later adapter-contract concern.

The two structured adapter fields use the same adapter-identifier pattern as
the Environment schema. The schema does not infer whether their exact tuple is
registered. Human-readable errors may display the pair as `connection+runtime`,
but that string is not the machine identity stored in the Plan.

The artifact intentionally contains only the environment name and digest, not
the original environment document, its `spec`, `target.config`, connection
data, resolved secrets, absolute paths, or other full configuration. Adapters
must likewise minimize observations and operation details; a digest proves
byte identity, not safety or authorization. Plan instances must not be emitted
to routine logs or published by default: environment names, observations, and
even digests may reveal operational metadata or act as comparison oracles for
low-entropy secret-bearing inputs.

## Canonicalization and identity

Canonical JSON is the UTF-8 byte representation defined by RFC 8785, JSON
Canonicalization Scheme (JCS). The Python implementation uses the dependency
`rfc8785>=0.1.4,<0.2` and its byte-producing API:

```python
rfc8785.dumps(value)
```

Inputs must be JSON-model- and JCS-compatible before serialization. This
excludes non-finite numbers, integers outside the I-JSON interoperable range,
non-string object keys, recursive values, dates, bytes, invalid Unicode, and
implementation-specific objects. Compatibility failures are owned validation
errors, not raw dependency exceptions. No byte-order mark, pretty printing,
timestamp, random nonce, process value, current directory, or path-dependent
field is included. Conformance tests cover numeric forms, Unicode, nested
objects, and member ordering so another language can reproduce the bytes.

The plan preimage is the full artifact above with `metadata.id` omitted and
with no replacement placeholder. Its ID is `sha256:` followed by the lowercase
SHA-256 hexadecimal digest of the canonical preimage bytes. Core then inserts
that ID and serializes the resulting artifact canonically. Therefore equal
validated configuration, exact adapter tuple, observation document, and ordered
operations produce byte-identical artifact bytes and the same plan ID.

The command writes exactly those final canonical artifact bytes followed by one
ASCII newline to stdout, with no prefix, pretty-printing, or diagnostic text.
The newline is CLI framing and is not part of the artifact or ID preimage. It
writes nothing to stderr on success.

## Command behavior and errors

The command surface is:

```text
forge plan --config PATH
```

The sequence is fixed:

1. Parse command-line arguments.
2. Read and validate the YAML/JSON environment using the existing foundation
   behavior.
3. Derive the exact adapter tuple from the validated target selection.
4. Resolve that exact tuple from the injected registry.
5. Observe, produce ordered operations, validate the finished artifact, and
   emit its canonical JSON bytes.

No step after validation reparses the configuration, and no adapter is chosen
before successful validation. `forge plan` must not treat a valid configuration
as evidence that the corresponding pair is installed, compatible, reachable,
or safe.

Exit codes remain:

| Code | Condition | stdout | stderr |
| --- | --- | --- | --- |
| 0 | Valid configuration and a successful plan | Canonical Plan bytes only | Empty |
| 2 | Command-line usage error | Empty | argparse usage/error |
| 3 | Configuration file read, decode, or YAML/JSON parse error | Empty | Existing `READ_ERROR` form |
| 4 | JSON-model or environment-schema validation error | Empty | Existing `INVALID` form |
| 5 | Exact adapter key is absent, or the selected adapter cannot plan | Empty | `PLAN_UNAVAILABLE <key>: <non-sensitive reason>` |

`PlanningUnavailable` is the only expected adapter failure exposed by this
slice. It includes a stable non-sensitive reason such as `adapter not
registered` or `observation unavailable`; it must not echo target connection
settings, environment contents, exception tracebacks, credentials, or raw tool
output. A selected adapter result that cannot produce a JSON-compatible,
schema-valid artifact is rejected as `PLAN_UNAVAILABLE <key>: invalid adapter
result` with no partial artifact. An unexpected programming error is not
translated into a successful or fallback plan. Tests call the CLI entry point
directly and must confirm that expected error paths do not write an artifact.

## Plan verification and stale-plan contract

Core first exposes `verify_plan(document) -> VerifiedPlan`. Verification is
fail-closed and ordered: validate the strict Plan schema; recompute and compare
the observation digest; remove only `/metadata/id`, recompute and compare the
plan ID; and reject an unsupported planning contract version. Unknown fields,
malformed or mismatched digests, and tampered IDs are invalid plans. They are
never represented as a safely current boolean result.

Core then exposes a pure predicate equivalent to:

```text
is_stale(verified_plan, current_basis) -> bool
```

`current_basis` contains the current environment name and digest, structured
adapter tuple, planning contract version, observation document and digest, and
ordered typed operations. The predicate materializes the candidate Plan
preimage, computes its ID, and compares that ID with the verified stored plan
ID. It returns `false` only for an identical full planning basis. A change to
any identity-bearing field, operation value, or operation order returns
`true`. The predicate performs no I/O, parsing, registry access, clock access,
or mutation and makes no approval decision.

Consumers must reject stale plans; they may not patch the stored artifact or
reuse its ID with current values. A future apply flow must verify the plan,
validate the current configuration, resolve the exact current adapter tuple,
obtain a fresh observation, reproduce the current planning basis with the same
contract version, and then use this predicate before considering approval or
effects.

## Security and trust boundaries

Configuration, observations, and adapter output are data, not authority. This
slice creates no policy decision and authorizes no effect. The `noop+noop`
adapter is intentionally non-privileged; a plan emitted by it is evidence only
of canonical input handling, not of target state or host enforcement.

The planning-client boundary preserves the repository security contracts by
failing closed on an unavailable exact adapter and by retaining only minimized,
serializable observation and operation data. It never upgrades trust because
data parsed, hashed, or successfully planned. Future adapters must carry the
appropriate trust, taint, and provenance envelope semantics before privileged
use; this slice neither implements nor claims that enforcement.

## Validation strategy

The implementation plan must add focused tests for:

- `forge plan` success with a valid `noop+noop` environment, stdout equal to
  the exact canonical artifact bytes, and empty stderr;
- validation precedence: malformed, unreadable, and schema-invalid
  configuration return 3 or 4 before adapter lookup or invocation;
- missing `ssh+systemd` (and any other unregistered exact pair) returns 5,
  emits no stdout, and never falls back to `noop+noop`;
- a test-injected unavailable adapter returning 5 with a redacted reason;
- the no-op adapter returning `{}` and `[]` without network, subprocess,
  target filesystem, or mutation calls;
- plan-schema positive and negative cases, including unknown Forge-owned
  fields, malformed digests, duplicate operation IDs, invalid actions, and
  non-JSON adapter output;
- configuration validation rejecting out-of-I-JSON-range integers with an
  owned pointer-bearing validation issue, while preserving existing 2/3/4 CLI
  error behavior;
- adapter-produced observation or details containing a JSON-model-valid but
  JCS-incompatible integer returning the redacted
  `PLAN_UNAVAILABLE <key>: invalid adapter result` form without a traceback;
- canonical equivalence across mapping order, including byte-identical output,
  observation digest, and plan ID;
- RFC 8785 conformance vectors covering `1` versus `1.0`, exponent forms,
  interoperable integer limits, Unicode, nested maps, and key ordering;
- ID verification by removing `metadata.id`, canonicalizing the preimage, and
  recomputing SHA-256; and
- verification rejecting malformed schema, observation-digest mismatch,
  unsupported contract version, and plan-ID mismatch; and
- the stale predicate accepting an identical complete basis and rejecting
  one-at-a-time changes to environment identity, either adapter member,
  planning version, observation, operation content, and operation order.

Existing `forge validate` tests remain unchanged except for shared helpers.
The full Python test suite and packaged-wheel smoke test must confirm that the
new schema is included in the distribution and the console command preserves
the exit-code and stream-separation contract.

## Rollback and delivery boundary

This slice makes no target, repository, service, credential, or infrastructure
mutation, so operational rollback is not required. Rolling back the release
means reverting the focused planning-client commit or reinstalling the prior
package; generated plan files are ordinary caller-owned output and can be
discarded. No state migration, host cleanup, or adapter teardown is involved.

The implementation is complete when the packaged CLI, injected adapter
boundary, strict schema, deterministic artifact creation, stale predicate, and
no-op conformance tests are present in one reviewable change. Adding a real
host adapter, an executor, application of operations, or a controller is a
separate reviewed slice.
