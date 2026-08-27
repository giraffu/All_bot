#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "operator must run as root" >&2
  exit 2
fi

deploy_root=/volume1/ApplePhotosGalleryRuntime/deploy
cd "$deploy_root"

case "${1:-}" in
  start)
    exec docker compose up -d --force-recreate
    ;;
  status)
    exec docker compose ps
    ;;
  logs)
    exec docker compose logs --tail 100 icloud-photos-gallery
    ;;
  stop)
    exec docker compose stop icloud-photos-gallery
    ;;
  credentials)
    echo "username: nas-gallery"
    echo "password file: /volume1/ApplePhotosGalleryRuntime/secrets/admin-password"
    ;;
  *)
    echo "usage: operator.sh {start|status|logs|stop|credentials}" >&2
    exit 2
    ;;
esac

