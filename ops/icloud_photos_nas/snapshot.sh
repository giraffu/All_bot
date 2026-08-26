#!/bin/sh
set -eu

source_subvolume=/volume1/ApplePhotos/originals
snapshot_root=/volume1/.apple-photos-snapshots
retain=${APPLE_PHOTOS_SNAPSHOT_RETAIN:-30}

case "$retain" in
  ''|*[!0-9]*) echo "retain must be numeric" >&2; exit 2 ;;
esac
if [ "$retain" -lt 1 ] || [ "$retain" -gt 365 ]; then
  echo "retain must be between 1 and 365" >&2
  exit 2
fi

btrfs subvolume show "$source_subvolume" >/dev/null
install -d -o root -g root -m 0700 "$snapshot_root"

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
snapshot=$snapshot_root/originals-$timestamp
btrfs subvolume snapshot -r "$source_subvolume" "$snapshot"

while [ "$(find "$snapshot_root" -mindepth 1 -maxdepth 1 -type d -name 'originals-*' | wc -l)" -gt "$retain" ]; do
  oldest=$(find "$snapshot_root" -mindepth 1 -maxdepth 1 -type d -name 'originals-*' -printf '%f\n' | sort | head -n 1)
  test -n "$oldest" || exit 2
  btrfs subvolume delete "$snapshot_root/$oldest"
done

echo "created read-only snapshot $snapshot"

