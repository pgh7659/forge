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
python3 -m json.tool \
  src/forge/resources/schemas/environment-v1alpha1.schema.json >/dev/null
python3 -m json.tool \
  src/forge/resources/schemas/plan-v1alpha1.schema.json >/dev/null

controller_json_files=(
  src/forge/resources/schemas/controller-command-v1alpha1.schema.json
  src/forge/resources/schemas/controller-response-v1alpha1.schema.json
  tests/fixtures/controller/valid-submit.json
  tests/fixtures/controller/valid-get-task.json
  tests/fixtures/controller/valid-submit-created-response.json
  tests/fixtures/controller/valid-submit-replayed-response.json
  tests/fixtures/controller/valid-get-task-response.json
  tests/fixtures/controller/valid-error-response.json
)

for controller_json_file in "${controller_json_files[@]}"; do
  python3 -m json.tool "$controller_json_file" >/dev/null
done

test -s pyproject.toml
test -s examples/environments/minimal.yaml
test -s examples/environments/noop.yaml

required_files=(
  docs/adr/0009-separate-portable-core-from-deployment-profiles.md
  docs/adr/0010-adopt-a-contract-first-single-node-controller-core.md
  docs/operations/README.md
  docs/superpowers/plans/2026-08-10-planning-client.md
  docs/superpowers/plans/2026-08-11-controller-state.md
  docs/superpowers/specs/2026-08-10-planning-client-design.md
  docs/superpowers/specs/2026-08-11-controller-state-design.md
  src/forge/resources/schemas/controller-command-v1alpha1.schema.json
  src/forge/resources/schemas/controller-response-v1alpha1.schema.json
  tests/fixtures/controller/valid-submit.json
  tests/fixtures/controller/valid-get-task.json
  tests/fixtures/controller/valid-submit-created-response.json
  tests/fixtures/controller/valid-submit-replayed-response.json
  tests/fixtures/controller/valid-get-task-response.json
  tests/fixtures/controller/valid-error-response.json
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
grep -q 'strict in-process controller contract' docs/architecture.md
grep -Eq 'SQLite.*state adapter' docs/architecture.md
grep -Eq 'Controller and state.*implemented' docs/roadmap.md
grep -q 'Structural validation is not host enforcement' SECURITY.md

test ! -e prompts/hermes-ops-soul.md

if grep -R -q -E '(BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|gh[opurs]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})' \
  --exclude-dir=.git \
  --exclude-dir=.venv \
  --exclude-dir=build \
  --exclude-dir=dist \
  --exclude-dir=wheel-smoke \
  .; then
  printf 'credential-like content detected\n' >&2
  exit 1
fi

printf 'contract validation passed\n'
