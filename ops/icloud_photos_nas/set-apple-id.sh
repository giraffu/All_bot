#!/bin/sh
set -eu

umask 077
secret_path=/volume1/ApplePhotosRuntime/secrets/apple-id
secret_dir=$(dirname "$secret_path")
test -d "$secret_dir" || { echo "run bootstrap first" >&2; exit 2; }

printf 'Apple ID email (input is not echoed to logs): ' >&2
IFS= read -r apple_id
case "$apple_id" in
  ''|*[![:graph:]]*) echo "Apple ID must be one non-empty value" >&2; exit 2 ;;
esac

temporary=$(mktemp "$secret_dir/.apple-id.XXXXXX")
trap 'rm -f "$temporary"' EXIT HUP INT TERM
printf '%s\n' "$apple_id" > "$temporary"
chown 1000:100 "$temporary"
chmod 0600 "$temporary"
mv -f "$temporary" "$secret_path"
trap - EXIT HUP INT TERM
echo "Apple ID secret installed with mode 0600"

