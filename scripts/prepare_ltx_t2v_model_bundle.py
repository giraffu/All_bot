#!/usr/bin/env python3
"""Prepare the content-addressed LTX T2V bundle without logging HF credentials."""

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

BUNDLE = "ltx_t2v_runtime"
VERSION = "2026-07-22"
MIN_FREE_BYTES = 75 * 1024**3

FILES = (
    {
        "relative_path": "diffusion_models/LTX 2.3/ltx-2.3-22b-dev-fp8.safetensors",
        "sha256": "28606c5b5a06ce56f896d4dfcb20f212739e07a68fbe48e53638188449d26450",
        "size_bytes": 29145431166,
        "url": "https://huggingface.co/Lightricks/LTX-2.3-fp8/resolve/1d756cd27fa11c0896c4dfee093cd1bf36c7f7a1/ltx-2.3-22b-dev-fp8.safetensors",
        "gated": False,
    },
    {
        "relative_path": "loras/ltx2.3/sulphur_lora_rank_768.safetensors",
        "sha256": "b7151fc78066457a38153f3f1c899851c667527aa2108e39a7f4be3e3b5e4f2d",
        "size_bytes": 10268001040,
        "url": "https://huggingface.co/SulphurAI/Sulphur-2-base/resolve/875e886e556b955d21149316fd631cc121db6cc1/sulphur_lora_rank_768.safetensors",
        "gated": False,
    },
    {
        "relative_path": "loras/ltx2.3/ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors",
        "sha256": "515e4e139001ac6282357a5b35372e42e98b3affd5fcc886a52242abeed19559",
        "size_bytes": 1308778338,
        "url": "https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Ingredients/resolve/08896e49f7620d7d250c37a3a1e7b1edd7322bd4/ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors",
        "gated": True,
    },
)

REUSED = (
    (
        "loras/ltx2.3/ltx-2.3-22b-distilled-lora-384-1.1.safetensors",
        "f5d4953f3386197a4b4f5abdb17616ff256171e8075c111d6e7d2dfa6e823b3a",
        7605507256,
    ),
    (
        "clip/LTX 2.3/gemma_3_12B_it_fp8_e4m3fn.safetensors",
        "38c8ca98d01afc93a04f9fb18255755884b9eb52b7b40080076e9c892609751b",
        13210008986,
    ),
    (
        "clip/LTX 2.3/ltx-2.3_text_projection_bf16.safetensors",
        "911d59bb4cb7708179c9a0045ea0fe41212ecfb77aed3a02702b7c0a8274911f",
        2312149072,
    ),
    (
        "latent_upscale_models/LTX 2.3/ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
        "5f416311fa8172b65af67530758964708d29a317b830d689a51143b7f91913ed",
        995743560,
    ),
    (
        "vae/LTX 2.3/LTX23_video_vae_bf16.safetensors",
        "01ea62d09bc139f95c5dee7b5c062ad6a3e6cd8be910a1983ac02e7eb5b8ee3b",
        1452258578,
    ),
    (
        "vae/LTX23_audio_vae_bf16.safetensors",
        "5bc10fa4adecf99dda132d916e23048cbd56797702c5fa50eb5d2079048a38c3",
        364855188,
    ),
    (
        "vae/taeltx2_3.safetensors",
        "f0773b4e3e57318e6aa4dd4a35e1d16213a5f160fbc0376163f06888bbcbe246",
        23531296,
    ),
)


def _download(*, url: str, target: Path, token: str | None) -> None:
    request = urllib.request.Request(
        url, headers={"User-Agent": "allbot-model-bundle/1"}
    )
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with (
        urllib.request.urlopen(request, timeout=120) as response,
        target.open("wb") as output,
    ):
        while chunk := response.read(8 * 1024 * 1024):
            output.write(chunk)


def _ensure_download(registry: ModelRegistry, spec: dict, *, token: str | None) -> None:
    blob = registry.blob_path(spec["sha256"])
    if blob.exists() and blob.stat().st_size == spec["size_bytes"]:
        return
    if spec["gated"] and not token:
        raise RuntimeError(
            "Ingredients is gated: accept the Hugging Face license and export read-only HF_TOKEN before retrying."
        )
    temp_root = registry.root / "tmp" / f"{BUNDLE}-{VERSION}"
    temp_root.mkdir(parents=True, exist_ok=True)
    partial = temp_root / f"{spec['sha256']}.part"
    try:
        _download(
            url=spec["url"], target=partial, token=token if spec["gated"] else None
        )
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
        partial.unlink()
    except urllib.error.HTTPError as exc:
        if spec["gated"] and exc.code in {401, 403}:
            raise RuntimeError(
                "Hugging Face token lacks accepted Ingredients repository access."
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
            f"refusing download: registry filesystem has {free / 1024**3:.1f} GiB free; 75 GiB required"
        )
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
    gated_missing = any(
        spec["gated"] and not registry.blob_path(spec["sha256"]).exists()
        for spec in FILES
    )
    if gated_missing and not token:
        raise RuntimeError(
            "Ingredients is gated: accept the Hugging Face license and export read-only HF_TOKEN before retrying."
        )
    for spec in FILES:
        _ensure_download(registry, spec, token=token)
    manifest_files = []
    for relative_path, sha256, size_bytes in REUSED:
        blob = registry.blob_path(sha256)
        if not blob.exists() or blob.stat().st_size != size_bytes:
            raise RuntimeError(f"required shared blob missing: {relative_path}")
        manifest_files.append(
            {
                "relative_path": relative_path,
                "sha256": sha256,
                "size_bytes": size_bytes,
                "source_path": str(blob),
            }
        )
    for spec in FILES:
        blob = registry.blob_path(spec["sha256"])
        manifest_files.append(
            {
                "relative_path": spec["relative_path"],
                "sha256": spec["sha256"],
                "size_bytes": spec["size_bytes"],
                "source_path": str(blob),
            }
        )
    path = registry.write_bundle_manifest(
        bundle=BUNDLE,
        version=VERSION,
        profiles=["ltx_t2v"],
        source={
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "revisions": {
                "ltx_fp8": "1d756cd27fa11c0896c4dfee093cd1bf36c7f7a1",
                "sulphur": "875e886e556b955d21149316fd631cc121db6cc1",
                "ingredients": "08896e49f7620d7d250c37a3a1e7b1edd7322bd4",
            },
        },
        files=manifest_files,
    )
    print(path)


if __name__ == "__main__":
    main()
