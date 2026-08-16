#!/usr/bin/env python3
"""Download and register the pinned split-author MiniMax H3 model bundle."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.gpu_pool_controller.model_repo import ModelRegistry  # noqa: E402

BUNDLE = "minimax_h3_runtime"
VERSION = "2026-08-16-10eros-beta2-addon6-lightx2v8-v1"
MIN_FREE_BYTES = 55 * 1024**3
FILES = (
    (
        "diffusion_models/MiniMaxH3/10Eros_Max_h3_fl2va_beta2_pruned.safetensors",
        "57da2b2a12b9efc89eeaa6d751e1ef46ef3e406ca227684c31848abc749f1b20",
        40_222_933_592,
        "https://huggingface.co/TenStrip/10Eros-Max/resolve/47aa7e38dc2aca9a1e71a5b01b7ffefd462b57b5/10Eros_Max_h3_fl2va_beta2_pruned.safetensors",
    ),
    (
        "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6",
        15_687_142_551,
        "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/014cd40f7e177756c6b2473c0d93b1c89a790dd2/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    ),
    (
        "vae/MiniMaxH3/minimax_h3_audio_vae_fp32.safetensors",
        "8e505d95dd1561d47abd43d4238fd40d9bb1ae9e147ed0a4cba778d76ae4db48",
        605_254_808,
        "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/014cd40f7e177756c6b2473c0d93b1c89a790dd2/vae/minimax_h3_audio_vae_fp32.safetensors",
    ),
    (
        "vae/MiniMaxH3/minimax_h3_video_vae_fp16.safetensors",
        "7c1f131492e7eddacaac9069a61b81bdd39de5cc96561e677c5eab1cdce5e522",
        5_207_808_496,
        "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/014cd40f7e177756c6b2473c0d93b1c89a790dd2/vae/minimax_h3_video_vae_fp16.safetensors",
    ),
    (
        "loras/MiniMaxH3/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
        "2339acdf19bfe123f46b971ea35d367a84adb85de43627e1eceafa5a5b2b111e",
        1_956_193_000,
        "https://huggingface.co/lightx2v/Minimax-h3-Turbo/resolve/62487ee643501626a71502d679f735a23ee6af45/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
    ),
    (
        "loras/MiniMaxH3/NaughtyTimes_pruned_r256_v2.safetensors",
        "947efec5a357505bb93bdc1b050d33786ec150aa1c85f24337f0d59f39aaf31a",
        2_242_444_272,
        "https://civitai.red/api/download/models/3212436?fileId=3094173",
    ),
    (
        "loras/MiniMaxH3/HMNSFW_AIO_V2.safetensors",
        "608e4212f2788b6063330ff1196fc1f4b4228cfd9a413a63c198a09d7e4a61cb",
        310_168_344,
        "https://civitai.red/api/download/models/3206518",
    ),
    (
        "loras/MiniMaxH3/HMBreasts_085e0750_e40.safetensors",
        "039b6d5399def81c9a459d7cca8ccf749195fcb5f766f0899a387ba2fa6ad967",
        310_168_344,
        "https://civitai.red/api/download/models/3216751",
    ),
    (
        "loras/MiniMaxH3/vagassist_e40.safetensors",
        "2c2fdb66bf558de1aabda504a81d4ada5f4cebc20e8f519dc6ed3bb6d4be8c9a",
        310_168_344,
        "https://civitai.red/api/download/models/3215304",
    ),
    (
        "loras/MiniMaxH3/hmpussy_v6_epoch30.safetensors",
        "3080f4fbcbba4fc06bd09240c7eedb6a5128eb0e19feb001cdf97a7a0941a6ee",
        626_294_968,
        "https://civitai.red/api/download/models/3215304?fileId=3097100",
    ),
    (
        "loras/MiniMaxH3/HMPenis_v2_e35.safetensors",
        "c6c58e9fee848b45e99f97d2520aba4ac63dfc354c07e13c29ac5d8a31a68060",
        310_168_344,
        "https://civitai.red/api/download/models/3218160",
    ),
)


class _AssetRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never forward an optional Civitai token to signed object-store URLs."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and urlsplit(req.full_url).netloc != urlsplit(newurl).netloc:
            redirected.remove_header("Authorization")
        return redirected


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _request(url: str, *, offset: int) -> urllib.request.Request:
    headers = {"User-Agent": "allbot-minimax-h3-bundle/3"}
    token = os.getenv("CIVITAI_API_TOKEN", "").strip()
    if urlsplit(url).netloc in {"civitai.com", "civitai.red"} and not token:
        raise RuntimeError("CIVITAI_API_TOKEN is required for the pinned NaughtyTimes asset")
    if token and urlsplit(url).netloc in {"civitai.com", "civitai.red"}:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    if offset:
        request.add_header("Range", f"bytes={offset}-")
    return request


def _download(url: str, partial: Path) -> None:
    offset = partial.stat().st_size if partial.exists() else 0
    opener = urllib.request.build_opener(_AssetRedirectHandler())
    with opener.open(_request(url, offset=offset), timeout=180) as response:
        append = offset > 0 and response.status == 206
        with partial.open("ab" if append else "wb") as output:
            while chunk := response.read(8 * 1024 * 1024):
                output.write(chunk)


def prepare(registry: ModelRegistry) -> Path:
    registry.ensure_layout()
    if shutil.disk_usage(registry.root).free < MIN_FREE_BYTES:
        raise RuntimeError("MiniMax H3 split bundle requires at least 55 GiB free space")
    temp_root = registry.root / "tmp" / f"{BUNDLE}-{VERSION}"
    temp_root.mkdir(parents=True, exist_ok=True)
    manifest_files = []
    for relative_path, sha256, size_bytes, url in FILES:
        blob = registry.blob_path(sha256)
        if not (
            blob.exists()
            and blob.stat().st_size == size_bytes
            and _hash(blob) == sha256
        ):
            partial = temp_root / f"{sha256}.part"
            if not (partial.exists() and partial.stat().st_size == size_bytes):
                _download(url, partial)
            if partial.stat().st_size != size_bytes:
                raise RuntimeError(f"size mismatch for {relative_path}")
            if _hash(partial) != sha256:
                raise RuntimeError(f"SHA256 mismatch for {relative_path}")
            blob.parent.mkdir(parents=True, exist_ok=True)
            os.replace(partial, blob)
        manifest_files.append(
            {
                "relative_path": relative_path,
                "sha256": sha256,
                "size_bytes": size_bytes,
                "source_path": str(blob),
            }
        )
    return registry.write_bundle_manifest(
        bundle=BUNDLE,
        version=VERSION,
        profiles=["minimax_h3"],
        source={
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "repositories": [
                "TenStrip/10Eros-Max",
                "Comfy-Org/MiniMax-H3",
                "lightx2v/Minimax-h3-Turbo",
                "civitai:modelVersion/3212436:file/3094173",
                "civitai:modelVersion/3206518",
                "civitai:modelVersion/3216751",
                "civitai:modelVersion/3215304",
                "civitai:modelVersion/3218160",
            ],
            "revision": "10eros=47aa7e38; comfy=014cd40f; lightx2v=62487ee6",
            "variant": (
                "10Eros-Max Beta2 pruned base plus fixed LightX2V FL2VA 8-step "
                "v1.0 acceleration and six optional one-file LoRAs: NaughtyTimes "
                "v2, HMNSFW AIO v2, HMBreasts, VagAssist, HMPussy v6 and HMPenis "
                "v2; official Qwen3-VL encoder and FP16 video/FP32 audio VAEs"
            ),
        },
        files=manifest_files,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--registry-root",
        type=Path,
        default=Path("/srv/allbot/model-registry"),
    )
    args = parser.parse_args()
    print(prepare(ModelRegistry(args.registry_root)))


if __name__ == "__main__":
    main()
