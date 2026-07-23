#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


RUNPOD_API_BASE_URL = "https://rest.runpod.io/v1"
DEFAULT_SOURCE_URL = (
    "https://huggingface.co/Phr00t/Qwen-Image-Edit-Rapid-AIO/resolve/main/"
    "v23/Qwen-Rapid-AIO-NSFW-v23.safetensors"
)
DEFAULT_KEY = "img2img_lora/2026-06-10/models/checkpoints/Qwen-Rapid-AIO-NSFW-v23.safetensors"
DEFAULT_RELATIVE_PATH = "checkpoints/Qwen-Rapid-AIO-NSFW-v23.safetensors"
DEFAULT_SHA256 = "fdb919fc81bea63f13759967fc92c9118142e5c70d4e6795199233a35eefa233"
DEFAULT_SIZE_BYTES = 28431840023
MODEL_R2_ACCESS_KEY_REF = "{{ RUNPOD_SECRET_allbot_model_cache_r2_access_key }}"
MODEL_R2_SECRET_KEY_REF = "{{ RUNPOD_SECRET_allbot_model_cache_r2_secret_key }}"
CIVITAI_TOKEN_SECRET_REF = "{{ RUNPOD_SECRET_allbot_civitai_api_token }}"
PORNMASTER_FLUX2_EDIT_BF16_PREFIX = "pornmaster_flux2_edit_bf16/2026-07-12"
PORNMASTER_FLUX2_EDIT_BF16_TRANSFERS = (
    {
        "source_url": "https://civitai.com/api/download/models/3025484",
        "key": (
            f"{PORNMASTER_FLUX2_EDIT_BF16_PREFIX}/models/diffusion_models/flux2/"
            "PornMaster_flux2_klein_9b_turbo_bf16_V4.safetensors"
        ),
        "relative_path": (
            "diffusion_models/flux2/"
            "PornMaster_flux2_klein_9b_turbo_bf16_V4.safetensors"
        ),
        "sha256": "5085c05fa34b2455245a75f393885780b41e80a7517265b4b53da2e5044b004e",
        "size_bytes": 18157213600,
        "source_token_env": "CIVITAI_API_TOKEN",
        "source_token_query_param": "token",
    },
    {
        "source_url": (
            "https://huggingface.co/Comfy-Org/flux2-klein-9B/resolve/main/"
            "split_files/text_encoders/qwen_3_8b_fp8mixed.safetensors"
        ),
        "key": (
            f"{PORNMASTER_FLUX2_EDIT_BF16_PREFIX}/models/text_encoders/flux2/"
            "qwen_3_8b_fp8mixed.safetensors"
        ),
        "relative_path": "text_encoders/flux2/qwen_3_8b_fp8mixed.safetensors",
        "sha256": "abad16806e0cbabc54e0325d6565847443fe396d5f0be38bb3cd3fe75a1201d6",
        "size_bytes": 8664848742,
    },
    {
        "source_url": (
            "https://huggingface.co/black-forest-labs/"
            "FLUX.2-small-decoder/resolve/main/full_encoder_small_decoder.safetensors"
        ),
        "key": (
            f"{PORNMASTER_FLUX2_EDIT_BF16_PREFIX}/models/vae/flux2/"
            "full_encoder_small_decoder.safetensors"
        ),
        "relative_path": "vae/flux2/full_encoder_small_decoder.safetensors",
        "sha256": "ea4273f02d1fafbf8e1d1c2cf6018ed8748652eb0bf34f2dd91171f16f15ab62",
        "size_bytes": 249519092,
    },
)


