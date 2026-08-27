#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "operator must run as root" >&2
  exit 2
fi

deploy_root=/volume1/ApplePhotosGalleryRuntime/deploy
username_file=/volume1/ApplePhotosGalleryRuntime/secrets/admin-username
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
    test -s "$username_file" || { echo "missing gallery administrator username" >&2; exit 2; }
    gallery_user=$(tr -d '\r\n' < "$username_file")
    test -n "$gallery_user" || { echo "empty gallery administrator username" >&2; exit 2; }
    echo "username: $gallery_user"
    echo "password file: /volume1/ApplePhotosGalleryRuntime/secrets/admin-password"
    ;;
  *)
    echo "usage: operator.sh {start|status|logs|stop|credentials}" >&2
    exit 2
    ;;
esac
