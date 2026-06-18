#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REMOTE_HOST="${CLOUD_TEST_REMOTE_HOST:-allbot-do-sgp1-test-control}"
REMOTE_DIR="${CLOUD_TEST_REMOTE_DIR:-/home/deploy/APP/All_bot}"
REMOTE_MAINTENANCE_FILE="runtime/cloud-test/GENERATION_MAINTENANCE"
LOCAL_ENV_FILE="${CLOUD_TEST_LOCAL_ENV_FILE:-$ROOT_DIR/.env.cloud.test}"
REMOTE_ENV_FILE=".env.cloud.test"
DRAIN_TIMEOUT_SECONDS=7200
DRAIN_INTERVAL_SECONDS=15
BOT_MODE="auto"
EXECUTE=false
KEEP_MAINTENANCE=false
SKIP_DRAIN=false
SKIP_SYNC=false
SYNC_ENV=true
SKIP_EDGE_WEB=false
RSYNC_DELETE=true
MAINTENANCE_ACTIVE=false
ERROR_REPORTED=false

usage() {
    cat <<'EOF'
Usage:
  scripts/update_cloud_test_with_maintenance.sh [options]

Purpose:
  Put cloud-test Web/Bot generation entrypoints into maintenance, wait for the
  Central queue to drain, sync local code to the cloud-test control host, rebuild
  cloud-test control-plane containers, optionally deploy the edge test Web app,
  and then disable maintenance after successful verification.

Options:
  --execute                    Execute remote mutations. Without this, print steps only.
  --remote-host HOST           SSH host alias. Default: allbot-do-sgp1-test-control.
  --remote-dir DIR             Remote repo dir. Default: /home/deploy/APP/All_bot.
  --drain-timeout-seconds N    Max wait for pending/running to reach 0. Default: 7200.
  --drain-interval-seconds N   Queue polling interval. Default: 15.
  --skip-drain                 Do not wait for queue drain after enabling maintenance.
  --skip-sync                  Do not rsync local code to the remote host.
  --skip-env-sync              Do not sync local .env.cloud.test to the remote host.
  --env-file FILE              Local cloud-test env file to sync. Default: .env.cloud.test.
  --no-delete                  Do not delete stale remote files during rsync.
  --bot-mode MODE              auto|start|skip|stop. Default: auto.
                               auto rebuilds/starts bot-test only if it was already running.
  --skip-edge-web              Do not run frontend npm run deploy:edge-test.
  --keep-maintenance           Leave generation maintenance enabled after success.
  -h, --help                   Show this help.

Environment overrides:
  CLOUD_TEST_REMOTE_HOST, CLOUD_TEST_REMOTE_DIR, CLOUD_TEST_LOCAL_ENV_FILE,
  SSH_KEY_PATH, EDGE_HOST, EDGE_PORT, EDGE_TEST_DIR are honored by the
  underlying commands.
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
        --skip-sync)
            SKIP_SYNC=true
            shift
            ;;
        --skip-env-sync)
            SYNC_ENV=false
            shift
            ;;
        --env-file)
            LOCAL_ENV_FILE="${2:-}"
            [ -n "$LOCAL_ENV_FILE" ] || die "--env-file requires a value"
            shift 2
            ;;
        --no-delete)
            RSYNC_DELETE=false
            shift
            ;;
        --bot-mode)
            BOT_MODE="${2:-}"
            case "$BOT_MODE" in
                auto|start|skip|stop) ;;
                *) die "--bot-mode must be auto, start, skip, or stop" ;;
            esac
            shift 2
            ;;
        --skip-edge-web)
            SKIP_EDGE_WEB=true
            shift
            ;;
        --keep-maintenance)
            KEEP_MAINTENANCE=true
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

