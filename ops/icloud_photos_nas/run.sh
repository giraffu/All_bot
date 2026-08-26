#!/bin/sh
set -eu

umask 077

photos_path=${PHOTOS_PATH:-/photos}
state_path=${STATE_PATH:-/state}
apple_id_file=${APPLE_ID_FILE:-/run/secrets/apple_id}
icloudpd_bin=${ICLOUDPD_BIN:-/app/icloudpd}
icloud_domain=${ICLOUD_DOMAIN:-cn}
sync_interval=${SYNC_INTERVAL_SECONDS:-21600}
max_used_percent=${MAX_USED_PERCENT:-80}

case "$icloud_domain" in
  cn|com) ;;
  *) echo "ICLOUD_DOMAIN must be cn or com" >&2; exit 2 ;;
esac

case "$sync_interval" in
  ''|*[!0-9]*) echo "SYNC_INTERVAL_SECONDS must be numeric" >&2; exit 2 ;;
esac
case "$max_used_percent" in
  ''|*[!0-9]*) echo "MAX_USED_PERCENT must be numeric" >&2; exit 2 ;;
esac
if [ "$max_used_percent" -lt 1 ] || [ "$max_used_percent" -gt 99 ]; then
  echo "MAX_USED_PERCENT must be between 1 and 99" >&2
  exit 2
fi

test -d "$photos_path" || { echo "missing photos path" >&2; exit 2; }
test -d "$state_path" || { echo "missing state path" >&2; exit 2; }
test -r "$apple_id_file" || { echo "missing Apple ID secret" >&2; exit 2; }

apple_id=$(tr -d '\r\n' < "$apple_id_file")
test -n "$apple_id" || { echo "empty Apple ID secret" >&2; exit 2; }
mkdir -p "$state_path/cookies" "$state_path/home" "$state_path/xdg"

capacity_guard() {
  used_percent=$(df -P "$photos_path" | awk 'NR == 2 {gsub(/%/, "", $5); print $5}')
  case "$used_percent" in
    ''|*[!0-9]*) echo "cannot determine NAS capacity" >&2; return 2 ;;
  esac
  if [ "$used_percent" -ge "$max_used_percent" ]; then
    echo "NAS capacity gate reached (${used_percent}% used)" >&2
    return 2
  fi
}

sync_once() {
  recent=${1:-}
  capacity_guard

  set -- "$icloudpd_bin" \
    --domain "$icloud_domain" \
    --log-level info \
    --no-progress-bar \
    --password-provider keyring \
    --mfa-provider console \
    --directory "$photos_path" \
    --cookie-directory "$state_path/cookies" \
    --size original \
    --live-photo-size original \
    --xmp-sidecar \
    --folder-structure '{:%Y/%m/%d}' \
    --file-match-policy name-id7 \
    --keep-unicode-in-filenames \
    --notification-script /opt/allbot/notify-reauth.sh \
    --username "$apple_id"

  if [ -n "$recent" ]; then
    set -- "$@" --recent "$recent"
  fi
  "$@"
}

mode=${1:-watch}
case "$mode" in
  canary)
    canary_recent=${CANARY_RECENT:-10}
    case "$canary_recent" in
      ''|*[!0-9]*) echo "CANARY_RECENT must be numeric" >&2; exit 2 ;;
    esac
    sync_once "$canary_recent"
    ;;
  once)
    sync_once
    ;;
  watch)
    while :; do
      if sync_once; then
        rm -f "$state_path/reauth-required"
      else
        status=$?
        echo "iCloud download cycle failed with status $status; retrying after interval" >&2
      fi
      sleep "$sync_interval"
    done
    ;;
  *)
    echo "usage: run.sh [canary|once|watch]" >&2
    exit 2
    ;;
esac

