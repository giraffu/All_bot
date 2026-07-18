#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTROLLER="${RUNPOD_PROD_OPS_CONTROLLER:-${ROOT_DIR}/scripts/gpu_pool_controller.py}"

ACTION="status"
MODE="dry-run"
PROFILE=""
SLOT=""
DESIRED=""
COUNT=""
ROLLBACK_MODE="keep-pod"
RUNPOD_ENV_FILE=".env.cloud.test"
PROD_ENV_FILE=".env.cloud.prod"
RETRY_UNAVAILABLE="false"
MAX_ATTEMPTS="20"
RETRY_INTERVAL_SECONDS="90"
READINESS_TIMEOUT_SECONDS=""
WORKER_TIMEOUT_SECONDS=""
RELEASE_INDEX=""
RELEASE_SHA=""
RELEASE_STRATEGY="direct"
RELEASE_ROLLBACK_REF=""
ROLLOUT_RESOLVER="${ROOT_DIR}/scripts/gpu_release_rollout.py"

STATUS_PROFILES=(img2img image_to_video wan22_video_v2 i2i_pro scail2 ltx_video pornmaster_flux2_edit pornmaster_flux2_edit_bf16)

usage() {
  cat <<'USAGE'
Usage:
  scripts/runpod_prod_ops.sh <action> [options]

Actions:
  status    Read cloud-prod manual RunPod worker status.
  up        Create/start a prod manual Pod and wait for disabled heartbeat.
  add       Add N prod manual Pods without deleting or enabling existing slots.
  enable    Enable the selected prod manual worker.
  disable   Disable the selected prod manual worker.
  restart   Disable, call RunPod native restart for the selected Pod, then enable it.
  down      Disable, wait for no current_task_id, then delete the selected Pod.
  scale     Scale one prod manual profile to --desired N.
  canary    Run a real prod canary and leave the target worker disabled.
  rollback  Disable or delete the selected prod manual capacity.
  rollout-release
            Replace exactly one slot from an attested release digest. The new
            Pod stays disabled through digest/heartbeat checks and restores the
            old exact image if the slot update fails.

Options:
  --profile <name>            Required for mutations. One of img2img,
                              image_to_video, wan22_video_v2, i2i_pro,
                              scail2, ltx_video, pornmaster_flux2_edit,
                              pornmaster_flux2_edit_bf16.
  --slot <NN>                 Optional manual worker slot, for example 01.
  --count <N>                 Required for add.
  --desired <N>               Required for scale.
  --keep-pod                  With rollback, disable only. Default.
  --delete-pod                With rollback, delete capacity after drain.
  --runpod-env-file <path>    RunPod env/profile defaults. Default .env.cloud.test.
  --prod-env-file <path>      Prod Central/Web/R2 values. Default .env.cloud.prod.
  --retry-unavailable         Retry up/add/scale on RunPod inventory/resource errors.
  --max-attempts <N>          Max attempts with --retry-unavailable. Default 20.
  --retry-interval <sec>      Sleep seconds between retry attempts. Default 90.
  --readiness-timeout <sec>   Override prod-worker pod readiness timeout.
  --worker-timeout <sec>      Override prod-worker heartbeat timeout.
  --release-index <path>      Required for rollout-release.
  --sha <full-sha>            Required release SHA for rollout-release.
  --strategy <direct|standard>
                              GPU evidence policy. Default direct.
  --rollback-ref <repo@sha256:...>
                              Exact old image used only when the live legacy
                              Pod still reports a tag. Repository must match.
  --dry-run                   Print guarded mutation plan only. Default.
  --execute                   Execute the selected mutation.
  -h, --help                  Show this help.
USAGE
}

is_valid_profile() {
  case "$1" in
    img2img|image_to_video|wan22_video_v2|i2i_pro|scail2|ltx_video|pornmaster_flux2_edit|pornmaster_flux2_edit_bf16) return 0 ;;
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
  if [ -n "$READINESS_TIMEOUT_SECONDS" ]; then
    printf ' %q' --readiness-timeout "$READINESS_TIMEOUT_SECONDS"
  fi
  if [ -n "$WORKER_TIMEOUT_SECONDS" ]; then
    printf ' %q' --worker-timeout "$WORKER_TIMEOUT_SECONDS"
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
  if [ -n "$READINESS_TIMEOUT_SECONDS" ]; then
    cmd+=(--readiness-timeout "$READINESS_TIMEOUT_SECONDS")
  fi
  if [ -n "$WORKER_TIMEOUT_SECONDS" ]; then
    cmd+=(--worker-timeout "$WORKER_TIMEOUT_SECONDS")
  fi
  cmd+=("$@")
  "${cmd[@]}"
}

