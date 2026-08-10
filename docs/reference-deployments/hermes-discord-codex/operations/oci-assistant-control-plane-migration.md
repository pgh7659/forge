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
- Discord as the personal-assistant and development-request interface;
- Tailscale-only dashboard access;
- existing runtime data, Kanban history, worktrees, and recoverable profile
  history until the new flow is accepted.

Change:

- keep the physical Hermes default profile and narrow it to the logical
  `assistant` responsibility;
- stop using Hermes Kanban and `forge-worker` for engineering;
- capture Discord source messages before model interpretation;
- dispatch `/dev plan` and `/dev run` through a version-verified Forge Codex
  adapter;
- persist branch, PR, session, validation, owner, and approval state;
- separate protected repositories, task worktrees, production releases, and
  runtime data;
- reconcile public templates with a private operations inventory.

## Stage 0 - Read-Only Audit

1. Run `../scripts/audit-oci-host.sh` as the operator account.
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

## Stage 2 - Immutable Inbox and Dispatcher Shadow Mode

Before changing assistant behavior:

1. install the private Discord channel-to-project registrations;
2. capture source messages and hashes without dispatching them;
3. implement the Forge task ledger outside Hermes Kanban;
4. validate Forum post and source-message provenance;
5. implement `/dev plan`, `/dev run`, `/dev status`, `/dev continue`,
   `/dev cancel`, and `/dev handoff` in disabled or shadow mode; and
6. test the Codex adapter against a disposable repository.

Shadow mode must prove that the executor retrieves the original message from
the inbox rather than accepting model-generated request text.

## Stage 3 - Assistant Identity

Using only version-verified Hermes commands:

1. keep the existing physical default profile and treat `assistant` as its
   logical role;
2. install the reviewed `../prompts/hermes-assistant-soul.md` content as its
   identity;
3. remove general repository, engineering Kanban, and unrestricted terminal
   tools from its enabled toolsets;
4. preserve the existing Discord allowlist and minimal bot permissions;
5. ensure only one gateway process owns the bot token;
6. start the assistant gateway under service supervision; and
7. test operator routing, project Forum mapping, post creation without
   execution, authorized and unauthorized identities, restart, and approvals.

Rollback stops the gateway, restores the backed-up identity and tool policy,
and leaves `forge-worker` stopped. Never start another profile with the same bot
token.

## Stage 4 - Codex Executor Adapter

The first adapter is disabled by default and tested against a disposable
repository.

It must:

- accept an opaque inbox request ID and independently verify `raw_request` and
  its content hash;
- enforce `/dev plan` as read-only and `/dev run` as the implementation gate;
- resolve only allowlisted repositories and refs;
- operate only in the supplied task worktree;
- use the installed Codex CLI's verified non-interactive and resume contract;
- capture machine-readable events without exposing secrets;
- produce the structured result contract;
- record `waiting_user` and `waiting_approval` without retaining a live process;
- retain failed, cancelled, or dirty workspaces;
- push only the task branch and create or update a Draft PR; and
- refuse merge, deploy, migration, publication, credential expansion, and
  destructive cleanup without fresh approval.

Do not install an always-running Codex daemon for the first slice. A bounded
process per accepted task keeps ownership and failure state easier to inspect.

## Stage 5 - Repository and Runtime Separation

For each project:

- keep a protected checkout under `/srv/forge/repos/<project>`;
- use Forge-managed worktrees below its `.worktrees/` directory;
- keep production releases outside task worktrees;
- keep databases, `.env`, generated output, and backups outside Git checkouts;
- use GitHub as the only cross-device engineering source of truth; and
- deploy only an approved commit from the protected branch.

Do not onboard a sensitive or production repository before the disposable
vertical slice passes.

## Stage 6 - Acceptance

The migration is accepted only when:

- Discord personal-assistant behavior remains available;
- a new Forum post performs no engineering action by itself;
- `/dev plan` makes no repository change;
- one `/dev run` request preserves and verifies its raw text through dispatch;
- Codex changes only its task worktree;
- a pushed branch and Draft PR allow continuation from another device;
- deterministic CI passes;
- merge and deployment remain approval-gated;
- unauthorized Discord and public dashboard access are denied; and
- backup and rollback are exercised.

After the acceptance window, archive the old Kanban state and retire the
stopped `forge-worker` profile through a separately approved cleanup. Neither is
part of the steady-state engineering path.
