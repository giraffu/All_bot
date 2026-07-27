#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REMOTE_HOST="${REMOTE_HOST:-allbot-do-sgp1-control}"
REMOTE_DIR="${REMOTE_DIR:-/home/deploy/APP/All_bot}"
CLOUD_TEST_ENV="${CLOUD_TEST_ENV:-.env.cloud.test}"
EXECUTE=false

usage() {
    cat <<'EOF'
Usage: scripts/cleanup_cloud_test_for_prod.sh [--dry-run] [--execute]

Retire the cloud test runtime before using the cloud host only for production.

Default mode is --dry-run. Real cleanup requires --execute.

This script:
  - removes cloud *-test containers on allbot-do-sgp1-control
  - drops the managed PostgreSQL database bot_db_test
  - flushes managed Valkey DB3 and DB4
  - removes local cloud-comfy-agent-test-* containers

This script does NOT:
  - touch production local containers or production Redis/PostgreSQL/MinIO
  - delete the R2 user-data-test bucket
  - start cloud production services or cloud-tg-bot-prod
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run)
            EXECUTE=false
            ;;
        --execute)
            EXECUTE=true
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage
            exit 2
            ;;
    esac
    shift
done

mode_label() {
    if [ "$EXECUTE" = "true" ]; then
        echo "execute"
    else
        echo "dry-run"
    fi
}

log() {
    printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"
}

remote() {
    ssh -o BatchMode=yes "$REMOTE_HOST" "$@"
}

remote_allbot() {
    remote "cd '$REMOTE_DIR' && $*"
}

list_local_cloud_test_workers() {
    docker ps -a --format '{{.Names}}' | grep '^cloud-comfy-agent-test-' || true
}

remove_local_cloud_test_workers() {
    local names
    names="$(list_local_cloud_test_workers)"
    if [ -z "$names" ]; then
        echo "No local cloud-comfy-agent-test-* containers found."
        return
    fi

    echo "$names"
    if [ "$EXECUTE" = "true" ]; then
        echo "$names" | xargs -r docker rm -f
    else
        echo "[dry-run] would remove local containers listed above."
    fi
}

list_remote_cloud_test_containers() {
    remote "docker ps -a --format '{{.Names}}' | grep '^cloud-.*-test$' || true"
}

remote_test_tool_image_command() {
    cat <<'EOF'
if docker inspect cloud-web-api-test >/dev/null 2>&1; then
    docker inspect -f '{{.Config.Image}}' cloud-web-api-test
elif docker image inspect deploy-web-api-test:latest >/dev/null 2>&1; then
    echo deploy-web-api-test:latest
else
    docker image ls --format '{{.Repository}}:{{.Tag}}' | grep -E 'web-api-test|deploy-web-api-test' | head -n 1
fi
EOF
}

require_remote_test_tool_image() {
    remote_allbot "$(remote_test_tool_image_command) | grep -v '^$' | head -n 1"
}

remove_remote_cloud_test_containers_except_web_api() {
    local names
    names="$(
        remote "docker ps -a --format '{{.Names}}' | grep '^cloud-.*-test$' | grep -v '^cloud-web-api-test$' || true"
    )"
    if [ -z "$names" ]; then
        echo "No remote cloud test containers except cloud-web-api-test found."
        return
    fi

    echo "$names"
    if [ "$EXECUTE" = "true" ]; then
        remote "docker ps -a --format '{{.Names}}' | grep '^cloud-.*-test$' | grep -v '^cloud-web-api-test$' | xargs -r docker rm -f"
    else
        echo "[dry-run] would remove remote containers listed above."
    fi
}

remove_remote_remaining_cloud_test_containers() {
    local names
    names="$(list_remote_cloud_test_containers)"
    if [ -z "$names" ]; then
        echo "No remaining remote cloud test containers found."
        return
    fi

    echo "$names"
    if [ "$EXECUTE" = "true" ]; then
        remote "docker ps -a --format '{{.Names}}' | grep '^cloud-.*-test$' | xargs -r docker rm -f"
    else
        echo "[dry-run] would remove remaining remote containers listed above."
    fi
}

