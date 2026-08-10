# OCI Environment Audit

## Purpose

The repository describes a target architecture, while a real OCI host may have
been configured manually. Audit the host before automation or migration so
Forge records observed capabilities instead of assuming that upstream
documentation matches the installed versions.

The audit is read-only. It does not read credentials, `.env` files, message
bodies, session contents, or repository source files.

## Run

From the OCI operator account:

```sh
FORGE_ROOT=/srv/forge ./scripts/audit-oci-host.sh > forge-oci-audit.txt
chmod 0600 forge-oci-audit.txt
```

Store the report in the private deployment inventory or encrypted off-host
backup. Do not commit it to this public repository. Review and redact it before
sharing excerpts.

## Required Manual Inventory

The script cannot prove cloud control-plane configuration. Record these items
separately in the private inventory:

- OCI tenancy and compartment references as opaque private identifiers;
- VCN, NSG, security-list, public-ingress, and boot-volume policy;
- backup destination, encryption, retention, and last restore test;
- Discord allowlist and bot permissions without storing its token;
- Tailscale ACL ownership and Funnel-disabled evidence;
- GitHub token scope and repository allowlist;
- locations and owners of runtime data, secrets, and deployment state;
- current release commit for every deployed project.

## Acceptance

The audit is accepted when:

- installed Hermes and Codex versions are recorded;
- the installed `--help` output supports every command proposed for automation;
- profiles, services, timers, listeners, repositories, and worktrees are
  accounted for;
- public listeners and privileged credentials have explicit owners;
- dirty or unpushed worktrees are preserved;
- observed state is reconciled with `docs/architecture.md` and the roadmap; and
- no public artifact contains the private report.

## Rollback

The audit makes no host changes. Delete the local report through the operator's
approved secure-disposal process after its evidence has been recorded in the
private inventory.
