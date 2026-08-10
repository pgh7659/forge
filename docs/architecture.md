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
    -> provisioner
      -> controller
        -> adapters
```

The configuration schema and `forge` CLI are the first executable slice. The
first schema is `forge.dev/v1alpha1`; `forge validate` checks YAML/JSON syntax,
schema shape, and JSON-model compatibility without mutation. It does not
verify adapter existence or combinations, resolve secret references, detect
resolved secret values in arbitrary adapter configuration, or prove runtime
or deployment safety. Adapter and secret semantics remain later slices.

The provisioner, controller, and adapters are proposed components, not current
runtime capabilities. Each adapter must declare its capabilities and tested
enforcement rather than inheriting guarantees from the core.

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
