# Caddy

`Caddyfile.tailnet` is the first OCI host's loopback-only compatibility proxy.
It exists because Hermes 0.19.0 requires the proxied `Host` header to match its
`127.0.0.1:9119` bind. Tailscale Serve forwards Dashboard requests to Caddy on
`127.0.0.1:9120`, and Caddy normalizes the header before forwarding to Hermes.

Caddy must not bind public ports in this deployment. Validate before install:

```sh
caddy validate --config caddy/Caddyfile.tailnet
sudo install -o root -g root -m 0644 caddy/Caddyfile.tailnet \
  /etc/caddy/Caddyfile
sudo systemctl restart caddy
```

If a deployment retains a pre-migration configuration for rollback, record its
path and deletion date in the private deployment inventory. Do not commit that
host-specific path or configuration to this repository.
