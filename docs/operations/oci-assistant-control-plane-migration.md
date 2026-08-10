# OCI Assistant Control-Plane Migration

## Purpose

This runbook stages the existing OCI Hermes deployment toward ADR-0008 without
changing infrastructure before observed host state is accepted. It is a
migration plan, not evidence that the host has been changed.

Do not copy commands from current upstream Hermes documentation into the host
until the installed OCI version and its `--help` output confirm them.

## Change Boundary

Keep:

- the OCI host;
- the host-installed Hermes and Codex CLI binaries until the audit shows a
  compatibility or security reason to change them;
- Discord as the assistant and operations interface;
- Tailscale-only dashboard access;
- Hermes Kanban and native task worktrees;
- existing runtime data and recoverable profile history.

Change:

- narrow the Discord-connected profile to the `assistant` responsibility;
- add an optional `ops` profile without a messaging token;
- stop using a Hermes coding personality as the primary engineer;
- dispatch accepted implementation tasks to a version-verified Codex adapter;
- persist branch, PR, session, validation, owner, and approval state;
- separate protected repositories, task worktrees, production releases, and
  runtime data;
- reconcile public templates with a private operations inventory.

## Stage 0 - Read-Only Audit

1. Run `scripts/audit-oci-host.sh` as the operator account.
2. Store the output mode `0600` in the private inventory.
3. Record cloud network, backup, GitHub scope, Discord allowlist, and Tailscale
   evidence manually.
4. Compare installed Hermes and Codex help output with every proposed adapter
   command.
5. Inventory dirty or unpushed worktrees and stop if any owner is unknown.

Exit only when the audit is reviewed and contains no unowned service, listener,
credential boundary, repository, or worktree.

## Stage 1 - Recovery Point

Obtain explicit approval, then:

1. export or back up all Hermes profiles, sessions, Kanban databases, config,
   skills, and scheduled jobs without publishing secret material;
2. preserve every dirty or unpushed worktree;
3. copy the encrypted backup off the OCI instance;
4. verify restore into a temporary location; and
5. record the old gateway service, profile, dashboard, and rollback owner.

Do not proceed when restore has not been demonstrated.

## Stage 2 - Assistant Profile

Using only version-verified Hermes commands:

1. create or migrate to the `assistant` profile;
2. install the reviewed `prompts/hermes-assistant-soul.md` content as its
   identity;
3. restrict its terminal working directory and enabled toolsets;
4. preserve the existing Discord allowlist and minimal bot permissions;
5. ensure only one gateway process owns the bot token;
6. start the assistant gateway under service supervision; and
7. test authorized, unauthorized, thread, restart, and approval behavior.

Rollback stops the assistant gateway and restores the backed-up original
gateway and profile state. Never run both profiles with the same bot token.

## Stage 3 - Operations Profile

Create `ops` only when a registered runbook needs it. It receives no Discord bot
token and no product-development responsibility. Start with read-only health,
status, incremental synchronization, and backup verification. Each mutating
runbook declares its target, authority, approval, validation, and rollback.
Install `prompts/hermes-ops-soul.md` as the reviewed identity template only
after the installed Hermes profile procedure has been verified.

## Stage 4 - Codex Executor Adapter

The first adapter is disabled by default and tested against a disposable
repository.

It must:

- accept a validated task envelope and preserve `raw_request`;
- resolve only allowlisted repositories and refs;
- operate only in the supplied task worktree;
- use the installed Codex CLI's verified non-interactive and resume contract;
- capture machine-readable events without exposing secrets;
- produce the structured result contract;
- retain blocked or dirty workspaces;
- push only the task branch and create or update a Draft PR; and
- refuse merge, deploy, migration, publication, credential expansion, and
  destructive cleanup without fresh approval.

Do not install an always-running Codex daemon for the first slice. A bounded
process per accepted task keeps ownership and failure state easier to inspect.

## Stage 5 - Repository and Runtime Separation

For each project:

- keep a protected checkout under `/srv/forge/repos/<project>`;
- use Hermes-native worktrees below its `.worktrees/` directory;
- keep production releases outside task worktrees;
- keep databases, `.env`, generated output, and backups outside Git checkouts;
- use GitHub as the only cross-device engineering source of truth; and
- deploy only an approved commit from the protected branch.

Do not onboard a sensitive or production repository before the disposable
vertical slice passes.

## Stage 6 - Acceptance

The migration is accepted only when:

- Discord status and operations behavior remains available;
- ambiguous design requests route to direct Codex;
- one implementation request preserves its raw text through dispatch;
- Codex changes only its task worktree;
- a pushed branch and Draft PR allow continuation from another device;
- deterministic CI passes;
- merge and deployment remain approval-gated;
- unauthorized Discord and public dashboard access are denied; and
- backup and rollback are exercised.
