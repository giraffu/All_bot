from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

from botocore.exceptions import ClientError

from ops.gpu_pool_controller.model_repo import ModelRegistry


MODULE_PATH = Path("scripts/upload_all_task_models_to_lan_cache.py")


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "upload_all_task_models_to_lan_cache", MODULE_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeLanClient:
    def __init__(self, existing: dict[str, dict] | None = None) -> None:
        self.existing = existing or {}
        self.uploads: list[dict] = []
        self.puts: list[dict] = []

    def head_bucket(self, *, Bucket: str) -> dict:
        assert Bucket == "allbot-model-cache"
        return {}

    def list_objects_v2(self, **kwargs) -> dict:
        assert kwargs["Bucket"] == "allbot-model-cache"
        contents = [
            {"Key": key, "Size": int(value.get("ContentLength", 0))}
            for key, value in self.existing.items()
        ]
        return {"Contents": contents, "IsTruncated": False}

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        assert Bucket == "allbot-model-cache"
        if Key not in self.existing:
            raise ClientError(
                {"Error": {"Code": "404", "Message": "not found"}}, "GetObject"
            )
        body = self.existing[Key].get("Body", b"")
        if isinstance(body, str):
            body = body.encode("utf-8")
        return {"Body": io.BytesIO(body)}

    def head_object(self, *, Bucket: str, Key: str) -> dict:
        assert Bucket == "allbot-model-cache"
        if Key in self.existing:
            return self.existing[Key]
        raise ClientError(
            {"Error": {"Code": "404", "Message": "not found"}}, "HeadObject"
        )

    def upload_file(self, source: str, bucket: str, key: str, **kwargs) -> None:
        self.uploads.append(
            {
                "source": source,
                "bucket": bucket,
                "key": key,
                "kwargs": kwargs,
            }
        )

    def put_object(self, **kwargs) -> None:
        self.puts.append(kwargs)
        body = kwargs["Body"]
        self.existing[kwargs["Key"]] = {
            "ContentLength": len(body),
            "Body": body,
            "Metadata": kwargs.get("Metadata") or {},
        }


def _write_manifest(
    registry: ModelRegistry,
    bundle: str,
    version: str,
    files: list[dict],
) -> None:
    registry.write_manifest(
        bundle,
        version,
        {
            "bundle": bundle,
            "version": version,
            "profiles": [bundle.replace("_baseline", "")],
            "source": {"node_id": "unit-test"},
            "files": files,
        },
    )


def _touch_blob(registry: ModelRegistry, sha256: str) -> None:
    path = registry.blob_path(sha256)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"model")


def test_face_swap_model_cache_target_is_independent_and_opt_in():
    module = _load_module()
    target = module.TARGETS_BY_NAME["face_swap"]

    assert target not in module.DEFAULT_BASE_TARGETS
    assert target.prefix == "face_swap_v2/2026-07-25"
    assert target.manifest_key == "face_swap_v2/2026-07-25/manifest.json"
    assert target.bundle_versions == (("face_swap_v2_baseline", "2026-07-25"),)


def _seed_default_bundle_manifests(registry: ModelRegistry) -> dict[str, str]:
    shas = {name: str(index) * 64 for index, name in enumerate("abcdefghijkl", start=1)}
    _write_manifest(
        registry,
        "img2img_lora_baseline",
        "2026-06-10",
        [
            {
                "relative_path": "checkpoints/qwen.safetensors",
                "sha256": shas["a"],
                "size_bytes": 10,
            }
        ],
    )
    _write_manifest(
        registry,
        "i2i_pro_baseline",
        "2026-06-14-test",
        [
            {
                "relative_path": "unet/i2i.safetensors",
                "sha256": shas["b"],
                "size_bytes": 20,
            }
        ],
    )
    _write_manifest(
        registry,
        "ltx_video_baseline",
        "2026-06-10",
        [
            {
                "relative_path": "clip/LTX 2.3/gemma.safetensors",
                "sha256": shas["c"],
                "size_bytes": 30,
            }
        ],
    )
    _write_manifest(
        registry,
        "face_i2i_t2i_baseline",
        "2026-06-10",
        [
            {
                "relative_path": "unet/face.safetensors",
                "sha256": shas["d"],
                "size_bytes": 40,
            }
        ],
    )
    _write_manifest(
        registry,
        "video_basic_baseline",
        "2026-06-10",
        [
            {
                "relative_path": "diffusion_models/wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8H.safetensors",
                "sha256": shas["e"],
                "size_bytes": 50,
            },
            {
                "relative_path": "loras/Dance_high_noise.safetensors",
                "sha256": shas["f"],
                "size_bytes": 60,
            },
            {
                "relative_path": "text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "sha256": shas["g"],
                "size_bytes": 70,
            },
            {
                "relative_path": "vae/wan_2.1_vae.safetensors",
                "sha256": shas["h"],
                "size_bytes": 80,
            },
        ],
    )
    _write_manifest(
        registry,
        "wan22_video_v2_baseline",
        "2026-06-10",
        [
            {
                "relative_path": "diffusion_models/DasiwaWAN22I2V14BLightspeed_snatchkissHighV11.safetensors",
                "sha256": shas["i"],
                "size_bytes": 90,
            },
            {
                "relative_path": "clip/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "sha256": shas["g"],
                "size_bytes": 70,
            },
            {
                "relative_path": "vae/wan_2.1_vae.safetensors",
                "sha256": shas["h"],
                "size_bytes": 80,
            },
        ],
    )
    _write_manifest(
        registry,
        "wan22_explicit_lora_library",
        "2026-07-18",
        [
            {
                "relative_path": (
                    "loras/wan2.2/explicit_top200/005-example/high.safetensors"
                ),
                "sha256": shas["k"],
                "size_bytes": 110,
            },
            {
                "relative_path": (
                    "loras/wan2.2/explicit_top200/005-example/low.safetensors"
                ),
                "sha256": shas["l"],
                "size_bytes": 120,
            },
        ],
    )
    _write_manifest(
        registry,
        "pornmaster_flux2_edit_bf16_baseline",
        "2026-07-12",
        [
            {
                "relative_path": (
                    "diffusion_models/flux2/"
                    "PornMaster_flux2_klein_9b_turbo_bf16_V4.safetensors"
                ),
                "sha256": shas["j"],
                "size_bytes": 100,
            }
        ],
    )
    for sha in shas.values():
        _touch_blob(registry, sha)
    return shas


