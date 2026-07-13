#!/usr/bin/env bash
set -euo pipefail

EXECUTE=0
OUTPUT_TEMP_MINUTES=60
INPUT_MINUTES=1440
HOST_FILTER=""
FORCE_SHORT_INPUT=0

usage() {
  cat <<'EOF'
Usage:
  scripts/cleanup_lan_comfy_artifacts.sh [--execute] [--host HOST] [options]

Options:
  --execute                 Delete files. Without this flag the script is dry-run only.
  --host HOST               Limit to one SSH alias: allbot-gpu-226/177/252/002.
  --output-temp-minutes N   Retention for ComfyUI output/temp files. Default: 60.
  --input-minutes N         Retention for ComfyUI input files. Default: 1440.
  --force-short-input       Allow input retention shorter than 360 minutes.
  -h, --help                Show this help.

Default policy:
  output/temp: remove files older than 60 minutes.
  input: remove files older than 24 hours.

Input files are intentionally kept longer because already queued/running
ComfyUI prompts can still reference them. Do not lower --input-minutes in
production unless the target queue has been checked.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute)
      EXECUTE=1
      shift
      ;;
    --host)
      HOST_FILTER="${2:-}"
      shift 2
      ;;
    --output-temp-minutes)
      OUTPUT_TEMP_MINUTES="${2:-}"
      shift 2
      ;;
    --input-minutes)
      INPUT_MINUTES="${2:-}"
      shift 2
      ;;
    --force-short-input)
      FORCE_SHORT_INPUT=1
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

if ! [[ "$OUTPUT_TEMP_MINUTES" =~ ^[0-9]+$ && "$INPUT_MINUTES" =~ ^[0-9]+$ ]]; then
  echo "Retention values must be integers." >&2
  exit 2
fi

if (( INPUT_MINUTES < 360 && FORCE_SHORT_INPUT == 0 )); then
  echo "Refusing input retention shorter than 360 minutes without --force-short-input." >&2
  exit 2
fi

HOSTS=(allbot-gpu-226 allbot-gpu-177 allbot-gpu-252 allbot-gpu-002)

should_run_host() {
  local host="$1"
  [[ -z "$HOST_FILTER" || "$HOST_FILTER" == "$host" ]]
}

cleanup_host_paths() {
  local host="$1"
  ssh "$host" "bash -s" -- "$EXECUTE" "$OUTPUT_TEMP_MINUTES" "$INPUT_MINUTES" <<'REMOTE'
set -euo pipefail
execute="$1"
output_temp_minutes="$2"
input_minutes="$3"

cleanup_dir() {
  d="$1"
  mins="$2"
  label="$3"

  if [ ! -d "$d" ]; then
    echo "MISSING $label $d"
    return 0
  fi

  count=$(find "$d" -xdev -type f -mmin +"$mins" ! -name "_output_images_will_be_put_here" | wc -l | tr -d ' ')
  bytes=$(find "$d" -xdev -type f -mmin +"$mins" ! -name "_output_images_will_be_put_here" -printf "%s\n" | awk '{s+=$1} END {printf "%.2f GiB", s/1024/1024/1024}')
  echo "SCAN $label path=$d older_than=${mins}min files=$count bytes=$bytes"

  if [ "$execute" = "1" ]; then
    find "$d" -xdev -type f -mmin +"$mins" ! -name "_output_images_will_be_put_here" -delete
    find "$d" -xdev -depth -mindepth 1 -type d -empty -delete 2>/dev/null || true
    du -sh "$d" 2>/dev/null || true
  fi
}

echo "== before df =="
df -h /
cleanup_dir /home/ubantu/comfyui/output "$output_temp_minutes" output
cleanup_dir /home/ubantu/comfyui/temp "$output_temp_minutes" temp
cleanup_dir /home/ubantu/comfyui/input "$input_minutes" input
echo "== after df =="
df -h /
REMOTE
}

