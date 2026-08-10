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
deployability, safety, secret absence, or real target observation. Apply,
doctor, controller/state, real adapters, `forge-ops`, OCI reconciliation,
merge, and deployment remain unimplemented or separately approval-gated.