def _normalise_transfer_item(raw_item: dict[str, Any]) -> dict[str, Any]:
    source_url = str(raw_item.get("source_url") or raw_item.get("sourceUrl") or "").strip()
    key = str(raw_item.get("key") or raw_item.get("object_key") or raw_item.get("objectKey") or "").strip()
    relative_path = str(
        raw_item.get("relative_path")
        or raw_item.get("relativePath")
        or ""
    ).strip()
    sha256 = str(raw_item.get("sha256") or raw_item.get("expected_sha256") or "").strip()
    size_value = raw_item.get("size_bytes") or raw_item.get("sizeBytes") or raw_item.get("expected_size")
    missing = [
        name
        for name, value in {
            "source_url": source_url,
            "key": key,
            "relative_path": relative_path,
            "sha256": sha256,
            "size_bytes": size_value,
        }.items()
        if value in {"", None}
    ]
    if missing:
        raise ValueError(f"model transfer item missing required field(s): {','.join(missing)}")
    item = {
        "source_url": source_url,
        "key": key.strip("/"),
        "relative_path": relative_path.lstrip("/"),
        "sha256": sha256,
        "size_bytes": int(size_value),
    }
    source_token_env = str(raw_item.get("source_token_env") or raw_item.get("sourceTokenEnv") or "").strip()
    source_token_query_param = str(
        raw_item.get("source_token_query_param")
        or raw_item.get("sourceTokenQueryParam")
        or ""
    ).strip()
    if source_token_env:
        item["source_token_env"] = source_token_env
    if source_token_query_param:
        item["source_token_query_param"] = source_token_query_param
    return item


def _load_transfer_items(args: argparse.Namespace) -> list[dict[str, Any]]:
    if getattr(args, "pornmaster_flux2_edit_bf16", False):
        if getattr(args, "batch_file", None):
            raise ValueError(
                "--pornmaster-flux2-edit-bf16 cannot be combined with --batch-file"
            )
        return [
            _normalise_transfer_item(item)
            for item in PORNMASTER_FLUX2_EDIT_BF16_TRANSFERS
        ]
    if getattr(args, "batch_file", None):
        raw_payload = json.loads(Path(args.batch_file).read_text(encoding="utf-8"))
        if isinstance(raw_payload, dict):
            raw_items = raw_payload.get("transfers") or raw_payload.get("files") or []
        else:
            raw_items = raw_payload
        if not isinstance(raw_items, list) or not raw_items:
            raise ValueError("batch transfer file must contain a non-empty list")
        return [_normalise_transfer_item(item) for item in raw_items]
    return [
        _normalise_transfer_item(
            {
                "source_url": args.source_url,
                "key": args.key,
                "relative_path": args.relative_path,
                "sha256": args.sha256,
                "size_bytes": args.size_bytes,
            }
        )
    ]


