#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

probe_file="$(mktemp "$repo_root/.credential-scan-probe.XXXXXX")"
output_file="$(mktemp)"
trap 'rm -f "$probe_file" "$output_file"' EXIT

probe_prefix='sk-'
probe_suffix="$(printf 'A%.0s' {1..24})"
probe_value="${probe_prefix}${probe_suffix}"
printf '%s\n' "$probe_value" >"$probe_file"

if ./tests/validate-contracts.sh >"$output_file" 2>&1; then
  printf 'credential scanner accepted synthetic credential-like content\n' >&2
  exit 1
fi

if grep -F -q -- "$probe_value" "$output_file"; then
  printf 'credential scanner echoed synthetic credential-like content\n' >&2
  exit 1
fi

if ! grep -q '^credential-like content detected$' "$output_file"; then
  printf 'credential scanner did not emit its generic failure\n' >&2
  exit 1
fi

printf 'credential scanner redaction regression passed\n'
