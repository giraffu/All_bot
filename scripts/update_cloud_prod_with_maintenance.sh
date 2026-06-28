#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REMOTE_HOST="${CLOUD_PROD_REMOTE_HOST:-allbot-do-sgp1-control}"
REMOTE_DIR="${CLOUD_PROD_REMOTE_DIR:-/home/deploy/APP/All_bot}"
REMOTE_MAINTENANCE_FILE="runtime/cloud-prod/GENERATION_MAINTENANCE"
LOCAL_ENV_FILE="${CLOUD_PROD_LOCAL_ENV_FILE:-$ROOT_DIR/.env.cloud.prod}"
REMOTE_ENV_FILE=".env.cloud.prod"

DRAIN_TIMEOUT_SECONDS=7200
DRAIN_INTERVAL_SECONDS=15
EXECUTE=false
CONFIRM_PROD=false
KEEP_MAINTENANCE=false
SKIP_DRAIN=false
SKIP_GENERATION_MAINTENANCE=false
SKIP_SYNC=false
SYNC_ENV=false
RSYNC_DELETE=false
WITH_DB_UPGRADE=false
SKIP_NETWORK_CHECKS=false
SKIP_PUBLIC_VERIFY=false
SKIP_LOCAL_RELAY_VERIFY=false
SCOPE="control-plane"
SERVICES=""
BOT_MODE="skip"
BOT_WAS_RUNNING="unknown"
QQCC_BOT_MODE="skip"
QQCC_BOT_WAS_RUNNING="unknown"
MAINTENANCE_ACTIVE=false
ERROR_REPORTED=false

