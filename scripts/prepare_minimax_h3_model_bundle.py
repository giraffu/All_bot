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
VERSION = "2026-09-02-10eros-beta4-bf16-int8-addon4"
MIN_FREE_BYTES = 90 * 1024**3
OBSOLETE_FILES = (
    {
        "relative_path": "diffusion_models/MiniMaxH3/10Eros_Max_h3_TURBO-hybrid_beta3.safetensors",
        "sha256": "ea0df6670a84dfe594fe12c1202dfd82a497dbf2a75d6f06279a6b6993ab64b2",
        "size_bytes": 40_228_492_688,
    },
    {
        "relative_path": "diffusion_models/MiniMaxH3/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        "sha256": "e889202c41dafb67b10d67b97f0d8541508036a6090af23425a5c2615d03c47a",
        "size_bytes": 20_970_379_616,
    },
    {
        "relative_path": "diffusion_models/MiniMaxH3/minimax_h3_ref2va_pruned_int8_convrot.safetensors",
        "sha256": "9255f52b6677845ad238f20dfaafa94727053694127ab7f255c048f0f9365779",
        "size_bytes": 20_970_379_616,
    },
    {
        "relative_path": "loras/MiniMaxH3/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
        "sha256": "2339acdf19bfe123f46b971ea35d367a84adb85de43627e1eceafa5a5b2b111e",
        "size_bytes": 1_956_193_000,
    },
    {
        "relative_path": "loras/MiniMaxH3/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors",
        "sha256": "5b9ab5ade15d0775676d01a907268a69a1468dc6033b3b0d3ded5502f3ebb84c",
        "size_bytes": 1_956_193_000,
    },
    {
        "relative_path": "loras/MiniMaxH3/NaughtyTimes_pruned_r256_v2.safetensors",
        "sha256": "947efec5a357505bb93bdc1b050d33786ec150aa1c85f24337f0d59f39aaf31a",
        "size_bytes": 2_242_444_272,
    },
    {
        "relative_path": "loras/MiniMaxH3/HMNSFW-AIO-V2.5.safetensors",
        "sha256": "a07732a84fd733085eb5d910f602f918fa7a3658117116927e4329f5951a9d2d",
        "size_bytes": 86_040_232,
    },
    {
        "relative_path": "loras/MiniMaxH3/H3_Motion_BoosterV2.safetensors",
        "sha256": "f6a6897162b921d2b74abe1fdebcd80c8189147e70e0e0738200756c250336c3",
        "size_bytes": 155_110_272,
    },
    {
        "relative_path": "loras/MiniMaxH3/ref2VA_Motion_v2.safetensors",
        "sha256": "b48cf96ebb14985789528449fe61985babf786feb658740a82a88ac685167fd9",
        "size_bytes": 155_110_288,
    },
    {
        "relative_path": "loras/MiniMaxH3/VBVR_H3_attn_only.safetensors",
        "sha256": "372597997f646301dea204bf00e899b0f470254d7b9ac345e7b7417cc2140b34",
        "size_bytes": 32_826_752,
    },
    {
        "relative_path": "loras/MiniMaxH3/MysticXXX_MMH3-V4.safetensors",
        "sha256": "fc3e856d14c6c19557c888f48662d591e4794e281233ec0d987be5003068afba",
        "size_bytes": 155_095_800,
    },
    {
        "relative_path": "loras/MiniMaxH3/breastplayjiggle_h3_v1.safetensors",
        "sha256": "f9cbcaa596b6b281f154388e407e7b4c4ee97ba9917614ab36bc5e86edf374f5",
        "size_bytes": 298_260_984,
    },
    {
        "relative_path": "loras/MiniMaxH3/HMInnie_v1_e50.safetensors",
        "sha256": "499196c9d0e5f81ff575ba39a82987112c3bb1e09fbede858877cd950d6c8833",
        "size_bytes": 310_168_344,
    },
    {
        "relative_path": "loras/MiniMaxH3/HMBreasts_085e0750_e40.safetensors",
        "sha256": "039b6d5399def81c9a459d7cca8ccf749195fcb5f766f0899a387ba2fa6ad967",
        "size_bytes": 310_168_344,
    },
    {
        "relative_path": "loras/MiniMaxH3/vagassist_e40.safetensors",
        "sha256": "2c2fdb66bf558de1aabda504a81d4ada5f4cebc20e8f519dc6ed3bb6d4be8c9a",
        "size_bytes": 310_168_344,
    },
    {
        "relative_path": "loras/MiniMaxH3/hmpussy_v6_epoch30.safetensors",
        "sha256": "3080f4fbcbba4fc06bd09240c7eedb6a5128eb0e19feb001cdf97a7a0941a6ee",
        "size_bytes": 626_294_968,
    },
    {
        "relative_path": "loras/MiniMaxH3/PenisV2_minimax-h3_epoch60.safetensors",
        "sha256": "017dd1adddc1be3ec0605dd2e7de97138eb2c6c6ba24be402cf47f103ac1f1b3",
        "size_bytes": 77_580_008,
    },
    {
        "relative_path": "loras/MiniMaxH3/Vagina_minimax-h3_epoch20.safetensors",
        "sha256": "373c3cad3bf27047fdd754fe111443d97e70e3108a8829f2ec63c48832466eb3",
        "size_bytes": 77_580_008,
    },
    {
        "relative_path": "loras/MiniMaxH3/Titjob_Titfuck_V1-MiniMaxh3_ComfyTinker.safetensors",
        "sha256": "4a0679c613a5c52d8fd59c48455996402206eefa347939e5bbc736b530d196f5",
        "size_bytes": 155_110_304,
    },
)
FILES = (
    (
        "diffusion_models/MiniMaxH3/10Eros_Max_h3_TURBO-hybrid_beta4.safetensors",
        "bf34b4c9d2fa973ae84c480a1a5a04d2978958023bb6be7375b3b9e4818965e3",
        40_222_982_192,
        "https://huggingface.co/TenStrip/10Eros-Max/resolve/3c071106f5b62c02b3cb0b7d831083cdb582b289/10Eros_Max_h3_TURBO-hybrid_beta4.safetensors",
    ),
    (
        "diffusion_models/MiniMaxH3/10Eros_Max_h3_TURBO-hybrid_beta4_int8_convrot.safetensors",
        "54d56b15c65923b54c9ca16b494dae641bfe9455cfcb1c19c49b1008e270bbc1",
        20_967_637_320,
        "https://huggingface.co/TenStrip/10Eros-Max/resolve/3c071106f5b62c02b3cb0b7d831083cdb582b289/10Eros_Max_h3_TURBO-hybrid_beta4_int8_convrot.safetensors",
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
        "loras/MiniMaxH3/deepthroat_v02.safetensors",
        "1fd239662f6290255b0bb3a220764fb53aab2859378f7fd3024030c1e1991cb2",
        298_263_792,
        "https://civitai.com/api/download/models/3226989?fileId=3109184",
    ),
    (
        "loras/MiniMaxH3/H3_Mis_Insrt_v07.safetensors",
        "8d1ed16cdae02e25308063053f7f459b88fb4c50d7e6ea4d05ebc4950a992584",
        310_190_448,
        "https://civitai.com/api/download/models/3210503?fileId=3092209",
    ),
    (
        "loras/MiniMaxH3/H3_Footjob_TypeB_v1.safetensors",
        "6e293977389020e2e327d5e375cdc55352659f0ac61b41f270ec5ddf453fc620",
        298_260_800,
        "https://civitai.com/api/download/models/3217238?fileId=3099030",
    ),
    (
        "loras/MiniMaxH3/HMCumshot_V2.safetensors",
        "1a5b7948bb97f27737e62c3dd5497a3afb77517f230787f45e45c7d8fe3dc24d",
        626_294_968,
        "https://civitai.red/api/download/models/3238531?fileId=3121030",
    ),
)


class _AssetRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never forward an optional Civitai token to signed object-store URLs."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if (
            redirected is not None
            and urlsplit(req.full_url).netloc != urlsplit(newurl).netloc
        ):
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
        raise RuntimeError("CIVITAI_API_TOKEN is required for pinned Civitai assets")
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
        raise RuntimeError(
            "MiniMax H3 split bundle requires at least 90 GiB free space"
        )
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
                "civitai:modelVersion/3226989:file/3109184",
                "civitai:modelVersion/3210503:file/3092209",
                "civitai:modelVersion/3217238:file/3099030",
                "civitai:modelVersion/3238531:file/3121030",
            ],
            "revision": "10eros-beta4-bf16-int8=3c071106; comfy-support=014cd40f",
            "variant": (
                "10Eros-Max TURBO hybrid Beta4 BF16 and native INT8 ConvRot for "
                "all FL2VA/Ref2VA modes; four optional action LoRAs: Daring "
                "Deepthroat v0.2, H3 POV Missionary v0.7, H3 Footjobs Type B v1, "
                "and HMCumshot v0.5; official Qwen3-VL encoder and FP16 video/FP32 "
                "audio VAEs"
            ),
        },
        files=manifest_files,
        obsolete_files=list(OBSOLETE_FILES),
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