is_retryable_unavailable_output() {
  local path="$1"
  grep -Eiq \
    'There are no instances currently available|no instances currently available|no[[:space:]_-]*instances.*available|instances.*currently.*available|machine does not have the resources to deploy your pod|Please try a different machine|Please try again later|runpod create-pod failed.*runpod_http_500' \
    "$path"
}

run_controller_with_unavailable_retry() {
  local command_name="$1"
  shift
  local attempt=1
  local max_attempts=1
  if [ "$RETRY_UNAVAILABLE" = "true" ]; then
    max_attempts="$MAX_ATTEMPTS"
  fi

  while true; do
    local output_file
    output_file="$(mktemp)"
    set +e
    run_controller "$command_name" "$@" > >(tee "$output_file") 2>&1
    local status=$?
    set -e
    if [ "$status" -eq 0 ]; then
      rm -f "$output_file"
      return 0
    fi
    if [ "$RETRY_UNAVAILABLE" != "true" ] \
      || [ "$attempt" -ge "$max_attempts" ] \
      || ! is_retryable_unavailable_output "$output_file"; then
      rm -f "$output_file"
      return "$status"
    fi
    rm -f "$output_file"
    echo "[runpod-prod-ops] RunPod inventory/resource unavailable; retry ${attempt}/${max_attempts}, sleeping ${RETRY_INTERVAL_SECONDS}s before next attempt." >&2
    sleep "$RETRY_INTERVAL_SECONDS"
    attempt=$((attempt + 1))
  done
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

require_rollout_release_options() {
  require_profile_for_mutation
  if [ -z "$SLOT" ] || [ -z "$RELEASE_INDEX" ] || [ -z "$RELEASE_SHA" ]; then
    echo "rollout-release requires --profile, --slot, --release-index and --sha" >&2
    exit 2
  fi
  case "$RELEASE_STRATEGY" in
    direct|standard) ;;
    *) echo "--strategy must be direct or standard for rollout-release" >&2; exit 2 ;;
  esac
  if [ -n "$RELEASE_ROLLBACK_REF" ] \
    && ! [[ "$RELEASE_ROLLBACK_REF" =~ ^[^[:space:]@]+@sha256:[0-9a-f]{64}$ ]]; then
    echo "--rollback-ref must be an exact digest-pinned image" >&2
    exit 2
  fi
}

image_repository() {
  local ref="$1"
  ref="${ref%@*}"
  local final_component="${ref##*/}"
  if [[ "$final_component" == *:* ]]; then
    ref="${ref%:*}"
  fi
  printf '%s\n' "$ref"
}

resolve_rollout_field() {
  python3 "$ROLLOUT_RESOLVER" \
    --release-index "$RELEASE_INDEX" \
    --sha "$RELEASE_SHA" \
    --profile "$PROFILE" \
    --strategy "$RELEASE_STRATEGY" \
    --operator runpod \
    --slot "$SLOT" \
    --field "$1"
}

set_profile_image_ref() {
  local env_key="$1"
  local image_ref="$2"
  printf -v "$env_key" '%s' "$image_ref"
  export "$env_key"
}