preflight() {
    log "Preflight"
    command -v ssh >/dev/null || die "ssh is required"
    command -v rsync >/dev/null || die "rsync is required"
    command -v sha256sum >/dev/null || die "sha256sum is required"

    if [ "$SYNC_ENV" = true ] && [ ! -f "$LOCAL_ENV_FILE" ]; then
        die "local cloud-test env file not found: $LOCAL_ENV_FILE (pass --skip-env-sync or --env-file)"
    fi

    if [ "$SKIP_EDGE_WEB" = false ]; then
        local edge_key="${SSH_KEY_PATH:-$ROOT_DIR/frontend/ssh_key/id_rsa.pem}"
        if [ "$EXECUTE" = true ] && [ ! -f "$edge_key" ]; then
            die "edge Web deploy key not found: $edge_key (pass --skip-edge-web or set SSH_KEY_PATH)"
        fi
    fi

    if [ "$EXECUTE" = true ]; then
        ssh -o BatchMode=yes "$REMOTE_HOST" "test -d $(printf %q "$REMOTE_DIR")"
        if [ "$SYNC_ENV" != true ]; then
            ssh -o BatchMode=yes "$REMOTE_HOST" \
                "test -f $(printf %q "$REMOTE_DIR/$REMOTE_ENV_FILE")"
        fi
    else
        echo "[dry-run] check remote dir on ${REMOTE_HOST}:${REMOTE_DIR}"
        if [ "$SYNC_ENV" = true ]; then
            echo "[dry-run] sync ${LOCAL_ENV_FILE} to ${REMOTE_HOST}:${REMOTE_DIR}/${REMOTE_ENV_FILE}"
        else
            echo "[dry-run] check remote ${REMOTE_ENV_FILE} on ${REMOTE_HOST}:${REMOTE_DIR}"
        fi
    fi
}

remote_bot_was_running() {
    if [ "$EXECUTE" != true ]; then
        return 1
    fi
    ssh -o BatchMode=yes "$REMOTE_HOST" \
        "docker ps --format '{{.Names}}' | grep -qx cloud-tg-bot-test"
}

enable_maintenance() {
    log "Enable cloud-test generation maintenance"
    remote_sh "$(cat <<'REMOTE'
set -euo pipefail
cd "$REMOTE_DIR"
mkdir -p "$(dirname "$REMOTE_MAINTENANCE_FILE")"
printf '1\n' > "$REMOTE_MAINTENANCE_FILE"
for container in cloud-web-api-test cloud-tg-bot-test; do
  if docker ps --format '{{.Names}}' | grep -qx "$container"; then
    docker exec "$container" sh -lc 'printf "1\n" > /app/GENERATION_MAINTENANCE'
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
    log "Disable cloud-test generation maintenance"
    remote_sh "$(cat <<'REMOTE'
set -euo pipefail
cd "$REMOTE_DIR"
rm -f "$REMOTE_MAINTENANCE_FILE"
for container in cloud-web-api-test cloud-tg-bot-test; do
  if docker ps --format '{{.Names}}' | grep -qx "$container"; then
    if docker exec "$container" sh -lc 'rm -f /app/GENERATION_MAINTENANCE /app/runtime-flags/GENERATION_MAINTENANCE || true'; then
      echo "$container=open"
    else
      echo "$container=maintenance_cleanup_warning"
    fi
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

    log "Wait for cloud-test Central queue drain"
    remote_sh "$(cat <<'REMOTE'
set -euo pipefail

read_queue_counts() {
  docker exec cloud-redis-test sh -lc '
    set -eu
    redis_db="${CLOUD_TEST_WORKER_REDIS_URL##*/}"
    redis_db="${redis_db%%\?*}"
    case "$redis_db" in
      ""|*[!0-9]*) redis_db=0 ;;
    esac
    pending="$(REDISCLI_AUTH="$CLOUD_TEST_REDIS_PASSWORD" redis-cli --raw -n "$redis_db" zcard comfy:queue:pending)"
    running="$(REDISCLI_AUTH="$CLOUD_TEST_REDIS_PASSWORD" redis-cli --raw -n "$redis_db" scard comfy:queue:running)"
    printf "%s %s %s\n" "${pending:-0}" "${running:-0}" "$redis_db"
  '
}

