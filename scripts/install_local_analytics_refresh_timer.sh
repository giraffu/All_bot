#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SYSTEMD_DIR="/etc/systemd/system"
SERVICE_NAME="allbot-local-analytics-refresh.service"
TIMER_NAME="allbot-local-analytics-refresh.timer"
EXECUTE=0
INSTALL_MODE="system"
SYSTEMD_DIR_SET=0
SERVICE_USER="${USER:-hfy}"
SERVICE_GROUP="$(id -gn "${SERVICE_USER}" 2>/dev/null || printf '%s' "${SERVICE_USER}")"

usage() {
  cat <<USAGE
Usage: $0 [--execute] [--user-systemd] [--root PATH] [--user USER] [--group GROUP] [--systemd-dir PATH]

Installs and enables the daily user profile snapshot refresh timer.
Default mode is dry-run; pass --execute to write systemd units and enable the timer.
Use --user-systemd to install under the current user's systemd manager without sudo.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute)
      EXECUTE=1
      ;;
    --user-systemd)
      INSTALL_MODE="user"
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
      SYSTEMD_DIR_SET=1
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
if [[ "$INSTALL_MODE" == "user" && "$SYSTEMD_DIR_SET" -eq 0 ]]; then
  SYSTEMD_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
fi
SERVICE_SRC="${ROOT_DIR}/deploy/systemd/${SERVICE_NAME}"
TIMER_SRC="${ROOT_DIR}/deploy/systemd/${TIMER_NAME}"

render_unit() {
  local src="$1"
  local rendered
  rendered="$(sed \
    -e "s#__ALLBOT_ROOT__#${ROOT_DIR}#g" \
    -e "s#__ALLBOT_USER__#${SERVICE_USER}#g" \
    -e "s#__ALLBOT_GROUP__#${SERVICE_GROUP}#g" \
    "$src")"
  if [[ "$INSTALL_MODE" == "user" && "$src" == *".service" ]]; then
    printf '%s\n' "$rendered" | sed \
      -e '/^User=/d' \
      -e '/^Group=/d' \
      -e '/^Requires=docker.service/d' \
      -e '/^Wants=network-online.target/d' \
      -e 's/^After=.*/After=default.target/'
  else
    printf '%s\n' "$rendered"
  fi
}

install_unit() {
  local src="$1"
  local name="$2"
  local tmp
  tmp="$(mktemp)"
  render_unit "$src" > "$tmp"
  if [[ "$EXECUTE" -eq 1 ]]; then
    if [[ "$INSTALL_MODE" == "user" ]]; then
      mkdir -p "$SYSTEMD_DIR"
      install -m 0644 "$tmp" "${SYSTEMD_DIR}/${name}"
    else
      sudo install -m 0644 "$tmp" "${SYSTEMD_DIR}/${name}"
    fi
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

install_unit "$SERVICE_SRC" "$SERVICE_NAME"
install_unit "$TIMER_SRC" "$TIMER_NAME"

if [[ "$EXECUTE" -eq 1 ]]; then
  if [[ "$INSTALL_MODE" == "user" ]]; then
    systemctl --user daemon-reload
    systemctl --user enable --now "$TIMER_NAME"
    systemctl --user list-timers "$TIMER_NAME" --no-pager
  else
    sudo systemctl daemon-reload
    sudo systemctl enable --now "$TIMER_NAME"
    systemctl list-timers "$TIMER_NAME" --no-pager
  fi
else
  if [[ "$INSTALL_MODE" == "user" ]]; then
    echo "[dry-run] would run: systemctl --user daemon-reload"
    echo "[dry-run] would run: systemctl --user enable --now ${TIMER_NAME}"
    echo "[dry-run] would run: systemctl --user list-timers ${TIMER_NAME} --no-pager"
  else
    echo "[dry-run] would run: sudo systemctl daemon-reload"
    echo "[dry-run] would run: sudo systemctl enable --now ${TIMER_NAME}"
    echo "[dry-run] would run: systemctl list-timers ${TIMER_NAME} --no-pager"
  fi
fi