rollout_release() {
  require_rollout_release_options
  local target_ref image_env
  target_ref="$(resolve_rollout_field ref)"
  image_env="$(resolve_rollout_field runpod_image_env)"
  if [ "$MODE" != "execute" ]; then
    python3 "$ROLLOUT_RESOLVER" \
      --release-index "$RELEASE_INDEX" --sha "$RELEASE_SHA" \
      --profile "$PROFILE" --strategy "$RELEASE_STRATEGY" \
      --operator runpod --slot "$SLOT"
    return
  fi

  command -v jq >/dev/null 2>&1 || {
    echo "rollout-release execute requires jq" >&2
    exit 2
  }
  local before_file after_file observed_old_ref="" old_ref=""
  before_file="$(mktemp)"
  after_file="$(mktemp)"
  trap 'rm -f "$before_file" "$after_file"' RETURN
  run_controller status >"$before_file"
  observed_old_ref="$(jq -r '.prod_pods[0].image // empty' "$before_file")"
  if [[ "$observed_old_ref" =~ @sha256:[0-9a-f]{64}$ ]]; then
    old_ref="$observed_old_ref"
    if [ -n "$RELEASE_ROLLBACK_REF" ] && [ "$RELEASE_ROLLBACK_REF" != "$old_ref" ]; then
      echo "--rollback-ref does not match the live digest-pinned image" >&2
      return 1
    fi
  else
    if [ -z "$RELEASE_ROLLBACK_REF" ]; then
      echo "legacy tagged Pod requires --rollback-ref with its verified exact digest" >&2
      return 1
    fi
    if [ "$(image_repository "$observed_old_ref")" != "$(image_repository "$RELEASE_ROLLBACK_REF")" ]; then
      echo "--rollback-ref repository does not match the live legacy image" >&2
      return 1
    fi
    old_ref="$RELEASE_ROLLBACK_REF"
  fi

  set_profile_image_ref "$image_env" "$target_ref"
  set +e
  run_controller disable --execute && \
    run_controller down --execute && \
    run_controller up --execute && \
    run_controller status >"$after_file"
  local rollout_status=$?
  if [ "$rollout_status" -eq 0 ]; then
    jq -e --arg ref "$target_ref" \
      '.prod_pod_count == 1 and .prod_pods[0].image == $ref and
       .worker != null and .worker.image_ref == $ref and
       (.worker.status != "error" and .worker.status != "quarantined") and
       .control.state == "disabled"' \
      "$after_file" >/dev/null
    rollout_status=$?
  fi
  if [ "$rollout_status" -eq 0 ]; then
    run_controller enable --execute
    rollout_status=$?
  fi
  set -e
  if [ "$rollout_status" -eq 0 ]; then
    echo "[runpod-prod-ops] rollout-release verified ${PROFILE}/${SLOT} at ${target_ref}"
    return
  fi

  echo "[runpod-prod-ops] rollout failed; stopping and restoring this slot" >&2
  run_controller disable --execute >/dev/null 2>&1 || true
  run_controller down --execute >/dev/null 2>&1 || true
  if [ -z "$old_ref" ]; then
    echo "old exact image is unavailable; slot remains disabled" >&2
    return 1
  fi
  set_profile_image_ref "$image_env" "$old_ref"
  if run_controller up --execute && \
    run_controller status >"$after_file" && \
    jq -e --arg ref "$old_ref" \
      '.prod_pod_count == 1 and .prod_pods[0].image == $ref and
       .worker.image_ref == $ref and .control.state == "disabled"' \
      "$after_file" >/dev/null && \
    run_controller enable --execute; then
    echo "[runpod-prod-ops] restored ${PROFILE}/${SLOT} to ${old_ref}" >&2
  else
    run_controller disable --execute >/dev/null 2>&1 || true
    echo "rollback verification failed; slot remains disabled" >&2
  fi
  return 1
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

require_count_for_add() {
  if [ -z "$COUNT" ]; then
    echo "--count is required for add" >&2
    exit 2
  fi
  case "$COUNT" in
    ''|*[!0-9]*)
      echo "--count must be a positive integer" >&2
      exit 2
      ;;
  esac
  if [ "$COUNT" -lt 1 ]; then
    echo "--count must be a positive integer" >&2
    exit 2
  fi
}

