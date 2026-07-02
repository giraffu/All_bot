#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REMOTE_HOST="${CLOUD_PROD_REMOTE_HOST:-allbot-do-sgp1-control}"
REMOTE_DIR="${CLOUD_PROD_REMOTE_DIR:-/home/deploy/APP/All_bot}"
LOCAL_ENV_FILE="${CLOUD_PROD_LOCAL_ENV_FILE:-$ROOT_DIR/.env.cloud.prod}"
REMOTE_ENV_FILE=".env.cloud.prod"

EXECUTE=false
CONFIRM_PROD=false
CONFIRM_SINGLE_POLLING=false
SKIP_SYNC=false
SYNC_ENV=false
RSYNC_DELETE=false
SKIP_SAFE_PREFLIGHT=false
SKIP_NETWORK_CHECKS=false
ERROR_REPORTED=false

usage() {
    cat <<'EOF'
Usage:
  scripts/update_cloud_prod_qqcc_bot.sh [options]

Purpose:
  Update only the cloud-production QQCC Telegram Bot service. By default this is
  a dry-run. Real mutation requires --execute --confirm-prod and
  --confirm-single-polling.

What this script does:
  sync local code to the cloud-prod control host, optionally sync .env.cloud.prod,
  run the read-only cloud-prod safe preflight, rebuild/start only qqcc-bot-prod
  with the qqcc-bot compose profile, then verify cloud-qqcc-bot-prod.

What this script never does:
  it does not enable generation maintenance, wait for queue drain, rebuild the
  control plane, restart the main Telegram Bot, touch workers, RunPod, Cloudflare
  Pages, DNS, or edge routing.

Options:
  --execute                    Execute mutations. Without this, print steps only.
  --confirm-prod               Required together with --execute.
  --confirm-single-polling     Required with --execute. Confirms there is no
                               second @QQCC666_bot polling instance outside
                               this target production service.
  --remote-host HOST           SSH host alias. Default: allbot-do-sgp1-control.
  --remote-dir DIR             Remote repo dir. Default: /home/deploy/APP/All_bot.
  --skip-sync                  Do not rsync local code to the remote host.
  --delete                     Delete stale remote files during rsync. Default: off.
  --sync-env                   Explicitly sync local .env.cloud.prod to the remote host.
  --env-file FILE              Local prod env file to sync when --sync-env is set.
  --skip-safe-preflight        Skip scripts/safe_deploy_cloud_prod.sh --preflight-only.
  --skip-network-checks        Pass --skip-network-checks to safe preflight.
  --dry-run                    Explicit no-op alias for the default mode.
  -h, --help                   Show this help.

Environment overrides:
  CLOUD_PROD_REMOTE_HOST, CLOUD_PROD_REMOTE_DIR, CLOUD_PROD_LOCAL_ENV_FILE.
EOF
}

die() {
    echo "ERROR: $*" >&2
    exit 2
}

log() {
    echo
    echo "==> $*"
}

remote_env_prefix() {
    printf 'REMOTE_DIR=%q bash -s' "$REMOTE_DIR"
}

remote_path() {
    local path=$1
    printf '%s:%s/%s' "$REMOTE_HOST" "$REMOTE_DIR" "$path"
}

sha256_file() {
    local file=$1
    sha256sum "$file" | awk '{print $1}'
}

read_local_env_value() {
    local file=$1
    local key=$2
    sed -n "s/^${key}=//p" "$file" | tail -n 1
}

require_local_env_true() {
    local file=$1
    local key=$2
    local value
    value="$(read_local_env_value "$file" "$key")"
    if [ "$value" != "true" ]; then
        die "local env ${file} must set ${key}=true before --sync-env"
    fi
}

remote_sh() {
    local script=$1
    if [ "$EXECUTE" = true ]; then
        ssh -o BatchMode=yes "$REMOTE_HOST" "$(remote_env_prefix)" <<<"$script"
    else
        echo "[dry-run] ssh -o BatchMode=yes ${REMOTE_HOST} \"$(remote_env_prefix)\" <<'REMOTE'"
        printf '%s\n' "$script"
        echo "REMOTE"
    fi
}

