#!/usr/bin/env sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
env_path="$project_dir/.env"
credentials_path="$project_dir/.local-admin-credentials"

if [ -e "$env_path" ] || [ -e "$credentials_path" ]; then
  echo "Local credentials already exist; refusing to overwrite them." >&2
  exit 1
fi

umask 077
postgres_password=$(openssl rand -hex 24)
minio_password=$(openssl rand -hex 24)
jwt_secret=$(openssl rand -hex 48)
agent_token=$(openssl rand -hex 48)
phone_hash_secret=$(openssl rand -hex 48)
admin_password=$(openssl rand -base64 24 | tr -d '\n')
admin_email=clarity-admin@example.com

{
  echo "CLARITY_WEB_PORT=8095"
  echo "POSTGRES_PASSWORD=$postgres_password"
  echo "MINIO_ROOT_USER=clarity"
  echo "MINIO_ROOT_PASSWORD=$minio_password"
  echo "CLARITY_JWT_SECRET=$jwt_secret"
  echo "CLARITY_AGENT_TOKEN=$agent_token"
  echo "CLARITY_PHONE_HASH_SECRET=$phone_hash_secret"
  echo "CLARITY_SMS_PROVIDER=disabled"
  echo "CLARITY_ADMIN_EMAIL=$admin_email"
  echo "CLARITY_ADMIN_PASSWORD=$admin_password"
} > "$env_path"

{
  echo "Clarity AI local administrator"
  echo "Email: $admin_email"
  echo "Password: $admin_password"
} > "$credentials_path"

chmod 600 "$env_path" "$credentials_path"
echo "Created .env and .local-admin-credentials with mode 0600."
