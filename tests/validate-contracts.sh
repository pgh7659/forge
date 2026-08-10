#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

bash -n \
  docs/reference-deployments/hermes-discord-codex/scripts/audit-oci-host.sh
python3 -m json.tool \
  docs/reference-deployments/hermes-discord-codex/contracts/codex-task-envelope.example.json \
  >/dev/null
python3 -m json.tool \
  docs/reference-deployments/hermes-discord-codex/contracts/codex-result.example.json \
  >/dev/null

required_files=(
  docs/adr/0009-separate-portable-core-from-deployment-profiles.md
  docs/operations/README.md
  docs/reference-deployments/hermes-discord-codex/README.md
  docs/reference-deployments/hermes-discord-codex/AGENTS.md
  docs/reference-deployments/hermes-discord-codex/architecture.md
  docs/reference-deployments/hermes-discord-codex/roadmap.md
  docs/reference-deployments/hermes-discord-codex/operations/discord-forum-codex-routing.md
  docs/reference-deployments/hermes-discord-codex/prompts/hermes-assistant-soul.md
  docs/reference-deployments/hermes-discord-codex/contracts/codex-task-envelope.example.json
  docs/reference-deployments/hermes-discord-codex/contracts/codex-result.example.json
)

for required_file in "${required_files[@]}"; do
  test -s "$required_file"
done

moved_paths=(
  'docs/adr/0001-use-hermes-as-initial-orchestrator.md|docs/reference-deployments/hermes-discord-codex/decisions/0001-use-hermes-as-initial-orchestrator.md'
  'docs/adr/0002-use-host-install-on-oci-for-first-deployment.md|docs/reference-deployments/hermes-discord-codex/decisions/0002-use-host-install-on-oci-for-first-deployment.md'
  'docs/adr/0003-use-discord-as-primary-operator-interface.md|docs/reference-deployments/hermes-discord-codex/decisions/0003-use-discord-as-primary-operator-interface.md'
  'docs/adr/0004-use-tailscale-for-private-dashboard-access.md|docs/reference-deployments/hermes-discord-codex/decisions/0004-use-tailscale-for-private-dashboard-access.md'
  'docs/adr/0005-use-protected-checkouts-and-hermes-worktrees.md|docs/reference-deployments/hermes-discord-codex/decisions/0005-use-protected-checkouts-and-hermes-worktrees.md'
  'docs/adr/0006-use-hermes-profiles-kanban-and-provider-fallback.md|docs/reference-deployments/hermes-discord-codex/decisions/0006-use-hermes-profiles-kanban-and-provider-fallback.md'
  'docs/adr/0008-separate-assistant-control-plane-from-engineering-execution.md|docs/reference-deployments/hermes-discord-codex/decisions/0008-separate-assistant-control-plane-from-engineering-execution.md'
  'docs/operations/assistant-codex-handoff.md|docs/reference-deployments/hermes-discord-codex/operations/assistant-codex-handoff.md'
  'docs/operations/discord-forum-codex-routing.md|docs/reference-deployments/hermes-discord-codex/operations/discord-forum-codex-routing.md'
  'docs/operations/hermes-incident-runbook.md|docs/reference-deployments/hermes-discord-codex/operations/hermes-incident-runbook.md'
  'docs/operations/oci-assistant-control-plane-migration.md|docs/reference-deployments/hermes-discord-codex/operations/oci-assistant-control-plane-migration.md'
  'docs/operations/oci-environment-audit.md|docs/reference-deployments/hermes-discord-codex/operations/oci-environment-audit.md'
  'prompts/hermes-assistant-soul.md|docs/reference-deployments/hermes-discord-codex/prompts/hermes-assistant-soul.md'
  'caddy/Caddyfile.tailnet|docs/reference-deployments/hermes-discord-codex/assets/caddy/Caddyfile.tailnet'
  'caddy/README.md|docs/reference-deployments/hermes-discord-codex/assets/caddy/README.md'
  'systemd/hermes-dashboard.service|docs/reference-deployments/hermes-discord-codex/assets/systemd/hermes-dashboard.service'
  'systemd/README.md|docs/reference-deployments/hermes-discord-codex/assets/systemd/README.md'
  'scripts/audit-oci-host.sh|docs/reference-deployments/hermes-discord-codex/scripts/audit-oci-host.sh'
  'templates/codex-task-envelope.example.json|docs/reference-deployments/hermes-discord-codex/contracts/codex-task-envelope.example.json'
  'templates/codex-result.example.json|docs/reference-deployments/hermes-discord-codex/contracts/codex-result.example.json'
)

for moved_path in "${moved_paths[@]}"; do
  moved_source="${moved_path%%|*}"
  moved_target="${moved_path#*|}"
  test ! -e "$moved_source"
  test -s "$moved_target"
done

grep -q 'portable engineering-control framework' README.md
grep -q 'Reference deployments' docs/architecture.md
grep -q 'Deployment-specific rules' AGENTS.md

test ! -e prompts/hermes-ops-soul.md

if grep -R -E '(BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|gh[opurs]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})' \
  --exclude-dir=.git .; then
  printf 'credential-like content detected\n' >&2
  exit 1
fi

printf 'contract validation passed\n'
