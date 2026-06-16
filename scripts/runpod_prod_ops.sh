#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTROLLER="${ROOT_DIR}/scripts/gpu_pool_controller.py"

ACTION="status"
MODE="dry-run"
PROFILE=""
SLOT=""
DESIRED=""
ROLLBACK_MODE="keep-pod"
RUNPOD_ENV_FILE=".env.cloud.test"
PROD_ENV_FILE=".env.cloud.prod"

STATUS_PROFILES=(img2img image_to_video wan22_video_v2 i2i_pro)

usage() {
  cat <<'USAGE'
Usage:
  scripts/runpod_prod_ops.sh <action> [options]

Actions:
  status    Read cloud-prod manual RunPod worker status.
  up        Create/start a prod manual Pod and wait for disabled heartbeat.
  enable    Enable the selected prod manual worker.
  disable   Disable the selected prod manual worker.
  down      Disable, wait for no current_task_id, then delete the selected Pod.
  scale     Scale one prod manual profile to --desired N.
  canary    Run a real prod canary and leave the target worker disabled.
  rollback  Disable or delete the selected prod manual capacity.

Options:
  --profile <name>            Required for mutations. One of img2img,
                              image_to_video, wan22_video_v2, i2i_pro.
  --slot <NN>                 Optional manual worker slot, for example 01.
  --desired <N>               Required for scale.
  --keep-pod                  With rollback, disable only. Default.
  --delete-pod                With rollback, delete capacity after drain.
  --runpod-env-file <path>    RunPod env/profile defaults. Default .env.cloud.test.
  --prod-env-file <path>      Prod Central/Web/R2 values. Default .env.cloud.prod.
  --dry-run                   Print guarded mutation plan only. Default.
  --execute                   Execute the selected mutation.
  -h, --help                  Show this help.
USAGE
}

is_valid_profile() {
  case "$1" in
    img2img|image_to_video|wan22_video_v2|i2i_pro) return 0 ;;
    *) return 1 ;;
  esac
}

print_shell_command() {
  local command_name="$1"
  shift
  printf '[dry-run] Would run:'
  printf ' %q' python3 "$CONTROLLER" runpod prod-worker "$command_name"
  printf ' %q' --runpod-env-file "$RUNPOD_ENV_FILE" --prod-env-file "$PROD_ENV_FILE"
  if [ -n "$PROFILE" ]; then
    printf ' %q' --profile "$PROFILE"
  fi
  if [ -n "$SLOT" ]; then
    printf ' %q' --slot "$SLOT"
  fi
  while [ "$#" -gt 0 ]; do
    printf ' %q' "$1"
    shift
  done
  printf '\n'
}

run_controller() {
  local command_name="$1"
  shift
  local cmd=(python3 "$CONTROLLER" runpod prod-worker "$command_name")
  cmd+=(--runpod-env-file "$RUNPOD_ENV_FILE" --prod-env-file "$PROD_ENV_FILE")
  if [ -n "$PROFILE" ]; then
    cmd+=(--profile "$PROFILE")
  fi
  if [ -n "$SLOT" ]; then
    cmd+=(--slot "$SLOT")
  fi
  cmd+=("$@")
  "${cmd[@]}"
}

require_profile_for_mutation() {
  if [ -z "$PROFILE" ]; then
    echo "--profile is required for ${ACTION}" >&2
    exit 2
  fi
  if ! is_valid_profile "$PROFILE"; then
    echo "Unsupported --profile: ${PROFILE}" >&2
    exit 2
  fi
}

require_desired_for_scale() {
  if [ -z "$DESIRED" ]; then
    echo "--desired is required for scale" >&2
    exit 2
  fi
  case "$DESIRED" in
    ''|*[!0-9]*)
      echo "--desired must be a non-negative integer" >&2
      exit 2
      ;;
  esac
}

status() {
  if [ -n "$PROFILE" ]; then
    is_valid_profile "$PROFILE" || {
      echo "Unsupported --profile: ${PROFILE}" >&2
      exit 2
    }
    run_controller status
    return
  fi

  local original_profile="$PROFILE"
  for item in "${STATUS_PROFILES[@]}"; do
    echo "== prod RunPod status: ${item} =="
    PROFILE="$item"
    run_controller status || true
  done
  PROFILE="$original_profile"
}

