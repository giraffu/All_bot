#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SYSTEMD_DIR="/etc/systemd/system"
SERVICE_NAME="allbot-cloud-prod-shadow-sync.service"
TIMER_NAME="allbot-cloud-prod-shadow-sync.timer"
EXECUTE=0
SERVICE_USER="${USER:-hfy}"
SERVICE_GROUP="$(id -gn "${SERVICE_USER}" 2>/dev/null || printf '%s' "${SERVICE_USER}")"

usage() {
  cat <<USAGE
Usage: $0 [--execute] [--root PATH] [--user USER] [--group GROUP] [--systemd-dir PATH]

Installs and enables the daily cloud-production-to-local-shadow sync timer.
Default mode is dry-run; pass --execute to write systemd units and enable the timer.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute)
      EXECUTE=1
      ;;
    --root)
      ROOT_DIR="$2"
      shift
      ;;
    --user)
      SERVICE_USER="$2"
      SERVICE_GROUP="$(id -gn "$2" 2>/dev/null || printf '%s' "$2")"
      shift
      ;;
    --group)
      SERVICE_GROUP="$2"
      shift
      ;;
    --systemd-dir)
      SYSTEMD_DIR="$2"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

ROOT_DIR="$(cd "${ROOT_DIR}" && pwd)"
SERVICE_SRC="${ROOT_DIR}/deploy/systemd/${SERVICE_NAME}"
TIMER_SRC="${ROOT_DIR}/deploy/systemd/${TIMER_NAME}"
ENV_FILE="${ROOT_DIR}/.env.cloud-prod-shadow-sync.local"

render_unit() {
  local src="$1"
  sed \
    -e "s#__ALLBOT_ROOT__#${ROOT_DIR}#g" \
    -e "s#__ALLBOT_USER__#${SERVICE_USER}#g" \
    -e "s#__ALLBOT_GROUP__#${SERVICE_GROUP}#g" \
    "$src"
}

install_unit() {
  local src="$1"
  local name="$2"
  local tmp
  tmp="$(mktemp)"
  render_unit "$src" > "$tmp"
  if [[ "$EXECUTE" -eq 1 ]]; then
    sudo install -m 0644 "$tmp" "${SYSTEMD_DIR}/${name}"
  else
    echo "[dry-run] would install ${SYSTEMD_DIR}/${name}"
    sed 's/^/[unit] /' "$tmp"
  fi
  rm -f "$tmp"
}

if [[ ! -f "$SERVICE_SRC" || ! -f "$TIMER_SRC" ]]; then
  echo "Missing systemd unit templates under ${ROOT_DIR}/deploy/systemd" >&2
  exit 2
fi

if [[ "$EXECUTE" -eq 1 && ! -f "$ENV_FILE" ]]; then
  echo "Missing ${ENV_FILE}; copy .env.cloud-prod-shadow-sync.example and fill local credentials first." >&2
  exit 2
fi

install_unit "$SERVICE_SRC" "$SERVICE_NAME"
install_unit "$TIMER_SRC" "$TIMER_NAME"

if [[ "$EXECUTE" -eq 1 ]]; then
  sudo systemctl daemon-reload
  sudo systemctl enable --now "$TIMER_NAME"
  systemctl list-timers "$TIMER_NAME" --no-pager
else
  echo "[dry-run] would run: sudo systemctl daemon-reload"
  echo "[dry-run] would run: sudo systemctl enable --now ${TIMER_NAME}"
  echo "[dry-run] would run: systemctl list-timers ${TIMER_NAME} --no-pager"
fi
