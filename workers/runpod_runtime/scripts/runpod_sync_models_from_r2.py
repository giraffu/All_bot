#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from minio import Minio


def _bool_env(value: str | None, *, default: bool) -> bool:
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
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format_mib(byte_count: int) -> str:
    return f"{byte_count / 1024 / 1024:.1f} MiB"


def _normalise_endpoint(raw_endpoint: str, secure: bool) -> tuple[str, bool]:
    endpoint = raw_endpoint.strip()
    if "://" not in endpoint:
        return endpoint, secure
    parsed = urlparse(endpoint)
    if not parsed.netloc:
        raise ValueError("invalid R2 endpoint")
    return parsed.netloc, parsed.scheme == "https"


def _client_from_env() -> Minio:
    raw_endpoint = os.getenv("RUNPOD_MODEL_ENDPOINT") or os.getenv("MINIO_ENDPOINT") or ""
    access_key = os.getenv("RUNPOD_MODEL_ACCESS_KEY") or os.getenv("MINIO_ACCESS_KEY") or ""
    secret_key = os.getenv("RUNPOD_MODEL_SECRET_KEY") or os.getenv("MINIO_SECRET_KEY") or ""
    secure = _bool_env(
        os.getenv("RUNPOD_MODEL_SECURE") or os.getenv("MINIO_SECURE"),
        default=True,
    )
    if not raw_endpoint:
        raise RuntimeError("RUNPOD_MODEL_ENDPOINT/MINIO_ENDPOINT is required")
    if not access_key or not secret_key:
        raise RuntimeError("RUNPOD_MODEL_ACCESS_KEY/RUNPOD_MODEL_SECRET_KEY is required")
    endpoint, secure = _normalise_endpoint(raw_endpoint, secure)
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)


def _manifest_key(prefix: str) -> str:
    explicit = os.getenv("RUNPOD_MODEL_MANIFEST_KEY", "").strip().strip("/")
    if explicit:
        return explicit
    return f"{prefix.strip('/')}/manifest.json"


def _object_key(file_info: dict[str, object], prefix: str) -> str:
    explicit = str(file_info.get("key") or file_info.get("object_key") or "").strip()
    if explicit:
        return explicit.strip("/")
    relative_path = str(file_info["relative_path"]).strip().lstrip("/")
    return f"{prefix.strip('/')}/models/{relative_path}"


def _target_valid(path: Path, *, expected_size: int, expected_sha256: str, verify: bool) -> bool:
    if not path.exists() or not path.is_file():
        return False
    if path.stat().st_size != expected_size:
        return False
    if verify and _sha256_file(path) != expected_sha256:
        return False
    return True


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


def sync_models(*, bucket: str, prefix: str, target_dir: Path, verify_existing: bool) -> dict[str, object]:
    client = _client_from_env()
    manifest_object = _manifest_key(prefix)
    response = client.get_object(bucket, manifest_object)
    try:
        manifest = json.loads(response.read().decode("utf-8"))
    finally:
        response.close()
        response.release_conn()

    files = manifest.get("files") or []
    if not isinstance(files, list):
        raise RuntimeError("model manifest files must be a list")

    downloaded: list[str] = []
    skipped: list[str] = []
    target_dir.mkdir(parents=True, exist_ok=True)
    local_overrides = {
        str(item["relative_path"]): item
        for item in json.loads(os.getenv("RUNPOD_LAN_LOCAL_MODEL_OVERRIDES", "[]"))
    }
    for raw_file in files:
        if not isinstance(raw_file, dict):
            raise RuntimeError("model manifest file entries must be objects")
        relative_path = str(raw_file["relative_path"]).strip().lstrip("/")
        expected_size = int(raw_file["size_bytes"])
        expected_sha256 = str(raw_file["sha256"])
        key = _object_key(raw_file, prefix)
        target = target_dir / relative_path
        override = local_overrides.get(relative_path)
        if override is not None:
            if not _target_valid(target, expected_size=int(override["size_bytes"]), expected_sha256=str(override["sha256"]), verify=True):
                raise RuntimeError(f"LAN local model override is missing or invalid: {relative_path}")
            skipped.append(relative_path)
            continue
        if _target_valid(
            target,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            verify=verify_existing,
        ):
            skipped.append(relative_path)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        temp_target = target.with_name(f"{target.name}.partial")
        _download_object_with_resume(
            client,
            bucket=bucket,
            key=key,
            temp_target=temp_target,
            expected_size=expected_size,
            relative_path=relative_path,
        )
        actual_size = temp_target.stat().st_size
        if actual_size != expected_size:
            temp_target.unlink(missing_ok=True)
            raise RuntimeError(
                f"size mismatch for {relative_path}: expected {expected_size}, got {actual_size}"
            )
        actual_sha256 = _sha256_file(temp_target)
        if actual_sha256 != expected_sha256:
            temp_target.unlink(missing_ok=True)
            raise RuntimeError(f"sha256 mismatch for {relative_path}")
        temp_target.replace(target)
        downloaded.append(relative_path)

    return {
        "ok": True,
        "bucket": bucket,
        "prefix": prefix,
        "manifest_key": manifest_object,
        "target_dir": str(target_dir),
        "file_count": len(files),
        "downloaded_count": len(downloaded),
        "skipped_existing_count": len(skipped),
        "downloaded": downloaded,
        "skipped_existing": skipped,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync AllBot RunPod model bundle from R2")
    parser.add_argument("--bucket", default=os.getenv("RUNPOD_MODEL_BUCKET", ""))
    parser.add_argument("--prefix", default=os.getenv("RUNPOD_MODEL_PREFIX", "img2img_lora/2026-06-10"))
    parser.add_argument("--target-dir", type=Path, default=Path(os.getenv("RUNPOD_MODEL_TARGET_DIR", "")))
    parser.add_argument(
        "--skip-existing-sha256",
        action="store_true",
        help="trust size-only checks for already present files",
    )
    args = parser.parse_args()
    if not args.bucket:
        print("RUNPOD_MODEL_BUCKET is required", file=sys.stderr)
        return 2
    if not str(args.target_dir):
        print("RUNPOD_MODEL_TARGET_DIR/--target-dir is required", file=sys.stderr)
        return 2
    payload = sync_models(
        bucket=args.bucket,
        prefix=args.prefix,
        target_dir=args.target_dir,
        verify_existing=not args.skip_existing_sha256,
    )
    print("[runpod-model-sync] " + json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
