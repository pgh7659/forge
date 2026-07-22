# ADR-0004: Use Tailscale for Private Dashboard Access

## Status

Accepted

## Date

2026-07-22

## Context

Hermes dashboard can view and modify sensitive state, including agent control
surfaces and secret-bearing configuration. It must not be exposed directly to
the public internet.

Forge needs a private and simple remote access path that works across desktop
and mobile devices.

## Decision Drivers

- Avoid public dashboard exposure
- Low operator friction
- Good fit with OCI single-host deployment

## Decision

Forge will expose the Hermes dashboard only over Tailscale for the first
deployment.

Hermes remains bound to loopback and Tailscale Serve publishes that loopback
service to authenticated Tailnet members over HTTPS. Public internet exposure
is not part of the first operating model.

This replaces the earlier proposed direct Tailnet bind. Hermes 0.19.0 engages
an OAuth gate for non-loopback binds and fails closed without a registered
dashboard auth provider. Forge uses OpenAI Codex OAuth for inference, which
does not provision the Nous dashboard OAuth client ID required by the bundled
dashboard provider. Loopback plus Tailscale Serve therefore preserves a private
identity boundary without bypassing Hermes' non-loopback safety check.

## Alternatives Considered

- Public reverse proxy with password protection
- SSH tunneling as the normal path
- Direct bind to the Tailnet address
- Non-loopback bind with `--insecure`

SSH tunneling remains a useful fallback. Direct binding requires a configured
Hermes dashboard OAuth provider, while `--insecure` explicitly disables that
gate. Neither is the correct default for this Codex-authenticated deployment.

## Consequences

Benefits:

- private operator access across devices
- reduced attack surface
- simpler first deployment than a public reverse proxy

Costs:

- Tailscale becomes part of the host setup
- remote access now depends on Tailnet availability
- Tailnet identity and ACL policy become part of the dashboard access boundary
- the dashboard must never be published with Tailscale Funnel

Any future public exposure path requires a new ADR.