deadline=$(( $(date +%s) + DRAIN_TIMEOUT_SECONDS ))
last_counts=""
while true; do
  counts="$(read_queue_counts)"
  pending_count="$(printf '%s\n' "$counts" | awk '{print $1}')"
  running_count="$(printf '%s\n' "$counts" | awk '{print $2}')"
  redis_db="$(printf '%s\n' "$counts" | awk '{print $3}')"
  if [ "$counts" != "$last_counts" ]; then
    echo "queue db=${redis_db} pending=${pending_count} running=${running_count}"
    last_counts="$counts"
  fi
  if [ "$pending_count" = "0" ] && [ "$running_count" = "0" ]; then
    echo "queue drained"
    exit 0
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "queue drain timed out: db=${redis_db} pending=${pending_count} running=${running_count}" >&2
    exit 2
  fi
  sleep "$DRAIN_INTERVAL_SECONDS"
done
REMOTE
)"
}

sync_env_file() {
    if [ "$SYNC_ENV" != true ]; then
        log "Skip cloud-test env sync by request"
        return
    fi

    log "Sync cloud-test env file"
    if [ "$EXECUTE" = true ]; then
        ssh -o BatchMode=yes "$REMOTE_HOST" "$(remote_env_prefix)" <<REMOTE
set -euo pipefail
cd "\$REMOTE_DIR"
if [ -f "$REMOTE_ENV_FILE" ]; then
  backup_path="${REMOTE_ENV_FILE}.bak.\$(date +%Y%m%d_%H%M%S)"
  cp -p "$REMOTE_ENV_FILE" "\$backup_path"
  chmod 600 "\$backup_path" || true
  echo "remote env backup created"
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
        echo "cloud-test env synced"
    else
        printf '[dry-run] rsync -az --chmod=F600 %q %q\n' \
            "$LOCAL_ENV_FILE" \
            "$(remote_path "$REMOTE_ENV_FILE")"
    fi
}

cleanup_remote_sync_artifacts() {
    log "Clean remote sync artifacts"
    remote_sh "$(cat <<'REMOTE'
set -euo pipefail
cd "$REMOTE_DIR"
rm -rf \
  .venv \
  venv \
  ENV \
  node_modules \
  frontend/node_modules \
  frontend/dist \
  frontend/.vite \
  dashboard/frontend/node_modules \
  dashboard/frontend/dist \
  dashboard/frontend/.vite \
  backups \
  user_data \
  downloads \
  htmlcov \
  test_data \
  templates/temps \
  templates/video_nice \
  templates/quick_face \
  ton_payment_frontend/node_modules \
  ton_payment_frontend/dist \
  ton_payment_frontend/.vite
echo "remote sync artifacts cleaned"
REMOTE
)"
}

sync_code() {
    if [ "$SKIP_SYNC" = true ]; then
        log "Skip code sync by request"
        return
    fi

    log "Sync local code to cloud-test control host"
    cleanup_remote_sync_artifacts
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
        --exclude='*.pem'
    )
    if [ "$RSYNC_DELETE" = true ]; then
        rsync_args+=(--delete)
    fi
    run_local rsync "${rsync_args[@]}" ./ "${REMOTE_HOST}:${REMOTE_DIR}/"
}

deploy_control_plane() {
    log "Rebuild cloud-test control-plane services"
    remote_sh "$(cat <<'REMOTE'
set -euo pipefail
cd "$REMOTE_DIR"
mkdir -p runtime/cloud-test
./scripts/safe_deploy_cloud_test.sh
REMOTE
)"
}

deploy_bot_if_needed() {
    local bot_was_running=$1
    local should_start=false

    case "$BOT_MODE" in
        auto)
            [ "$bot_was_running" = true ] && should_start=true
            ;;
        start)
            should_start=true
            ;;
        skip)
            log "Skip bot-test by request"
            return
            ;;
        stop)
            log "Stop bot-test by request"
            remote_sh "$(cat <<'REMOTE'
set -euo pipefail
cd "$REMOTE_DIR"
if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
else
  COMPOSE_CMD="docker-compose"
fi
$COMPOSE_CMD --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml --profile bot stop bot-test
REMOTE
)"
            return
            ;;
    esac

    if [ "$should_start" != true ]; then
        log "bot-test was not running; keep it stopped"
        return
    fi

    log "Rebuild and start bot-test"
    remote_sh "$(cat <<'REMOTE'
set -euo pipefail
cd "$REMOTE_DIR"
if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
else
  COMPOSE_CMD="docker-compose"
