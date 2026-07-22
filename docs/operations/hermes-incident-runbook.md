# Hermes Host Incident Runbook

## Purpose

This runbook is a reusable template for a single-host Forge deployment running
Hermes behind Tailscale. Keep hostnames, IP addresses, Tailnet names, account
identifiers, backup names, and secrets in a private deployment inventory, not
in this repository.

Before using the commands, define deployment-specific values in the operator's
shell or substitute them manually:

```sh
FORGE_TAILNET_HOST='<device>.<tailnet>.ts.net'
FORGE_DASHBOARD_PORT='443'
```

Do not enable Tailscale Funnel or add public ingress as a troubleshooting
shortcut.

## Expected Boundaries

A default single-host deployment should keep:

- Hermes Gateway and Dashboard under user systemd
- Hermes Dashboard on a loopback listener
- any compatibility reverse proxy on a loopback listener
- Tailscale Serve on Tailnet addresses only
- the operator allowlist enabled for messaging gateways

Deployment-specific services and port mappings belong in a private inventory.

## First Response

Confirm the host, kernel, capacity, and failed units:

```sh
date
uptime
uname -r
df -h /
free -h
systemctl --failed
systemctl --user --failed
```

Check the standard services:

```sh
systemctl status tailscaled caddy ssh.socket --no-pager -l
systemctl --user status hermes-gateway hermes-dashboard --no-pager -l
loginctl show-user "$USER" -p Linger
```

Check Tailscale and listeners without assuming deployment-specific ports:

```sh
tailscale status
tailscale serve status
ss -lntp
```

Compare listeners with the private deployment inventory. No Forge control
surface should listen on a public address.

## Logs

Follow Hermes logs:

```sh
journalctl --user -u hermes-gateway -f
journalctl --user -u hermes-dashboard -f
```

Read logs for the current boot:

```sh
journalctl --user -u hermes-gateway -b --no-pager -l
journalctl --user -u hermes-dashboard -b --no-pager -l
sudo journalctl -u tailscaled -b --no-pager -l
sudo journalctl -u caddy -b --no-pager -l
```

Do not paste environment files, OAuth credentials, bot tokens, session tokens,
or complete request headers into tickets or chat.

## Dashboard Health Check

Run from the host or another authenticated Tailnet device:

```sh
curl -fsS -o /dev/null -w 'dashboard=%{http_code}\n' \
  "https://${FORGE_TAILNET_HOST}:${FORGE_DASHBOARD_PORT}/"
curl -fsS \
  "https://${FORGE_TAILNET_HOST}:${FORGE_DASHBOARD_PORT}/api/status" | \
  jq '{version,gateway_running,auth_required}'
```

Record additional application health checks only in the private deployment
inventory. A Dashboard HTML response with zero bytes can indicate that a
reverse proxy host matcher excluded the external Tailnet hostname.

## Recovery Actions

Restart only the failed layer, then repeat the health checks:

```sh
systemctl --user restart hermes-gateway
systemctl --user restart hermes-dashboard
sudo systemctl restart caddy
sudo systemctl restart tailscaled
```

After restarting `tailscaled`, confirm that the expected persistent routes
return in `tailscale serve status`. Do not run `tailscale up --force-reauth`
remotely unless an independent console path is available.

Validate the tracked Caddy compatibility configuration before installing it:

```sh
caddy validate --config caddy/Caddyfile.tailnet
```

The template must remain loopback-only and normalize the upstream Host header
required by the supported Hermes version.

## Backup and Restore

The private deployment inventory should record:

- the backup provider and region
- the policy and retention period
- the latest verified restore point
- the restore owner and approval path
- the platform's free-tier or budget limits

Restore into a replacement volume or host when possible. Validate the restored
host before moving the Tailscale identity or messaging workload.

## Escalation Conditions

Obtain explicit approval before:

- changing ingress, routing, firewall, or SSH policy
- enabling any public Dashboard path
- rotating messaging or model credentials
- restoring a volume or replacing the running host
- deleting backups, runtime state, repositories, or rollback material
