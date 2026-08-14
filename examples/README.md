# Examples

Runnable examples and reference scenarios live here.

Examples should stay small enough to inspect and reset easily.

All examples are synthetic inputs. They are not evidence of deployed
infrastructure, active registrations, configured secrets, or runtime
enforcement.

Use Python `>=3.12` to reproduce the examples from a clean checkout:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
make validate
.venv/bin/forge validate --config examples/environments/minimal.yaml
.venv/bin/forge plan --config examples/environments/noop.yaml
```

`environments/noop.yaml` is the sole built-in planning example: exact
`noop+noop` planning has no target access or mutation. `ssh+systemd` remains
schema-valid but planning-unavailable until a later reviewed real-adapter
slice. Plans are private review/audit data by default and do not prove
deployability, safety, secret absence, or real target observation.

Slice 3 implements a strict in-process controller contract, pure task
transitions, AES-256-GCM request-body storage, and a first single-node SQLite
state adapter. Its synthetic tests verify idempotency, atomic task events and
transitions, injected concurrency including N=2, one running task per
repository, exclusive ownership, and restart reconciliation from `running` to
`failed(controller_restart)`. There is intentionally no deployed or
provider-connected controller example.

The Environment schema already carries `spec.executor.maxConcurrency` as an
executor selection. Slice 3 adds no Environment field or loader-to-controller
wiring; callers inject the effective positive value, and the core supplies no
default. The first reference deployment retains rollout value 1 pending
separate executor and host acceptance; a later target of 2 requires its own
reviewed configuration. Socket, daemon, or CLI ingress; authentication and
authorization; executors; Codex or Hermes integration; workspaces or
worktrees; secret-provider key delivery; approvals and policy; apply and
doctor; host enforcement; deployment; merge; and release remain absent or
separately approval-gated.
