#!/bin/sh
set -eu

archive_subvolume=${ARCHIVE_SUBVOLUME:-/volume1/AllBotArchive}
snapshot_root=${ARCHIVE_SNAPSHOT_ROOT:-/volume1/.allbot-archive-snapshots}
retain=${ARCHIVE_SNAPSHOT_RETAIN:-7}

case "$archive_subvolume" in
  /volume[0-9]/*) ;;
  *) echo "unsafe archive subvolume: $archive_subvolume" >&2; exit 2 ;;
esac
case "$snapshot_root" in
  /volume[0-9]/*) ;;
  *) echo "unsafe snapshot root: $snapshot_root" >&2; exit 2 ;;
esac
printf '%s\n' "$retain" | grep -Eq '^[1-9][0-9]*$' || { echo "invalid retention: $retain" >&2; exit 2; }
command -v btrfs >/dev/null 2>&1 || { echo "btrfs command is unavailable" >&2; exit 2; }
btrfs subvolume show "$archive_subvolume" >/dev/null
install -d -m 0700 "$snapshot_root"

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
snapshot="$snapshot_root/AllBotArchive-$timestamp"
test ! -e "$snapshot" || { echo "snapshot already exists: $snapshot" >&2; exit 2; }
btrfs subvolume snapshot -r "$archive_subvolume" "$snapshot"

while :; do
  snapshot_count=$(find "$snapshot_root" -mindepth 1 -maxdepth 1 -type d \
    -name 'AllBotArchive-*' -printf '%f\n' | wc -l)
  test "$snapshot_count" -gt "$retain" || break
  oldest=$(find "$snapshot_root" -mindepth 1 -maxdepth 1 -type d \
    -name 'AllBotArchive-*' -printf '%f\n' | sort | head -n 1)
  test -n "$oldest" || { echo "unable to resolve oldest snapshot" >&2; exit 2; }
  btrfs subvolume delete "$snapshot_root/$oldest"
done

echo "AllBot Archive snapshot completed: $snapshot"