cleanup_container_host() {
  local host="$1"
  ssh "$host" "bash -s" -- "$EXECUTE" "$OUTPUT_TEMP_MINUTES" "$INPUT_MINUTES" <<'REMOTE'
set -euo pipefail
execute="$1"
output_temp_minutes="$2"
input_minutes="$3"

cleanup_dir() {
  d="$1"
  mins="$2"
  label="$3"

  if [ ! -d "$d" ]; then
    echo "MISSING $label $d"
    return 0
  fi

  count=$(find "$d" -xdev -type f -mmin +"$mins" ! -name "_output_images_will_be_put_here" | wc -l | tr -d ' ')
  bytes=$(find "$d" -xdev -type f -mmin +"$mins" ! -name "_output_images_will_be_put_here" -printf "%s\n" | awk '{s+=$1} END {printf "%.2f GiB", s/1024/1024/1024}')
  echo "SCAN $label path=$d older_than=${mins}min files=$count bytes=$bytes"

  if [ "$execute" = "1" ]; then
    find "$d" -xdev -type f -mmin +"$mins" ! -name "_output_images_will_be_put_here" -delete
    find "$d" -xdev -depth -mindepth 1 -type d -empty -delete 2>/dev/null || true
    du -sh "$d" 2>/dev/null || true
  fi
}

mount_source() {
  container="$1"
  destination="$2"
  docker inspect "$container" --format '{{range .Mounts}}{{println .Destination "|" .Source}}{{end}}' \
    | awk -F ' \\| ' -v dest="$destination" '$1 == dest {print $2; exit}'
}

cleanup_stopped_container_mounts() {
  container="$1"
  output_dir=$(mount_source "$container" /root/ComfyUI/output || true)
  temp_dir=$(mount_source "$container" /root/ComfyUI/temp || true)
  input_dir=$(mount_source "$container" /root/ComfyUI/input || true)

  echo "container $container is stopped; scanning host bind mounts from docker inspect"
  [ -n "$output_dir" ] && cleanup_dir "$output_dir" "$output_temp_minutes" "$container/output"
  [ -n "$temp_dir" ] && cleanup_dir "$temp_dir" "$output_temp_minutes" "$container/temp"
  [ -n "$input_dir" ] && cleanup_dir "$input_dir" "$input_minutes" "$container/input"
}

echo "== before df =="
df -h /

for container in comfy0 comfy1; do
  if ! docker inspect "$container" >/dev/null 2>&1; then
    echo "MISSING container $container"
    continue
  fi

  echo "== $container =="
  status=$(docker inspect "$container" --format '{{.State.Status}}')
  if [ "$status" != "running" ]; then
    cleanup_stopped_container_mounts "$container"
    continue
  fi

  docker exec -i "$container" sh -s -- "$execute" "$output_temp_minutes" "$input_minutes" <<'CONTAINER'
set -eu
execute="$1"
output_temp_minutes="$2"
input_minutes="$3"

cleanup_dir() {
  d="$1"
  mins="$2"
  label="$3"

  if [ ! -d "$d" ]; then
    echo "MISSING $label $d"
    return 0
  fi

  count=$(find "$d" -xdev -type f -mmin +"$mins" ! -name "_output_images_will_be_put_here" | wc -l | tr -d ' ')
  bytes=$(find "$d" -xdev -type f -mmin +"$mins" ! -name "_output_images_will_be_put_here" -printf "%s\n" | awk '{s+=$1} END {printf "%.2f GiB", s/1024/1024/1024}')
  echo "SCAN $label path=$d older_than=${mins}min files=$count bytes=$bytes"

  if [ "$execute" = "1" ]; then
    find "$d" -xdev -type f -mmin +"$mins" ! -name "_output_images_will_be_put_here" -delete
    find "$d" -xdev -depth -mindepth 1 -type d -empty -delete 2>/dev/null || true
    du -sh "$d" 2>/dev/null || true
  fi
}

cleanup_dir /root/ComfyUI/output "$output_temp_minutes" output
cleanup_dir /root/ComfyUI/temp "$output_temp_minutes" temp
cleanup_dir /root/ComfyUI/input "$input_minutes" input
CONTAINER
done

echo "== after df =="
df -h /
REMOTE
}

for host in "${HOSTS[@]}"; do
  should_run_host "$host" || continue
  echo "### $host"
  case "$host" in
    allbot-gpu-226)
      cleanup_host_paths "$host"
      ;;
    allbot-gpu-177|allbot-gpu-252|allbot-gpu-002)
      cleanup_container_host "$host"
      ;;
    *)
      echo "Unsupported host: $host" >&2
      exit 2
      ;;
  esac
done
