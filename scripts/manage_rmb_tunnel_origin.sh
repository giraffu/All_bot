#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${CLOUDFLARED_RMB_CONFIG:-/home/hfy/.cloudflared/config.yml}"
SERVICE_NAME="${CLOUDFLARED_RMB_SERVICE:-cloudflared-rmb-pay}"
HOSTNAME="${RMB_TUNNEL_HOSTNAME:-rmb.aivison.it.com}"
LOCAL_SERVICE_URL="${RMB_TUNNEL_LOCAL_SERVICE_URL:-http://127.0.0.1:8021}"
CLOUD_SERVICE_URL="${RMB_TUNNEL_CLOUD_SERVICE_URL:-http://100.107.220.127:8002}"
BACKUP_DIR="${RMB_TUNNEL_BACKUP_DIR:-/home/hfy/APP/All_bot/backups/cloud-prod-rmb-tunnel}"
PUBLIC_HEALTH_URL="${RMB_TUNNEL_PUBLIC_HEALTH_URL:-https://rmb.aivison.it.com/healthz}"

TARGET=""
EXECUTE=false
SKIP_NETWORK_CHECKS=false

usage() {
  cat <<'EOF'
Usage:
  scripts/manage_rmb_tunnel_origin.sh --target cloud [--dry-run|--execute]
  scripts/manage_rmb_tunnel_origin.sh --target local [--dry-run|--execute]

Options:
  --target cloud|local       Required. cloud -> 100.107.220.127:8002, local -> 127.0.0.1:8021.
  --dry-run                  Default. Print planned changes without editing config or restarting.
  --execute                  Apply the change and restart cloudflared-rmb-pay.
  --config PATH              Cloudflared config path. Default: /home/hfy/.cloudflared/config.yml.
  --service-name NAME        Systemd service name. Default: cloudflared-rmb-pay.
  --hostname HOST            Tunnel hostname. Default: rmb.aivison.it.com.
  --cloud-url URL            Cloud Payment API origin. Default: http://100.107.220.127:8002.
  --local-url URL            Local Payment API origin. Default: http://127.0.0.1:8021.
  --backup-dir PATH          Backup directory for config snapshots.
  --skip-network-checks      Skip direct target and public URL health checks.

Environment variables with matching names can override defaults:
  CLOUDFLARED_RMB_CONFIG, CLOUDFLARED_RMB_SERVICE, RMB_TUNNEL_HOSTNAME,
  RMB_TUNNEL_LOCAL_SERVICE_URL, RMB_TUNNEL_CLOUD_SERVICE_URL,
  RMB_TUNNEL_BACKUP_DIR, RMB_TUNNEL_PUBLIC_HEALTH_URL

This script is dry-run by default. --execute changes the live RMB payment
callback/result origin and must only be used during the formal maintenance window.
EOF
}

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target)
      TARGET="${2:-}"
      shift 2
      ;;
    --dry-run)
      EXECUTE=false
      shift
      ;;
    --execute)
      EXECUTE=true
      shift
      ;;
    --config)
      CONFIG_PATH="${2:-}"
      shift 2
      ;;
    --service-name)
      SERVICE_NAME="${2:-}"
      shift 2
      ;;
    --hostname)
      HOSTNAME="${2:-}"
      shift 2
      ;;
    --cloud-url)
      CLOUD_SERVICE_URL="${2:-}"
      shift 2
      ;;
    --local-url)
      LOCAL_SERVICE_URL="${2:-}"
      shift 2
      ;;
    --backup-dir)
      BACKUP_DIR="${2:-}"
      shift 2
      ;;
    --skip-network-checks)
      SKIP_NETWORK_CHECKS=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

case "$TARGET" in
  cloud)
    TARGET_SERVICE_URL="$CLOUD_SERVICE_URL"
    ;;
  local)
    TARGET_SERVICE_URL="$LOCAL_SERVICE_URL"
    ;;
  *)
    usage >&2
    die "--target must be cloud or local"
    ;;
esac

[ -f "$CONFIG_PATH" ] || die "cloudflared config not found: $CONFIG_PATH"
command -v python3 >/dev/null 2>&1 || die "python3 is required"