run_local() {
    if [ "$EXECUTE" = true ]; then
        "$@"
    else
        printf '[dry-run]'
        printf ' %q' "$@"
        printf '\n'
    fi
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --execute)
            EXECUTE=true
            shift
            ;;
        --confirm-prod)
            CONFIRM_PROD=true
            shift
            ;;
        --confirm-single-polling)
            CONFIRM_SINGLE_POLLING=true
            shift
            ;;
        --remote-host)
            REMOTE_HOST="${2:-}"
            [ -n "$REMOTE_HOST" ] || die "--remote-host requires a value"
            shift 2
            ;;
        --remote-dir)
            REMOTE_DIR="${2:-}"
            [ -n "$REMOTE_DIR" ] || die "--remote-dir requires a value"
            shift 2
            ;;
        --skip-sync)
            SKIP_SYNC=true
            shift
            ;;
        --delete)
            RSYNC_DELETE=true
            shift
            ;;
        --sync-env)
            SYNC_ENV=true
            shift
            ;;
        --env-file)
            LOCAL_ENV_FILE="${2:-}"
            [ -n "$LOCAL_ENV_FILE" ] || die "--env-file requires a value"
            shift 2
            ;;
        --skip-safe-preflight)
            SKIP_SAFE_PREFLIGHT=true
            shift
            ;;
        --skip-network-checks)
            SKIP_NETWORK_CHECKS=true
            shift
            ;;
        --dry-run)
            EXECUTE=false
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "unknown option: $1"
            ;;
    esac
done

preflight() {
    log "QQCC single-service cloud-prod update"
    echo "No generation maintenance, queue drain, control-plane deploy, main Bot, worker, RunPod, or edge routing changes are performed."

    if [ "$EXECUTE" = true ] && [ "$CONFIRM_PROD" != true ]; then
        die "--execute requires --confirm-prod for cloud production"
    fi
    if [ "$EXECUTE" = true ] && [ "$CONFIRM_SINGLE_POLLING" != true ]; then
        die "--execute requires --confirm-single-polling after confirming no second @QQCC666_bot polling instance exists"
    fi
    if [ "$SYNC_ENV" = true ] && [ ! -f "$LOCAL_ENV_FILE" ]; then
        die "local cloud-prod env file not found: $LOCAL_ENV_FILE"
    fi
    if [ "$SYNC_ENV" = true ]; then
        require_local_env_true "$LOCAL_ENV_FILE" "MEMBERSHIP_SETTLEMENT_V2_ENABLED"
        require_local_env_true "$LOCAL_ENV_FILE" "AFFILIATE_MEMBERSHIP_REDEEM_ENABLED"
    fi

    if [ "$EXECUTE" = true ]; then
        command -v ssh >/dev/null || die "ssh is required"
        if [ "$SKIP_SYNC" != true ] || [ "$SYNC_ENV" = true ]; then
            command -v rsync >/dev/null || die "rsync is required"
        fi
        if [ "$SYNC_ENV" = true ]; then
            command -v sha256sum >/dev/null || die "sha256sum is required"
        fi
        ssh -o BatchMode=yes "$REMOTE_HOST" "test -d $(printf %q "$REMOTE_DIR")"
        if [ "$SYNC_ENV" != true ]; then
            ssh -o BatchMode=yes "$REMOTE_HOST" \
                "test -f $(printf %q "$REMOTE_DIR/$REMOTE_ENV_FILE")"
        fi
    else
        echo "Dry-run mode. Re-run with --execute --confirm-prod --confirm-single-polling to mutate cloud production."
        echo "[dry-run] check remote dir on ${REMOTE_HOST}:${REMOTE_DIR}"
        if [ "$SYNC_ENV" = true ]; then
            echo "[dry-run] sync ${LOCAL_ENV_FILE} to ${REMOTE_HOST}:${REMOTE_DIR}/${REMOTE_ENV_FILE}"
        else
            echo "[dry-run] leave remote ${REMOTE_ENV_FILE} unchanged"
        fi
    fi
}

