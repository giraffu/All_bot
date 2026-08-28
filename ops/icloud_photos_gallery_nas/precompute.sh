#!/bin/sh
set -eu

confirm_expected=PRECOMPUTE_ICLOUD_PHOTOS_GALLERY
execute=false
confirm=

while [ "$#" -gt 0 ]; do
  case "$1" in
    --execute) execute=true ;;
    --confirm)
      shift
      test "$#" -gt 0 || { echo "--confirm requires a value" >&2; exit 2; }
      confirm=$1
      ;;
    *) echo "usage: precompute.sh [--execute --confirm $confirm_expected]" >&2; exit 2 ;;
  esac
  shift
done

if [ "$execute" != true ]; then
  echo "dry-run: index the complete gallery, pre-generate thumbnails, then transcode videos to browser-compatible MP4"
  echo "media source remains read-only: /volume1/ApplePhotos/originals"
  exit 0
fi
if [ "$confirm" != "$confirm_expected" ]; then
  echo "exact confirmation required: $confirm_expected" >&2
  exit 2
fi
if [ "$(id -u)" -ne 0 ]; then
  echo "gallery precompute must run as root" >&2
  exit 2
fi
for command in curl mktemp python3; do
  command -v "$command" >/dev/null 2>&1 || { echo "missing required command: $command" >&2; exit 2; }
done

runtime_root=/volume1/ApplePhotosGalleryRuntime
username_file=$runtime_root/secrets/admin-username
password_file=$runtime_root/secrets/admin-password
success_file=$runtime_root/state/precompute-last-success
api_url=http://192.168.1.150:8099/pgapi
lock_dir=/run/allbot-pigallery-precompute.lock
poll_seconds=${PIGALLERY_JOB_POLL_SECONDS:-30}

case "$poll_seconds" in
  ''|*[!0-9]*) echo "PIGALLERY_JOB_POLL_SECONDS must be an integer" >&2; exit 2 ;;
esac
if [ "$poll_seconds" -lt 5 ] || [ "$poll_seconds" -gt 300 ]; then
  echo "PIGALLERY_JOB_POLL_SECONDS must be between 5 and 300" >&2
  exit 2
fi
test -s "$username_file" || { echo "missing gallery administrator username" >&2; exit 2; }
test -s "$password_file" || { echo "missing gallery administrator password" >&2; exit 2; }
mkdir "$lock_dir" 2>/dev/null || { echo "gallery precompute is already running" >&2; exit 2; }

umask 077
work_dir=$(mktemp -d /tmp/allbot-pigallery-precompute.XXXXXX)
cleanup() {
  rm -rf -- "$work_dir"
  rmdir "$lock_dir" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM
cookie_file=$work_dir/cookie
progress_file=$work_dir/progress.json

login() {
  gallery_user=$(tr -d '\r\n' < "$username_file")
  gallery_password=$(tr -d '\r\n' < "$password_file")
  test -n "$gallery_user" || { echo "empty gallery administrator username" >&2; return 2; }
  test -n "$gallery_password" || { echo "empty gallery administrator password" >&2; return 2; }
  export gallery_user gallery_password
  python3 -c 'import json, os; print(json.dumps({"loginCredential": {"username": os.environ["gallery_user"], "password": os.environ["gallery_password"], "rememberMe": False}}))' > "$work_dir/login.json"
  curl --noproxy '*' -fsS -o /dev/null -c "$cookie_file" \
    -H 'Content-Type: application/json' --data-binary "@$work_dir/login.json" \
    "$api_url/user/login"
  unset gallery_user gallery_password
}

get_progress() {
  if ! curl --noproxy '*' -fsS -b "$cookie_file" \
    "$api_url/admin/jobs/scheduled/progress" > "$progress_file"; then
    login
    curl --noproxy '*' -fsS -b "$cookie_file" \
      "$api_url/admin/jobs/scheduled/progress" > "$progress_file"
  fi
}

running_job() {
  get_progress
  python3 - "$progress_file" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
progresses = payload.get("result", payload).values()
running = [p for p in progresses if p.get("state") in (1, 2)]
if len(running) > 1:
    raise SystemExit("multiple gallery jobs are running")
print(running[0].get("jobName", "") if running else "")
PY
}

latest_status() {
  job_name=$1
  get_progress
  python3 - "$progress_file" "$job_name" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
matches = [p for p in payload.get("result", payload).values() if p.get("jobName") == sys.argv[2]]
if not matches:
    print("0 0 0 0")
else:
    latest = max(matches, key=lambda p: p.get("time", {}).get("start", 0))
    steps = latest.get("steps", {})
    print(latest.get("state", 0), steps.get("all", 0), steps.get("processed", 0), steps.get("skipped", 0))
PY
}

start_job() {
  job_name=$1
  job_config=$2
  job_path=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$job_name")
  export job_config
  python3 -c 'import json, os; print(json.dumps({"config": json.loads(os.environ["job_config"]), "soloRun": True, "allowParallelRun": False}))' > "$work_dir/start.json"
  unset job_config
  curl --noproxy '*' -fsS -o /dev/null -b "$cookie_file" -X POST \
    -H 'Content-Type: application/json' --data-binary "@$work_dir/start.json" \
    "$api_url/admin/jobs/scheduled/$job_path/start"
  echo "started gallery job: $job_name"
}

wait_job() {
  job_name=$1
  while :; do
    set -- $(latest_status "$job_name")
    state=$1
    all=$2
    processed=$3
    skipped=$4
    echo "gallery job progress: $job_name state=$state processed=$processed all=$all skipped=$skipped"
    case "$state" in
      1|2) sleep "$poll_seconds" ;;
      5) echo "finished gallery job: $job_name"; return 0 ;;
      3|4|6) echo "gallery job did not finish successfully: $job_name state=$state" >&2; return 2 ;;
      0) sleep 2 ;;
      *) echo "unknown gallery job state: $job_name state=$state" >&2; return 2 ;;
    esac
  done
}

run_phase() {
  job_name=$1
  job_config=$2
  current=$(running_job)
  if [ -n "$current" ]; then
    if [ "$current" != "$job_name" ]; then
      echo "another gallery job is already running: $current" >&2
      return 2
    fi
    echo "attaching to running gallery job: $job_name"
  else
    start_job "$job_name" "$job_config"
  fi
  wait_job "$job_name"
}

login
run_phase "Indexing" '{"indexChangesOnly":false}'
run_phase "Photo Converting" '{"indexedOnly":true,"sizes":[320],"maxVideoSize":800}'
run_phase "Video Converting" '{"indexedOnly":true}'
install -o root -g root -m 0600 /dev/null "$success_file"
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$success_file"
echo "gallery precompute complete"