read_current_service() {
  python3 - "$CONFIG_PATH" "$HOSTNAME" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
hostname = sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines()
in_block = False
for line in lines:
    stripped = line.strip()
    if stripped.startswith("- hostname:"):
        value = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        in_block = value == hostname
        continue
    if in_block and stripped.startswith("service:"):
        print(stripped.split(":", 1)[1].strip())
        raise SystemExit(0)
raise SystemExit(f"hostname {hostname!r} service entry not found in {path}")
PY
}

read_current_host_header() {
  python3 - "$CONFIG_PATH" "$HOSTNAME" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
hostname = sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines()
in_block = False
for line in lines:
    stripped = line.strip()
    if stripped.startswith("- hostname:"):
        value = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        in_block = value == hostname
        continue
    if in_block and stripped.startswith("httpHostHeader:"):
        print(stripped.split(":", 1)[1].strip())
        raise SystemExit(0)
raise SystemExit(f"hostname {hostname!r} httpHostHeader entry not found in {path}")
PY
}

rewrite_origin() {
  python3 - "$CONFIG_PATH" "$HOSTNAME" "$TARGET_SERVICE_URL" "$TARGET_HOST_HEADER" <<'PY'
from pathlib import Path
import os
import sys
import tempfile

path = Path(sys.argv[1])
hostname = sys.argv[2]
target = sys.argv[3]
target_host_header = sys.argv[4]
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

in_block = False
service_found = False
host_header_found = False
for idx, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith("- hostname:"):
        value = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        in_block = value == hostname
        continue
    if in_block and stripped.startswith("service:"):
        current = stripped.split(":", 1)[1].strip()
        if current != target:
            indent = line[: len(line) - len(line.lstrip())]
            newline = "\n" if line.endswith("\n") else ""
            lines[idx] = f"{indent}service: {target}{newline}"
        service_found = True
        continue
    if in_block and stripped.startswith("httpHostHeader:"):
        current = stripped.split(":", 1)[1].strip()
        if current != target_host_header:
            indent = line[: len(line) - len(line.lstrip())]
            newline = "\n" if line.endswith("\n") else ""
            lines[idx] = f"{indent}httpHostHeader: {target_host_header}{newline}"
        host_header_found = True

if not service_found:
    raise SystemExit(f"hostname {hostname!r} service entry not found in {path}")
if not host_header_found:
    raise SystemExit(f"hostname {hostname!r} httpHostHeader entry not found in {path}")

fd, tmp_name = tempfile.mkstemp(
    prefix=f".{path.name}.",
    suffix=".tmp",
    dir=str(path.parent),
)
with os.fdopen(fd, "w", encoding="utf-8") as handle:
    handle.writelines(lines)
os.chmod(tmp_name, path.stat().st_mode)
os.replace(tmp_name, path)
PY
}

current_service="$(read_current_service)"
current_host_header="$(read_current_host_header)"
TARGET_HOST_HEADER="$(
  python3 - "$TARGET_SERVICE_URL" <<'PY'
from urllib.parse import urlsplit
import sys

parsed = urlsplit(sys.argv[1])
if not parsed.hostname:
    raise SystemExit("target service URL has no hostname")
print(parsed.netloc)
PY
)"
timestamp="$(date +%Y%m%d-%H%M%S)"
backup_path="${BACKUP_DIR}/config.yml.before-${TARGET}.${timestamp}.bak"
target_health_url="${TARGET_SERVICE_URL%/}/healthz"

log "RMB tunnel hostname: ${HOSTNAME}"
log "Config path: ${CONFIG_PATH}"
log "Systemd service: ${SERVICE_NAME}"
log "Current origin: ${current_service}"
log "Current origin Host header: ${current_host_header}"
log "Target origin: ${TARGET_SERVICE_URL}"
log "Target origin Host header: ${TARGET_HOST_HEADER}"

if [ "$SKIP_NETWORK_CHECKS" = false ]; then
  command -v curl >/dev/null 2>&1 || die "curl is required unless --skip-network-checks is used"
  log "Checking direct target health: ${target_health_url}"
  curl -fsS -o /dev/null --max-time 8 "$target_health_url" \
    || die "target health check failed: ${target_health_url}"
fi

