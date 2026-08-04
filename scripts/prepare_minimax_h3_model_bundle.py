#!/usr/bin/env python3
"""Download and register the pinned official Comfy-Org MiniMax H3 model bundle."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.gpu_pool_controller.model_repo import ModelRegistry  # noqa: E402

BUNDLE = "minimax_h3_runtime"
VERSION = "2026-08-04-dasiwa-cmmh3-v1"
REVISION = "0543966fbdce5ba05709a8f2031c94bdba629b4a"
MIN_FREE_BYTES = 80 * 1024**3
FILES = (
    ("diffusion_models/MiniMaxH3/minimax_h3_fl2va_pruned_int8_convrot.safetensors", "e889202c41dafb67b10d67b97f0d8541508036a6090af23425a5c2615d03c47a", 20_970_379_616, "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors"),
    ("diffusion_models/MiniMaxH3/minimax_h3_ref2va_pruned_int8_convrot.safetensors", "9255f52b6677845ad238f20dfaafa94727053694127ab7f255c048f0f9365779", 20_970_379_616, "diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors"),
    ("text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6", 15_687_142_551, "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"),
    ("vae/MiniMaxH3/minimax_h3_audio_vae_fp32.safetensors", "8e505d95dd1561d47abd43d4238fd40d9bb1ae9e147ed0a4cba778d76ae4db48", 605_254_808, "vae/minimax_h3_audio_vae_fp32.safetensors"),
    ("vae/MiniMaxH3/minimax_h3_video_vae_fp16.safetensors", "7c1f131492e7eddacaac9069a61b81bdd39de5cc96561e677c5eab1cdce5e522", 5_207_808_496, "vae/minimax_h3_video_vae_fp16.safetensors"),
)


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, partial: Path) -> None:
    offset = partial.stat().st_size if partial.exists() else 0
    request = urllib.request.Request(url, headers={"User-Agent": "allbot-minimax-h3-bundle/1"})
    if offset:
        request.add_header("Range", f"bytes={offset}-")
    with urllib.request.urlopen(request, timeout=180) as response:
        append = offset > 0 and response.status == 206
        with partial.open("ab" if append else "wb") as output:
            while chunk := response.read(8 * 1024 * 1024):
                output.write(chunk)


def prepare(registry: ModelRegistry) -> Path:
    registry.ensure_layout()
    if shutil.disk_usage(registry.root).free < MIN_FREE_BYTES:
        raise RuntimeError("MiniMax H3 bundle requires at least 80 GiB free space")
    temp_root = registry.root / "tmp" / f"{BUNDLE}-{VERSION}"
    temp_root.mkdir(parents=True, exist_ok=True)
    manifest_files = []
    for relative_path, sha256, size_bytes, upstream_path in FILES:
        blob = registry.blob_path(sha256)
        if not (blob.exists() and blob.stat().st_size == size_bytes and _hash(blob) == sha256):
            partial = temp_root / f"{sha256}.part"
            url = f"https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/{REVISION}/{upstream_path}"
            _download(url, partial)
            if partial.stat().st_size != size_bytes:
                raise RuntimeError(f"size mismatch for {relative_path}")
            if _hash(partial) != sha256:
                raise RuntimeError(f"SHA256 mismatch for {relative_path}")
            blob.parent.mkdir(parents=True, exist_ok=True)
            os.replace(partial, blob)
        manifest_files.append({"relative_path": relative_path, "sha256": sha256, "size_bytes": size_bytes, "source_path": str(blob)})
    return registry.write_bundle_manifest(
        bundle=BUNDLE,
        version=VERSION,
        profiles=["minimax_h3"],
        source={
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "repository": "Comfy-Org/MiniMax-H3",
            "revision": REVISION,
            "variant": "official Comfy-Org quantized conversions; no LoRA or finetune",
        },
        files=manifest_files,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry-root", type=Path, default=Path("/srv/allbot/model-registry"))
    args = parser.parse_args()
    print(prepare(ModelRegistry(args.registry_root)))


if __name__ == "__main__":
    main()
