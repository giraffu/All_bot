from __future__ import annotations

import json

from botocore.exceptions import ClientError

from ops.gpu_pool_controller.providers.runpod import (
    RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY,
    RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY,
)
from ops.gpu_pool_controller.runpod_video_manifests import (
    prepare_split_video_manifests,
    split_wan22_aio_manifest,
)
from src.lora_catalog import VIDEO_LORA_MODELS


class _Body:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _FakeR2Client:
    def __init__(self, source: dict, missing: set[str] | None = None) -> None:
        self.source = source
        self.missing = missing or set()
        self.heads: list[str] = []
        self.puts: list[dict] = []

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        assert Bucket == "allbot-model-cache"
        return {"Body": _Body(self.source)}

    def head_object(self, *, Bucket: str, Key: str) -> dict:
        assert Bucket == "allbot-model-cache"
        self.heads.append(Key)
        if Key in self.missing:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"ContentLength": 1}

    def put_object(self, **kwargs) -> None:
        self.puts.append(kwargs)


def _source_manifest() -> dict:
    def item(relative_path: str, size: int) -> dict:
        return {
            "relative_path": relative_path,
            "sha256": "a" * 64,
            "size_bytes": size,
            "key": f"wan22_aio_video/2026-06-12-test/models/{relative_path}",
        }

    return {
        "bundle": "wan22_aio_video",
        "version": "2026-06-12-test",
        "files": [
            item("clip/umt5_xxl_fp8_e4m3fn_scaled.safetensors", 10),
            item("text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", 10),
            item("vae/wan_2.1_vae.safetensors", 10),
            item(
                "diffusion_models/wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8H.safetensors",
                20,
            ),
            item(
                "diffusion_models/wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8L.safetensors",
                20,
            ),
            item(
                "diffusion_models/DasiwaWAN22I2V14BLightspeed_snatchkissHighV11.safetensors",
                30,
            ),
            item(
                "diffusion_models/DasiwaWAN22I2V14BLightspeed_snatchkissLowV11.safetensors",
                30,
            ),
            *[
                item(f"loras/{name}_{noise}_noise.safetensors", 5)
                for name in VIDEO_LORA_MODELS
                if name
                for noise in ("high", "low")
            ],
        ],
    }


def test_split_wan22_aio_manifest_selects_profile_specific_files_and_reuses_keys():
    split = split_wan22_aio_manifest(_source_manifest())
    image_paths = {entry["relative_path"] for entry in split["image_to_video"]["files"]}
    wan22_paths = {entry["relative_path"] for entry in split["wan22_video_v2"]["files"]}

    assert (
        "diffusion_models/wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8H.safetensors"
        in image_paths
    )
    assert "loras/Insertion_high_noise.safetensors" in image_paths
    assert (
        "diffusion_models/DasiwaWAN22I2V14BLightspeed_snatchkissHighV11.safetensors"
        not in image_paths
    )
    assert (
        "diffusion_models/DasiwaWAN22I2V14BLightspeed_snatchkissHighV11.safetensors"
        in wan22_paths
    )
    assert "loras/Insertion_high_noise.safetensors" in wan22_paths
    assert {
        f"loras/{name}_{noise}_noise.safetensors"
        for name in VIDEO_LORA_MODELS
        if name
        for noise in ("high", "low")
    }.issubset(wan22_paths)
    assert split["wan22_video_v2"]["version"] == "2026-07-18-lora5"
    assert "vae/wan_2.1_vae.safetensors" in image_paths
    assert "vae/wan_2.1_vae.safetensors" in wan22_paths
    assert split["image_to_video"]["files"][0]["key"].startswith("wan22_aio_video/")


def test_prepare_split_video_manifests_heads_all_reused_keys_and_uploads_manifest_only():
    client = _FakeR2Client(_source_manifest())

    payload = prepare_split_video_manifests(
        client=client,
        bucket="allbot-model-cache",
        execute=True,
    )

    assert payload["ok"] is True
    assert payload["dry_run"] is False
    assert payload["missing_count"] == 0
    assert {put["Key"] for put in client.puts} == {
        RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY,
        RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY,
    }
    assert all(not put["Key"].endswith(".safetensors") for put in client.puts)
    assert any("FASTMOVE" in key for key in client.heads)
    assert any("DasiwaWAN22I2V14B" in key for key in client.heads)


def test_prepare_split_video_manifests_reports_missing_reused_object_before_upload():
    missing_key = (
        "wan22_aio_video/2026-06-12-test/models/"
        "diffusion_models/DasiwaWAN22I2V14BLightspeed_snatchkissHighV11.safetensors"
    )
    client = _FakeR2Client(_source_manifest(), missing={missing_key})

    payload = prepare_split_video_manifests(
        client=client,
        bucket="allbot-model-cache",
        execute=True,
    )

    assert payload["ok"] is False
    assert payload["missing_count"] == 1
    assert payload["missing"][0]["key"] == missing_key
    assert client.puts == []


def test_prepare_split_video_manifests_fails_closed_when_lora_object_is_missing():
    missing_key = (
        "wan22_aio_video/2026-06-12-test/models/"
        "loras/Insertion_high_noise.safetensors"
    )
    client = _FakeR2Client(_source_manifest(), missing={missing_key})

    payload = prepare_split_video_manifests(
        client=client,
        bucket="allbot-model-cache",
        execute=True,
    )

    assert payload["ok"] is False
    assert {item["profile"] for item in payload["missing"]} == {
        "image_to_video",
        "wan22_video_v2",
    }
    assert client.puts == []
