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
install -D -m 0644 systemd/hermes-dashboard.service \
  ~/.config/systemd/user/hermes-dashboard.service
systemctl --user daemon-reload
systemctl --user enable --now hermes-dashboard.service
```