if [ "$EXECUTE" = false ]; then
  if [ "$current_service" = "$TARGET_SERVICE_URL" ] \
    && [ "$current_host_header" = "$TARGET_HOST_HEADER" ]; then
    cat <<EOF
DRY-RUN only. No file will be edited and ${SERVICE_NAME} will not be restarted.
${HOSTNAME} is already configured for the target origin:
  ${TARGET_SERVICE_URL}
EOF
    exit 0
  fi

  cat <<EOF
DRY-RUN only. No file will be edited and ${SERVICE_NAME} will not be restarted.
Would backup config to: ${backup_path}
Would update ${HOSTNAME} origin from:
  ${current_service}
to:
  ${TARGET_SERVICE_URL}
Would update origin Host header from:
  ${current_host_header}
to:
  ${TARGET_HOST_HEADER}
Would restart systemd service:
  ${SERVICE_NAME}
EOF
  exit 0
fi

if [ "$current_service" = "$TARGET_SERVICE_URL" ] \
  && [ "$current_host_header" = "$TARGET_HOST_HEADER" ]; then
  log "Target origin is already active in config. A backup and restart will still be skipped."
  exit 0
fi

log "EXECUTE mode: this changes the live RMB payment origin."
mkdir -p "$BACKUP_DIR"
cp -p "$CONFIG_PATH" "$backup_path"
log "Backed up config to: ${backup_path}"

rewrite_origin
updated_service="$(read_current_service)"
updated_host_header="$(read_current_host_header)"
[ "$updated_service" = "$TARGET_SERVICE_URL" ] \
  || die "config rewrite verification failed: got ${updated_service}"
[ "$updated_host_header" = "$TARGET_HOST_HEADER" ] \
  || die "config Host header verification failed: got ${updated_host_header}"
log "Updated config origin: ${updated_service}"
log "Updated origin Host header: ${updated_host_header}"

restart_service() {
  if [ "$(id -u)" -eq 0 ]; then
    systemctl restart "$SERVICE_NAME"
    systemctl is-active --quiet "$SERVICE_NAME"
    return
  fi
  if command -v sudo >/dev/null 2>&1 \
    && sudo -n systemctl restart "$SERVICE_NAME" >/dev/null 2>&1; then
    sudo -n systemctl is-active --quiet "$SERVICE_NAME"
    return
  fi

  local current_pid service_user restart_policy new_pid active
  current_pid="$(systemctl show "$SERVICE_NAME" --property=MainPID --value)"
  service_user="$(systemctl show "$SERVICE_NAME" --property=User --value)"
  restart_policy="$(systemctl show "$SERVICE_NAME" --property=Restart --value)"
  [ "$current_pid" != 0 ] \
    || die "systemd service has no running process: ${SERVICE_NAME}"
  [ "$service_user" = "$(id -un)" ] \
    || die "sudo is required to restart ${SERVICE_NAME}"
  [ "$restart_policy" = always ] \
    || die "safe owner restart requires Restart=always: ${SERVICE_NAME}"

  kill -TERM "$current_pid"
  for _attempt in $(seq 1 20); do
    sleep 1
    new_pid="$(systemctl show "$SERVICE_NAME" --property=MainPID --value)"
    active="$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || true)"
    if [ "$active" = active ] \
      && [ "$new_pid" != 0 ] \
      && [ "$new_pid" != "$current_pid" ]; then
      return
    fi
  done
  die "systemd service did not restart with a new process: ${SERVICE_NAME}"
}

restart_service \
  || die "systemd service is not active after restart: ${SERVICE_NAME}"
log "Restarted systemd service: ${SERVICE_NAME}"

if [ "$SKIP_NETWORK_CHECKS" = false ]; then
  log "Checking public RMB endpoint: ${PUBLIC_HEALTH_URL}"
  for attempt in $(seq 1 20); do
    if curl -fsS -o /dev/null --max-time 8 "$PUBLIC_HEALTH_URL"; then
      log "Public RMB endpoint is reachable."
      exit 0
    fi
    sleep 2
    log "Waiting for public RMB endpoint (${attempt}/20)..."
  done
  die "public RMB endpoint did not become reachable: ${PUBLIC_HEALTH_URL}"
fi

log "Done. Network checks were skipped."
