#!/bin/sh
set -eu

confirm_expected=LOAD_PIGALLERY_OFFLINE_IMAGE
offline_image=sha256:074da989a73e4e26d666c89989272b3b76c1d63a92a4e99e82fd98e8f7d36189
archive=
archive_sha256=
confirm=
execute=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --archive)
      shift
      test "$#" -gt 0 || { echo "--archive requires a value" >&2; exit 2; }
      archive=$1
      ;;
    --archive-sha256)
      shift
      test "$#" -gt 0 || { echo "--archive-sha256 requires a value" >&2; exit 2; }
      archive_sha256=$1
      ;;
    --execute) execute=true ;;
    --confirm)
      shift
      test "$#" -gt 0 || { echo "--confirm requires a value" >&2; exit 2; }
      confirm=$1
      ;;
    *)
      echo "usage: load-offline-image.sh --archive PATH --archive-sha256 SHA256 [--execute --confirm $confirm_expected]" >&2
      exit 2
      ;;
  esac
  shift
done

case "$archive_sha256" in
  ''|*[!0-9a-f]*) echo "archive SHA-256 must be lowercase hexadecimal" >&2; exit 2 ;;
esac
if [ "${#archive_sha256}" -ne 64 ]; then
  echo "archive SHA-256 must contain 64 characters" >&2
  exit 2
fi
test -n "$archive" || { echo "--archive is required" >&2; exit 2; }

if [ "$execute" != true ]; then
  echo "dry-run: verify $archive as $archive_sha256 and load $offline_image"
  exit 0
fi
if [ "$confirm" != "$confirm_expected" ]; then
  echo "exact confirmation required: $confirm_expected" >&2
  exit 2
fi
if [ "$(id -u)" -ne 0 ]; then
  echo "offline image load must run as root" >&2
  exit 2
fi
test -f "$archive" || { echo "offline image archive is missing" >&2; exit 2; }

actual_sha256=$(sha256sum "$archive" | awk '{print $1}')
if [ "$actual_sha256" != "$archive_sha256" ]; then
  echo "offline image archive SHA-256 mismatch" >&2
  exit 2
fi
gzip -t "$archive"
gzip -dc "$archive" | docker load

loaded_id=$(docker image inspect --format '{{.Id}}' "$offline_image" 2>/dev/null || true)
if [ "$loaded_id" != "$offline_image" ]; then
  echo "loaded image ID does not match approved identity" >&2
  exit 2
fi
echo "offline image verified and loaded: $offline_image"

