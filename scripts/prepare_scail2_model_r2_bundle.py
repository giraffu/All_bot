#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse


DEFAULT_BUCKET = "allbot-model-cache"
DEFAULT_PREFIX = "scail2/2026-06-17-test"
DEFAULT_MANIFEST_KEY = f"{DEFAULT_PREFIX}/manifest.json"
CONTENT_TYPE = "application/octet-stream"
USER_AGENT = "AllBot-SCAIL2-Model-R2-Bundle/1.0"


@dataclass(frozen=True)
class Scail2ModelFile:
    relative_path: str
    url: str


SCAIL2_MODEL_FILES: tuple[Scail2ModelFile, ...] = (
    Scail2ModelFile(
        relative_path="checkpoints/sam3.1_multiplex_fp16.safetensors",
        url=(
            "https://huggingface.co/Comfy-Org/sam3.1/resolve/main/"
            "checkpoints/sam3.1_multiplex_fp16.safetensors"
        ),
    ),
    Scail2ModelFile(
        relative_path="clip_vision/clip_vision_h.safetensors",
        url=(
            "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/"
            "resolve/main/split_files/clip_vision/clip_vision_h.safetensors"
        ),
    ),
    Scail2ModelFile(
        relative_path="diffusion_models/wan2.1_14B_SCAIL_2_fp8_scaled.safetensors",
        url=(
            "https://huggingface.co/Comfy-Org/SCAIL-2/resolve/main/"
            "diffusion_models/wan2.1_14B_SCAIL_2_fp8_scaled.safetensors"
        ),
    ),
    Scail2ModelFile(
        relative_path=(
            "loras/Wan2.1/"
            "Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors"
        ),
        url=(
            "https://huggingface.co/lightx2v/"
            "Wan2.1-I2V-14B-480P-StepDistill-CfgDistill-Lightx2v/resolve/main/"
            "loras/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors"
        ),
    ),
    Scail2ModelFile(
        relative_path="text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        url=(
            "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/"
            "resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
        ),
    ),
    Scail2ModelFile(
        relative_path="vae/wan_2.1_vae.safetensors",
        url=(
            "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/"
            "resolve/main/split_files/vae/wan_2.1_vae.safetensors"
        ),
    ),
)


ProbeFunc = Callable[[str], dict[str, Any]]


class TransferProgress:
    def __init__(
        self,
        label: str,
        total_size: int | None,
        *,
        step_bytes: int = 1024 * 1024 * 1024,
    ) -> None:
        self.label = label
        self.total_size = total_size
        self.step_bytes = step_bytes
        self.transferred = 0
        self.last_reported = 0

    def add(self, amount: int) -> None:
        self.transferred += amount
        if (
            self.transferred - self.last_reported >= self.step_bytes
            or (self.total_size is not None and self.transferred >= self.total_size)
        ):
            self.last_reported = self.transferred
            suffix = f"/{self.total_size}" if self.total_size is not None else ""
            print(
                f"[scail2-model-r2] {self.label}: {self.transferred}{suffix} bytes",
                file=sys.stderr,
                flush=True,
            )


