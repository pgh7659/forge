#!/usr/bin/env bash

set -uo pipefail

readonly FORGE_ROOT="${FORGE_ROOT:-/srv/forge}"

section() {
  printf '\n[%s]\n' "$1"
}

command_version() {
  local command_name="$1"
  shift

  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf '%s: missing\n' "$command_name"
    return 0
  fi

  printf '%s: %s\n' "$command_name" "$(command -v "$command_name")"
  "$@" 2>&1 | sed -n '1,3p'
}

run_optional() {
  "$@" 2>&1 || printf 'command failed: %s\n' "$*"
}

section metadata
printf 'captured_at_utc: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'architecture: %s\n' "$(uname -m)"
printf 'kernel: %s\n' "$(uname -sr)"
if [[ -r /etc/os-release ]]; then
  sed -n -E 's/^(ID|VERSION_ID|PRETTY_NAME)=/\1=/p' /etc/os-release
fi

section versions
command_version hermes hermes --version
command_version codex codex --version
command_version gh gh --version
command_version git git --version
command_version tailscale tailscale version
command_version caddy caddy version

section capabilities
if command -v hermes >/dev/null 2>&1; then
  run_optional hermes profile --help
  run_optional hermes kanban --help
  run_optional hermes gateway --help
fi
if command -v codex >/dev/null 2>&1; then
  run_optional codex exec --help
  run_optional codex exec resume --help
fi

section hermes-health
if command -v hermes >/dev/null 2>&1; then
  run_optional hermes profile list
  run_optional hermes doctor
fi

section service-state
if command -v systemctl >/dev/null 2>&1; then
  run_optional systemctl --user list-units --type=service --all --no-pager
  run_optional systemctl --user list-timers --all --no-pager
  run_optional systemctl list-units --type=service --all --no-pager
  run_optional systemctl list-timers --all --no-pager
fi

section forge-layout
if [[ -d "$FORGE_ROOT" ]]; then
  find "$FORGE_ROOT" -maxdepth 4 -mindepth 1 \
    -printf '%M %u:%g %p\n' 2>/dev/null | sort
else
  printf 'missing: %s\n' "$FORGE_ROOT"
fi

section repository-state
if [[ -d "$FORGE_ROOT/repos" ]]; then
  while IFS= read -r git_dir; do
    repository="${git_dir%/.git}"
    printf 'repository: %s\n' "$repository"
    run_optional git -C "$repository" status --short --branch
    run_optional git -C "$repository" worktree list --porcelain
  done < <(find "$FORGE_ROOT/repos" -mindepth 2 -maxdepth 2 -type d -name .git | sort)
fi

section listeners
if command -v ss >/dev/null 2>&1; then
  run_optional ss -ltnp
fi

section capacity
run_optional df -h /
run_optional free -h

cat <<'NOTICE'

[operator-notice]
This report can contain private usernames, filesystem paths, profile names,
repository names, listener addresses, and service metadata. Store it only in
the private deployment inventory. Review and redact it before sharing. It never
reads Hermes .env files, model credentials, Codex auth, SSH keys, message
bodies, or repository file contents.
NOTICE
