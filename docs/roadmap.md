# Roadmap

The [approved portable MVP design](superpowers/specs/2026-08-10-portable-forge-mvp-design.md)
defines these ordered delivery slices. Each slice needs its own implementation
plan and reviewable commit or PR.

1. **Portable foundation — implemented:** replace deployment-specific root policy with the
   core/adapter/reference-deployment boundary and publish
   `forge.dev/v1alpha1` plus `forge validate`.
2. **Planning client — implemented:** add deterministic
   Plan artifacts, stale-plan detection, and the exact built-in `noop+noop`
   adapter. It performs no target access or mutation; `ssh+systemd` remains
   schema-valid but planning-unavailable pending a reviewed real adapter.
3. **Controller and state — implemented:** add the
   strict in-process service protocol, pure transitions, AES-256-GCM
   request-body boundary, and first single-node SQLite state adapter. Tests
   verify idempotency, atomic task events and transitions, configurable
   injected N including N=2, repository-one scheduling, exclusive ownership,
   and `running` to `failed(controller_restart)` reconciliation.
4. **Hermes ingress reference adapter — next, separately design- and
   approval-gated:** add capability probing, the pre-dispatch plugin,
   Unix-socket delivery, and fail-closed `/dev plan`.
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
part of the portable foundation. The Environment schema's existing
`spec.executor.maxConcurrency` selection is not wired into the Slice 3
controller. Slice 3 adds no Environment field; callers inject the effective
positive value, and the core supplies no default. The first reference rollout
remains 1 pending separate executor and host acceptance; a later target of 2
requires its own reviewed configuration.

Socket, daemon, or CLI ingress; authentication and authorization; executors;
Codex or Hermes integration; workspaces or worktrees; secret-provider key
delivery; approvals and policy; apply and doctor; host enforcement; private
`forge-ops`; OCI reconciliation; deployment; merge; and release remain absent
or separately approval-gated. Plans are private review/audit data by default,
and do not prove deployability, safety, secret absence, or real target
observation.
