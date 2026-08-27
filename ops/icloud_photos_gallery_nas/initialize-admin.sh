#!/bin/sh
set -eu

umask 077

runtime_root=/volume1/ApplePhotosGalleryRuntime
secret_file=$runtime_root/secrets/admin-password
marker=$runtime_root/state/admin-initialized
cookie_file=$runtime_root/state/init-cookie
users_file=$runtime_root/state/init-users.json
gallery_url=http://127.0.0.1:8099
gallery_user=nas-gallery

if [ "$(id -u)" -ne 0 ]; then
  echo "gallery administrator initialization must run as root" >&2
  exit 2
fi
test -s "$secret_file" || { echo "missing gallery administrator secret" >&2; exit 2; }
test ! -e "$marker" || exit 0

gallery_password=$(tr -d '\r\n' < "$secret_file")
test -n "$gallery_password" || { echo "empty gallery administrator secret" >&2; exit 2; }
rm -f "$cookie_file" "$users_file"
trap 'rm -f "$cookie_file" "$users_file"' EXIT HUP INT TERM

printf '%s' '{"loginCredential":{"username":"admin","password":"admin","rememberMe":false}}' |
  curl -fsS -o /dev/null -c "$cookie_file" \
    -H 'Content-Type: application/json' --data-binary @- \
    "$gallery_url/pgapi/user/login"

printf '{"newUser":{"name":"nas-gallery","password":"%s","role":4}}' "$gallery_password" |
  curl -fsS -o /dev/null -b "$cookie_file" -X PUT \
    -H 'Content-Type: application/json' --data-binary @- \
    "$gallery_url/pgapi/user"

rm -f "$cookie_file"
printf '{"loginCredential":{"username":"nas-gallery","password":"%s","rememberMe":false}}' "$gallery_password" |
  curl -fsS -o /dev/null -c "$cookie_file" \
    -H 'Content-Type: application/json' --data-binary @- \
    "$gallery_url/pgapi/user/login"

curl -fsS -b "$cookie_file" "$gallery_url/pgapi/user/list" > "$users_file"
default_admin_id=$(python3 -c '
import json, sys
payload = json.load(sys.stdin)
users = payload.get("result", payload)
matches = [str(user["id"]) for user in users if user.get("name") == "admin"]
if len(matches) != 1:
    raise SystemExit(2)
print(matches[0])
' < "$users_file")

curl -fsS -o /dev/null -b "$cookie_file" -X DELETE \
  "$gallery_url/pgapi/user/$default_admin_id"

curl -fsS -b "$cookie_file" "$gallery_url/pgapi/user/list" > "$users_file"
python3 -c '
import json, sys
payload = json.load(sys.stdin)
users = payload.get("result", payload)
if any(user.get("name") == "admin" for user in users):
    raise SystemExit("upstream default administrator is still active")
matches = [user for user in users if user.get("name") == "nas-gallery" and user.get("role") == 4]
if len(matches) != 1:
    raise SystemExit("replacement gallery administrator is not active")
' < "$users_file"

install -o root -g root -m 0600 /dev/null "$marker"
echo "gallery administrator initialized: $gallery_user"
