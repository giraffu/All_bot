from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path("scripts/publish_pornmaster_flux2_model_manifest.py")


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "publish_pornmaster_flux2_model_manifest",
        MODULE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeS3Client:
    def __init__(self, heads: dict[str, dict]):
        self.heads = heads
        self.puts: list[dict] = []

    def head_object(self, *, Bucket, Key):
        del Bucket
        return self.heads[Key]

    def put_object(self, **kwargs):
        self.puts.append(kwargs)
        return {"ok": True}


def test_manifest_builds_from_pornmaster_bundle_config():
    module = _load_module()

    bundle = module._load_bundle(module.DEFAULT_CONFIG, module.DEFAULT_BUNDLE)
    manifest = module._manifest_from_bundle(
        bundle_id=module.DEFAULT_BUNDLE,
        bundle=bundle,
        prefix=module.DEFAULT_PREFIX,
    )

    assert manifest["bundle"] == "pornmaster_flux2_edit_baseline"
    assert manifest["version"] == "2026-06-27"
    assert manifest["profiles"] == ["pornmaster_flux2_edit"]
    assert manifest["file_count"] == 3
    assert manifest["total_size_bytes"] == 18347472706
    assert [item["relative_path"] for item in manifest["files"]] == [
        "diffusion_models/flux2/PornMaster_flux2_klein_9b_turbo_fp8_V4.safetensors",
        "text_encoders/flux2/qwen_3_8b_fp8mixed.safetensors",
        "vae/flux2/full_encoder_small_decoder.safetensors",
    ]
    assert all(
        item["key"].startswith("pornmaster_flux2_edit/2026-06-27/models/")
        for item in manifest["files"]
    )


def test_validate_manifest_objects_requires_size_and_sha_metadata():
    module = _load_module()
    manifest = {
        "files": [
            {
                "key": "prefix/models/a.safetensors",
                "relative_path": "a.safetensors",
                "size_bytes": 12,
                "sha256": "a" * 64,
            },
            {
                "key": "prefix/models/b.safetensors",
                "relative_path": "b.safetensors",
                "size_bytes": 34,
                "sha256": "b" * 64,
            },
        ]
    }
    client = FakeS3Client(
        {
            "prefix/models/a.safetensors": {
                "ContentLength": 12,
                "Metadata": {"sha256": "a" * 64},
            },
            "prefix/models/b.safetensors": {
                "ContentLength": 34,
                "Metadata": {"sha256": "wrong"},
            },
        }
    )

    checks = module.validate_manifest_objects(
        client,
        bucket="allbot-model-cache",
        manifest=manifest,
    )

    assert checks[0]["ok"] is True
    assert checks[1]["ok"] is False
    assert checks[1]["reason"] == "sha256_metadata_mismatch"


def test_publish_manifest_writes_json_without_model_blobs():
    module = _load_module()
    manifest = {
        "bundle": "pornmaster_flux2_edit_baseline",
        "version": "2026-06-27",
        "profiles": ["pornmaster_flux2_edit"],
        "file_count": 0,
        "total_size_bytes": 0,
        "files": [],
    }
    client = FakeS3Client({})

    module.publish_manifest(
        client,
        bucket="allbot-model-cache",
        manifest_key="pornmaster_flux2_edit/2026-06-27/manifest.json",
        manifest=manifest,
    )

    assert len(client.puts) == 1
    put = client.puts[0]
    assert put["Bucket"] == "allbot-model-cache"
    assert put["Key"] == "pornmaster_flux2_edit/2026-06-27/manifest.json"
    assert put["ContentType"] == "application/json"
    assert json.loads(put["Body"].decode("utf-8")) == manifest
    assert put["Metadata"]["profile"] == "pornmaster_flux2_edit"
