#!/bin/sh
set -eu

umask 077

state_path=${STATE_PATH:-/state}
apple_id_file=${APPLE_ID_FILE:-/run/secrets/apple_id}
icloudpd_bin=${ICLOUDPD_BIN:-/app/icloudpd}
icloud_domain=${ICLOUD_DOMAIN:-cn}

case "$icloud_domain" in
  cn|com) ;;
  *) echo "ICLOUD_DOMAIN must be cn or com" >&2; exit 2 ;;
esac
test -r "$apple_id_file" || { echo "missing Apple ID secret" >&2; exit 2; }

apple_id=$(tr -d '\r\n' < "$apple_id_file")
test -n "$apple_id" || { echo "empty Apple ID secret" >&2; exit 2; }
mkdir -p "$state_path/cookies" "$state_path/home" "$state_path/xdg"

"$icloudpd_bin" \
  --domain "$icloud_domain" \
  --password-provider keyring \
  --password-provider console \
  --mfa-provider console \
  --auth-only \
  --cookie-directory "$state_path/cookies" \
  --username "$apple_id"

rm -f "$state_path/reauth-required"
echo "iCloud authentication completed"

