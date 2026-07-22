# ADR-0002: Use Host Install on OCI for the First Deployment

## Status

Accepted

## Date

2026-07-22

## Context

The first deployment target is a dedicated OCI Ubuntu ARM64 VM. Forge must
decide whether Hermes should run directly on the host or inside a container.

The first deployment also needs direct access to host-level tooling and user
credentials used by:

- Git and SSH
- GitHub CLI
- Codex CLI
- Claude Code
- Gemini CLI

## Decision Drivers

- Simplicity of first deployment
- Low friction for CLI credentials and host tooling
- Fast path to a working operator node

## Decision

Forge will install Hermes directly on the OCI host for the first deployment.

Containers remain available for future workload isolation and service
dependencies, but not as the primary Hermes runtime on day one.

## Alternatives Considered

- Run Hermes in Docker from the start
- Build a split design with Hermes in one container and task containers beside
  it

These were not chosen because they add container credential, volume, and
runtime complexity before the first deployment proves its value.

## Consequences

Benefits:

- simpler access to host-installed developer tools
- easier use of user-level auth and systemd
- fewer moving pieces during bootstrap

Costs:

- weaker isolation than a container-first design
- more care needed around host permissions and secrets

Host installation does not isolate profiles from shared Unix-user credentials
or protect the host from commands allowed to Hermes. The first deployment must
use a dedicated non-root service account, least-privilege tools, and a
non-sensitive test repository before broader access is granted.

If Forge later needs stronger runtime isolation, that should be introduced as a
separate, explicit change after the host-installed deployment is stable.
