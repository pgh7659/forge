# Roadmap

The [approved portable MVP design](superpowers/specs/2026-08-10-portable-forge-mvp-design.md)
defines these ordered delivery slices. Each slice needs its own implementation
plan and reviewable commit or PR.

1. **Portable foundation:** replace deployment-specific root policy with the
   core/adapter/reference-deployment boundary and publish
   `forge.dev/v1alpha1` plus `forge validate`.
2. **Planning client:** add target observation, deterministic plan artifacts,
   stale-plan detection, and a no-op reference adapter.
3. **Controller and state:** add the service protocol, SQLite ledger,
   encryption boundary, state transitions, and restart reconciliation.
4. **Hermes ingress reference adapter:** add capability probing, the
   pre-dispatch plugin, Unix-socket delivery, and fail-closed `/dev plan`.
5. **Codex plan reference adapter:** add read-only execution, structured
   events, suspension, resume, and no-write validation.
6. **Ubuntu systemd provisioner:** add Ansible installation, service units,
   backup, rollback, and `forge doctor` checks.
7. **Private deployment configuration:** create `pgh7659/forge-ops`, pin a
   compatible Forge release, and describe `personal-primary` without applying
   it.
8. **OCI reconciliation:** after separate operator approval, compare the
   desired private configuration with the existing host, apply it, and run the
   reference acceptance suite.

`forge-ops` follows the published configuration contract; it is not created as
part of the portable foundation. OCI reconciliation is last and remains a
separately approved deployment action.
