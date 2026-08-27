#!/bin/sh
set -eu

confirm_expected=CREATE_ICLOUD_PHOTOS_PREVIEW_GALLERY
online_image=docker.io/bpatrik/pigallery2@sha256:d7a61b6daa410537064d4f661122545bc4d9b16cd91a3862d654c3555cb63992
offline_image=sha256:074da989a73e4e26d666c89989272b3b76c1d63a92a4e99e82fd98e8f7d36189
gallery_image=${PIGALLERY_IMAGE:-$online_image}
execute=false
confirm=

case "$gallery_image" in
  "$online_image"|"$offline_image") ;;
  *) echo "PIGALLERY_IMAGE must be the approved registry digest or offline image ID" >&2; exit 2 ;;
esac

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

originals=/volume1/ApplePhotos/originals
runtime_root=/volume1/ApplePhotosGalleryRuntime
config_root=$runtime_root/config
db_root=$runtime_root/db
tmp_root=$runtime_root/tmp
secrets_root=$runtime_root/secrets
state_root=$runtime_root/state
deploy_root=$runtime_root/deploy
secret_file=$secrets_root/admin-password
username_file=$secrets_root/admin-username
default_gallery_user=nas-gallery
marker=$state_root/admin-initialized
source_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ "$execute" != true ]; then
  echo "dry-run: create read-only iCloud Photos preview gallery"
  echo "media source: $originals (read_only)"
  echo "initialization endpoint: http://127.0.0.1:8099"
  echo "LAN endpoint after initialization: http://192.168.1.150:8099"
  echo "runtime: $runtime_root"
  exit 0
fi

if [ "$confirm" != "$confirm_expected" ]; then
  echo "exact confirmation required: $confirm_expected" >&2
  exit 2
fi
if [ "$(id -u)" -ne 0 ]; then
  echo "gallery bootstrap execute must run as root" >&2
  exit 2
fi
test -d "$originals" || { echo "iCloud originals directory is missing" >&2; exit 2; }
for command in curl docker openssl python3; do
  command -v "$command" >/dev/null 2>&1 || { echo "missing required command: $command" >&2; exit 2; }
done

used_percent=$(df -P /volume1 | awk 'NR == 2 {gsub(/%/, "", $5); print $5}')
case "$used_percent" in
  ''|*[!0-9]*) echo "cannot determine /volume1 capacity" >&2; exit 2 ;;
esac
if [ "$used_percent" -ge 80 ]; then
  echo "capacity gate reached (${used_percent}% used)" >&2
  exit 2
fi

install -d -o root -g root -m 0750 "$runtime_root"
install -d -o 1000 -g 100 -m 0700 "$config_root" "$db_root" "$tmp_root"
install -d -o root -g root -m 0700 "$secrets_root" "$state_root"
install -d -o root -g root -m 0755 "$deploy_root"

install -o root -g root -m 0644 "$source_root/compose.yml" "$deploy_root/compose.yml"
for script in bootstrap.sh initialize-admin.sh load-offline-image.sh operator.sh; do
  install -o root -g root -m 0755 "$source_root/$script" "$deploy_root/$script"
done

if [ ! -s "$secret_file" ]; then
  openssl rand -base64 24 | tr -d '\r\n' > "$secret_file"
  printf '\n' >> "$secret_file"
fi
chown root:root "$secret_file"
chmod 0600 "$secret_file"
if [ ! -s "$username_file" ]; then
  printf '%s\n' "$default_gallery_user" > "$username_file"
fi
chown root:root "$username_file"
chmod 0600 "$username_file"

write_env() {
  bind_ip=$1
  public_url=$2
  candidate=$deploy_root/.env.candidate
  {
    printf 'PIGALLERY_IMAGE=%s\n' "$gallery_image"
    printf 'GALLERY_BIND_IP=%s\n' "$bind_ip"
    printf 'GALLERY_PUBLIC_URL=%s\n' "$public_url"
  } > "$candidate"
  chown root:root "$candidate"
  chmod 0600 "$candidate"
  mv -f "$candidate" "$deploy_root/.env"
}

if [ "$gallery_image" = "$offline_image" ]; then
  loaded_id=$(docker image inspect --format '{{.Id}}' "$gallery_image" 2>/dev/null || true)
  if [ "$loaded_id" != "$offline_image" ]; then
    echo "approved offline image is not loaded: $offline_image" >&2
    exit 2
  fi
else
  PIGALLERY_IMAGE=$gallery_image docker compose -f "$deploy_root/compose.yml" pull icloud-photos-gallery
fi

wait_healthy() {
  attempts=0
  while [ "$attempts" -lt 60 ]; do
    health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' allbot-icloud-photos-gallery 2>/dev/null || true)
    test "$health" = healthy && return 0
    attempts=$((attempts + 1))
    sleep 2
  done
  echo "gallery did not become healthy" >&2
  docker compose -f "$deploy_root/compose.yml" logs --tail 100 icloud-photos-gallery >&2 || true
  return 2
}

if [ ! -e "$marker" ]; then
  write_env 127.0.0.1 http://127.0.0.1:8099
  docker compose -f "$deploy_root/compose.yml" up -d --force-recreate icloud-photos-gallery
  wait_healthy
  "$deploy_root/initialize-admin.sh"
fi

write_env 192.168.1.150 http://192.168.1.150:8099
docker compose -f "$deploy_root/compose.yml" up -d --force-recreate icloud-photos-gallery
wait_healthy

echo "gallery ready: http://192.168.1.150:8099"
echo "credentials: sudo $deploy_root/operator.sh credentials"
