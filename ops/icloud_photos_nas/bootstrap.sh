#!/bin/sh
set -eu

confirm_expected=CREATE_ICLOUD_PHOTOS_ARCHIVE
execute=false
confirm=

while [ "$#" -gt 0 ]; do
  case "$1" in
    --execute) execute=true ;;
    --confirm)
      shift
      test "$#" -gt 0 || { echo "--confirm requires a value" >&2; exit 2; }
      confirm=$1
      ;;
    *) echo "usage: bootstrap.sh [--execute --confirm $confirm_expected]" >&2; exit 2 ;;
  esac
  shift
done

photos_root=/volume1/ApplePhotos
originals=$photos_root/originals
runtime_root=/volume1/ApplePhotosRuntime
state_root=$runtime_root/state
secrets_root=$runtime_root/secrets
deploy_root=$runtime_root/deploy
snapshot_root=/volume1/.apple-photos-snapshots
source_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ "$execute" != true ]; then
  echo "dry-run: create protected iCloud photo backup storage"
  echo "originals: $originals (Btrfs subvolume, uid 1000 gid 100)"
  echo "private runtime: $runtime_root"
  echo "read-only snapshots: $snapshot_root"
  echo "container: exact icloudpd digest; not started before interactive authentication"
  exit 0
fi

if [ "$confirm" != "$confirm_expected" ]; then
  echo "exact confirmation required: $confirm_expected" >&2
  exit 2
fi
if [ "$(id -u)" -ne 0 ]; then
  echo "bootstrap execute must run as root" >&2
  exit 2
fi
if [ "$(findmnt -n -o FSTYPE -T /volume1)" != btrfs ]; then
  echo "/volume1 must be Btrfs" >&2
  exit 2
fi

used_percent=$(df -P /volume1 | awk 'NR == 2 {gsub(/%/, "", $5); print $5}')
case "$used_percent" in
  ''|*[!0-9]*) echo "cannot determine /volume1 capacity" >&2; exit 2 ;;
esac
if [ "$used_percent" -ge 80 ]; then
  echo "capacity gate reached (${used_percent}% used)" >&2
  exit 2
fi

install -d -o root -g root -m 0750 "$photos_root"
if [ -e "$originals" ]; then
  btrfs subvolume show "$originals" >/dev/null 2>&1 || {
    echo "existing originals path is not a Btrfs subvolume" >&2
    exit 2
  }
else
  btrfs subvolume create "$originals"
fi
chown 1000:100 "$originals"
chmod 0750 "$originals"

install -d -o root -g root -m 0750 "$runtime_root"
install -d -o 1000 -g 100 -m 0700 "$state_root" "$secrets_root"
install -d -o root -g root -m 0755 "$deploy_root"
install -d -o root -g root -m 0700 "$snapshot_root"

install_runtime_file() {
  source_file=$1
  target_file=$2
  mode=$3
  if [ "$(readlink -f "$source_file")" != "$(readlink -f "$target_file" 2>/dev/null || true)" ]; then
    install -o root -g root -m "$mode" "$source_file" "$target_file"
  else
    chown root:root "$target_file"
    chmod "$mode" "$target_file"
  fi
}

install_runtime_file "$source_root/compose.yml" "$deploy_root/compose.yml" 0644
for script in run.sh auth.sh notify-reauth.sh set-apple-id.sh snapshot.sh bootstrap.sh; do
  install_runtime_file "$source_root/$script" "$deploy_root/$script" 0755
done

install -o root -g root -m 0644 \
  "$source_root/allbot-icloud-photos-snapshot.service" \
  /etc/systemd/system/allbot-icloud-photos-snapshot.service
install -o root -g root -m 0644 \
  "$source_root/allbot-icloud-photos-snapshot.timer" \
  /etc/systemd/system/allbot-icloud-photos-snapshot.timer

docker compose -f "$deploy_root/compose.yml" config >/dev/null
docker compose -f "$deploy_root/compose.yml" pull icloud-photo-backup
systemctl daemon-reload
systemctl enable --now allbot-icloud-photos-snapshot.timer

echo "bootstrap complete; run set-apple-id.sh and interactive authentication next"