usage() {
    cat <<'EOF'
Usage:
  scripts/update_cloud_prod_with_maintenance.sh [options]

Purpose:
  Conservative cloud-production update helper. By default it is dry-run, does not
  sync .env.cloud.prod, does not touch Telegram Bot, workers, RunPod, Cloudflare
  Pages, DNS, or edge routing. Real mutation requires both --execute and
  --confirm-prod.

Default flow for --scope control-plane:
  enable generation maintenance, wait for Central pending/running queue drain,
  rsync code to allbot-do-sgp1-control, run safe_deploy_cloud_prod.sh preflight,
  rebuild/start control-plane services, verify cloud/internal/public endpoints,
  then disable maintenance after success.

Options:
  --execute                    Execute mutations. Without this, print steps only.
  --confirm-prod               Required together with --execute for any mutation.
  --remote-host HOST           SSH host alias. Default: allbot-do-sgp1-control.
  --remote-dir DIR             Remote repo dir. Default: /home/deploy/APP/All_bot.
  --scope MODE                 preflight-only|control-plane|services. Default: control-plane.
  --services "SVC ..."         With --scope services, build/up only these services.
                               Allowed services exclude bot-prod; use --bot-mode for Bot.
  --skip-generation-maintenance
                               With --scope services, skip generation maintenance and queue drain.
  --with-db-upgrade            Pass --with-db-upgrade to safe_deploy_cloud_prod.sh.
                               Only supported with --scope control-plane.
  --skip-network-checks        Pass --skip-network-checks to safe_deploy_cloud_prod.sh.
  --drain-timeout-seconds N    Max wait for pending/running to reach 0. Default: 7200.
  --drain-interval-seconds N   Queue polling interval. Default: 15.
  --skip-drain                 Do not wait for queue drain after enabling maintenance.
  --skip-sync                  Do not rsync local code to the remote host.
  --delete                     Delete stale remote files during rsync. Default: off.
  --sync-env                   Explicitly sync local .env.cloud.prod to the remote host.
  --env-file FILE              Local prod env file to sync when --sync-env is set.
  --bot-mode MODE              skip|auto|start|stop. Default: skip.
                               auto rebuilds/starts bot-prod only if it was running at start.
  --qqcc-bot-mode MODE         skip|auto|start|stop. Default: skip.
                               auto rebuilds/starts qqcc-bot-prod only if it was running at start.
                               start requires QQCC_BOT_TOKEN in the remote env.
  --keep-maintenance           Leave generation maintenance enabled after success.
  --skip-public-verify         Skip public domain verification.
  --skip-local-relay-verify    Skip local 127.0.0.1:8013 relay verification.
  -h, --help                   Show this help.

Environment overrides:
  CLOUD_PROD_REMOTE_HOST, CLOUD_PROD_REMOTE_DIR, CLOUD_PROD_LOCAL_ENV_FILE.
EOF
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

log() {
    echo
    echo "==> $*"
}

require_int() {
    local name=$1
    local value=$2
    if ! [[ "$value" =~ ^[0-9]+$ ]]; then
        die "$name must be a non-negative integer: $value"
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
        --scope)
            SCOPE="${2:-}"
            case "$SCOPE" in
                preflight-only|control-plane|services) ;;
                *) die "--scope must be preflight-only, control-plane, or services" ;;
            esac
            shift 2
            ;;
        --services)
            SERVICES="${2:-}"
            [ -n "$SERVICES" ] || die "--services requires a value"
            shift 2
            ;;
        --with-db-upgrade)
            WITH_DB_UPGRADE=true
            shift
            ;;
        --skip-network-checks)
            SKIP_NETWORK_CHECKS=true
            shift
            ;;
        --drain-timeout-seconds)
            DRAIN_TIMEOUT_SECONDS="${2:-}"
            require_int "--drain-timeout-seconds" "$DRAIN_TIMEOUT_SECONDS"
            shift 2
            ;;
        --drain-interval-seconds)
            DRAIN_INTERVAL_SECONDS="${2:-}"
            require_int "--drain-interval-seconds" "$DRAIN_INTERVAL_SECONDS"
            [ "$DRAIN_INTERVAL_SECONDS" -gt 0 ] || die "--drain-interval-seconds must be > 0"
            shift 2
            ;;
        --skip-drain)
            SKIP_DRAIN=true
            shift
            ;;
        --skip-generation-maintenance)
            SKIP_GENERATION_MAINTENANCE=true
            shift
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
        --bot-mode)
            BOT_MODE="${2:-}"
            case "$BOT_MODE" in
                skip|auto|start|stop) ;;
                *) die "--bot-mode must be skip, auto, start, or stop" ;;
            esac
            shift 2
            ;;
        --qqcc-bot-mode)
            QQCC_BOT_MODE="${2:-}"
            case "$QQCC_BOT_MODE" in
                skip|auto|start|stop) ;;
                *) die "--qqcc-bot-mode must be skip, auto, start, or stop" ;;
            esac
            shift 2
            ;;
        --keep-maintenance)
            KEEP_MAINTENANCE=true
            shift
            ;;
        --skip-public-verify)
            SKIP_PUBLIC_VERIFY=true
            shift
            ;;
        --skip-local-relay-verify)
            SKIP_LOCAL_RELAY_VERIFY=true
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

remote_env_prefix() {
    printf 'REMOTE_DIR=%q REMOTE_MAINTENANCE_FILE=%q DRAIN_TIMEOUT_SECONDS=%q DRAIN_INTERVAL_SECONDS=%q bash -s' \
        "$REMOTE_DIR" \
        "$REMOTE_MAINTENANCE_FILE" \
        "$DRAIN_TIMEOUT_SECONDS" \
        "$DRAIN_INTERVAL_SECONDS"
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

validate_services() {
    [ "$SCOPE" != "services" ] && return
    [ -n "$SERVICES" ] || die "--scope services requires --services"

    local service
    for service in $SERVICES; do
        case "$service" in
            central-api-prod|web-api-prod|payment-api-prod|dashboard-backend-prod|dashboard-frontend-prod|imgproxy-prod|paid-group-guard-bot-prod|qqcc-bot-prod) ;;
            bot-prod)
                die "do not put bot-prod in --services; use --bot-mode auto|start|stop explicitly"
                ;;
            *)
                die "unsupported production service: $service"
                ;;
        esac
    done
}