def _bool_env(value: str | None, *, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_env_file(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"loaded": False, "path": None}
    if not path.exists():
        return {"loaded": False, "path": str(path), "missing": True}
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = _strip_env_quotes(value.strip())
    return {"loaded": True, "path": str(path)}


def _strip_env_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def object_key_for(prefix: str, relative_path: str) -> str:
    return f"{prefix.strip('/')}/models/{relative_path.lstrip('/')}"


def manifest_key_for(prefix: str) -> str:
    return f"{prefix.strip('/')}/manifest.json"


def build_manifest(
    *,
    prefix: str,
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    total_size = sum(int(item.get("size_bytes") or 0) for item in files)
    return {
        "bundle": "scail2",
        "profile": "scail2",
        "version": "2026-06-17-test",
        "prefix": prefix.strip("/"),
        "source": {
            "type": "huggingface-direct-urls",
            "file_count": len(SCAIL2_MODEL_FILES),
        },
        "file_count": len(files),
        "total_size_bytes": total_size,
        "files": sorted(files, key=lambda item: str(item["relative_path"])),
    }


def prepare_scail2_model_r2_bundle(
    *,
    client: Any | None,
    bucket: str = DEFAULT_BUCKET,
    prefix: str = DEFAULT_PREFIX,
    execute: bool = False,
    skip_existing: bool = True,
    part_size_bytes: int = 64 * 1024 * 1024,
    probe_func: ProbeFunc = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    probe_func = probe_func or probe_url
    manifest_key = manifest_key_for(prefix)
    existing_manifest = (
        _read_existing_manifest(client, bucket=bucket, key=manifest_key)
        if client is not None
        else {}
    )
    existing_by_relative = {
        str(item.get("relative_path") or ""): item
        for item in existing_manifest.get("files", [])
        if isinstance(item, dict)
    }
    entries: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    errors: list[str] = []

    for item in SCAIL2_MODEL_FILES:
        key = object_key_for(prefix, item.relative_path)
        head = _head_object(client, bucket=bucket, key=key) if client is not None else None
        existing_entry = existing_by_relative.get(item.relative_path) or {}
        existing_sha = str(
            ((head or {}).get("Metadata") or {}).get("sha256")
            or existing_entry.get("sha256")
            or ""
        )
        existing_size = (
            int((head or {}).get("ContentLength") or 0) if head is not None else 0
        )
        if skip_existing and head is not None and existing_sha:
            entry = _manifest_file_entry(
                relative_path=item.relative_path,
                key=key,
                size_bytes=existing_size,
                sha256=existing_sha,
            )
            entries.append(entry)
            actions.append(
                {
                    "relative_path": item.relative_path,
                    "key": key,
                    "action": "skip_existing",
                    "size_bytes": existing_size,
                    "sha256": existing_sha,
                }
            )
            continue

        if not execute:
            probe = _safe_probe(probe_func, item.url)
            size_bytes = existing_size or int(probe.get("content_size") or 0)
            entries.append(
                _manifest_file_entry(
                    relative_path=item.relative_path,
                    key=key,
                    size_bytes=size_bytes,
                    sha256=existing_sha,
                )
            )
            actions.append(
                {
                    "relative_path": item.relative_path,
                    "key": key,
                    "action": "would_upload" if head is None else "would_refresh",
                    "remote_size_bytes": probe.get("content_size"),
                    "existing_size_bytes": existing_size or None,
                    "existing_sha256": existing_sha or None,
                }
            )
            continue

        if client is None:
            errors.append("R2 client is required when --execute is used")
            break
        uploaded = transfer_model_url_to_r2(
            client=client,
            source_url=item.url,
            bucket=bucket,
            key=key,
            relative_path=item.relative_path,
            part_size_bytes=part_size_bytes,
        )
        entry = _manifest_file_entry(
            relative_path=item.relative_path,
            key=key,
            size_bytes=int(uploaded["size_bytes"]),
            sha256=str(uploaded["sha256"]),
        )
        entries.append(entry)
        actions.append({"relative_path": item.relative_path, "key": key, **uploaded})

    manifest = build_manifest(prefix=prefix, files=entries)
    uploads: list[dict[str, Any]] = []
    if execute and not errors:
        missing_hash = [item["relative_path"] for item in entries if not item["sha256"]]
        if missing_hash:
            errors.append(
                "manifest entries missing sha256: " + ", ".join(sorted(missing_hash))
            )
        else:
            body = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            client.put_object(
                Bucket=bucket,
                Key=manifest_key,
                Body=body,
                ContentType="application/json",
            )
            uploads.append({"key": manifest_key, "bytes": len(body)})

    return {
        "ok": not errors,
        "dry_run": not execute,
        "bucket": bucket,
        "prefix": prefix.strip("/"),
        "manifest_key": manifest_key,
        "file_count": len(entries),
        "actions": actions,
        "uploads": uploads,
        "manifest": manifest,
        "errors": errors,
    }


def _manifest_file_entry(
    *,
    relative_path: str,
    key: str,
    size_bytes: int,
    sha256: str,
) -> dict[str, Any]:
    return {
        "relative_path": relative_path,
        "key": key,
        "size_bytes": int(size_bytes or 0),
        "sha256": sha256,
    }


def _safe_probe(probe_func: ProbeFunc, url: str) -> dict[str, Any]:
    try:
        return probe_func(url)
    except Exception as exc:
        return {"error": str(exc)}


def transfer_model_url_to_r2(
    *,
    client: Any,
    source_url: str,
    bucket: str,
    key: str,
    relative_path: str,
    part_size_bytes: int,
) -> dict[str, Any]:
    upload_id = ""
    parts: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    transferred = 0
    probe = _safe_probe(probe_url, source_url)
    total_size = (
        int(probe["content_size"]) if str(probe.get("content_size") or "").isdigit() else None
    )
    progress = TransferProgress(relative_path, total_size)
    try:
        create_resp = client.create_multipart_upload(
            Bucket=bucket,
            Key=key,
            ContentType=CONTENT_TYPE,
            Metadata={
                "relative-path": relative_path,
                "source": "scail2-huggingface-url",
            },
        )
        upload_id = create_resp["UploadId"]
        request = urllib.request.Request(
            source_url,
            method="GET",
            headers={"User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            part_number = 1
            while True:
                chunk = response.read(part_size_bytes)
                if not chunk:
                    break
                digest.update(chunk)
                transferred += len(chunk)
                part_resp = client.upload_part(
                    Bucket=bucket,
                    Key=key,
                    UploadId=upload_id,
                    PartNumber=part_number,
                    Body=chunk,
                )
                parts.append({"PartNumber": part_number, "ETag": part_resp["ETag"]})
                progress.add(len(chunk))
                part_number += 1
        sha256 = digest.hexdigest()
        client.complete_multipart_upload(
            Bucket=bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
        _replace_object_metadata(
            client,
            bucket=bucket,
            key=key,
            relative_path=relative_path,
            sha256=sha256,
        )
        return {
            "ok": True,
            "action": "uploaded",
            "size_bytes": transferred,
            "sha256": sha256,
            "part_count": len(parts),
        }
    except BaseException:
        if upload_id:
            try:
                client.abort_multipart_upload(
                    Bucket=bucket,
                    Key=key,
                    UploadId=upload_id,
                )
            except Exception:
                pass
        raise


def _replace_object_metadata(
    client: Any,
    *,
    bucket: str,
    key: str,
    relative_path: str,
    sha256: str,
) -> None:
    if not hasattr(client, "copy_object"):
        return
    client.copy_object(
        Bucket=bucket,
        Key=key,
        CopySource={"Bucket": bucket, "Key": key},
        ContentType=CONTENT_TYPE,
        Metadata={
            "sha256": sha256,
            "relative-path": relative_path,
            "source": "scail2-huggingface-url",
        },
        MetadataDirective="REPLACE",
    )


def probe_url(source_url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        source_url,
        method="GET",
        headers={"Range": "bytes=0-0", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        headers = {key.lower(): value for key, value in response.headers.items()}
        return {
            "status": response.status,
            "content_size": _content_size_from_headers(response.status, headers),
            "content_length": headers.get("content-length"),
            "content_range": headers.get("content-range"),
        }


def _content_size_from_headers(status: int, headers: dict[str, str]) -> int | None:
    content_range = headers.get("content-range", "")
    match = re.search(r"/(\d+)$", content_range)
    if match:
        return int(match.group(1))
    if status == 200 and headers.get("content-length"):
        return int(headers["content-length"])
    return None


def create_model_r2_client_from_env() -> Any:
    try:
        import boto3
        from botocore.config import Config
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"boto3 is required for R2 model upload: {exc}") from exc
    endpoint = (
        os.getenv("RUNPOD_MODEL_ENDPOINT")
        or os.getenv("R2_ENDPOINT")
        or os.getenv("MINIO_ENDPOINT")
        or ""
    )
    access_key = (
        os.getenv("RUNPOD_MODEL_ACCESS_KEY")
        or os.getenv("R2_ACCESS_KEY")
        or os.getenv("R2_ACCESS_KEY_ID")
        or os.getenv("MINIO_ACCESS_KEY")
        or ""
    )
    secret_key = (
        os.getenv("RUNPOD_MODEL_SECRET_KEY")
        or os.getenv("R2_SECRET_KEY")
        or os.getenv("R2_SECRET_ACCESS_KEY")
        or os.getenv("MINIO_SECRET_KEY")
        or ""
    )
    if not access_key or not secret_key:
        raise RuntimeError("RUNPOD_MODEL_ACCESS_KEY/RUNPOD_MODEL_SECRET_KEY is required")
    return boto3.client(
        "s3",
        endpoint_url=_endpoint_url(endpoint, _bool_env(os.getenv("RUNPOD_MODEL_SECURE"), default=True)),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=os.getenv("R2_REGION", "auto"),
        config=Config(signature_version="s3v4"),
    )


def _endpoint_url(raw_endpoint: str, secure: bool) -> str:
    endpoint = raw_endpoint.strip()
    if not endpoint:
        raise RuntimeError("RUNPOD_MODEL_ENDPOINT/R2_ENDPOINT/MINIO_ENDPOINT is required")
    if "://" in endpoint:
        parsed = urlparse(endpoint)
        if not parsed.netloc:
            raise RuntimeError("invalid R2 endpoint")
        return endpoint.rstrip("/")
    scheme = "https" if secure else "http"
    return f"{scheme}://{endpoint}"


def _head_object(client: Any, *, bucket: str, key: str) -> dict[str, Any] | None:
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except Exception as exc:
        code = _client_error_code(exc)
        if code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise RuntimeError(f"head_object failed for {key}: {_safe_client_error(exc)}") from exc


def _read_existing_manifest(client: Any, *, bucket: str, key: str) -> dict[str, Any]:
    try:
        response = client.get_object(Bucket=bucket, Key=key)
    except Exception as exc:
        code = _client_error_code(exc)
        if code in {"404", "NoSuchKey", "NotFound"}:
            return {}
        raise RuntimeError(f"get_object failed for {key}: {_safe_client_error(exc)}") from exc
    body = response["Body"].read()
    return json.loads(body.decode("utf-8") if isinstance(body, bytes) else str(body))


def _client_error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None) or {}
    error = response.get("Error") if isinstance(response, dict) else {}
    return str(error.get("Code") or "")


def _safe_client_error(exc: Exception) -> str:
    response = getattr(exc, "response", None) or {}
    error = response.get("Error") if isinstance(response, dict) else {}
    code = str(error.get("Code") or exc.__class__.__name__)
    message = str(error.get("Message") or exc)
    return f"{code}: {message}"


def _client_from_env_if_available() -> Any | None:
    try:
        return create_model_r2_client_from_env()
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare the SCAIL-2 model bundle in the R2 model cache bucket"
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env.cloud.test"))
    parser.add_argument("--no-env-file", action="store_const", const=None, dest="env_file")
    parser.add_argument("--bucket", default=None)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--part-size-mib", type=int, default=64)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--skip-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    args = parser.parse_args()

    env_file_info = load_env_file(args.env_file)
    bucket = args.bucket or os.getenv("RUNPOD_MODEL_BUCKET") or DEFAULT_BUCKET
    client = create_model_r2_client_from_env() if args.execute else _client_from_env_if_available()
    try:
        payload = prepare_scail2_model_r2_bundle(
            client=client,
            bucket=bucket,
            prefix=args.prefix,
            execute=args.execute,
            skip_existing=args.skip_existing,
            part_size_bytes=args.part_size_mib * 1024 * 1024,
        )
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "dry_run": not args.execute, "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2
    payload["env_file"] = env_file_info
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
