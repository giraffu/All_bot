#!/usr/bin/env python3
"""Build the deduplicated LTX unified model bundle."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.gpu_pool_controller.model_repo import ModelRegistry  # noqa: E402


BUNDLE = "ltx_unified_runtime"
VERSION = "2026-07-29"
SOURCE_BUNDLES = (
    ("ltx_video_baseline", "2026-06-10"),
    ("ltx_t2v_runtime", "2026-07-22"),
)
EXCLUDED_FULL_CHECKPOINTS = frozenset(
    {
        "diffusion_models/LTX 2.3/10Eros_v1.2_fp8mixed_learned.safetensors",
        "diffusion_models/LTX 2.3/ltx2310eros_v1.safetensors",
    }
)
EXTRACTED_LORA = {
    "relative_path": (
        "loras/ltx2.3/LTX_10Eros-v12_LoRA_fro99-avgrank91.safetensors"
    ),
    "sha256": "ac98553c007ea949603765d0e2a4ed97c6d5758bb2bb4d5e0c2cfdce0e4b3e76",
    "size_bytes": 3_162_331_448,
    "url": (
        "https://huggingface.co/maximsobolev275/LTX-10Eros-LoRA-r768/resolve/"
        "7170ebca094fcb73e8f621e88ee38fc0524c9fcf/"
        "LTX_10Eros-v12_LoRA_fro99-avgrank91.safetensors"
    ),
}
EXPECTED_FILE_COUNT = 48
EXPECTED_TOTAL_SIZE_BYTES = 99_621_123_430
MIN_FREE_BYTES = 8 * 1024**3


def _validated_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "relative_path": str(item["relative_path"]).lstrip("/"),
        "sha256": str(item["sha256"]),
        "size_bytes": int(item["size_bytes"]),
    }


def build_manifest_files(
    registry: ModelRegistry,
    *,
    extracted_lora: dict[str, Any] = EXTRACTED_LORA,
    require_blobs: bool = True,
) -> list[dict[str, Any]]:
    files_by_path: dict[str, dict[str, Any]] = {}
    for bundle, version in SOURCE_BUNDLES:
        manifest = registry.load_manifest(bundle, version)
        for raw_item in manifest.get("files") or []:
            item = _validated_item(raw_item)
            path = item["relative_path"]
            if path in EXCLUDED_FULL_CHECKPOINTS:
                continue
            existing = files_by_path.get(path)
            if existing and (
                existing["sha256"] != item["sha256"]
                or existing["size_bytes"] != item["size_bytes"]
            ):
                raise RuntimeError(f"conflicting LTX model path: {path}")
            files_by_path[path] = item

    extracted = _validated_item(extracted_lora)
    existing = files_by_path.get(extracted["relative_path"])
    if existing and existing != extracted:
        raise RuntimeError(
            f"conflicting LTX model path: {extracted['relative_path']}"
        )
    files_by_path[extracted["relative_path"]] = extracted

    result = []
    for path in sorted(files_by_path):
        item = files_by_path[path]
        blob = registry.blob_path(item["sha256"])
        if require_blobs and (
            not blob.is_file() or blob.stat().st_size != item["size_bytes"]
        ):
            raise RuntimeError(f"required LTX blob missing or invalid: {path}")
        result.append({**item, "source_path": str(blob)})
    return result


def _download_extracted_lora(registry: ModelRegistry) -> None:
    blob = registry.blob_path(EXTRACTED_LORA["sha256"])
    if blob.is_file() and blob.stat().st_size == EXTRACTED_LORA["size_bytes"]:
        return
    temp_root = registry.root / "tmp" / f"{BUNDLE}-{VERSION}"
    temp_root.mkdir(parents=True, exist_ok=True)
    partial = temp_root / f"{EXTRACTED_LORA['sha256']}.part"
    request = urllib.request.Request(
        EXTRACTED_LORA["url"],
        headers={"User-Agent": "allbot-model-bundle/1"},
    )
    try:
        digest = hashlib.sha256()
        size = 0
        with urllib.request.urlopen(request, timeout=120) as response, partial.open(
            "wb"
        ) as output:
            while chunk := response.read(8 * 1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        if size != EXTRACTED_LORA["size_bytes"]:
            raise RuntimeError("size mismatch for extracted 10Eros LoRA")
        if digest.hexdigest() != EXTRACTED_LORA["sha256"]:
            raise RuntimeError("SHA256 mismatch for extracted 10Eros LoRA")
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.unlink(missing_ok=True)
        try:
            os.link(partial, blob)
        except OSError:
            shutil.copy2(partial, blob)
    finally:
        partial.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry-root", default="/srv/allbot/model-registry")
    args = parser.parse_args()
    registry = ModelRegistry(Path(args.registry_root))
    registry.ensure_layout()
    free = shutil.disk_usage(registry.root).free
    if free < MIN_FREE_BYTES:
        raise SystemExit(
            f"refusing download: registry filesystem has {free / 1024**3:.1f} GiB free"
        )
    _download_extracted_lora(registry)
    files = build_manifest_files(registry)
    total_size = sum(item["size_bytes"] for item in files)
    if len(files) != EXPECTED_FILE_COUNT or total_size != EXPECTED_TOTAL_SIZE_BYTES:
        raise RuntimeError(
            "unexpected unified manifest shape: "
            f"{len(files)} files / {total_size} bytes"
        )
    path = registry.write_bundle_manifest(
        bundle=BUNDLE,
        version=VERSION,
        profiles=["ltx_unified"],
        source={
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_bundles": [
                {"bundle": bundle, "version": version}
                for bundle, version in SOURCE_BUNDLES
            ],
            "excluded_full_checkpoints": sorted(EXCLUDED_FULL_CHECKPOINTS),
            "extracted_lora_revision": (
                "7170ebca094fcb73e8f621e88ee38fc0524c9fcf"
            ),
        },
        files=files,
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