preflight() {
    log "Preflight"
    command -v ssh >/dev/null || die "ssh is required"
    command -v rsync >/dev/null || die "rsync is required"
    command -v sha256sum >/dev/null || die "sha256sum is required"

    validate_services

    if [ "$EXECUTE" = true ] && [ "$CONFIRM_PROD" != true ]; then
        die "--execute requires --confirm-prod for cloud production"
    fi
    if [ "$WITH_DB_UPGRADE" = true ] && [ "$SCOPE" != "control-plane" ]; then
        die "--with-db-upgrade is only supported with --scope control-plane"
    fi
    if [ "$SKIP_GENERATION_MAINTENANCE" = true ] && [ "$SCOPE" != "services" ]; then
        die "--skip-generation-maintenance is only supported with --scope services"
    fi
    if [ "$SYNC_ENV" = true ] && [ ! -f "$LOCAL_ENV_FILE" ]; then
        die "local cloud-prod env file not found: $LOCAL_ENV_FILE"
    fi
    if [ "$SYNC_ENV" = true ]; then
        require_local_env_true "$LOCAL_ENV_FILE" "MEMBERSHIP_SETTLEMENT_V2_ENABLED"
        require_local_env_true "$LOCAL_ENV_FILE" "AFFILIATE_MEMBERSHIP_REDEEM_ENABLED"
    fi

    if [ "$EXECUTE" = true ]; then
        ssh -o BatchMode=yes "$REMOTE_HOST" "test -d $(printf %q "$REMOTE_DIR")"
        if [ "$SYNC_ENV" != true ]; then
            ssh -o BatchMode=yes "$REMOTE_HOST" \
                "test -f $(printf %q "$REMOTE_DIR/$REMOTE_ENV_FILE")"
        fi
    else
        echo "Dry-run mode. Re-run with --execute --confirm-prod to mutate cloud production."
        echo "[dry-run] check remote dir on ${REMOTE_HOST}:${REMOTE_DIR}"
        if [ "$SYNC_ENV" = true ]; then
            echo "[dry-run] sync ${LOCAL_ENV_FILE} to ${REMOTE_HOST}:${REMOTE_DIR}/${REMOTE_ENV_FILE}"
        else
            echo "[dry-run] leave remote ${REMOTE_ENV_FILE} unchanged"
        fi
    fi
}

remote_bot_was_running() {
    if [ "$EXECUTE" != true ]; then
        return 1
    fi
    ssh -o BatchMode=yes "$REMOTE_HOST" \
        "docker ps --format '{{.Names}}' | grep -qx cloud-tg-bot-prod"
}

remote_qqcc_bot_was_running() {
    if [ "$EXECUTE" != true ]; then
        return 1
    fi
    ssh -o BatchMode=yes "$REMOTE_HOST" \
        "docker ps --format '{{.Names}}' | grep -qx cloud-qqcc-bot-prod"
}

capture_initial_bot_state() {
    if [ "$BOT_MODE" = "auto" ]; then
        log "Capture initial bot-prod state"
        if [ "$EXECUTE" = true ]; then
            if remote_bot_was_running; then
                BOT_WAS_RUNNING=true
                echo "bot-prod=running"
            else
                BOT_WAS_RUNNING=false
                echo "bot-prod=stopped"
            fi
        else
            echo "[dry-run] query whether cloud-tg-bot-prod is running before deployment"
        fi
    fi

    if [ "$QQCC_BOT_MODE" = "auto" ]; then
        log "Capture initial qqcc-bot-prod state"
        if [ "$EXECUTE" = true ]; then
            if remote_qqcc_bot_was_running; then
                QQCC_BOT_WAS_RUNNING=true
                echo "qqcc-bot-prod=running"
            else
                QQCC_BOT_WAS_RUNNING=false
                echo "qqcc-bot-prod=stopped"
            fi
        else
            echo "[dry-run] query whether cloud-qqcc-bot-prod is running before deployment"
        fi
    fi
}

enable_maintenance() {
    log "Enable cloud-prod generation maintenance"
    remote_sh "$(cat <<'REMOTE'
set -euo pipefail
cd "$REMOTE_DIR"
mkdir -p "$(dirname "$REMOTE_MAINTENANCE_FILE")"
printf '1\n' > "$REMOTE_MAINTENANCE_FILE"
for container in cloud-web-api-prod cloud-tg-bot-prod cloud-qqcc-bot-prod; do
  if docker ps --format '{{.Names}}' | grep -qx "$container"; then
    docker exec "$container" sh -lc '
      set -eu
      printf "1\n" > /app/GENERATION_MAINTENANCE
      if [ -d /app/runtime-flags ]; then
        printf "1\n" > /app/runtime-flags/GENERATION_MAINTENANCE
      fi
    '
    echo "$container=generation_maintenance"
  else
    echo "$container=not_running"
  fi
done
REMOTE
)"
    MAINTENANCE_ACTIVE=true
}

