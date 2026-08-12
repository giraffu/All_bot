from pathlib import Path

from ops.gpu_pool_controller.model_repo import ModelRegistry
from scripts.upload_all_task_models_to_lan_cache import (
    OPTIONAL_TARGETS,
    TARGETS_BY_NAME,
    build_target_manifests,
)


def test_ltx_t2v_optional_target_uses_shared_object_pool_without_wan_dependency(
    tmp_path: Path,
):
    registry = ModelRegistry(tmp_path / "registry")
    registry.ensure_layout()
    sha256 = "a" * 64
    blob = registry.blob_path(sha256)
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(b"model")
    registry.write_bundle_manifest(
        bundle="ltx_t2v_runtime",
        version="2026-08-01-comfy-fast",
        profiles=["ltx_t2v"],
        source={"revision": "fixed"},
        files=[
            {
                "relative_path": "loras/ltx2.3/example.safetensors",
                "sha256": sha256,
                "size_bytes": 5,
                "source_path": str(blob),
            }
        ],
    )
    target = next(item for item in OPTIONAL_TARGETS if item.name == "ltx_t2v")

    manifests = build_target_manifests(
        registry=registry,
        existing_by_sha={},
        targets=(target,),
    )

    manifest = manifests["ltx_t2v/2026-08-01-comfy-fast/manifest.json"]
    assert manifest["file_count"] == 1
    assert manifest["files"][0]["key"] == f"models/by-sha256/aa/{sha256}"


def test_ltx_unified_target_is_opt_in_and_uses_one_manifest():
    target = TARGETS_BY_NAME["ltx_unified"]

    assert target in OPTIONAL_TARGETS
    assert target.prefix == "ltx_unified/2026-08-03-10eros-v14-runexx-msr"
    assert target.manifest_key == ("ltx_unified/2026-08-03-10eros-v14-runexx-msr/manifest.json")
    assert target.bundle_versions == (("ltx_unified_runtime", "2026-08-03-10eros-v14-runexx-msr"),)


def test_minimax_h3_target_is_opt_in_and_uses_pinned_bundle():
    target = TARGETS_BY_NAME["minimax_h3"]

    assert target in OPTIONAL_TARGETS
    assert target.prefix == "minimax_h3/2026-08-12-fl2va-bf16-addon5-lightx2v8-v1"
    assert target.manifest_key == "minimax_h3/2026-08-12-fl2va-bf16-addon5-lightx2v8-v1/manifest.json"
    assert target.bundle_versions == (("minimax_h3_runtime", "2026-08-12-fl2va-bf16-addon5-lightx2v8-v1"),)
