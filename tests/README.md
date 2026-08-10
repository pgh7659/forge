# Tests

Validation and regression checks live here.

Tests should focus first on contracts, safety rules, and repeatable workflows.

Set up the local development environment and run the complete validation flow:

```bash
make setup
make validate
```

`make validate` syntax-checks public scripts, validates JSON contracts and the
synthetic `forge.dev/v1alpha1` environment, runs the Python test suite, asserts
required public artifacts, scans source inputs for common credential patterns,
and runs a controlled regression proving scanner failures do not echo matched
values. It also runs the deterministic exact built-in `noop+noop` planning
smoke with no target access or mutation. `ssh+systemd` remains schema-valid
but planning-unavailable until a later reviewed real adapter.

For a reproducible checkout on Python `>=3.12`, run the setup above, then:

```bash
.venv/bin/forge validate --config examples/environments/minimal.yaml
.venv/bin/forge plan --config examples/environments/noop.yaml
```

The Plan output is private review/audit data by default; it does not prove
deployability, safety, secret absence, or real target observation. Apply,
doctor, controller/state, real adapters, `forge-ops`, OCI reconciliation,
merge, and deployment remain unimplemented or separately approval-gated.