disable_maintenance() {
    log "Disable cloud-prod generation maintenance"
    remote_sh "$(cat <<'REMOTE'
set -euo pipefail
cd "$REMOTE_DIR"
rm -f "$REMOTE_MAINTENANCE_FILE"
for container in cloud-web-api-prod cloud-tg-bot-prod cloud-qqcc-bot-prod; do
  if docker ps --format '{{.Names}}' | grep -qx "$container"; then
    docker exec "$container" sh -lc 'rm -f /app/GENERATION_MAINTENANCE /app/runtime-flags/GENERATION_MAINTENANCE || true'
    echo "$container=open"
  else
    echo "$container=not_running"
  fi
done
REMOTE
)"
    MAINTENANCE_ACTIVE=false
}

wait_for_queue_drain() {
    if [ "$SKIP_DRAIN" = true ]; then
        log "Skip queue drain by request"
        return
    fi

    log "Wait for cloud-prod Central queue drain"
    remote_sh "$(cat <<'REMOTE'
set -euo pipefail

read_queue_counts() {
  container=""
  for candidate in cloud-central-api-prod cloud-web-api-prod; do
    if docker ps --format '{{.Names}}' | grep -qx "$candidate"; then
      container="$candidate"
      break
    fi
  done
  [ -n "$container" ] || { echo "no running Central/Web container for Redis queue check" >&2; exit 2; }
  docker exec -i "$container" python - <<'PY'
import os
import redis

url = os.environ.get("WORKER_REDIS_URL") or os.environ.get("REDIS_URL")
if not url:
    raise SystemExit("missing WORKER_REDIS_URL/REDIS_URL in container env")
client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=5, socket_timeout=10)
print(client.zcard("comfy:queue:pending"), client.scard("comfy:queue:running"))
PY
}

deadline=$(( $(date +%s) + DRAIN_TIMEOUT_SECONDS ))
last_counts=""
while true; do
  counts="$(read_queue_counts)"
  pending_count="$(printf '%s\n' "$counts" | awk '{print $1}')"
  running_count="$(printf '%s\n' "$counts" | awk '{print $2}')"
  if [ "$counts" != "$last_counts" ]; then
    echo "queue pending=${pending_count} running=${running_count}"
    last_counts="$counts"
  fi
  if [ "$pending_count" = "0" ] && [ "$running_count" = "0" ]; then
    echo "queue drained"
    exit 0
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "queue drain timed out: pending=${pending_count} running=${running_count}" >&2
    exit 2
  fi
  sleep "$DRAIN_INTERVAL_SECONDS"
done
REMOTE
)"
}

sync_code() {
    if [ "$SKIP_SYNC" = true ] || [ "$SCOPE" = "preflight-only" ]; then
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

run_prod_preflight() {
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

deploy_control_plane() {
    log "Deploy cloud-prod control plane"
    local args="--start-control-plane"
    if [ "$WITH_DB_UPGRADE" = true ]; then
        args+=" --with-db-upgrade"
    fi
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

deploy_services() {
    [ "$SCOPE" = "services" ] || return
    log "Deploy selected cloud-prod services"
    remote_sh "$(cat <<REMOTE
set -euo pipefail
cd "\$REMOTE_DIR"
docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml build $SERVICES
docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml up -d --no-deps $SERVICES
if printf '%s\n' "$SERVICES" | grep -qw dashboard-backend-prod; then
  if docker ps --format '{{.Names}}' | grep -qx cloud-dashboard-frontend-prod; then
    docker exec cloud-dashboard-frontend-prod nginx -s reload || true
  fi
fi
REMOTE
)"
}

deploy_bot_if_requested() {
    case "$BOT_MODE" in
        skip)
            log "Skip bot-prod"
            return
            ;;
        stop)
            log "Stop bot-prod by request"
            remote_sh "$(cat <<'REMOTE'
set -euo pipefail
cd "$REMOTE_DIR"
docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml --profile bot stop bot-prod
REMOTE
)"
            return
            ;;
    esac

    local should_start=false
    case "$BOT_MODE" in
        auto)
            if [ "$EXECUTE" != true ]; then
                log "bot-prod auto mode would use the initial running/stopped snapshot"
                return
            fi
            if [ "$BOT_WAS_RUNNING" = true ]; then
                should_start=true
            fi
            ;;
        start)
            should_start=true
            ;;
    esac

    if [ "$should_start" != true ]; then
        log "bot-prod was not running; keep it stopped"
        return
    fi

    log "Rebuild and start bot-prod"
    remote_sh "$(cat <<'REMOTE'
