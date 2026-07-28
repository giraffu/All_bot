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

rewrite_service() {
  python3 - "$CONFIG_PATH" "$HOSTNAME" "$TARGET_SERVICE_URL" <<'PY'
from pathlib import Path
import os
import sys
import tempfile

path = Path(sys.argv[1])
hostname = sys.argv[2]
target = sys.argv[3]
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

in_block = False
changed = False
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
        changed = True
        break

if not changed:
    raise SystemExit(f"hostname {hostname!r} service entry not found in {path}")

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
timestamp="$(date +%Y%m%d-%H%M%S)"
backup_path="${BACKUP_DIR}/config.yml.before-${TARGET}.${timestamp}.bak"
target_health_url="${TARGET_SERVICE_URL%/}/healthz"

log "RMB tunnel hostname: ${HOSTNAME}"
log "Config path: ${CONFIG_PATH}"
log "Systemd service: ${SERVICE_NAME}"
log "Current origin: ${current_service}"
log "Target origin: ${TARGET_SERVICE_URL}"

if [ "$SKIP_NETWORK_CHECKS" = false ]; then
  command -v curl >/dev/null 2>&1 || die "curl is required unless --skip-network-checks is used"
  log "Checking direct target health: ${target_health_url}"
  curl -fsS -o /dev/null --max-time 8 "$target_health_url" \
    || die "target health check failed: ${target_health_url}"
fi

if [ "$EXECUTE" = false ]; then
  if [ "$current_service" = "$TARGET_SERVICE_URL" ]; then
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
Would restart systemd service:
  ${SERVICE_NAME}
EOF
  exit 0
fi

if [ "$current_service" = "$TARGET_SERVICE_URL" ]; then
  log "Target origin is already active in config. A backup and restart will still be skipped."
  exit 0
fi

log "EXECUTE mode: this changes the live RMB payment origin."
mkdir -p "$BACKUP_DIR"
cp -p "$CONFIG_PATH" "$backup_path"
log "Backed up config to: ${backup_path}"

rewrite_service
updated_service="$(read_current_service)"
[ "$updated_service" = "$TARGET_SERVICE_URL" ] \
  || die "config rewrite verification failed: got ${updated_service}"
log "Updated config origin: ${updated_service}"

SUDO=()
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null 2>&1 || die "sudo is required to restart ${SERVICE_NAME}"
  SUDO=(sudo)
fi

"${SUDO[@]}" systemctl restart "$SERVICE_NAME"
"${SUDO[@]}" systemctl is-active --quiet "$SERVICE_NAME" \
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