dry_run_plan() {
  case "$ACTION" in
    up)
      echo "[dry-run] Would create/start a cloud-prod manual RunPod Pod and wait for disabled heartbeat."
      print_shell_command up --execute
      ;;
    enable)
      echo "[dry-run] Would enable the selected cloud-prod manual RunPod worker."
      print_shell_command enable --execute
      ;;
    disable)
      echo "[dry-run] Would disable the selected cloud-prod manual RunPod worker and keep the Pod."
      print_shell_command disable --execute
      ;;
    down)
      echo "[dry-run] Would disable the worker, wait until current_task_id is empty, then delete the selected Pod."
      print_shell_command down --execute
      ;;
    scale)
      echo "[dry-run] Would scale the selected cloud-prod manual RunPod profile to desired=${DESIRED}."
      print_shell_command scale --desired "$DESIRED" --execute
      ;;
    canary)
      echo "[dry-run] Would run a real prod canary and leave the selected worker disabled afterwards."
      print_shell_command canary --execute
      ;;
    rollback)
      if [ "$ROLLBACK_MODE" = "delete-pod" ]; then
        if [ -n "$SLOT" ]; then
          echo "[dry-run] Would rollback by disabling and deleting selected slot ${SLOT}."
          print_shell_command down --execute
        else
          echo "[dry-run] Would rollback by scaling the selected profile to desired=0."
          print_shell_command scale --desired 0 --execute
        fi
      else
        echo "[dry-run] Would rollback by disabling the selected worker and keeping the Pod."
        print_shell_command disable --execute
      fi
      ;;
    *)
      echo "Unsupported dry-run action: ${ACTION}" >&2
      exit 2
      ;;
  esac
}

run_mutation() {
  require_profile_for_mutation
  if [ "$ACTION" = "scale" ]; then
    require_desired_for_scale
  fi
  if [ "$MODE" != "execute" ]; then
    dry_run_plan
    return
  fi

  case "$ACTION" in
    up|enable|disable|down|canary)
      run_controller "$ACTION" --execute
      ;;
    scale)
      run_controller scale --desired "$DESIRED" --execute
      ;;
    rollback)
      if [ "$ROLLBACK_MODE" = "delete-pod" ]; then
        if [ -n "$SLOT" ]; then
          run_controller down --execute
        else
          run_controller scale --desired 0 --execute
        fi
      else
        run_controller disable --execute
      fi
      ;;
    *)
      echo "Unknown action: ${ACTION}" >&2
      usage >&2
      exit 2
      ;;
  esac
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    status|up|enable|disable|down|scale|canary|rollback)
      ACTION="$1"
      shift
      ;;
    --action)
      ACTION="${2:?missing value for --action}"
      shift 2
      ;;
    --profile)
      PROFILE="${2:?missing value for --profile}"
      shift 2
      ;;
    --slot)
      SLOT="${2:?missing value for --slot}"
      shift 2
      ;;
    --desired)
      DESIRED="${2:?missing value for --desired}"
      shift 2
      ;;
    --keep-pod)
      ROLLBACK_MODE="keep-pod"
      shift
      ;;
    --delete-pod)
      ROLLBACK_MODE="delete-pod"
      shift
      ;;
    --runpod-env-file)
      RUNPOD_ENV_FILE="${2:?missing value for --runpod-env-file}"
      shift 2
      ;;
    --prod-env-file)
      PROD_ENV_FILE="${2:?missing value for --prod-env-file}"
      shift 2
      ;;
    --execute)
      MODE="execute"
      shift
      ;;
    --dry-run)
      MODE="dry-run"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$ACTION" in
  status)
    status
    ;;
  up|enable|disable|down|scale|canary|rollback)
    run_mutation
    ;;
  *)
    echo "Unknown action: ${ACTION}" >&2
    usage >&2
    exit 2
    ;;
esac