def _load_env_file(path: Path | None) -> None:
    if path is None or not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def _bool_env(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(value: str | None, *, default: int) -> int:
    if value is None or not value.strip():
        return default
    return int(value)


def _request(
    *,
    method: str,
    path: str,
    api_key: str,
    base_url: str,
    body: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"runpod_http_{exc.code}: {error_body[:1200]}") from exc
    if not text:
        return {}
    return json.loads(text)


def _managed_transfer_pods(pods: Any) -> list[dict[str, Any]]:
    raw_pods = pods if isinstance(pods, list) else pods.get("pods", [])
    result = []
    for pod in raw_pods:
        env = pod.get("env") or {}
        if (
            str(env.get("RUNPOD_MANAGED") or "").lower() == "true"
            and str(env.get("RUNPOD_TASK_TYPE") or "") == "model_transfer"
        ):
            result.append(pod)
    return result


def _transfer_guard_reasons(
    *,
    dry_run: bool,
    autoscaler_enabled: bool,
    max_pods_total: int,
    existing_count: int,
    confirmed: bool = True,
) -> list[str]:
    reasons = []
    if dry_run:
        reasons.append("RUNPOD_DRY_RUN=true")
    if not autoscaler_enabled:
        reasons.append("RUNPOD_AUTOSCALER_ENABLED=false")
    if not confirmed:
        reasons.append("--confirm-model-transfer is required")
    if not 1 <= max_pods_total <= 2:
        reasons.append("RUNPOD_MAX_PODS_TOTAL must be 1 or 2")
    if existing_count >= max_pods_total:
        reasons.append("model transfer pod limit reached")
    return reasons


def _transfer_start_script() -> str:
    return r"""set -eu
LOG_FILE="${RUNPOD_TRANSFER_LOG_FILE:-/tmp/allbot-model-transfer.log}"
exec > "$LOG_FILE" 2>&1
keepalive_on_failure() {
    status="$?"
    echo "[model-transfer] failed with exit status ${status}" >&2
    if [ "${RUNPOD_MODEL_TRANSFER_EXIT_ON_COMPLETE:-true}" = "false" ]; then
        echo "[model-transfer] keeping failed container alive for diagnostics" >&2
        tail -f /dev/null
    fi
    exit "$status"
}
trap keepalive_on_failure ERR
echo "[model-transfer] boot $(date -Is)"
if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends openssh-server
    rm -rf /var/lib/apt/lists/*
    mkdir -p /root/.ssh /run/sshd
    printf '%s\n' "${PUBLIC_KEY:-}" | awk '/^ssh-/' > /root/.ssh/authorized_keys
    chmod 700 /root/.ssh
    chmod 600 /root/.ssh/authorized_keys
    ssh-keygen -A >/dev/null 2>&1 || true
    /usr/sbin/sshd
    echo "[model-transfer] sshd started"
fi
python3 -m pip install --no-cache-dir boto3
python3 - <<'PY'
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request

import boto3
from botocore.config import Config

bucket = os.environ["RUNPOD_MODEL_BUCKET"]
endpoint = os.environ["RUNPOD_MODEL_ENDPOINT"]
if "://" not in endpoint:
    endpoint = "https://" + endpoint

raw_transfers = os.environ.get("RUNPOD_MODEL_TRANSFERS_JSON", "").strip()
if raw_transfers:
    transfers = json.loads(raw_transfers)
else:
    transfers = [
        {
            "source_url": os.environ["MODEL_SOURCE_URL"],
            "key": os.environ["RUNPOD_MODEL_KEY"],
            "relative_path": os.environ.get("RUNPOD_MODEL_RELATIVE_PATH", ""),
            "sha256": os.environ["RUNPOD_MODEL_EXPECTED_SHA256"],
            "size_bytes": int(os.environ["RUNPOD_MODEL_EXPECTED_SIZE"]),
        }
    ]

client = boto3.client(
    "s3",
    endpoint_url=endpoint,
    aws_access_key_id=os.environ["RUNPOD_MODEL_ACCESS_KEY"],
    aws_secret_access_key=os.environ["RUNPOD_MODEL_SECRET_KEY"],
    region_name="auto",
    config=Config(signature_version="s3v4"),
)

def source_request_for(item):
    source_url = item["source_url"]
    headers = {"User-Agent": "AllBotModelTransfer/1.0"}
    token_env = str(item.get("source_token_env") or "").strip()
    token_query_param = str(item.get("source_token_query_param") or "").strip()
    if token_env:
        token = os.environ.get(token_env, "").strip()
        if not token:
            raise RuntimeError(f"missing source token env: {token_env}")
        if token_query_param:
            split = urllib.parse.urlsplit(source_url)
            query = urllib.parse.parse_qsl(split.query, keep_blank_values=True)
            query = [(key, value) for key, value in query if key != token_query_param]
            query.append((token_query_param, token))
            source_url = urllib.parse.urlunsplit(
                (
                    split.scheme,
                    split.netloc,
                    split.path,
                    urllib.parse.urlencode(query),
                    split.fragment,
                )
            )
        else:
            headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(source_url, headers=headers)


def transfer_one(item, index, total):
    key = item["key"]
    expected_sha = item["sha256"]
    expected_size = int(item["size_bytes"])
    relative_path = item.get("relative_path", "")
    print(f"[model-transfer] item {index}/{total} {relative_path or key}", flush=True)
    try:
        existing = client.head_object(Bucket=bucket, Key=key)
        metadata = existing.get("Metadata") or {}
        if int(existing.get("ContentLength") or 0) == expected_size and metadata.get("sha256") == expected_sha:
            print("[model-transfer] object already exists and matches", flush=True)
            return
    except Exception:
        pass

    upload_id = ""
    parts = []
    digest = hashlib.sha256()
    transferred = 0
    part_size = 64 * 1024 * 1024
    try:
        created = client.create_multipart_upload(
            Bucket=bucket,
            Key=key,
            ContentType="application/octet-stream",
            Metadata={
                "sha256": expected_sha,
                "relative-path": relative_path,
                "source": "external-url",
            },
        )
        upload_id = created["UploadId"]
        request = source_request_for(item)
        with urllib.request.urlopen(request, timeout=120) as response:
            part_number = 1
            while True:
                chunk = response.read(part_size)
                if not chunk:
                    break
                digest.update(chunk)
                transferred += len(chunk)
                uploaded = client.upload_part(
                    Bucket=bucket,
                    Key=key,
                    UploadId=upload_id,
                    PartNumber=part_number,
                    Body=chunk,
                )
                parts.append({"PartNumber": part_number, "ETag": uploaded["ETag"]})
                if transferred == expected_size or transferred % (1024 * 1024 * 1024) < part_size:
                    print(f"[model-transfer] {transferred}/{expected_size} bytes", flush=True)
                part_number += 1

        actual_sha = digest.hexdigest()
        if transferred != expected_size:
            raise RuntimeError(f"size mismatch: {transferred} != {expected_size}")
        if actual_sha != expected_sha:
            raise RuntimeError(f"sha256 mismatch: {actual_sha} != {expected_sha}")
        client.complete_multipart_upload(
            Bucket=bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
        print("[model-transfer] complete", flush=True)
    except BaseException:
        if upload_id:
            try:
                client.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)
            except Exception:
                pass
        raise


for index, item in enumerate(transfers, start=1):
    transfer_one(item, index, len(transfers))
PY
touch /tmp/allbot-model-transfer.done
echo "[model-transfer] done $(date -Is)"
if [ "${RUNPOD_MODEL_TRANSFER_EXIT_ON_COMPLETE:-true}" != "false" ]; then
  exit 0
fi
tail -f /dev/null
"""


def _create_body(args: argparse.Namespace, items: list[dict[str, Any]]) -> dict[str, Any]:
    endpoint = os.getenv("RUNPOD_MODEL_ENDPOINT") or os.getenv("MINIO_ENDPOINT") or ""
    first_item = items[0]
    env = {
        "RUNPOD_MANAGED": "true",
        "ALLBOT_RUNPOD_MANAGED": "true",
        "RUNPOD_TASK_TYPE": "model_transfer",
        "RUNPOD_ENVIRONMENT": "cloud-test",
        "RUNPOD_MODEL_BUCKET": args.bucket,
        "RUNPOD_MODEL_ENDPOINT": endpoint,
        "RUNPOD_MODEL_ACCESS_KEY": MODEL_R2_ACCESS_KEY_REF,
        "RUNPOD_MODEL_SECRET_KEY": MODEL_R2_SECRET_KEY_REF,
        "RUNPOD_MODEL_TRANSFER_COUNT": str(len(items)),
        "RUNPOD_MODEL_TRANSFER_EXIT_ON_COMPLETE": (
            "false" if args.keepalive_on_complete else "true"
        ),
        "RUNPOD_MODEL_TRANSFERS_JSON": json.dumps(items, ensure_ascii=False, separators=(",", ":")),
        "RUNPOD_MODEL_KEY": first_item["key"],
        "RUNPOD_MODEL_RELATIVE_PATH": first_item["relative_path"],
        "RUNPOD_MODEL_EXPECTED_SHA256": first_item["sha256"],
        "RUNPOD_MODEL_EXPECTED_SIZE": str(first_item["size_bytes"]),
        "MODEL_SOURCE_URL": first_item["source_url"],
    }
    if any(item.get("source_token_env") == "CIVITAI_API_TOKEN" for item in items):
        if args.civitai_token_secret_ref:
            env["CIVITAI_API_TOKEN"] = args.civitai_token_secret_ref
    return {
        "name": args.name,
        "cloudType": args.cloud_type,
        "computeType": "GPU",
        "gpuCount": 1,
        "gpuTypeIds": args.gpu_type_ids,
        "gpuTypePriority": "availability",
        "containerDiskInGb": args.container_disk_gb,
        "volumeInGb": 0,
        "volumeMountPath": "/workspace",
        "interruptible": False,
        "imageName": args.image,
        "env": env,
        "dockerStartCmd": ["sh", "-lc", _transfer_start_script()],
    }


def _redacted_body(body: dict[str, Any]) -> dict[str, Any]:
    redacted = json.loads(json.dumps(body))
    env = redacted.get("env") or {}
    for key in list(env):
        normalized = key.upper()
        if "TOKEN" in normalized or "SECRET_KEY" in normalized or "ACCESS_KEY" in normalized:
            env[key] = "<redacted>"
    if "MODEL_SOURCE_URL" in env:
        env["MODEL_SOURCE_URL"] = "<source-url>"
    if "RUNPOD_MODEL_TRANSFERS_JSON" in env:
        try:
            items = json.loads(env["RUNPOD_MODEL_TRANSFERS_JSON"])
            for item in items:
                if "source_url" in item:
                    item["source_url"] = "<source-url>"
            env["RUNPOD_MODEL_TRANSFERS_JSON"] = json.dumps(
                items,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        except Exception:
            env["RUNPOD_MODEL_TRANSFERS_JSON"] = "<redacted>"
    return redacted


def _delete_guard_reasons(
    *,
    dry_run: bool,
    autoscaler_enabled: bool,
    confirmed: bool = True,
) -> list[str]:
    reasons = []
    if dry_run:
        reasons.append("RUNPOD_DRY_RUN=true")
    if not autoscaler_enabled:
        reasons.append("RUNPOD_AUTOSCALER_ENABLED=false")
    if not confirmed:
        reasons.append("--confirm-model-transfer is required")
    return reasons


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a temporary RunPod Pod to transfer a model URL into R2")
    parser.add_argument("--env-file", type=Path, default=Path(".env.cloud.test"))
    parser.add_argument(
        "--batch-file",
        type=Path,
        default=None,
        help="JSON file containing transfers/files with source_url, key, relative_path, sha256, size_bytes.",
    )
    parser.add_argument(
        "--pornmaster-flux2-edit-bf16",
        action="store_true",
        help=(
            "Use the built-in PornMaster Flux2 V4 turbo BF16 three-file "
            "direct-to-R2 transfer batch."
        ),
    )
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--bucket", default="allbot-model-cache")
    parser.add_argument("--key", default=DEFAULT_KEY)
    parser.add_argument("--relative-path", default=DEFAULT_RELATIVE_PATH)
    parser.add_argument("--sha256", default=DEFAULT_SHA256)
    parser.add_argument("--size-bytes", type=int, default=DEFAULT_SIZE_BYTES)
    parser.add_argument("--name", default=f"allbot-model-transfer-qwen-v23-{int(time.time())}")
    parser.add_argument("--image", default="python:3.11-slim")
    parser.add_argument(
        "--civitai-token-secret-ref",
        default=CIVITAI_TOKEN_SECRET_REF,
        help="RunPod secret reference injected as CIVITAI_API_TOKEN for the built-in PornMaster Civitai URL.",
    )
    parser.add_argument(
        "--keepalive-on-complete",
        action="store_true",
        help="Keep the transfer Pod alive after completion for manual inspection.",
    )
    parser.add_argument("--cloud-type", default=os.getenv("RUNPOD_CLOUD_TYPE", "SECURE"))
    parser.add_argument("--container-disk-gb", type=int, default=20)
    parser.add_argument(
        "--gpu-type-id",
        action="append",
        dest="gpu_type_ids",
        default=[],
        help="RunPod GPU type id. Can be repeated.",
    )
    parser.add_argument(
        "--delete-pod-id",
        default="",
        help="Delete a temporary transfer Pod by id instead of creating a new one.",
    )
    parser.add_argument(
        "--confirm-model-transfer",
        action="store_true",
        help="Required together with --execute for real transfer Pod create/delete mutations.",
    )
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    _load_env_file(args.env_file)
    if not args.gpu_type_ids:
        args.gpu_type_ids = ["NVIDIA GeForce RTX 4090", "NVIDIA L40S", "NVIDIA GeForce RTX 5090"]
    api_key = os.getenv("RUNPOD_API_KEY", "")
    if not api_key and args.execute:
        print(json.dumps({"ok": False, "error": "missing_RUNPOD_API_KEY"}, indent=2))
        return 2

    base_url = os.getenv("RUNPOD_API_BASE_URL", RUNPOD_API_BASE_URL)
    dry_run = _bool_env(os.getenv("RUNPOD_DRY_RUN"), default=True)
    autoscaler_enabled = _bool_env(os.getenv("RUNPOD_AUTOSCALER_ENABLED"), default=False)
    max_pods_total = _int_env(os.getenv("RUNPOD_MAX_PODS_TOTAL"), default=1)

    if args.delete_pod_id:
        guard_reasons = _delete_guard_reasons(
            dry_run=dry_run,
            autoscaler_enabled=autoscaler_enabled,
            confirmed=(not args.execute or args.confirm_model_transfer),
        )
        if not args.execute or guard_reasons:
            print(
                json.dumps(
                    {
                        "ok": not bool(guard_reasons),
                        "dry_run": True,
                        "delete_pod_id": args.delete_pod_id,
                        "guard": {
                            "allowed": not guard_reasons,
                            "reasons": guard_reasons,
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 2 if args.execute and guard_reasons else 0
        deleted = _request(
            method="DELETE",
            path=f"/pods/{urllib.parse.quote(args.delete_pod_id, safe='')}",
            api_key=api_key,
            base_url=base_url,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": False,
                    "deleted_pod_id": args.delete_pod_id,
                    "response": deleted,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    try:
        transfer_items = _load_transfer_items(args)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    existing: list[dict[str, Any]] = []
    pod_lookup_skipped = True
    preflight_guard_reasons = _transfer_guard_reasons(
        dry_run=dry_run,
        autoscaler_enabled=autoscaler_enabled,
        max_pods_total=max_pods_total,
        existing_count=0,
        confirmed=(not args.execute or args.confirm_model_transfer),
    )
    if args.execute and not preflight_guard_reasons and api_key:
        pods = _request(
            method="GET",
            path="/pods",
            api_key=api_key,
            base_url=base_url,
            params={"computeType": "GPU"},
        )
        pod_lookup_skipped = False
        existing = _managed_transfer_pods(pods)
    body = _create_body(args, transfer_items)
    guard_reasons = _transfer_guard_reasons(
        dry_run=dry_run,
        autoscaler_enabled=autoscaler_enabled,
        max_pods_total=max_pods_total,
        existing_count=len(existing),
        confirmed=(not args.execute or args.confirm_model_transfer),
    )

    if not args.execute or guard_reasons:
        print(
            json.dumps(
                {
                    "ok": not bool(guard_reasons),
                    "dry_run": True,
                    "guard": {"allowed": not guard_reasons, "reasons": guard_reasons},
                    "existing_transfer_pod_count": len(existing),
                    "pod_lookup_skipped": pod_lookup_skipped,
                    "transfer_count": len(transfer_items),
                    "request": _redacted_body(body),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2 if args.execute and guard_reasons else 0

    created = _request(
        method="POST",
        path="/pods",
        api_key=api_key,
        base_url=base_url,
        body=body,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "dry_run": False,
                "pod": {
                    "id": created.get("id"),
                    "name": created.get("name"),
                    "desiredStatus": created.get("desiredStatus") or created.get("status"),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
