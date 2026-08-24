#!/usr/bin/env bash
set -euo pipefail

source_path="/volume1/AllBotInfra/model-registry"
snapshot_root="/volume1/.allbot-infra-snapshots"
retain="${ALLBOT_MODEL_REGISTRY_SNAPSHOT_RETAIN:-3}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="${snapshot_root}/model-registry-${stamp}"

case "$retain" in
  ''|*[!0-9]*) echo "retain must be an integer" >&2; exit 2 ;;
esac
test "$retain" -ge 1 || { echo "retain must be at least 1" >&2; exit 2; }
test -d "$source_path" || { echo "missing model registry subvolume" >&2; exit 2; }
install -d -m 0755 "$snapshot_root"
echo "Creating readonly model registry snapshot: ${target}"
btrfs subvolume snapshot -r "$source_path" "$target"

mapfile -t snapshots < <(
  find "$snapshot_root" -mindepth 1 -maxdepth 1 -type d \
    -name 'model-registry-*' -printf '%p\n' | sort
)
excess=$((${#snapshots[@]} - retain))
if [ "$excess" -gt 0 ]; then
  for ((i=0; i<excess; i++)); do
    btrfs subvolume delete "${snapshots[$i]}"
  done
fi

