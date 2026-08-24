#!/usr/bin/env bash
set -euo pipefail

mode="dry-run"
confirm=""
confirm_value="MIGRATE_LAN_ARTIFACTS_TO_NAS"
root="/volume1/AllBotInfra"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --execute) mode="execute"; shift ;;
    --confirm) confirm="${2:-}"; shift 2 ;;
    -h|--help)
      echo "usage: $0 [--execute --confirm ${confirm_value}]"
      exit 0
      ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for required in compose.yml allbot-infra.exports snapshot-model-registry.sh; do
  test -f "${script_dir}/${required}" || {
    echo "missing managed asset: ${required}" >&2
    exit 2
  }
done

echo "NAS artifact root: ${root}"
echo "Model registry export: ${root}/model-registry -> 10.250.150.1 only"
echo "Registry backend: 10.250.150.2:5000"
echo "Model cache backend: 10.250.150.2:9010"

if [ "$mode" != "execute" ]; then
  echo "read-only preflight passed"
  exit 0
fi
if [ "$confirm" != "$confirm_value" ]; then
  echo "execute requires exact confirmation: ${confirm_value}" >&2
  exit 2
fi
test "$(id -u)" -eq 0 || { echo "execute requires root" >&2; exit 2; }
test -f "${script_dir}/.env" || { echo "missing private .env" >&2; exit 2; }

set -a
# shellcheck disable=SC1091
source "${script_dir}/.env"
set +a
: "${NAS_DIRECT_BIND_IP:?required}"
: "${REGISTRY_IMAGE:?required}"
: "${MODEL_CACHE_IMAGE:?required}"
: "${MODEL_CACHE_MC_IMAGE:?required}"
: "${LAN_MODEL_CACHE_ACCESS_KEY:?required}"
: "${LAN_MODEL_CACHE_SECRET_KEY:?required}"

ip -4 address show | grep -Fq "${NAS_DIRECT_BIND_IP}/" || {
  echo "NAS direct-link address is not active: ${NAS_DIRECT_BIND_IP}" >&2
  exit 2
}
for image in "$REGISTRY_IMAGE" "$MODEL_CACHE_IMAGE" "$MODEL_CACHE_MC_IMAGE"; do
  docker image inspect "$image" >/dev/null
done

if [ ! -e "$root" ]; then
  btrfs subvolume create "$root"
fi
for name in model-registry model-cache-lan docker-registry; do
  if [ ! -e "${root}/${name}" ]; then
    btrfs subvolume create "${root}/${name}"
  fi
done
install -d -m 0755 /etc/exports.d
install -m 0644 "${script_dir}/allbot-infra.exports" \
  /etc/exports.d/allbot-infra.exports
systemctl enable --now nfs-server
exportfs -ra
echo "NAS artifact mutation preflight passed"

