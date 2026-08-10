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
  docs/reference-deployments/hermes-discord-codex/operations/discord-forum-codex-routing.md
  docs/reference-deployments/hermes-discord-codex/prompts/hermes-assistant-soul.md
  docs/reference-deployments/hermes-discord-codex/contracts/codex-task-envelope.example.json
  docs/reference-deployments/hermes-discord-codex/contracts/codex-result.example.json
)

for required_file in "${required_files[@]}"; do
  test -s "$required_file"
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