set -euo pipefail
cd "$REMOTE_DIR"
docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml --profile bot build bot-prod
docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml --profile bot up -d --no-deps bot-prod
REMOTE
)"
}

deploy_qqcc_bot_if_requested() {
    case "$QQCC_BOT_MODE" in
        skip)
            log "Skip qqcc-bot-prod"
            return
            ;;
        stop)
            log "Stop qqcc-bot-prod by request"
            remote_sh "$(cat <<'REMOTE'
set -euo pipefail
cd "$REMOTE_DIR"
docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml --profile qqcc-bot stop qqcc-bot-prod
REMOTE
)"
            return
            ;;
    esac

    local should_start=false
    case "$QQCC_BOT_MODE" in
        auto)
            if [ "$EXECUTE" != true ]; then
                log "qqcc-bot-prod auto mode would use the initial running/stopped snapshot"
                return
            fi
            if [ "$QQCC_BOT_WAS_RUNNING" = true ]; then
                should_start=true
            fi
            ;;
        start)
            should_start=true
            ;;
    esac

    if [ "$should_start" != true ]; then
        log "qqcc-bot-prod was not running; keep it stopped"
        return
    fi

    log "Rebuild and start qqcc-bot-prod"
    remote_sh "$(cat <<'REMOTE'
set -euo pipefail
cd "$REMOTE_DIR"
if ! grep -q '^QQCC_BOT_TOKEN=.' .env.cloud.prod; then
  echo "QQCC_BOT_TOKEN is required before starting qqcc-bot-prod" >&2
  exit 2
fi
docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml --profile qqcc-bot build qqcc-bot-prod
docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml --profile qqcc-bot up -d --no-deps qqcc-bot-prod
REMOTE
)"
}

verify_remote() {
    log "Verify cloud-prod services"
    remote_sh "$(cat <<'REMOTE'
set -euo pipefail
cd "$REMOTE_DIR"
docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml ps

read_env_value() {
  key=$1
  sed -n "s/^${key}=//p" .env.cloud.prod | tail -n 1
}
health_host="${CLOUD_PROD_BIND_IP:-$(read_env_value CLOUD_PROD_BIND_IP)}"
health_host="${health_host:-127.0.0.1}"
if [ "$health_host" = "0.0.0.0" ]; then
  health_host="127.0.0.1"
fi
dashboard_port="${DASHBOARD_FRONTEND_PORT:-$(read_env_value DASHBOARD_FRONTEND_PORT)}"
dashboard_port="${dashboard_port:-8086}"

curl --noproxy '*' -fsS "http://${health_host}:8003/health" >/dev/null
echo "central-api-prod=healthy"
curl --noproxy '*' -fsS "http://${health_host}:8000/api/health" >/dev/null
echo "web-api-prod=healthy"
curl --noproxy '*' -fsS "http://${health_host}:8021/pay/result" >/dev/null
echo "payment-api-prod=healthy"
curl --noproxy '*' -fsS "http://${health_host}:8043/api/health" >/dev/null
echo "dashboard-backend-prod=healthy"
curl --noproxy '*' -fsS "http://${health_host}:${dashboard_port}/api/health" >/dev/null
echo "dashboard-frontend-prod=healthy"
curl --noproxy '*' -fsS "http://${health_host}:8003/system/status" >/dev/null
echo "central-status=reachable"
curl --noproxy '*' -fsS "http://${health_host}:8003/system/workers" >/dev/null
echo "central-workers=reachable"

container=""
for candidate in cloud-central-api-prod cloud-web-api-prod; do
  if docker ps --format '{{.Names}}' | grep -qx "$candidate"; then
    container="$candidate"
    break
  fi
done
[ -n "$container" ] || { echo "no running Central/Web container for Redis queue check" >&2; exit 2; }
docker exec -i "$container" python - <<'PY'
import os
import redis

url = os.environ.get("WORKER_REDIS_URL") or os.environ.get("REDIS_URL")
client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=5, socket_timeout=10)
print(f"queue pending={client.zcard('comfy:queue:pending')} running={client.scard('comfy:queue:running')}")
PY