stop_remote_web_api_test_for_cleanup() {
    if [ "$EXECUTE" != "true" ]; then
        echo "[dry-run] would stop cloud-web-api-test before dropping bot_db_test."
        return
    fi

    remote "docker stop cloud-web-api-test >/dev/null 2>&1 || true"
    echo "cloud-web-api-test stopped for data cleanup."
}

check_remote_env() {
    remote_allbot "test -f '$CLOUD_TEST_ENV'"
}

print_remote_env_summary() {
    remote_allbot "python3 - '$CLOUD_TEST_ENV' <<'PY'
from pathlib import Path
import sys
from urllib.parse import urlparse

path = Path(sys.argv[1])
values = {}
for line in path.read_text(errors='ignore').splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith('#') or '=' not in stripped:
        continue
    key, value = stripped.split('=', 1)
    values[key.strip()] = value.strip().strip('\"').strip(\"'\")

for key in (
    'CLOUD_TEST_BIND_IP',
    'CLOUD_TEST_TAILSCALE_IP',
    'MINIO_BUCKET',
    'R2_BUCKET',
    'R2_PUBLIC_DOMAIN',
):
    print(f'{key}={values.get(key, \"missing\") or \"empty\"}')

for key in ('CLOUD_TEST_DATABASE_URL', 'CLOUD_TEST_REDIS_URL', 'CLOUD_TEST_WORKER_REDIS_URL'):
    value = values.get(key)
    if not value:
        print(f'{key}=missing')
        continue
    parsed = urlparse(value.replace('postgresql+asyncpg://', 'postgresql://'))
    if key == 'CLOUD_TEST_DATABASE_URL':
        print(f'{key}=set database={(parsed.path or \"/\").lstrip(\"/\") or \"unknown\"}')
    else:
        print(f'{key}=set db={(parsed.path or \"/\").lstrip(\"/\") or \"0\"}')
PY"
}

print_remote_test_db_summary() {
    if remote "docker inspect cloud-web-api-test >/dev/null 2>&1"; then
        remote_allbot "docker exec -i cloud-web-api-test python - <<'PY'
import asyncio
import os
import ssl
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import asyncpg


def normalize(url: str) -> str:
    return url.replace('postgresql+asyncpg://', 'postgresql://', 1)


def build_asyncpg_connect_args(url: str, database: str) -> tuple[str, dict]:
    parsed = urlparse(normalize(url))
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    ssl_enabled = any(key in {'ssl', 'sslmode'} for key, _value in query_items)
    safe_query = urlencode(
        [(key, value) for key, value in query_items if key not in {'ssl', 'sslmode'}]
    )
    connect_url = urlunparse(parsed._replace(path='/' + database, query=safe_query))
    kwargs = {'ssl': ssl._create_unverified_context()} if ssl_enabled else {}
    return connect_url, kwargs


async def main() -> None:
    raw_url = os.environ.get('CLOUD_TEST_DATABASE_URL') or os.environ.get('DATABASE_URL')
    if not raw_url:
        raise SystemExit('CLOUD_TEST_DATABASE_URL is missing in cloud-web-api-test')

    target_url = normalize(raw_url)
    parsed = urlparse(target_url)
    target_db = (parsed.path or '').lstrip('/')
    print(f'target_database={target_db or \"missing\"}')
    if target_db != 'bot_db_test':
        raise SystemExit(f'refusing to inspect unexpected database: {target_db!r}')

    maintenance_db = os.environ.get('CLOUD_TEST_MAINTENANCE_DB', 'defaultdb')
    maintenance_url, connect_kwargs = build_asyncpg_connect_args(target_url, maintenance_db)
    conn = await asyncpg.connect(maintenance_url, **connect_kwargs)
    try:
        exists = await conn.fetchval(
            'SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = \$1)',
            target_db,
        )
        print(f'target_exists={bool(exists)}')
        if not exists:
            return
        rows = await conn.fetchval(
            \"SELECT count(*) FROM pg_stat_activity WHERE datname = \$1\",
            target_db,
        )
        print(f'active_connections={rows}')
    finally:
        await conn.close()


asyncio.run(main())
PY"
        return
    fi

    remote_allbot "image=\$($(remote_test_tool_image_command)); test -n \"\$image\"; docker run --rm -i --env-file '$CLOUD_TEST_ENV' \"\$image\" python - <<'PY'
import asyncio
import os
import ssl
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import asyncpg


def normalize(url: str) -> str:
    return url.replace('postgresql+asyncpg://', 'postgresql://', 1)


def build_asyncpg_connect_args(url: str, database: str) -> tuple[str, dict]:
    parsed = urlparse(normalize(url))
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    ssl_enabled = any(key in {'ssl', 'sslmode'} for key, _value in query_items)
    safe_query = urlencode(
        [(key, value) for key, value in query_items if key not in {'ssl', 'sslmode'}]
    )
    connect_url = urlunparse(parsed._replace(path='/' + database, query=safe_query))
    kwargs = {'ssl': ssl._create_unverified_context()} if ssl_enabled else {}
    return connect_url, kwargs


async def main() -> None:
    raw_url = os.environ.get('CLOUD_TEST_DATABASE_URL') or os.environ.get('DATABASE_URL')
    if not raw_url:
        raise SystemExit('CLOUD_TEST_DATABASE_URL is missing in cloud test env')

    target_url = normalize(raw_url)
    parsed = urlparse(target_url)
    target_db = (parsed.path or '').lstrip('/')
    print(f'target_database={target_db or \"missing\"}')
    if target_db != 'bot_db_test':
        raise SystemExit(f'refusing to inspect unexpected database: {target_db!r}')

    maintenance_db = os.environ.get('CLOUD_TEST_MAINTENANCE_DB', 'defaultdb')
    maintenance_url, connect_kwargs = build_asyncpg_connect_args(target_url, maintenance_db)
    conn = await asyncpg.connect(maintenance_url, **connect_kwargs)
    try:
        exists = await conn.fetchval(
            'SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = \$1)',
            target_db,
        )
        print(f'target_exists={bool(exists)}')
        if not exists:
            return
        rows = await conn.fetchval(
            \"SELECT count(*) FROM pg_stat_activity WHERE datname = \$1\",
            target_db,
        )
        print(f'active_connections={rows}')
    finally:
        await conn.close()


asyncio.run(main())
PY"
}

drop_remote_test_db() {
    if [ "$EXECUTE" != "true" ]; then
        print_remote_test_db_summary
        echo "[dry-run] would terminate connections and DROP DATABASE bot_db_test."
        return
    fi

    remote_allbot "image=\$($(remote_test_tool_image_command)); test -n \"\$image\"; docker run --rm -i --env-file '$CLOUD_TEST_ENV' -e CLEANUP_EXECUTE=true \"\$image\" python - <<'PY'
import asyncio
import os
import ssl
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import asyncpg


def quote_ident(identifier: str) -> str:
    return '\"' + identifier.replace('\"', '\"\"') + '\"'


def normalize(url: str) -> str:
    return url.replace('postgresql+asyncpg://', 'postgresql://', 1)


def build_asyncpg_connect_args(url: str, database: str) -> tuple[str, dict]:
    parsed = urlparse(normalize(url))
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    ssl_enabled = any(key in {'ssl', 'sslmode'} for key, _value in query_items)
    safe_query = urlencode(
        [(key, value) for key, value in query_items if key not in {'ssl', 'sslmode'}]
    )
    connect_url = urlunparse(parsed._replace(path='/' + database, query=safe_query))
    kwargs = {'ssl': ssl._create_unverified_context()} if ssl_enabled else {}
    return connect_url, kwargs


async def main() -> None:
    raw_url = os.environ.get('CLOUD_TEST_DATABASE_URL') or os.environ.get('DATABASE_URL')
    if not raw_url:
        raise SystemExit('CLOUD_TEST_DATABASE_URL is missing in cloud-web-api-test')

    target_url = normalize(raw_url)
    parsed = urlparse(target_url)
    target_db = (parsed.path or '').lstrip('/')
    print(f'target_database={target_db}')
    if target_db != 'bot_db_test':
        raise SystemExit(f'refusing to drop unexpected database: {target_db!r}')

    maintenance_db = os.environ.get('CLOUD_TEST_MAINTENANCE_DB', 'defaultdb')
    maintenance_url, connect_kwargs = build_asyncpg_connect_args(target_url, maintenance_db)
    conn = await asyncpg.connect(maintenance_url, **connect_kwargs)
    try:
        exists = await conn.fetchval(
            'SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = \$1)',
            target_db,
        )
        print(f'target_exists={bool(exists)}')
        if not exists:
            return
        await conn.execute(
            'SELECT pg_terminate_backend(pid) '
            'FROM pg_stat_activity '
            'WHERE datname = \$1 AND pid <> pg_backend_pid()',
            target_db,
        )
        await conn.execute(f'DROP DATABASE {quote_ident(target_db)}')
        exists_after = await conn.fetchval(
            'SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = \$1)',
            target_db,
        )
        print(f'target_exists_after={bool(exists_after)}')
    finally:
        await conn.close()


asyncio.run(main())
PY"
}

flush_remote_test_valkey() {
    if [ "$EXECUTE" = "true" ]; then
        remote_allbot "image=\$($(remote_test_tool_image_command)); test -n \"\$image\"; docker run --rm -i --env-file '$CLOUD_TEST_ENV' -e CLEANUP_EXECUTE=true \"\$image\" python - <<'PY'
import asyncio
import os
from urllib.parse import urlparse

import redis.asyncio as redis


async def flush_one(label: str, url: str, expected_db: int) -> None:
    if not url:
        raise SystemExit(f'{label} is missing in cloud-web-api-test')

    parsed = urlparse(url)
    try:
        db = int((parsed.path or '/0').strip('/') or '0')
    except ValueError as exc:
        raise SystemExit(f'{label} has invalid DB path: {parsed.path!r}') from exc

    if db != expected_db:
        raise SystemExit(f'refusing to flush {label}: expected DB {expected_db}, got DB {db}')

    client = redis.from_url(url)
    try:
        before = await client.dbsize()
        print(f'{label}: db={db} keys_before={before}')
        await client.flushdb()
        after = await client.dbsize()
        print(f'{label}: db={db} keys_after={after}')
    finally:
        await client.aclose()


async def main() -> None:
    await flush_one(
        'CLOUD_TEST_REDIS_URL',
        os.environ.get('CLOUD_TEST_REDIS_URL') or os.environ.get('REDIS_URL', ''),
        3,
    )
    await flush_one(
        'CLOUD_TEST_WORKER_REDIS_URL',
        os.environ.get('CLOUD_TEST_WORKER_REDIS_URL') or os.environ.get('WORKER_REDIS_URL', ''),
        4,
    )


asyncio.run(main())
PY"
        return
    fi

    if remote "docker inspect cloud-web-api-test >/dev/null 2>&1"; then
        remote_allbot "docker exec -i -e CLEANUP_EXECUTE=false cloud-web-api-test python - <<'PY'
import asyncio
import os
from urllib.parse import urlparse

import redis.asyncio as redis


async def flush_one(label: str, url: str, expected_db: int) -> None:
    if not url:
        raise SystemExit(f'{label} is missing in cloud-web-api-test')

    parsed = urlparse(url)
    try:
        db = int((parsed.path or '/0').strip('/') or '0')
    except ValueError as exc:
        raise SystemExit(f'{label} has invalid DB path: {parsed.path!r}') from exc

    if db != expected_db:
        raise SystemExit(f'refusing to flush {label}: expected DB {expected_db}, got DB {db}')

    client = redis.from_url(url)
    try:
        before = await client.dbsize()
        print(f'{label}: db={db} keys_before={before}')
        print(f'{label}: dry_run_would_flush=true')
    finally:
        await client.aclose()


async def main() -> None:
    await flush_one(
        'CLOUD_TEST_REDIS_URL',
        os.environ.get('CLOUD_TEST_REDIS_URL') or os.environ.get('REDIS_URL', ''),
        3,
    )
    await flush_one(
        'CLOUD_TEST_WORKER_REDIS_URL',
        os.environ.get('CLOUD_TEST_WORKER_REDIS_URL') or os.environ.get('WORKER_REDIS_URL', ''),
        4,
    )


asyncio.run(main())
PY"
        return
    fi

    remote_allbot "image=\$($(remote_test_tool_image_command)); test -n \"\$image\"; docker run --rm -i --env-file '$CLOUD_TEST_ENV' -e CLEANUP_EXECUTE=false \"\$image\" python - <<'PY'
import asyncio
import os
from urllib.parse import urlparse

import redis.asyncio as redis


async def flush_one(label: str, url: str, expected_db: int) -> None:
    if not url:
        raise SystemExit(f'{label} is missing in cloud-web-api-test')

    parsed = urlparse(url)
    try:
        db = int((parsed.path or '/0').strip('/') or '0')
    except ValueError as exc:
        raise SystemExit(f'{label} has invalid DB path: {parsed.path!r}') from exc

    if db != expected_db:
        raise SystemExit(f'refusing to flush {label}: expected DB {expected_db}, got DB {db}')

    client = redis.from_url(url)
    try:
        before = await client.dbsize()
        print(f'{label}: db={db} keys_before={before}')
        if os.environ.get('CLEANUP_EXECUTE') == 'true':
            await client.flushdb()
            after = await client.dbsize()
            print(f'{label}: db={db} keys_after={after}')
        else:
            print(f'{label}: dry_run_would_flush=true')
    finally:
        await client.aclose()


async def main() -> None:
    await flush_one(
        'CLOUD_TEST_REDIS_URL',
        os.environ.get('CLOUD_TEST_REDIS_URL') or os.environ.get('REDIS_URL', ''),
        3,
    )
    await flush_one(
        'CLOUD_TEST_WORKER_REDIS_URL',
        os.environ.get('CLOUD_TEST_WORKER_REDIS_URL') or os.environ.get('WORKER_REDIS_URL', ''),
        4,
    )


asyncio.run(main())
PY"
}

print_remote_test_valkey_summary() {
    local saved_execute
    saved_execute="$EXECUTE"
    EXECUTE=false
    flush_remote_test_valkey
    EXECUTE="$saved_execute"
}

print_production_local_status() {
    docker ps --format '{{.Names}} {{.Status}}' |
        grep -E '^(tg-bot|web-api|payment-api|backend_api_1|comfy-agent-[0-9]+) ' ||
        true
}

print_final_remote_status() {
    echo "Remote cloud test containers:"
    list_remote_cloud_test_containers
    echo "Local cloud test worker containers:"
    list_local_cloud_test_workers
}

log "Cloud test cleanup mode: $(mode_label)"
log "Remote host: $REMOTE_HOST"
log "Remote dir: $REMOTE_DIR"

log "Preflight: remote env and current cloud test resources"
check_remote_env
print_remote_env_summary
echo
echo "Remote cloud test containers:"
list_remote_cloud_test_containers
echo
echo "Local cloud test worker containers:"
list_local_cloud_test_workers

log "Preflight: cloud test PostgreSQL and Valkey state"
print_remote_test_db_summary
print_remote_test_valkey_summary

log "Step 1: remove local cloud test GPU workers"
remove_local_cloud_test_workers

log "Step 2: remove remote cloud test containers except cloud-web-api-test"
remove_remote_cloud_test_containers_except_web_api

log "Step 3: stop cloud-web-api-test before data cleanup"
stop_remote_web_api_test_for_cleanup

log "Step 4: drop bot_db_test and flush Valkey DB3/DB4"
drop_remote_test_db
if [ "$EXECUTE" = "true" ]; then
    flush_remote_test_valkey
fi

log "Step 5: remove remaining remote cloud test containers"
remove_remote_remaining_cloud_test_containers

log "Post-check"
print_final_remote_status
echo
echo "Local production containers still running:"
print_production_local_status

if [ "$EXECUTE" = "true" ]; then
    log "Cloud test runtime retired. R2 user-data-test and web-test edge static site were left untouched."
else
    log "Dry-run complete. Re-run with --execute to retire cloud test runtime."
fi
