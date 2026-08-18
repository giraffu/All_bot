#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

DIFF_RANGE="${1:-${COMPAT_GATE_DIFF_RANGE:-}}"

python3 scripts/validate_compat_registry.py

if [[ -z "${DIFF_RANGE}" ]]; then
  echo "Usage: ./scripts/check_compat_registry.sh <git-diff-range>" >&2
  exit 1
fi

mapfile -t changed_files < <(git diff --name-only "${DIFF_RANGE}")

if [[ ${#changed_files[@]} -eq 0 ]]; then
  echo "Compat registry gate: no changed files."
  exit 0
fi

registry_changed="false"
for file in "${changed_files[@]}"; do
  if [[ "${file}" == "config/compat_registry.json" ]]; then
    registry_changed="true"
    break
  fi
done

added_compat_lines="$(git diff --unified=0 "${DIFF_RANGE}" -- \
  '*.py' '*.ts' '*.tsx' '*.vue' '*.js' '*.md' \
  | grep -E '^\+.*\b(compat|legacy|alias)\b' \
  | grep -vE '^\+\+\+' || true)"

if [[ -z "${added_compat_lines}" ]]; then
  echo "Compat registry gate: no newly added compat/legacy/alias markers."
  exit 0
fi

if [[ "${registry_changed}" == "true" ]]; then
  echo "Compat registry gate: detected compat markers and machine registry was updated."
  exit 0
fi

echo "::error::Detected new compat/legacy/alias markers, but config/compat_registry.json was not updated."
echo "${added_compat_lines}"
exit 1