for c in cloud-central-api-prod cloud-web-api-prod cloud-payment-api-prod cloud-dashboard-backend-prod cloud-dashboard-frontend-prod cloud-imgproxy-prod cloud-paid-group-guard-bot-prod cloud-qqcc-bot-prod; do
  if docker ps -a --format '{{.Names}}' | grep -qx "$c"; then
    docker inspect -f "$c restart_count={{.RestartCount}} status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}" "$c"
    errors="$(docker logs --since 5m "$c" 2>&1 | grep -Eic 'ERROR|Traceback|Exception' || true)"
    echo "$c recent_error_lines=$errors"
  fi
done
REMOTE
)"
}

verify_public_endpoints() {
    if [ "$SKIP_PUBLIC_VERIFY" = true ]; then
        log "Skip public endpoint verification"
        return
    fi
    log "Verify public production endpoints"
    run_local curl -fsS -o /dev/null https://web.aivison.it.com
    run_local curl -fsS -o /dev/null https://api.aivison.it.com/api/health
    run_local curl -fsS -o /dev/null https://rmb.aivison.it.com/pay/result
}

verify_local_relay() {
    if [ "$SKIP_LOCAL_RELAY_VERIFY" = true ]; then
        log "Skip local relay verification"
        return
    fi
    log "Verify local production worker relay"
    run_local curl --noproxy '*' -fsS -o /dev/null http://127.0.0.1:8013/health
}

on_error() {
    if [ "$ERROR_REPORTED" = true ]; then
        return
    fi
    ERROR_REPORTED=true
    echo >&2
    echo "ERROR: cloud-prod update did not complete." >&2
    if [ "$MAINTENANCE_ACTIVE" = true ]; then
        echo "Generation maintenance is intentionally left enabled. Re-run after fixing the issue," >&2
        echo "or manually remove ${REMOTE_DIR}/${REMOTE_MAINTENANCE_FILE} on ${REMOTE_HOST} after verification." >&2
    elif [ "$SKIP_GENERATION_MAINTENANCE" = true ]; then
        echo "Generation maintenance was intentionally skipped for this services-only update." >&2
    else
        echo "Generation maintenance was not marked active by this script; verify remote state before retrying." >&2
    fi
}

main() {
    trap on_error ERR

    preflight

    if [ "$SCOPE" = "preflight-only" ]; then
        run_prod_preflight
        trap - ERR
        echo
        echo "Cloud-prod preflight completed."
        return
    fi

    capture_initial_bot_state
    if [ "$SKIP_GENERATION_MAINTENANCE" = true ]; then
        log "Skip generation maintenance and queue drain"
    else
        enable_maintenance
        wait_for_queue_drain
    fi
    sync_code
    sync_env_file
    run_prod_preflight

    case "$SCOPE" in
        control-plane)
            deploy_control_plane
            ;;
        services)
            deploy_services
            ;;
    esac

    deploy_bot_if_requested
    deploy_qqcc_bot_if_requested
    verify_remote
    verify_public_endpoints
    verify_local_relay

    if [ "$KEEP_MAINTENANCE" = true ]; then
        log "Keep maintenance enabled by request"
    elif [ "$SKIP_GENERATION_MAINTENANCE" = true ]; then
        log "Generation maintenance was skipped"
    else
        disable_maintenance
    fi

    trap - ERR
    echo
    echo "Cloud-prod update completed."
}

main "$@"
