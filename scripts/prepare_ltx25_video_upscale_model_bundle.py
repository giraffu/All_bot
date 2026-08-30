#!/usr/bin/env python3
"""Prepare the gated, content-addressed LTX-2.5 upscale model bundle."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.gpu_pool_controller.model_repo import ModelRegistry  # noqa: E402

BUNDLE = "ltx25_video_upscale_runtime"
VERSION = "2026-08-31-int8-ic-v1"
MIN_FREE_BYTES = 50 * 1024**3
LTX25_REVISION = "e8dc69fd26150afbfa20351f6bc9ac384257f9fd"
IC_LORA_REVISION = "74c4e68ee7dd99f3997d5a1bb1a3784941822222"


def _spec(relative_path: str, sha256: str, size_bytes: int, *, ic: bool = False):
    repository = (
        "Lightricks/LTX-2.5-22b-IC-LoRA-Pixel-Spatial-Upscaler"
        if ic
        else "Lightricks/LTX-2.5"
    )
    revision = IC_LORA_REVISION if ic else LTX25_REVISION
    source_path = Path(relative_path).name if ic else relative_path
    return {
        "relative_path": relative_path,
        "sha256": sha256,
        "size_bytes": size_bytes,
        "url": f"https://huggingface.co/{repository}/resolve/{revision}/{source_path}",
    }


FILES = (
    _spec(
        "diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors",
        "c4279eeff115cbeaca494bd2183e7d768c38fe85a184dc6afbb7159157c44334",
        21_504_034_224,
    ),
    _spec(
        "text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors",
        "6ce688a0aa98a5fa36a9f1e6c3f42152a498cc2b53ee8c15674c64244f91487f",
        15_372_969_374,
    ),
    _spec(
        "vae/ltx-2.5-video-vae-bf16.safetensors",
        "847e14ca7f3355debca0cea4eaa24ac0fbcdf0061da054ac89ca638a869ddba3",
        1_472_223_346,
    ),
    _spec(
        "vae/ltx-2.5-audio-vae-bf16.safetensors",
        "c52733d37f6a7fb7949c3dc0fb468c6cb2169e4d836983a73babb9f0d54837a5",
        364_866_540,
    ),
    _spec(
        "loras/ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors",
        "984851b769ea2bcb4c9e0a239a7676239e42c6a6001ddc69943b41ff0b283c1d",
        327_322_640,
        ic=True,
    ),
)


def _download(url: str, target: Path, token: str) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "allbot-ltx25-model-bundle/1",
        },
    )
    with (
        urllib.request.urlopen(request, timeout=120) as response,
        target.open("wb") as output,
    ):
        while chunk := response.read(8 * 1024 * 1024):
            output.write(chunk)


def _ensure_file(registry: ModelRegistry, spec: dict, token: str) -> None:
    blob = registry.blob_path(spec["sha256"])
    if blob.exists() and blob.stat().st_size == spec["size_bytes"]:
        return
    temp_root = registry.root / "tmp" / f"{BUNDLE}-{VERSION}"
    temp_root.mkdir(parents=True, exist_ok=True)
    partial = temp_root / f"{spec['sha256']}.part"
    try:
        _download(spec["url"], partial, token)
        if partial.stat().st_size != spec["size_bytes"]:
            raise RuntimeError(f"size mismatch for {spec['relative_path']}")
        digest = hashlib.sha256()
        with partial.open("rb") as stream:
            for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != spec["sha256"]:
            raise RuntimeError(f"SHA256 mismatch for {spec['relative_path']}")
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.unlink(missing_ok=True)
        os.link(partial, blob)
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise RuntimeError(
                "HF_TOKEN has not accepted both gated LTX-2.5 repository licenses."
            ) from exc
        raise
    finally:
        partial.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry-root", default="/srv/allbot/model-registry")
    args = parser.parse_args()
    registry = ModelRegistry(Path(args.registry_root))
    registry.ensure_layout()
    free = shutil.disk_usage(registry.root).free
    if free < MIN_FREE_BYTES:
        raise SystemExit(
            f"refusing download: only {free / 1024**3:.1f} GiB free; 50 GiB required"
        )
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
    if not token:
        raise RuntimeError(
            "Accept both LTX-2.5 Hugging Face licenses and export a read-only HF_TOKEN."
        )
    for spec in FILES:
        _ensure_file(registry, spec, token)
    manifest_files = [
        {
            "relative_path": spec["relative_path"],
            "sha256": spec["sha256"],
            "size_bytes": spec["size_bytes"],
            "source_path": str(registry.blob_path(spec["sha256"])),
        }
        for spec in FILES
    ]
    manifest = registry.write_bundle_manifest(
        bundle=BUNDLE,
        version=VERSION,
        profiles=["ltx25_video_upscale"],
        source={
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "revisions": {
                "ltx25": LTX25_REVISION,
                "pixel_spatial_upscaler": IC_LORA_REVISION,
            },
            "license_acceptance_required": True,
        },
        files=manifest_files,
    )
    print(manifest)


if __name__ == "__main__":
    main()
