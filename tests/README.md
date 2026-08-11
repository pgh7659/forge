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
but planning-unavailable until a later reviewed real adapter. The test suite
also exercises the strict in-process controller contract, pure task
transitions, AES-256-GCM request-body storage boundary, and first single-node
SQLite state adapter.

Controller coverage verifies idempotency, atomic task events and transitions,
injected positive concurrency including N=2, one running task per repository,
exclusive ownership, and restart reconciliation from `running` to
`failed(controller_restart)`. `tests/wheel_controller_smoke.py` separately
loads both schemas from an installed wheel, performs an authenticated-encryption
round trip, and opens and closes only a synthetic temporary SQLite database.
It makes no provider or network call.

For a reproducible checkout on Python `>=3.12`, run the setup above, then:

```bash
.venv/bin/forge validate --config examples/environments/minimal.yaml
.venv/bin/forge plan --config examples/environments/noop.yaml
```

The Plan output is private review/audit data by default; it does not prove
deployability, safety, secret absence, or real target observation. The
Environment schema's existing `spec.executor.maxConcurrency` selection is not
wired into the Slice 3 controller. Slice 3 adds no Environment field; callers
inject the effective positive value, and the core supplies no default.
Reference rollout remains 1 pending separate executor and host acceptance; a
later target of 2 requires reviewed deployment configuration.

Socket, daemon, or CLI ingress; authentication and authorization; executors;
Codex or Hermes integration; workspaces or worktrees; secret-provider key
delivery; approvals and policy; apply and doctor; host enforcement; deployment;
merge; and release remain absent or separately approval-gated.
