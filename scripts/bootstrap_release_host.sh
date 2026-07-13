#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT=""
TARGET="local"
EXECUTE=0
REPOSITORY_URL="git@github.com:giraffu/All_bot.git"
DEPLOY_KEY="/home/deploy/.ssh/allbot_release_ed25519"

usage() {
  echo "Usage: $0 --env test|prod [--target local|SSH_HOST] [--deploy-key PATH] [--execute]"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --env) ENVIRONMENT="${2:-}"; shift 2 ;;
    --target) TARGET="${2:-}"; shift 2 ;;
    --deploy-key) DEPLOY_KEY="${2:-}"; shift 2 ;;
    --execute) EXECUTE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$ENVIRONMENT" in test|prod) ;; *) echo "--env test|prod is required" >&2; exit 2 ;; esac

CHECKOUT_ROOT="/home/deploy/APP/All_bot-release"
LEGACY_ROOT="/home/deploy/APP/All_bot"
if [ "$TARGET" = local ]; then
  CHECKOUT_ROOT="/home/deploy/APP/All_bot-release"
  LEGACY_ROOT="/home/hfy/APP/All_bot"
fi

read -r -d '' SCRIPT <<EOF || true
set -euo pipefail
test "\$(id -un)" = deploy || { echo 'bootstrap execute must run as the deploy account' >&2; exit 2; }
test -f ${DEPLOY_KEY@Q}
test "\$(stat -c %a ${DEPLOY_KEY@Q})" = 600
command -v git >/dev/null
command -v gh >/dev/null
command -v oras >/dev/null
docker compose version >/dev/null
install -d -m 755 ${CHECKOUT_ROOT@Q} ${CHECKOUT_ROOT@Q}/releases ${CHECKOUT_ROOT@Q}/release-env
sudo -n install -d -m 755 -o deploy -g deploy /var/lib/allbot /var/lib/allbot/releases /var/lib/allbot/deployments
sudo -n install -d -m 700 -o deploy -g deploy /etc/allbot /etc/allbot/backups
if [ ! -d ${CHECKOUT_ROOT@Q}/repo/.git ]; then
  GIT_SSH_COMMAND='ssh -i ${DEPLOY_KEY} -o IdentitiesOnly=yes' git clone --filter=blob:none ${REPOSITORY_URL@Q} ${CHECKOUT_ROOT@Q}/repo
fi
git -C ${CHECKOUT_ROOT@Q}/repo config core.sshCommand 'ssh -i ${DEPLOY_KEY} -o IdentitiesOnly=yes'
git -C ${CHECKOUT_ROOT@Q}/repo remote set-url --push origin DISABLED
if [ -d ${LEGACY_ROOT@Q} ]; then
  stamp="\$(date -u +%Y%m%dT%H%M%SZ)"
  archive=${CHECKOUT_ROOT@Q}/legacy-${ENVIRONMENT}-"\$stamp"
  install -d -m 700 "\$archive"
  cp ${LEGACY_ROOT@Q}/deploy/docker-compose-cloud-${ENVIRONMENT}.yml "\$archive/" 2>/dev/null || true
  docker ps --no-trunc --format '{{.Names}} {{.Image}} {{.ID}}' > "\$archive/container-images.txt"
  tar --exclude='.git' --exclude='.env*' --exclude='logs' --exclude='runtime' --exclude='backups' -czf "\$archive/mixed-source.tgz" -C ${LEGACY_ROOT@Q} .
fi
echo 'release host bootstrap complete; no environment file or credential was copied'
EOF

if [ "$EXECUTE" -ne 1 ]; then
  echo "[dry-run] bootstrap immutable release checkout on ${TARGET}"
  echo "[dry-run] require existing read-only deploy key: ${DEPLOY_KEY}"
  echo "[dry-run] archive legacy compose/image IDs/source without env or secrets"
  exit 0
fi

if [ "$TARGET" = local ]; then
  bash -ceu "$SCRIPT"
else
  ssh -o BatchMode=yes "$TARGET" bash -ceu "$SCRIPT"
fi
