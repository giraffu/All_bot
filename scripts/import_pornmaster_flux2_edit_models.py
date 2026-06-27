#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.gpu_pool_controller.model_repo import ModelRegistry  # noqa: E402


BUNDLE = "pornmaster_flux2_edit_baseline"
VERSION = "2026-06-27"
PROFILE = "pornmaster_flux2_edit"
DOWNLOAD_ROOT = Path("/srv/allbot/model-downloads/pornmaster_flux2_image_edit/2026-06-27")
I2I_BUNDLE = "i2i_pro_baseline"
I2I_VERSION = "2026-06-14-test"

UNET_RELATIVE_PATH = (
    "diffusion_models/flux2/PornMaster_flux2_klein_9b_turbo_fp8_V4.safetensors"
)
QWEN_RELATIVE_PATH = "text_encoders/flux2/qwen_3_8b_fp8mixed.safetensors"
VAE_RELATIVE_PATH = "vae/flux2/full_encoder_small_decoder.safetensors"

UNET_SOURCE_NAME = "pornmasterFlux2Klein_v4TurboFp8.safetensors"
UNET_DOWNLOAD_URL = "https://civitai.com/api/download/models/2973304"
UNET_EXPECTED_SHA256 = (
    "e90eeb50140a10806341b7521c340214c6f76cec2f8f8dae7a443c5806072df7"
)
UNET_EXPECTED_MD5 = "c5dfa390478c827190be68d22f9f4974"

QWEN_EXISTING_RELATIVE_PATH = "text_encoders/qwen_3_8b_fp8mixed.safetensors"
QWEN_EXPECTED_SHA256 = (
    "abad16806e0cbabc54e0325d6565847443fe396d5f0be38bb3cd3fe75a1201d6"
)

VAE_DOWNLOAD_URL = (
    "https://huggingface.co/black-forest-labs/FLUX.2-small-decoder/resolve/main/"
    "full_encoder_small_decoder.safetensors"
)
VAE_EXPECTED_SHA256 = (
    "ea4273f02d1fafbf8e1d1c2cf6018ed8748652eb0bf34f2dd91171f16f15ab62"
)


