from __future__ import annotations

import importlib.util
from pathlib import Path

from botocore.exceptions import ClientError

from ops.gpu_pool_controller.model_repo import ModelRegistry


MODULE_PATH = Path("scripts/upload_model_bundle_to_r2.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("upload_model_bundle_to_r2", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeR2Client:
    def __init__(self, existing: dict[str, dict] | None = None) -> None:
        self.existing = existing or {}
        self.uploads: list[dict] = []
        self.puts: list[dict] = []

    def head_bucket(self, *, Bucket: str) -> dict:
        assert Bucket == "allbot-model-cache"
        return {}

    def head_object(self, *, Bucket: str, Key: str) -> dict:
        assert Bucket == "allbot-model-cache"
        if Key in self.existing:
            return self.existing[Key]
        raise ClientError({"Error": {"Code": "404", "Message": "not found"}}, "HeadObject")

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


def _write_bundle_manifest(registry: ModelRegistry, bundle: str, files: list[dict]) -> None:
    registry.write_manifest(
        bundle,
        "2026-06-10",
        {
            "bundle": bundle,
            "version": "2026-06-10",
            "profiles": [bundle.replace("_baseline", "")],
            "source": {"node_id": "unit-test"},
            "files": files,
        },
    )


def _touch_blob(registry: ModelRegistry, sha256: str) -> None:
    path = registry.blob_path(sha256)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"model")


def test_union_bundle_upload_dry_run_dedupes_and_reports_missing_local_blobs(tmp_path):
    module = _load_module()
    registry = ModelRegistry(tmp_path / "registry")
    common_sha = "a" * 64
    local_sha = "b" * 64
    missing_sha = "c" * 64
    _write_bundle_manifest(
        registry,
        "video_basic_baseline",
        [
            {"relative_path": "vae/common.safetensors", "sha256": common_sha, "size_bytes": 10},
            {"relative_path": "loras/local.safetensors", "sha256": local_sha, "size_bytes": 20},
        ],
    )
    _write_bundle_manifest(
        registry,
        "wan22_video_v2_baseline",
        [
            {"relative_path": "vae/common.safetensors", "sha256": common_sha, "size_bytes": 10},
            {"relative_path": "unet/missing.safetensors", "sha256": missing_sha, "size_bytes": 30},
        ],
    )
    _touch_blob(registry, local_sha)
    client = _FakeR2Client(
        {
            "wan22_aio_video/2026-06-12-test/models/vae/common.safetensors": {
                "ContentLength": 10,
                "Metadata": {"sha256": common_sha},
            }
        }
    )

    payload = module.upload_bundle(
        repo_root=registry.root,
        bundles=["video_basic_baseline", "wan22_video_v2_baseline"],
        version="2026-06-10",
        bucket="allbot-model-cache",
        prefix="wan22_aio_video/2026-06-12-test",
        execute=False,
        create_bucket=False,
        client=client,
    )

    assert payload["bundle_count"] == 2
    assert payload["file_count"] == 3
    assert payload["skipped_existing_count"] == 1
    assert payload["upload_count"] == 1
    assert payload["missing_local_blob_count"] == 1
    assert payload["uploads"][0]["relative_path"] == "loras/local.safetensors"
    assert payload["missing_local_blobs"][0]["relative_path"] == "unet/missing.safetensors"


def test_union_bundle_manifest_rejects_same_relative_path_with_different_sha():
    module = _load_module()

    try:
        module._build_r2_manifest_from_manifests(
            manifests=[
                {
                    "bundle": "a",
                    "version": "v1",
                    "files": [
                        {"relative_path": "same.safetensors", "sha256": "a" * 64, "size_bytes": 1}
                    ],
                },
                {
                    "bundle": "b",
                    "version": "v1",
                    "files": [
                        {"relative_path": "same.safetensors", "sha256": "b" * 64, "size_bytes": 1}
                    ],
                },
            ],
            prefix="wan22_aio_video/2026-06-12-test",
        )
    except RuntimeError as exc:
        assert "conflicting model bundle entries" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("conflicting bundle entries should fail")


def test_union_bundle_execute_uploads_available_blobs_and_manifest(tmp_path):
    module = _load_module()
    registry = ModelRegistry(tmp_path / "registry")
    sha256 = "d" * 64
    _write_bundle_manifest(
        registry,
        "video_basic_baseline",
        [{"relative_path": "vae/model.safetensors", "sha256": sha256, "size_bytes": 5}],
    )
    _touch_blob(registry, sha256)
    client = _FakeR2Client()

    payload = module.upload_bundle(
        repo_root=registry.root,
        bundles=["video_basic_baseline"],
        version="2026-06-10",
        bucket="allbot-model-cache",
        prefix="wan22_aio_video/2026-06-12-test",
        execute=True,
        create_bucket=False,
        client=client,
    )

    assert payload["dry_run"] is False
    assert payload["upload_count"] == 1
    assert client.uploads[0]["key"] == "wan22_aio_video/2026-06-12-test/models/vae/model.safetensors"
    assert client.puts[0]["Key"] == "wan22_aio_video/2026-06-12-test/manifest.json"


def test_union_bundle_execute_missing_local_blob_fails_before_partial_upload(tmp_path):
    module = _load_module()
    registry = ModelRegistry(tmp_path / "registry")
    local_sha = "e" * 64
    missing_sha = "f" * 64
    _write_bundle_manifest(
        registry,
        "video_basic_baseline",
        [
            {"relative_path": "vae/local.safetensors", "sha256": local_sha, "size_bytes": 5},
            {"relative_path": "unet/missing.safetensors", "sha256": missing_sha, "size_bytes": 7},
        ],
    )
    _touch_blob(registry, local_sha)
    client = _FakeR2Client()

    try:
        module.upload_bundle(
            repo_root=registry.root,
            bundles=["video_basic_baseline"],
            version="2026-06-10",
            bucket="allbot-model-cache",
            prefix="wan22_aio_video/2026-06-12-test",
            execute=True,
            create_bucket=False,
            client=client,
        )
    except RuntimeError as exc:
        assert "missing local registry blobs" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("missing local blobs should fail before upload")

    assert client.uploads == []
    assert client.puts == []
