#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "operator must run as root" >&2
  exit 2
fi

deploy_root=/volume1/ApplePhotosRuntime/deploy
cd "$deploy_root"

case "${1:-}" in
  authenticate)
    exec docker compose run --rm --entrypoint /opt/allbot/auth.sh icloud-photo-backup
    ;;
  canary)
    exec docker compose run --rm icloud-photo-backup canary
    ;;
  start)
    exec docker compose up -d icloud-photo-backup
    ;;
  status)
    exec docker compose ps
    ;;
  logs)
    exec docker compose logs --tail 100 icloud-photo-backup
    ;;
  stop)
    exec docker compose stop icloud-photo-backup
    ;;
  *)
    echo "usage: operator.sh {authenticate|canary|start|status|logs|stop}" >&2
    exit 2
    ;;
esac