sync_code() {
    if [ "$SKIP_SYNC" = true ]; then
        log "Skip code sync"
        return
    fi

    log "Sync local code to cloud-prod control host"
    local rsync_args=(
        -az
        --stats
        --exclude=.git/
        --exclude=.env
        --exclude=.env.*
        --exclude=.venv/
        --exclude=venv/
        --exclude=ENV/
        --exclude=logs/
        --exclude=runtime/
        --exclude=tmp/
        --exclude=temp/
        --exclude=tg_tmp/
        --exclude=__pycache__/
        --exclude=.pytest_cache/
        --exclude=.ruff_cache/
        --exclude=.mypy_cache/
        --exclude=.coverage
        --exclude=htmlcov/
        --exclude=downloads/
        --exclude=backups/
        --exclude=user_data/
        --exclude=test_data/
        --exclude=templates/temps/
        --exclude=templates/video_nice/
        --exclude=templates/quick_face/
        --exclude=local_analytics_platform/
        --exclude=node_modules/
        --exclude=frontend/node_modules/
        --exclude=frontend/dist/
        --exclude=frontend/ssh_key/
        --exclude=dashboard/frontend/node_modules/
        --exclude=dashboard/frontend/dist/
        --exclude=dashboard/frontend/.vite/
        --exclude=ton_payment_frontend/node_modules/
        --exclude=ton_payment_frontend/dist/
        --exclude=ton_payment_frontend/.vite/
        --exclude=bin/cloudflared
        --exclude='*.pem'
    )
    if [ "$RSYNC_DELETE" = true ]; then
        rsync_args+=(--delete)
    fi
    run_local rsync "${rsync_args[@]}" ./ "${REMOTE_HOST}:${REMOTE_DIR}/"
}

sync_env_file() {
    if [ "$SYNC_ENV" != true ]; then
        log "Leave cloud-prod env file unchanged"
        return
    fi

    log "Sync cloud-prod env file"
    if [ "$EXECUTE" = true ]; then
        ssh -o BatchMode=yes "$REMOTE_HOST" "$(remote_env_prefix)" <<REMOTE
set -euo pipefail
cd "\$REMOTE_DIR"
if [ -f "$REMOTE_ENV_FILE" ]; then
  backup_path="${REMOTE_ENV_FILE}.bak.\$(date +%Y%m%d_%H%M%S)"
  cp -p "$REMOTE_ENV_FILE" "\$backup_path"
  chmod 600 "\$backup_path" || true
  echo "remote prod env backup created"
fi
REMOTE
        rsync -az --chmod=F600 "$LOCAL_ENV_FILE" "$(remote_path "$REMOTE_ENV_FILE")"
        ssh -o BatchMode=yes "$REMOTE_HOST" \
            "chmod 600 $(printf %q "$REMOTE_DIR/$REMOTE_ENV_FILE") && test -s $(printf %q "$REMOTE_DIR/$REMOTE_ENV_FILE")"

        local local_hash
        local remote_hash
        local_hash="$(sha256_file "$LOCAL_ENV_FILE")"
        remote_hash="$(ssh -o BatchMode=yes "$REMOTE_HOST" \
            "sha256sum $(printf %q "$REMOTE_DIR/$REMOTE_ENV_FILE") | cut -d ' ' -f 1")"
        [ "$local_hash" = "$remote_hash" ] || die "remote ${REMOTE_ENV_FILE} checksum does not match local env file"
        echo "cloud-prod env synced"
    else
        printf '[dry-run] rsync -az --chmod=F600 %q %q\n' \
            "$LOCAL_ENV_FILE" \
            "$(remote_path "$REMOTE_ENV_FILE")"
    fi
}

