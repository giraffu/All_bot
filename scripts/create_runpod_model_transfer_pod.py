#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
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


def _transfer_start_script() -> str:
    return r"""set -eu
LOG_FILE="${RUNPOD_TRANSFER_LOG_FILE:-/tmp/allbot-model-transfer.log}"
exec > "$LOG_FILE" 2>&1
echo "[model-transfer] boot $(date -Is)"
python3 -m pip install --no-cache-dir boto3
python3 - <<'PY'
import hashlib
import os
import sys
import urllib.request

import boto3
from botocore.config import Config

source_url = os.environ["MODEL_SOURCE_URL"]
bucket = os.environ["RUNPOD_MODEL_BUCKET"]
key = os.environ["RUNPOD_MODEL_KEY"]
expected_sha = os.environ["RUNPOD_MODEL_EXPECTED_SHA256"]
expected_size = int(os.environ["RUNPOD_MODEL_EXPECTED_SIZE"])
relative_path = os.environ.get("RUNPOD_MODEL_RELATIVE_PATH", "")
endpoint = os.environ["RUNPOD_MODEL_ENDPOINT"]
if "://" not in endpoint:
    endpoint = "https://" + endpoint

client = boto3.client(
    "s3",
    endpoint_url=endpoint,
    aws_access_key_id=os.environ["RUNPOD_MODEL_ACCESS_KEY"],
    aws_secret_access_key=os.environ["RUNPOD_MODEL_SECRET_KEY"],
    region_name="auto",
    config=Config(signature_version="s3v4"),
)

try:
    existing = client.head_object(Bucket=bucket, Key=key)
    metadata = existing.get("Metadata") or {}
    if int(existing.get("ContentLength") or 0) == expected_size and metadata.get("sha256") == expected_sha:
        print("[model-transfer] object already exists and matches", flush=True)
        sys.exit(0)
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
            "source": "hf-url",
        },
    )
    upload_id = created["UploadId"]
    request = urllib.request.Request(source_url, headers={"User-Agent": "AllBotModelTransfer/1.0"})
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
PY
touch /tmp/allbot-model-transfer.done
echo "[model-transfer] done $(date -Is)"
tail -f /dev/null
"""


def _create_body(args: argparse.Namespace) -> dict[str, Any]:
    endpoint = os.getenv("RUNPOD_MODEL_ENDPOINT") or os.getenv("MINIO_ENDPOINT") or ""
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
        "env": {
            "RUNPOD_MANAGED": "true",
            "ALLBOT_RUNPOD_MANAGED": "true",
            "RUNPOD_TASK_TYPE": "model_transfer",
            "RUNPOD_ENVIRONMENT": "cloud-test",
            "RUNPOD_MODEL_BUCKET": args.bucket,
            "RUNPOD_MODEL_ENDPOINT": endpoint,
            "RUNPOD_MODEL_ACCESS_KEY": MODEL_R2_ACCESS_KEY_REF,
            "RUNPOD_MODEL_SECRET_KEY": MODEL_R2_SECRET_KEY_REF,
            "RUNPOD_MODEL_KEY": args.key,
            "RUNPOD_MODEL_RELATIVE_PATH": args.relative_path,
            "RUNPOD_MODEL_EXPECTED_SHA256": args.sha256,
            "RUNPOD_MODEL_EXPECTED_SIZE": str(args.size_bytes),
            "MODEL_SOURCE_URL": args.source_url,
        },
        "dockerStartCmd": ["sh", "-lc", _transfer_start_script()],
    }


def _redacted_body(body: dict[str, Any]) -> dict[str, Any]:
    redacted = json.loads(json.dumps(body))
    env = redacted.get("env") or {}
    if "RUNPOD_MODEL_ACCESS_KEY" in env:
        env["RUNPOD_MODEL_ACCESS_KEY"] = "<redacted>"
    if "RUNPOD_MODEL_SECRET_KEY" in env:
        env["RUNPOD_MODEL_SECRET_KEY"] = "<redacted>"
    if "MODEL_SOURCE_URL" in env:
        env["MODEL_SOURCE_URL"] = "<hf-resolve-url>"
    return redacted


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a temporary RunPod Pod to transfer a model URL into R2")
    parser.add_argument("--env-file", type=Path, default=Path(".env.cloud.test"))
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--bucket", default="allbot-model-cache")
    parser.add_argument("--key", default=DEFAULT_KEY)
    parser.add_argument("--relative-path", default=DEFAULT_RELATIVE_PATH)
    parser.add_argument("--sha256", default=DEFAULT_SHA256)
    parser.add_argument("--size-bytes", type=int, default=DEFAULT_SIZE_BYTES)
    parser.add_argument("--name", default=f"allbot-model-transfer-qwen-v23-{int(time.time())}")
    parser.add_argument("--image", default="python:3.11-slim")
    parser.add_argument("--cloud-type", default=os.getenv("RUNPOD_CLOUD_TYPE", "SECURE"))
    parser.add_argument("--container-disk-gb", type=int, default=20)
    parser.add_argument(
        "--gpu-type-id",
        action="append",
        dest="gpu_type_ids",
        default=[],
        help="RunPod GPU type id. Can be repeated.",
    )
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    _load_env_file(args.env_file)
    if not args.gpu_type_ids:
        args.gpu_type_ids = ["NVIDIA GeForce RTX 4090", "NVIDIA L40S", "NVIDIA GeForce RTX 5090"]

    api_key = os.getenv("RUNPOD_API_KEY", "")
    if not api_key:
        print(json.dumps({"ok": False, "error": "missing_RUNPOD_API_KEY"}, indent=2))
        return 2

    base_url = os.getenv("RUNPOD_API_BASE_URL", RUNPOD_API_BASE_URL)
    dry_run = _bool_env(os.getenv("RUNPOD_DRY_RUN"), default=True)
    autoscaler_enabled = _bool_env(os.getenv("RUNPOD_AUTOSCALER_ENABLED"), default=False)
    max_pods_total = _int_env(os.getenv("RUNPOD_MAX_PODS_TOTAL"), default=1)

    pods = _request(
        method="GET",
        path="/pods",
        api_key=api_key,
        base_url=base_url,
        params={"computeType": "GPU"},
    )
    existing = _managed_transfer_pods(pods)
    body = _create_body(args)
    guard_reasons = []
    if dry_run:
        guard_reasons.append("RUNPOD_DRY_RUN=true")
    if not autoscaler_enabled:
        guard_reasons.append("RUNPOD_AUTOSCALER_ENABLED=false")
    if max_pods_total != 1:
        guard_reasons.append("RUNPOD_MAX_PODS_TOTAL must be 1")
    if existing:
        guard_reasons.append("model transfer pod already exists")

    if not args.execute or guard_reasons:
        print(
            json.dumps(
                {
                    "ok": not bool(guard_reasons),
                    "dry_run": True,
                    "guard": {"allowed": not guard_reasons, "reasons": guard_reasons},
                    "existing_transfer_pod_count": len(existing),
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