validate_retry_options() {
  for value_name in MAX_ATTEMPTS RETRY_INTERVAL_SECONDS; do
    local value="${!value_name}"
    case "$value" in
      ''|*[!0-9]*)
        echo "--${value_name,,} must be a non-negative integer" >&2
        exit 2
        ;;
    esac
  done
  if [ "$RETRY_UNAVAILABLE" = "true" ] && [ "$MAX_ATTEMPTS" -lt 1 ]; then
    echo "--max-attempts must be at least 1" >&2
    exit 2
  fi
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
      if [ "$RETRY_UNAVAILABLE" = "true" ]; then
        echo "[dry-run] Would retry RunPod inventory/resource-unavailable responses up to ${MAX_ATTEMPTS} attempts every ${RETRY_INTERVAL_SECONDS}s."
      fi
      print_shell_command up --execute
      ;;
    add)
      echo "[dry-run] Would add ${COUNT} cloud-prod manual RunPod worker(s), choosing only free slots."
      echo "[dry-run] Would not enable, disable, drain, delete, or recreate any existing RunPod slot."
      if [ "$RETRY_UNAVAILABLE" = "true" ]; then
        echo "[dry-run] Would retry RunPod inventory/resource-unavailable responses up to ${MAX_ATTEMPTS} attempts every ${RETRY_INTERVAL_SECONDS}s."
      fi
      print_shell_command add --count "$COUNT" --execute
      ;;
    enable)
      echo "[dry-run] Would enable the selected cloud-prod manual RunPod worker."
      print_shell_command enable --execute
      ;;
    disable)
      echo "[dry-run] Would disable the selected cloud-prod manual RunPod worker and keep the Pod."
      print_shell_command disable --execute
      ;;
    restart)
      echo "[dry-run] Would restart the selected cloud-prod manual RunPod Pod in place."
      echo "[dry-run] Would set control disabled, call RunPod native restart, wait for healthy heartbeat, then enable it."
      print_shell_command restart --execute
      ;;
    down)
      echo "[dry-run] Would disable the worker, wait until current_task_id is empty, then delete the selected Pod."
      print_shell_command down --execute
      ;;
    scale)
      echo "[dry-run] Would scale the selected cloud-prod manual RunPod profile to desired=${DESIRED}."
      if [ "$RETRY_UNAVAILABLE" = "true" ]; then
        echo "[dry-run] Would retry RunPod inventory/resource-unavailable responses up to ${MAX_ATTEMPTS} attempts every ${RETRY_INTERVAL_SECONDS}s."
      fi
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
  validate_retry_options
  if [ "$ACTION" = "scale" ]; then
    require_desired_for_scale
  fi
  if [ "$ACTION" = "add" ]; then
    require_count_for_add
  fi
  if [ "$MODE" != "execute" ]; then
    dry_run_plan
    return
  fi

  case "$ACTION" in
    up)
      run_controller_with_unavailable_retry up --execute
      ;;
    add)
      run_controller_with_unavailable_retry add --count "$COUNT" --execute
      ;;
    enable|disable|restart|down|canary)
      run_controller "$ACTION" --execute
      ;;
    scale)
      run_controller_with_unavailable_retry scale --desired "$DESIRED" --execute
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
    status|up|add|enable|disable|restart|down|scale|canary|rollback|rollout-release)
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
    --count)
      COUNT="${2:?missing value for --count}"
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
    --retry-unavailable)
      RETRY_UNAVAILABLE="true"
      shift
      ;;
    --max-attempts)
      MAX_ATTEMPTS="${2:?missing value for --max-attempts}"
      shift 2
      ;;
    --retry-interval)
      RETRY_INTERVAL_SECONDS="${2:?missing value for --retry-interval}"
      shift 2
      ;;
    --readiness-timeout)
      READINESS_TIMEOUT_SECONDS="${2:?missing value for --readiness-timeout}"
      shift 2
      ;;
    --worker-timeout)
      WORKER_TIMEOUT_SECONDS="${2:?missing value for --worker-timeout}"
      shift 2
      ;;
    --release-index)
      RELEASE_INDEX="${2:?missing value for --release-index}"
      shift 2
      ;;
    --sha)
      RELEASE_SHA="${2:?missing value for --sha}"
      shift 2
      ;;
    --strategy)
      RELEASE_STRATEGY="${2:?missing value for --strategy}"
      shift 2
      ;;
    --rollback-ref)
      RELEASE_ROLLBACK_REF="${2:?missing value for --rollback-ref}"
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
  up|add|enable|disable|restart|down|scale|canary|rollback)
    run_mutation
    ;;
  rollout-release)
    rollout_release
    ;;
  *)
    echo "Unknown action: ${ACTION}" >&2
    usage >&2
    exit 2
    ;;
esac