run_safe_preflight() {
    if [ "$SKIP_SAFE_PREFLIGHT" = true ]; then
        log "Skip cloud-prod safe preflight"
        return
    fi

    log "Run cloud-prod safe preflight"
    local args="--preflight-only"
    if [ "$SKIP_NETWORK_CHECKS" = true ]; then
        args+=" --skip-network-checks"
    fi
    remote_sh "$(cat <<REMOTE
set -euo pipefail
cd "\$REMOTE_DIR"
scripts/safe_deploy_cloud_prod.sh $args
REMOTE
)"
}

deploy_qqcc_bot() {
    log "Rebuild and start qqcc-bot-prod only"
    remote_sh "$(cat <<'REMOTE'
set -euo pipefail
cd "$REMOTE_DIR"

docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml --profile qqcc-bot config --services | grep -qx qqcc-bot-prod

if ! grep -q '^QQCC_BOT_TOKEN=.' .env.cloud.prod; then
  echo "QQCC_BOT_TOKEN is required before starting qqcc-bot-prod" >&2
  exit 2
fi

docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml --profile qqcc-bot build qqcc-bot-prod
docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml --profile qqcc-bot up -d --no-deps qqcc-bot-prod
REMOTE
)"
}

verify_qqcc_bot() {
    log "Verify cloud-qqcc-bot-prod"
    remote_sh "$(cat <<'REMOTE'
set -euo pipefail
cd "$REMOTE_DIR"

sleep 8

if ! docker ps --format '{{.Names}}' | grep -qx cloud-qqcc-bot-prod; then
  docker ps -a --filter name=cloud-qqcc-bot-prod --format 'name={{.Names}} status={{.Status}}'
  echo "cloud-qqcc-bot-prod is not running" >&2
  exit 2
fi

status="$(docker inspect -f '{{.State.Status}}' cloud-qqcc-bot-prod)"
restart_count="$(docker inspect -f '{{.RestartCount}}' cloud-qqcc-bot-prod)"
started_at="$(docker inspect -f '{{.State.StartedAt}}' cloud-qqcc-bot-prod)"
echo "cloud-qqcc-bot-prod status=${status} restart_count=${restart_count} started_at=${started_at}"
[ "$status" = "running" ] || exit 2

docker exec cloud-qqcc-bot-prod sh -lc '
  set -eu
  [ "${BOT_TYPE:-}" = "PROD" ]
  [ "${TON_PAYMENT_POLLING_ENABLED:-}" = "false" ]
  [ "${GENERATION_MAINTENANCE_FILE:-}" = "/app/runtime-flags/GENERATION_MAINTENANCE" ]
  [ "${API_BASE:-}" = "http://central-api-prod:8003" ]
'
echo "cloud-qqcc-bot-prod env_contract=ok"

errors="$(docker logs --since 3m cloud-qqcc-bot-prod 2>&1 | grep -Eic 'ERROR|Traceback|Exception' || true)"
echo "cloud-qqcc-bot-prod recent_error_lines=${errors}"
if [ "$errors" -gt 0 ]; then
  echo "cloud-qqcc-bot-prod has recent error lines; inspect remote logs before considering the update healthy" >&2
  exit 2
fi
REMOTE
)"
}

on_error() {
    if [ "$ERROR_REPORTED" = true ]; then
        return
    fi
    ERROR_REPORTED=true
    echo >&2
    echo "ERROR: cloud-prod QQCC Bot update did not complete." >&2
    echo "This script does not touch generation maintenance or other production services." >&2
    echo "Check cloud-qqcc-bot-prod status/logs on ${REMOTE_HOST}:${REMOTE_DIR} before retrying." >&2
}

main() {
    trap on_error ERR

    preflight
    sync_code
    sync_env_file
    run_safe_preflight
    deploy_qqcc_bot
    verify_qqcc_bot

    trap - ERR
    echo
    echo "Cloud-prod QQCC Bot update completed."
}

main "$@"
