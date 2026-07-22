#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SYSTEMD_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
EXECUTE=0

usage() {
  cat <<USAGE
Usage: $0 [--execute] [--root PATH] [--systemd-dir PATH]

Install the user-level immutable handoff integration timer. The default is a
dry-run. The service can merge protected-main PRs and deploy only the shared
test environment; it has no production deployment option.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute) EXECUTE=1 ;;
    --root) ROOT_DIR="$2"; shift ;;
    --systemd-dir) SYSTEMD_DIR="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

ROOT_DIR="$(cd "${ROOT_DIR}" && pwd)"
SERVICE_NAME="allbot-ai-integration-queue.service"
TIMER_NAME="allbot-ai-integration-queue.timer"

for name in "$SERVICE_NAME" "$TIMER_NAME"; do
  source_path="${ROOT_DIR}/deploy/systemd/${name}"
  [[ -f "$source_path" ]] || { echo "Missing unit: ${source_path}" >&2; exit 2; }
  rendered="$(mktemp)"
  trap 'rm -f "${rendered:-}"' EXIT
  sed "s#__ALLBOT_ROOT__#${ROOT_DIR}#g" "$source_path" > "$rendered"
  if [[ "$EXECUTE" -eq 1 ]]; then
    mkdir -p "$SYSTEMD_DIR"
    install -m 0644 "$rendered" "${SYSTEMD_DIR}/${name}"
  else
    echo "[dry-run] would install ${SYSTEMD_DIR}/${name}"
    sed 's/^/[unit] /' "$rendered"
  fi
  rm -f "$rendered"
  trap - EXIT
done

if [[ "$EXECUTE" -eq 1 ]]; then
  command -v gh >/dev/null
  gh auth status >/dev/null
  git -C "$ROOT_DIR" ls-remote --exit-code origin refs/heads/main >/dev/null
  systemctl --user daemon-reload
  systemctl --user enable --now "$TIMER_NAME"
  systemctl --user list-timers "$TIMER_NAME" --no-pager
else
  echo "[dry-run] would verify: gh auth status"
  echo "[dry-run] would verify: git -C ${ROOT_DIR} ls-remote --exit-code origin refs/heads/main"
  echo "[dry-run] would run: systemctl --user daemon-reload"
  echo "[dry-run] would run: systemctl --user enable --now ${TIMER_NAME}"
fi
