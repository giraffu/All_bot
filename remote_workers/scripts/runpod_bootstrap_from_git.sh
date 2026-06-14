#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="${RUNPOD_BOOTSTRAP_LOG_FILE:-/tmp/allbot-runpod-bootstrap.log}"
touch "$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

log() {
    printf '[runpod-bootstrap] %s\n' "$*"
}

keepalive_on_failure() {
    local status="$1"
    log "bootstrap failed with exit status ${status}"
    if [ "${RUNPOD_KEEPALIVE_ON_BOOTSTRAP_FAILURE:-false}" = "true" ]; then
        log "RUNPOD_KEEPALIVE_ON_BOOTSTRAP_FAILURE=true; keeping container alive for SSH diagnostics"
        while true; do
            sleep 3600
        done
    fi
    exit "$status"
}
trap 'keepalive_on_failure "$?"' ERR

start_sshd_for_diagnostics() {
    if [ "${RUNPOD_START_SSHD:-true}" != "true" ]; then
        return
    fi
    local sshd_bin
    sshd_bin="$(command -v sshd 2>/dev/null || true)"
    if [ -z "$sshd_bin" ] && [ -x /usr/sbin/sshd ]; then
        sshd_bin=/usr/sbin/sshd
    fi
    if [ -z "$sshd_bin" ]; then
        if [ "${RUNPOD_INSTALL_SSHD_IF_MISSING:-true}" = "true" ] && command -v apt-get >/dev/null 2>&1; then
            log "sshd not found; installing openssh-server for direct TCP diagnostics"
            apt-get update
            DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends openssh-server
            rm -rf /var/lib/apt/lists/*
        fi
        sshd_bin="$(command -v sshd 2>/dev/null || true)"
        if [ -z "$sshd_bin" ] && [ -x /usr/sbin/sshd ]; then
            sshd_bin=/usr/sbin/sshd
        fi
        if [ -z "$sshd_bin" ]; then
            log "sshd still unavailable; direct TCP SSH will be unavailable"
            return
        fi
    fi

    mkdir -p /root/.ssh /run/sshd
    chmod 700 /root/.ssh
    if [ -n "${PUBLIC_KEY:-}" ]; then
        printf '%s\n' "${PUBLIC_KEY}" | awk '/^ssh-/' > /root/.ssh/authorized_keys
        chmod 600 /root/.ssh/authorized_keys
    fi
    if command -v ssh-keygen >/dev/null 2>&1; then
        ssh-keygen -A >/dev/null 2>&1 || true
    fi
    if pgrep -x sshd >/dev/null 2>&1; then
        log "sshd already running"
    else
        "$sshd_bin"
        log "sshd started for direct TCP diagnostics"
    fi
}
start_sshd_for_diagnostics

ROOT_DIR="${ALLBOT_RUNPOD_ROOT:-/workspace/allbot}"
REPO_URL="${ALLBOT_RUNPOD_GIT_URL:-https://github.com/giraffu/All_bot.git}"
REPO_BRANCH="${ALLBOT_RUNPOD_GIT_BRANCH:-deploy}"
REPO_DIR="${ALLBOT_RUNPOD_REPO_DIR:-${ROOT_DIR}/repo}"
REMOTE_WORKERS_DIR="${ALLBOT_RUNPOD_REMOTE_WORKERS_DIR:-${REPO_DIR}/remote_workers}"
WORKSPACE_DIR="${RUNPOD_WORKSPACE_DIR:-/workspace}"
VOLUME_COMFYUI_DIR="${RUNPOD_VOLUME_COMFYUI_DIR:-${WORKSPACE_DIR}/ComfyUI}"
PIP_CACHE_DIR="${PIP_CACHE_DIR:-${WORKSPACE_DIR}/.cache/pip}"
COMFY_READY_TIMEOUT_SECONDS="${RUNPOD_COMFY_READY_TIMEOUT_SECONDS:-900}"
COMFY_READY_INTERVAL_SECONDS="${RUNPOD_COMFY_READY_INTERVAL_SECONDS:-5}"
RELAY_READY_TIMEOUT_SECONDS="${RUNPOD_RELAY_READY_TIMEOUT_SECONDS:-120}"
RELAY_READY_PATH="${RUNPOD_RELAY_READY_PATH:-/health}"
LOCAL_RELAY_HOST="${LOCAL_RELAY_HOST:-127.0.0.1}"
LOCAL_RELAY_PORT="${LOCAL_RELAY_PORT:-8013}"
RUNPOD_POD_ID_SAFE="${RUNPOD_POD_ID:-${POD_ID:-$(hostname 2>/dev/null || echo pending)}}"

cleanup() {
    if [ -n "${RELAY_PID:-}" ]; then
        kill "$RELAY_PID" >/dev/null 2>&1 || true
    fi
    if [ -n "${COMFY_PID:-}" ]; then
        kill "$COMFY_PID" >/dev/null 2>&1 || true
    fi
}
trap cleanup INT TERM

if [ -z "${AGENT_ID:-}" ] || [[ "${AGENT_ID}" == *'${RUNPOD_POD_ID'* ]] || [[ "${AGENT_ID}" == *'${POD_ID'* ]]; then
    export AGENT_ID="${AGENT_ID_PREFIX:-runpod_test_img2img_lora}_${RUNPOD_POD_ID_SAFE}"
fi

export NO_PROXY="${NO_PROXY:-*}"
export no_proxy="${no_proxy:-*}"
export MASTER_API_URL="${MASTER_API_URL:-http://${LOCAL_RELAY_HOST}:${LOCAL_RELAY_PORT}}"
export UPLOAD_SIDECAR_URL="${UPLOAD_SIDECAR_URL:-http://${LOCAL_RELAY_HOST}:${LOCAL_RELAY_PORT}}"
export SUPPORTED_TASK_TYPES="${SUPPORTED_TASK_TYPES:-img2img,img2img_lora}"
export COMFY_API_URL="${COMFY_API_URL:-http://127.0.0.1:8188}"
export COMFY_WS_URL="${COMFY_WS_URL:-ws://127.0.0.1:8188/ws}"
export COMFY_INPUT_DIR="${COMFY_INPUT_DIR:-./input}"
export COMFY_OUTPUT_DIR="${COMFY_OUTPUT_DIR:-./output}"
export MINIO_INPUT_BUCKET="${MINIO_INPUT_BUCKET:-user-data-test}"
export MINIO_RESULT_BUCKET="${MINIO_RESULT_BUCKET:-user-data-test}"
export MINIO_TEMPLATE_BUCKET="${MINIO_TEMPLATE_BUCKET:-user-data-test}"
export MINIO_SECURE="${MINIO_SECURE:-true}"
export PIPELINE_ENABLED="${PIPELINE_ENABLED:-true}"
export PIPELINE_MAX_RUNNING_TASKS="${PIPELINE_MAX_RUNNING_TASKS:-1}"
export PREFETCH_ENABLED="${PREFETCH_ENABLED:-false}"
export CANCEL_LOCK_ON_POP="${CANCEL_LOCK_ON_POP:-true}"
export RESULT_SPOOL_DIR="${RESULT_SPOOL_DIR:-./spool/${AGENT_ID:-runpod_worker}}"
export PREFETCH_CACHE_DIR="${PREFETCH_CACHE_DIR:-./prefetch-cache/${AGENT_ID:-runpod_worker}}"
export PIP_CACHE_DIR

mkdir -p "$ROOT_DIR"
if [ -d "${REMOTE_WORKERS_DIR}/comfy_agent" ] && [ -f "${REMOTE_WORKERS_DIR}/requirements.txt" ]; then
    log "using existing AllBot remote worker bundle at ${REMOTE_WORKERS_DIR}"
else
    log "cloning AllBot remote worker bundle"
    rm -rf "$REPO_DIR"
    git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$REPO_DIR"
fi

cd "$REMOTE_WORKERS_DIR"
export PYTHONPATH="${REMOTE_WORKERS_DIR}:${REPO_DIR}:${PYTHONPATH:-}"
python3 - <<'PY'
from pathlib import Path

relay_path = Path("remote_relay/relay_main.py")
if relay_path.exists():
    text = relay_path.read_text(encoding="utf-8")
    text = text.replace(
        "async def update_status(request: Request) -> dict[str, str] | JSONResponse:",
        "async def update_status(request: Request):",
    )
    relay_path.write_text(text, encoding="utf-8")

agent_path = Path("comfy_agent/agent_main.py")
if agent_path.exists():
    text = agent_path.read_text(encoding="utf-8")
    text = text.replace(
        "params: dict[str, str] = {}",
        "params: dict[str, str] = {\"agent_id\": AGENT_ID}",
    )
    agent_path.write_text(text, encoding="utf-8")

patcher_path = Path("comfy_agent/workflow_task_patchers.py")
if patcher_path.exists():
    text = patcher_path.read_text(encoding="utf-8")
    if "WAN22_VIDEO_V2_LAST_FRAME_FALLBACK_INDEX" not in text:
        text = text.replace(
            'WAN22_VIDEO_V2_LAST_FRAME_NODE_ID = "2607"\n',
            'WAN22_VIDEO_V2_LAST_FRAME_NODE_ID = "2607"\n'
            "WAN22_VIDEO_V2_LAST_FRAME_FALLBACK_INDEX = 4095\n",
        )
    if 'input_name="resolution_preset"' not in text:
        old_resolution_patch = '''    set_node_input(
        workflow,
        node_id=WAN22_VIDEO_V2_RESOLUTION_NODE_ID,
        input_name="precision_presets",
        value=_normalize_wan22_video_v2_precision_preset(
            params.get("resolution_preset")
        ),
    )
'''
        new_resolution_patch = old_resolution_patch + '''    set_node_input(
        workflow,
        node_id=WAN22_VIDEO_V2_RESOLUTION_NODE_ID,
        input_name="resolution_preset",
        value=_normalize_wan22_video_v2_precision_preset(
            params.get("resolution_preset")
        ),
    )
    set_node_input(
        workflow,
        node_id=WAN22_VIDEO_V2_RESOLUTION_NODE_ID,
        input_name="swap_aspect_when_not_image",
        value=False,
    )
    set_node_input(
        workflow,
        node_id=WAN22_VIDEO_V2_RESOLUTION_NODE_ID,
        input_name="aspect_preset_when_not_image",
        value="9:16 - Social",
    )
    set_node_input(
        workflow,
        node_id=WAN22_VIDEO_V2_RESOLUTION_NODE_ID,
        input_name="custom_aspect_width",
        value=16,
    )
    set_node_input(
        workflow,
        node_id=WAN22_VIDEO_V2_RESOLUTION_NODE_ID,
        input_name="custom_aspect_height",
        value=9,
    )
'''
        text = text.replace(old_resolution_patch, new_resolution_patch)
    text = text.replace(
        'input_name="batch_index",\n        value=16384,',
        'input_name="batch_index",\n'
        "        value=WAN22_VIDEO_V2_LAST_FRAME_FALLBACK_INDEX,",
    )
    patcher_path.write_text(text, encoding="utf-8")

sync_path = Path("scripts/runpod_sync_models_from_r2.py")
if sync_path.exists():
    text = sync_path.read_text(encoding="utf-8")
    if "_download_object_with_resume" not in text:
        text = text.replace(
            "import sys\nfrom pathlib import Path",
            "import sys\nimport time\nfrom pathlib import Path",
        )
        text = text.replace(
            """def _bool_env(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
""",
            """def _bool_env(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, *, default: int, minimum: int = 1) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return max(minimum, value)


def _sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
""",
        )
        text = text.replace(
            """def _sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_endpoint(raw_endpoint: str, secure: bool) -> tuple[str, bool]:
""",
            """def _sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format_mib(byte_count: int) -> str:
    return f"{byte_count / 1024 / 1024:.1f} MiB"


def _normalise_endpoint(raw_endpoint: str, secure: bool) -> tuple[str, bool]:
""",
        )
        helper_marker = (
            "\ndef sync_models(*, bucket: str, prefix: str, target_dir: Path, "
            "verify_existing: bool) -> dict[str, object]:\n"
        )
        helper_code = r'''

def _stream_object_to_file(
    client: Minio,
    *,
    bucket: str,
    key: str,
    target: Path,
    offset: int,
    chunk_size: int,
    expected_size: int,
    relative_path: str,
) -> None:
    progress_bytes = _int_env(
        "RUNPOD_MODEL_DOWNLOAD_PROGRESS_BYTES",
        default=512 * 1024 * 1024,
        minimum=1024 * 1024,
    )
    progress_seconds = _int_env("RUNPOD_MODEL_DOWNLOAD_PROGRESS_SECONDS", default=30)
    response = client.get_object(bucket, key, offset=offset)
    try:
        started_at = time.monotonic()
        last_logged_at = started_at
        last_logged_size = offset
        with target.open("ab") as file_obj:
            for chunk in response.stream(amt=chunk_size):
                if chunk:
                    file_obj.write(chunk)
                    current_size = file_obj.tell()
                    now = time.monotonic()
                    should_log = (
                        current_size >= expected_size
                        or current_size - last_logged_size >= progress_bytes
                        or now - last_logged_at >= progress_seconds
                    )
                    if should_log:
                        elapsed = max(now - started_at, 0.001)
                        downloaded = max(current_size - offset, 0)
                        rate = downloaded / elapsed
                        percent = current_size / expected_size * 100 if expected_size else 0.0
                        print(
                            "[runpod-model-sync] progress "
                            f"{relative_path}: {_format_mib(current_size)}/"
                            f"{_format_mib(expected_size)} ({percent:.1f}%, "
                            f"{_format_mib(int(rate))}/s)",
                            flush=True,
                        )
                        last_logged_at = now
                        last_logged_size = current_size
    finally:
        response.close()
        response.release_conn()


def _download_object_with_resume(
    client: Minio,
    *,
    bucket: str,
    key: str,
    temp_target: Path,
    expected_size: int,
    relative_path: str,
) -> None:
    max_attempts = _int_env("RUNPOD_MODEL_DOWNLOAD_MAX_ATTEMPTS", default=8)
    retry_seconds = _int_env("RUNPOD_MODEL_DOWNLOAD_RETRY_SECONDS", default=5, minimum=0)
    chunk_size = _int_env(
        "RUNPOD_MODEL_DOWNLOAD_CHUNK_SIZE",
        default=1024 * 1024,
        minimum=64 * 1024,
    )

    for attempt in range(1, max_attempts + 1):
        current_size = temp_target.stat().st_size if temp_target.exists() else 0
        if current_size == expected_size:
            return
        if current_size > expected_size:
            print(
                f"[runpod-model-sync] discarding oversized partial {relative_path} "
                f"({current_size} > {expected_size})"
            )
            temp_target.unlink(missing_ok=True)
            current_size = 0

        action = "resuming" if current_size else "downloading"
        print(
            f"[runpod-model-sync] {action} {relative_path} "
            f"at byte {current_size}/{expected_size} "
            f"(attempt {attempt}/{max_attempts})",
            flush=True,
        )
        try:
            _stream_object_to_file(
                client,
                bucket=bucket,
                key=key,
                target=temp_target,
                offset=current_size,
                chunk_size=chunk_size,
                expected_size=expected_size,
                relative_path=relative_path,
            )
        except Exception as exc:
            partial_size = temp_target.stat().st_size if temp_target.exists() else 0
            print(
                f"[runpod-model-sync] interrupted {relative_path} after "
                f"{partial_size}/{expected_size} bytes: {type(exc).__name__}",
                flush=True,
            )
            if attempt >= max_attempts:
                raise RuntimeError(
                    f"download failed for {relative_path} after {max_attempts} attempts"
                ) from exc
            if retry_seconds:
                time.sleep(retry_seconds)
            continue

        current_size = temp_target.stat().st_size if temp_target.exists() else 0
        if current_size == expected_size:
            return
        if current_size > expected_size:
            temp_target.unlink(missing_ok=True)
            raise RuntimeError(
                f"size mismatch for {relative_path}: expected {expected_size}, got {current_size}"
            )
        if attempt >= max_attempts:
            raise RuntimeError(
                f"incomplete download for {relative_path}: expected {expected_size}, got {current_size}"
            )
        if retry_seconds:
            time.sleep(retry_seconds)
'''
        if helper_marker not in text:
            raise SystemExit("runpod model sync patch marker not found")
        text = text.replace(helper_marker, helper_code + helper_marker)
        old_download = """        temp_target = target.with_name(f"{target.name}.partial")
        if temp_target.exists():
            temp_target.unlink()
        print(f"[runpod-model-sync] downloading {relative_path} ({expected_size} bytes)")
        client.fget_object(bucket, key, str(temp_target))
"""
        new_download = """        temp_target = target.with_name(f"{target.name}.partial")
        _download_object_with_resume(
            client,
            bucket=bucket,
            key=key,
            temp_target=temp_target,
            expected_size=expected_size,
            relative_path=relative_path,
        )
"""
        if old_download not in text:
            raise SystemExit("runpod model sync download block not found")
        text = text.replace(old_download, new_download)
        sync_path.write_text(text, encoding="utf-8")
PY
python3 -m pip install -r requirements.txt
mkdir -p "$COMFY_INPUT_DIR" "$COMFY_OUTPUT_DIR" "$RESULT_SPOOL_DIR" "$PREFETCH_CACHE_DIR" logs

resolve_baked_comfyui_dir() {
    if [ -f /opt/allbot-comfyui-dir ]; then
        local baked_dir
        baked_dir="$(cat /opt/allbot-comfyui-dir)"
        if [ -n "$baked_dir" ] && [ -f "${baked_dir}/main.py" ]; then
            printf '%s\n' "$baked_dir"
            return 0
        fi
    fi
    return 1
}

if [ "${RUNPOD_PREPARE_COMFYUI_ON_VOLUME:-false}" = "true" ] \
    && [ ! -f "${VOLUME_COMFYUI_DIR}/main.py" ]; then
    seed_comfyui_dir=""
    if [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then
        seed_comfyui_dir="/default-comfyui-bundle/ComfyUI"
    elif seed_comfyui_dir="$(resolve_baked_comfyui_dir)"; then
        true
    fi
    if [ -n "$seed_comfyui_dir" ]; then
        log "seeding ComfyUI bundle into ${VOLUME_COMFYUI_DIR}"
        mkdir -p "$VOLUME_COMFYUI_DIR"
        cp -a "${seed_comfyui_dir}/." "$VOLUME_COMFYUI_DIR/"
    fi
fi

resolve_comfyui_dir_for_models() {
    if [ -n "${COMFYUI_DIR:-}" ] && [ -f "${COMFYUI_DIR}/main.py" ]; then
        printf '%s\n' "$COMFYUI_DIR"
    elif [ -f "${VOLUME_COMFYUI_DIR}/main.py" ]; then
        printf '%s\n' "$VOLUME_COMFYUI_DIR"
    elif baked_comfyui_dir="$(resolve_baked_comfyui_dir)"; then
        printf '%s\n' "$baked_comfyui_dir"
    elif [ -f /workspace/ComfyUI/main.py ]; then
        printf '%s\n' "/workspace/ComfyUI"
    elif [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then
        printf '%s\n' "/default-comfyui-bundle/ComfyUI"
    else
        return 1
    fi
}

install_comfyui_custom_nodes() {
    if [ "${RUNPOD_COMFY_CUSTOM_NODES_ENABLED:-true}" != "true" ]; then
        log "RunPod ComfyUI custom node install disabled"
        return
    fi

    local comfyui_dir="${RUNPOD_COMFY_CUSTOM_NODES_DIR:-}"
    if [ -z "$comfyui_dir" ]; then
        if resolved_comfy_dir="$(resolve_comfyui_dir_for_models)"; then
            comfyui_dir="$resolved_comfy_dir"
        fi
    fi
    if [ -z "$comfyui_dir" ] || [ ! -f "${comfyui_dir}/main.py" ]; then
        echo "RUNPOD_COMFY_CUSTOM_NODES_ENABLED=true but no ComfyUI directory was found." >&2
        exit 75
    fi

    if [ "${RUNPOD_COMFY_KJNODES_ENABLED:-true}" = "true" ]; then
        local repo_url="${RUNPOD_COMFY_KJNODES_REPO_URL:-https://github.com/kijai/ComfyUI-KJNodes.git}"
        local repo_ref="${RUNPOD_COMFY_KJNODES_REF:-}"
        local target_dir="${comfyui_dir%/}/custom_nodes/ComfyUI-KJNodes"
        mkdir -p "${comfyui_dir%/}/custom_nodes"
        if [ -d "${target_dir}/.git" ]; then
            log "updating ComfyUI-KJNodes in ${target_dir}"
            git -C "$target_dir" fetch --depth 1 origin "${repo_ref:-HEAD}"
            if [ -n "$repo_ref" ]; then
                git -C "$target_dir" checkout --force FETCH_HEAD
            else
                git -C "$target_dir" reset --hard FETCH_HEAD
            fi
        elif [ -d "$target_dir" ]; then
            log "ComfyUI-KJNodes already exists at ${target_dir}; leaving non-git directory unchanged"
        else
            log "installing ComfyUI-KJNodes into ${target_dir}"
            if [ -n "$repo_ref" ]; then
                git clone --depth 1 --branch "$repo_ref" "$repo_url" "$target_dir"
            else
                git clone --depth 1 "$repo_url" "$target_dir"
            fi
        fi
        if [ -f "${target_dir}/requirements.txt" ]; then
            python3 -m pip install -r "${target_dir}/requirements.txt"
        fi
    fi
}

if [ "${RUNPOD_MODEL_SYNC_ENABLED:-false}" = "true" ]; then
    COMFYUI_MODEL_SYNC_DIR="${RUNPOD_MODEL_COMFYUI_DIR:-}"
    if [ -z "$COMFYUI_MODEL_SYNC_DIR" ]; then
        if resolved_comfy_dir="$(resolve_comfyui_dir_for_models)"; then
            COMFYUI_MODEL_SYNC_DIR="$resolved_comfy_dir"
        fi
    fi
    if [ -z "$COMFYUI_MODEL_SYNC_DIR" ]; then
        echo "RUNPOD_MODEL_SYNC_ENABLED=true but no ComfyUI directory was found." >&2
        exit 75
    fi
    export RUNPOD_MODEL_TARGET_DIR="${RUNPOD_MODEL_TARGET_DIR:-${COMFYUI_MODEL_SYNC_DIR%/}/models}"
    log "syncing RunPod model bundle into ${RUNPOD_MODEL_TARGET_DIR}"
    python3 "$REMOTE_WORKERS_DIR/scripts/runpod_sync_models_from_r2.py" \
        --bucket "${RUNPOD_MODEL_BUCKET:-}" \
        --prefix "${RUNPOD_MODEL_PREFIX:-img2img_lora/2026-06-10}" \
        --target-dir "$RUNPOD_MODEL_TARGET_DIR"
fi

install_comfyui_custom_nodes

if [ -n "${COMFYUI_DIR:-}" ] && [ -f "${COMFYUI_DIR}/main.py" ]; then
    log "starting ComfyUI from COMFYUI_DIR"
    (
        cd "$COMFYUI_DIR"
        python3 main.py --listen 0.0.0.0 --port 8188 ${COMFY_EXTRA_ARGS:-}
    ) &
    COMFY_PID="$!"
elif [ -n "${COMFY_START_CMD:-}" ]; then
    log "starting ComfyUI from COMFY_START_CMD"
    bash -lc "$COMFY_START_CMD" &
    COMFY_PID="$!"
elif [ -f "${VOLUME_COMFYUI_DIR}/main.py" ]; then
    log "starting ComfyUI from ${VOLUME_COMFYUI_DIR}"
    (
        cd "$VOLUME_COMFYUI_DIR"
        python3 main.py --listen 0.0.0.0 --port 8188 ${COMFY_EXTRA_ARGS:-}
    ) &
    COMFY_PID="$!"
elif baked_comfyui_dir="$(resolve_baked_comfyui_dir)"; then
    log "starting ComfyUI from ${baked_comfyui_dir}"
    (
        cd "$baked_comfyui_dir"
        python3 main.py --listen 0.0.0.0 --port 8188 ${COMFY_EXTRA_ARGS:-}
    ) &
    COMFY_PID="$!"
elif [ -f /workspace/ComfyUI/main.py ]; then
    log "starting ComfyUI from /workspace/ComfyUI"
    (
        cd /workspace/ComfyUI
        python3 main.py --listen 0.0.0.0 --port 8188 ${COMFY_EXTRA_ARGS:-}
    ) &
    COMFY_PID="$!"
elif [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then
    log "starting ComfyUI from /default-comfyui-bundle/ComfyUI"
    (
        cd /default-comfyui-bundle/ComfyUI
        python3 main.py --listen 0.0.0.0 --port 8188 ${COMFY_EXTRA_ARGS:-}
    ) &
    COMFY_PID="$!"
else
    echo "No known ComfyUI main.py path found and COMFY_START_CMD is not set." >&2
    exit 75
fi

deadline=$(( $(date +%s) + COMFY_READY_TIMEOUT_SECONDS ))
until curl -fsS "${COMFY_API_URL%/}/system_stats" >/dev/null 2>&1; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
        echo "ComfyUI did not become ready before timeout: ${COMFY_API_URL}" >&2
        exit 75
    fi
    sleep "$COMFY_READY_INTERVAL_SECONDS"
done

log "ComfyUI ready; starting remote relay"
REMOTE_WORKER_ENV_FILE="${REMOTE_WORKER_ENV_FILE:-}" python3 -m remote_relay.relay_main &
RELAY_PID="$!"

relay_deadline=$(( $(date +%s) + RELAY_READY_TIMEOUT_SECONDS ))
until curl -fsS "http://${LOCAL_RELAY_HOST}:${LOCAL_RELAY_PORT}${RELAY_READY_PATH}" >/dev/null 2>&1; do
    if [ "$(date +%s)" -ge "$relay_deadline" ]; then
        echo "Remote relay did not become ready before timeout: ${RELAY_READY_PATH}" >&2
        exit 75
    fi
    sleep 2
done

log "remote relay ready; starting comfy agent"
python3 "$REMOTE_WORKERS_DIR/comfy_agent/agent_main.py"
agent_status="$?"
if [ "${RUNPOD_KEEPALIVE_ON_BOOTSTRAP_FAILURE:-false}" = "true" ]; then
    log "comfy agent exited with status ${agent_status}; keeping container alive for SSH diagnostics"
    while true; do
        sleep 3600
    done
fi
exit "$agent_status"