def _download_file(url: str, destination: Path, *, token: str | None = None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if token:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urlencode({'token': token})}"
    request = urllib.request.Request(url, headers={"User-Agent": "AllBotModelPrep/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        tmp = destination.with_suffix(destination.suffix + ".tmp")
        with tmp.open("wb") as output:
            while True:
                chunk = response.read(8 * 1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
        tmp.replace(destination)


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


def _sha256(path: Path) -> str:
    return ModelRegistry.sha256_file(path)


def _require_sha(path: Path, expected_sha256: str) -> None:
    actual = _sha256(path)
    if actual.lower() != expected_sha256.lower():
        raise RuntimeError(f"sha256 mismatch for {path}: {actual} != {expected_sha256}")


def _existing_qwen_blob(registry: ModelRegistry) -> Path:
    manifest = registry.load_manifest(I2I_BUNDLE, I2I_VERSION)
    for item in manifest.get("files", []):
        if item.get("relative_path") == QWEN_EXISTING_RELATIVE_PATH:
            if str(item.get("sha256", "")).lower() != QWEN_EXPECTED_SHA256:
                raise RuntimeError("existing qwen_3_8b_fp8mixed sha256 does not match expected")
            path = registry.blob_path(str(item["sha256"]))
            if not path.exists():
                raise RuntimeError(f"existing qwen blob missing: {path}")
            return path
    raise RuntimeError(f"{QWEN_EXISTING_RELATIVE_PATH} not found in {I2I_BUNDLE}/{I2I_VERSION}")


def _resolve_or_download(
    *,
    path: Path,
    download_url: str | None,
    expected_sha256: str,
    execute: bool,
    token: str | None = None,
) -> Path:
    if not path.exists() and download_url:
        if not execute:
            return path
        _download_file(download_url, path, token=token)
    if not path.exists():
        raise FileNotFoundError(path)
    _require_sha(path, expected_sha256)
    return path


def _import_file(
    registry: ModelRegistry,
    *,
    source_path: Path,
    relative_path: str,
) -> dict:
    return registry.import_file(
        bundle=BUNDLE,
        version=VERSION,
        source_path=source_path,
        relative_path=relative_path,
        source_node="local-model-downloads",
        profiles=[PROFILE],
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import PornMaster Flux2 edit models into the local AllBot model registry."
    )
    parser.add_argument("--repo-root", type=Path, default=ModelRegistry().root)
    parser.add_argument("--env-file", type=Path, default=Path(".env.local"))
    parser.add_argument(
        "--unet-path",
        type=Path,
        default=DOWNLOAD_ROOT / "diffusion_models" / "flux2" / UNET_SOURCE_NAME,
    )
    parser.add_argument(
        "--vae-path",
        type=Path,
        default=DOWNLOAD_ROOT / "vae" / "full_encoder_small_decoder.safetensors",
    )
    parser.add_argument(
        "--civitai-token",
        default="",
    )
    parser.add_argument("--download-unet", action="store_true")
    parser.add_argument("--download-vae", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    _load_env_file(args.env_file)
    civitai_token = (
        args.civitai_token
        or os.getenv("CIVITAI_API_TOKEN")
        or os.getenv("CIVITAI_TOKEN")
        or ""
    )

    registry = ModelRegistry(args.repo_root)
    qwen_path = _existing_qwen_blob(registry)
    vae_path = _resolve_or_download(
        path=args.vae_path,
        download_url=VAE_DOWNLOAD_URL if args.download_vae else None,
        expected_sha256=VAE_EXPECTED_SHA256,
        execute=args.execute,
    )
    try:
        unet_path = _resolve_or_download(
            path=args.unet_path,
            download_url=UNET_DOWNLOAD_URL if args.download_unet else None,
            expected_sha256=UNET_EXPECTED_SHA256,
            execute=args.execute,
            token=civitai_token or None,
        )
    except Exception as exc:
        payload = {
            "ok": False,
            "blocked": "pornmaster_unet_missing_or_unauthorized",
            "error": str(exc),
            "required_unet": {
                "relative_path": UNET_RELATIVE_PATH,
                "civitai_model_version_id": 2973304,
                "download_url": UNET_DOWNLOAD_URL,
                "sha256": UNET_EXPECTED_SHA256,
                "md5": UNET_EXPECTED_MD5,
            },
            "ready_inputs": {
                "qwen": str(qwen_path),
                "vae": str(vae_path),
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    if not args.execute:
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "bundle": BUNDLE,
                    "version": VERSION,
                    "files": [UNET_RELATIVE_PATH, QWEN_RELATIVE_PATH, VAE_RELATIVE_PATH],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    for source_path, relative_path in (
        (unet_path, UNET_RELATIVE_PATH),
        (qwen_path, QWEN_RELATIVE_PATH),
        (vae_path, VAE_RELATIVE_PATH),
    ):
        _import_file(registry, source_path=source_path, relative_path=relative_path)

    manifest = registry.load_manifest(BUNDLE, VERSION)
    manifest["source"] = {
        "imported_from": "local-model-downloads",
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "model_sources": {
            "pornmaster_unet": {
                "civitai_model_version_id": 2973304,
                "source_file": UNET_SOURCE_NAME,
                "workflow_filename": "PornMaster_flux2_klein_9b_turbo_fp8_V4.safetensors",
                "md5": UNET_EXPECTED_MD5,
            },
            "qwen_text_encoder": {"source_bundle": f"{I2I_BUNDLE}/{I2I_VERSION}"},
            "vae": {"url": VAE_DOWNLOAD_URL},
        },
    }
    registry.write_manifest(BUNDLE, VERSION, manifest)
    print(json.dumps({"ok": True, "bundle": BUNDLE, "version": VERSION}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
