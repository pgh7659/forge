# systemd

Linux service units and timers live here.

Units should be paired with documentation that explains purpose, dependencies,
rollback, and operational ownership.

## Hermes Dashboard

`hermes-dashboard.service` runs the dashboard on `127.0.0.1:9119`. It must not
be changed to a public or Tailnet bind. The first deployment publishes this
loopback listener through Tailscale Serve, never Tailscale Funnel.

Install it for the Hermes operator account:

```sh
install -D -m 0644 docs/reference-deployments/hermes-discord-codex/assets/systemd/hermes-dashboard.service \
  ~/.config/systemd/user/hermes-dashboard.service
systemctl --user daemon-reload
systemctl --user enable --now hermes-dashboard.service
```

## Dependencies and Ownership

The private deployment inventory must name the Hermes operator account,
service owner, installed Hermes version and binary path, prior-unit backup,
prior enabled/active state, and rollback approver. The operator must verify the
installed Hermes `dashboard --help` contract before installation. Tailscale
Serve and the loopback Caddy listener are separate dependencies for remote
access; this unit does not expose the dashboard by itself.

## Rollback

Installation and rollback are infrastructure changes and require scoped human
approval. Before installation, preserve any existing user unit in the private
deployment inventory. Rollback stops and disables this unit, restores the
recorded prior unit—or removes only the unit file installed by this procedure
when no prior unit existed—reloads the user manager, restores the recorded
enabled/disabled and active/inactive state, and then verifies the loopback
listener and Tailscale Serve route against the pre-change inventory. Service
rollback never deletes `~/.hermes`.
