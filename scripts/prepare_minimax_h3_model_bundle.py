#!/usr/bin/env python3
"""Download and register the pinned fixed RedMix MiniMax H3 model bundle."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import urllib.request
from urllib.parse import urlsplit
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.gpu_pool_controller.model_repo import ModelRegistry  # noqa: E402

BUNDLE = "minimax_h3_runtime"
VERSION = "2026-08-14-redmix-a2a-beta1-int8"
REVISION = "014cd40f7e177756c6b2473c0d93b1c89a790dd2"
MIN_FREE_BYTES = 48 * 1024**3
FILES = (
    ("diffusion_models/MiniMaxH3/REDMix-MiniMaxH3-A2A-pruned-int8-convrot-ComfyMCP.safetensors", "fc99ff051283ee05f29b1ebcb14e0d7b36c03e93512ac5479411cdfa2e284122", 20_970_384_488, "https://civitai.red/api/download/models/3226037?fileId=3108292"),
    ("text_encoders/qwen3vl_32b_heretic_minimax_h3_nvfp4.safetensors", "a166c7bbbe66a22065159e478335fee4a633c4a3e3bb34c8e8ac4cc91bf4996f", 15_683_129_587, "https://civitai.red/api/download/models/3226037?fileId=3108375"),
    ("vae/MiniMaxH3/minimax_h3_audio_vae_fp32.safetensors", "8e505d95dd1561d47abd43d4238fd40d9bb1ae9e147ed0a4cba778d76ae4db48", 605_254_808, "vae/minimax_h3_audio_vae_fp32.safetensors"),
    ("vae/MiniMaxH3/minimax_h3_video_vae_int8_convrot.safetensors", "9bb2d96f218c76babd85e0611b85ca8fb330a90546c01a0005e8a58a59593410", 3_171_670_912, "https://civitai.red/api/download/models/3226037?fileId=3108212"),
)


class _RedMixRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Keep the Civitai token on its API host and off signed object-store URLs."""

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


def _download(url: str, partial: Path) -> None:
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": "allbot-minimax-h3-bundle/2"}
    if url.startswith("https://civitai.red/"):
        token = os.getenv("CIVITAI_API_TOKEN", "").strip()
        if not token:
            raise RuntimeError("CIVITAI_API_TOKEN is required for the RedMix bundle")
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    if offset:
        request.add_header("Range", f"bytes={offset}-")
    opener = urllib.request.build_opener(_RedMixRedirectHandler())
    with opener.open(request, timeout=180) as response:
        append = offset > 0 and response.status == 206
        with partial.open("ab" if append else "wb") as output:
            while chunk := response.read(8 * 1024 * 1024):
                output.write(chunk)


def prepare(registry: ModelRegistry) -> Path:
    registry.ensure_layout()
    if shutil.disk_usage(registry.root).free < MIN_FREE_BYTES:
        raise RuntimeError("MiniMax H3 RedMix bundle requires at least 48 GiB free space")
    temp_root = registry.root / "tmp" / f"{BUNDLE}-{VERSION}"
    temp_root.mkdir(parents=True, exist_ok=True)
    manifest_files = []
    for relative_path, sha256, size_bytes, upstream_path in FILES:
        blob = registry.blob_path(sha256)
        if not (blob.exists() and blob.stat().st_size == size_bytes and _hash(blob) == sha256):
            partial = temp_root / f"{sha256}.part"
            url = upstream_path if upstream_path.startswith("https://") else (
                f"https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/{REVISION}/{upstream_path}"
            )
            if not (partial.exists() and partial.stat().st_size == size_bytes):
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
            "repositories": ["Comfy-Org/MiniMax-H3", "civitai:modelVersion/3226037"],
            "revision": REVISION,
            "variant": "RedMix A2A Beta1 INT8 convrot fixed stack with baked 10Eros-Max, LightX2V MiniMax H3 Turbo 8-step and SexGod NaughtyTimes; Heretic Qwen3-VL NVFP4 encoder and INT8 video VAE",
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