def test_all_task_lan_cache_manifests_use_canonical_video_keys(tmp_path):
    module = _load_module()
    registry = ModelRegistry(tmp_path / "registry")
    _seed_default_bundle_manifests(registry)
    client = _FakeLanClient()

    payload = module.upload_all_task_models(
        repo_root=registry.root,
        bucket="allbot-model-cache",
        execute=False,
        create_bucket=False,
        client=client,
    )

    manifests = payload["target_manifests"]
    assert "video_basic/2026-06-10/manifest.json" not in manifests
    assert "image_to_video/2026-07-18-lora5/manifest.json" in manifests
    assert "wan22_video_v2/2026-07-21-pruned-v11/manifest.json" in manifests
    assert "wan22_aio_video/2026-07-18-lora5/manifest.json" in manifests
    assert "pornmaster_flux2_edit_bf16/2026-07-12/manifest.json" in manifests
    assert manifests["pornmaster_flux2_edit_bf16/2026-07-12/manifest.json"][
        "models"
    ] == ["diffusion_models/flux2/PornMaster_flux2_klein_9b_turbo_bf16_V4.safetensors"]
    assert manifests["image_to_video/2026-07-18-lora5/manifest.json"]["file_count"] == 7
    assert manifests["wan22_video_v2/2026-07-21-pruned-v11/manifest.json"]["file_count"] == 7
    for manifest_key in (
        "image_to_video/2026-07-18-lora5/manifest.json",
        "wan22_video_v2/2026-07-21-pruned-v11/manifest.json",
    ):
        assert (
            "loras/wan2.2/explicit_top200/005-example/high.safetensors"
            in manifests[manifest_key]["models"]
        )
        assert (
            "loras/wan2.2/explicit_top200/005-example/low.safetensors"
            in manifests[manifest_key]["models"]
        )
    assert payload["target_unique_model_count"] == 12


def test_all_task_lan_cache_reuses_existing_manifest_object_key(tmp_path):
    module = _load_module()
    registry = ModelRegistry(tmp_path / "registry")
    shas = _seed_default_bundle_manifests(registry)
    existing_manifest = {
        "files": [
            {
                "relative_path": "checkpoints/qwen.safetensors",
                "sha256": shas["a"],
                "size_bytes": 10,
                "key": "img2img_lora/2026-06-10/models/checkpoints/qwen.safetensors",
            }
        ]
    }
    client = _FakeLanClient(
        {
            "img2img_lora/2026-06-10/manifest.json": {
                "ContentLength": 1,
                "Body": json.dumps(existing_manifest).encode("utf-8"),
                "Metadata": {},
            },
            "img2img_lora/2026-06-10/models/checkpoints/qwen.safetensors": {
                "ContentLength": 10,
                "Metadata": {"Sha256": shas["a"]},
            },
        }
    )

    payload = module.upload_all_task_models(
        repo_root=registry.root,
        bucket="allbot-model-cache",
        execute=False,
        create_bucket=False,
        client=client,
    )

    assert payload["existing_cached_unique_model_count"] == 1
    assert payload["skipped_existing_count"] == 1
    assert payload["upload_count"] == 11
    assert payload["target_manifests"]["img2img_lora/2026-06-10/manifest.json"][
        "models"
    ] == ["checkpoints/qwen.safetensors"]
