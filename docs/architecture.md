# Architecture

## Purpose

Forge separates portable engineering-control contracts from the deployment
profiles that select concrete implementations. The approved target and ordered
delivery slices are in the [portable MVP design](superpowers/specs/2026-08-10-portable-forge-mvp-design.md).

## Public boundary

Forge public core owns executable contracts, adapter interfaces, conformance
tests, and portable documentation. Private deployment repositories own selected
versions, inventory, registrations, and resolved operational policy. Named
public reference deployments provide conformance evidence without becoming core
defaults.

## Layer model

```text
Configuration
  -> Forge CLI
    -> planning adapters

Versioned controller protocol
  -> in-process controller service
    -> pure task-transition rules
    -> request-cipher protocol
      -> AES-256-GCM request cipher
    -> state-ledger protocol
      -> SQLite state adapter
```

The configuration schema and `forge` CLI are the first executable slices.
`forge validate` checks YAML/JSON syntax, schema shape, and JSON-model
compatibility without mutation. Slice 2 also provides deterministic planning
only for the exact built-in `noop+noop` tuple. Its synthetic plan observes
nothing and contains no operations, so `forge plan --config
examples/environments/noop.yaml` performs no target access or mutation.
`ssh+systemd` is schema-valid but planning-unavailable until a later reviewed
real-adapter slice; no adapter alias, fallback, or provider default exists.

Validation does not verify whether an adapter pair is registered. Planning
verifies only the exact in-process registry lookup and that the selected
adapter produces a valid Plan artifact; it does not verify target reachability,
real compatibility, safety, or deployability. Neither command resolves secret
references or detects resolved secret values in arbitrary adapter
configuration. A Plan is private review/audit data by default, not evidence of
deployability, safety, secret absence, or real target observation.

Slice 3 implements the strict in-process controller contract, its pure task
transitions, and the AES-256-GCM request-body storage boundary. SQLite is the
first single-node state adapter. The controller accepts only the versioned
`submitRequest` and `getTask` data shapes at its library boundary; no transport
is connected. SQLite is an injected adapter behind the state-ledger protocol,
not a portable-core storage requirement.

The controller and SQLite suites verify idempotent ingestion, atomic task
events and transitions, configurable injected positive concurrency including
N=2, at most one running task per repository, exclusive single-controller
ownership, and restart reconciliation that changes `running` to
`failed(controller_restart)` without automatic retry. The Environment schema's
existing `spec.executor.maxConcurrency` selection is not wired into this
controller slice. Slice 3 adds no Environment field; callers inject the
effective positive value, and the core supplies no default. The first
reference deployment retains its separately approved rollout value of 1 until
executor and host acceptance; a later target of 2 requires its own reviewed
deployment configuration.

Socket, daemon, or CLI ingress; authentication and authorization; an executor;
Codex or Hermes integration; workspaces or worktrees; secret-provider key
delivery; approvals and policy; apply and doctor; host enforcement; deployment;
merge; and release remain absent or separately approval-gated. Each future
adapter must declare its capabilities and tested enforcement rather than
inheriting guarantees from the core.

## Reference deployments

The [Hermes, Discord, and Codex reference deployment](reference-deployments/hermes-discord-codex/)
records one concrete selection of gateway, assistant, executor, host-runtime,
source-control, and secret adapters. Its operations, historical decisions,
assets, and examples are deployment-specific evidence. Other deployments may
choose different implementations while satisfying the same public contracts.

## Security and approvals

The runtime-neutral [security contracts](security/trust-taint-provenance.md)
and [threat model](security/threat-model.md) govern future implementations.
Contract validation is not host enforcement. Mutation-capable operations require
the scoped human approval defined by the selected adapter and deployment.
