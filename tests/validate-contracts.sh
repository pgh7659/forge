#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

bash -n scripts/audit-oci-host.sh
python3 -m json.tool templates/codex-task-envelope.example.json >/dev/null
python3 -m json.tool templates/codex-result.example.json >/dev/null

required_files=(
  docs/adr/0008-separate-assistant-control-plane-from-engineering-execution.md
  docs/operations/assistant-codex-handoff.md
  docs/operations/oci-assistant-control-plane-migration.md
  docs/operations/oci-environment-audit.md
  prompts/hermes-assistant-soul.md
  prompts/hermes-ops-soul.md
  templates/codex-task-envelope.example.json
  templates/codex-result.example.json
)

for required_file in "${required_files[@]}"; do
  test -s "$required_file"
done

if grep -R -E '(BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|gh[opurs]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})' \
  --exclude-dir=.git .; then
  printf 'credential-like content detected\n' >&2
  exit 1
fi

printf 'contract validation passed\n'