fi
$COMPOSE_CMD --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml --profile bot build bot-test
$COMPOSE_CMD --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml --profile bot up -d --no-deps bot-test
REMOTE
)"
}

deploy_edge_web() {
    if [ "$SKIP_EDGE_WEB" = true ]; then
        log "Skip edge test Web deploy by request"
        return
    fi

    log "Deploy edge test Web frontend"
    run_local bash -lc 'cd frontend && npm run deploy:edge-test'
}

verify_remote() {
    log "Verify cloud-test services"
    remote_sh "$(cat <<'REMOTE'
set -euo pipefail
cd "$REMOTE_DIR"
if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
else
  COMPOSE_CMD="docker-compose"
fi
read_env_value() {
  key=$1
  sed -n "s/^${key}=//p" .env.cloud.test | tail -n 1
}
health_host="${CLOUD_TEST_BIND_IP:-$(read_env_value CLOUD_TEST_BIND_IP)}"
health_host="${health_host:-127.0.0.1}"
if [ "$health_host" = "0.0.0.0" ]; then
  health_host="127.0.0.1"
fi
dashboard_port="${DASHBOARD_FRONTEND_TEST_PORT:-$(read_env_value DASHBOARD_FRONTEND_TEST_PORT)}"
dashboard_port="${dashboard_port:-8087}"
$COMPOSE_CMD --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml ps
curl -fsS "http://${health_host}:8004/health" >/dev/null
echo "central-api-test=healthy"
curl -fsS "http://${health_host}:8001/api/health" >/dev/null
echo "web-api-test=healthy"
curl -fsS "http://${health_host}:8044/api/health" >/dev/null
echo "dashboard-backend-test=healthy"
curl -fsS "http://${health_host}:${dashboard_port}/api/health" >/dev/null
echo "dashboard-frontend-test=healthy"
curl -fsS "http://${health_host}:8004/system/workers" >/dev/null
echo "central-workers=reachable"
docker exec cloud-redis-test sh -lc '
  set -eu
  redis_db="${CLOUD_TEST_WORKER_REDIS_URL##*/}"
  redis_db="${redis_db%%\?*}"
  case "$redis_db" in
    ""|*[!0-9]*) redis_db=0 ;;
  esac
  pending="$(REDISCLI_AUTH="$CLOUD_TEST_REDIS_PASSWORD" redis-cli --raw -n "$redis_db" zcard comfy:queue:pending)"
  running="$(REDISCLI_AUTH="$CLOUD_TEST_REDIS_PASSWORD" redis-cli --raw -n "$redis_db" scard comfy:queue:running)"
  printf "queue db=%s pending=%s running=%s\n" "$redis_db" "${pending:-0}" "${running:-0}"
'
REMOTE
	)"
}

on_error() {
    if [ "$ERROR_REPORTED" = true ]; then
        return
    fi
    ERROR_REPORTED=true
    echo >&2
    echo "ERROR: cloud-test update did not complete." >&2
    if [ "$MAINTENANCE_ACTIVE" = true ]; then
        echo "Generation maintenance is intentionally left enabled. Re-run after fixing the issue," >&2
        echo "or manually remove ${REMOTE_DIR}/${REMOTE_MAINTENANCE_FILE} on ${REMOTE_HOST}." >&2
    else
        echo "Generation maintenance was not marked active by this script; verify remote state before retrying." >&2
    fi
}

main() {
    trap on_error ERR

    if [ "$EXECUTE" != true ]; then
        echo "Dry-run mode. Re-run with --execute to mutate cloud-test."
    fi

    preflight

    local bot_was_running=false
    if remote_bot_was_running; then
        bot_was_running=true
    fi
    echo "bot-test initially running: ${bot_was_running}"

    enable_maintenance
    wait_for_queue_drain
    sync_code
    sync_env_file
    deploy_control_plane
    deploy_bot_if_needed "$bot_was_running"
    deploy_edge_web
    verify_remote

    if [ "$KEEP_MAINTENANCE" = true ]; then
        log "Keep maintenance enabled by request"
    else
        disable_maintenance
    fi

    trap - ERR
    echo
    echo "Cloud-test update completed."
}

main "$@"
