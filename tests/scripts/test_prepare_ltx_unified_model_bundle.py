import importlib.util
from pathlib import Path

from ops.gpu_pool_controller.model_repo import ModelRegistry


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/prepare_ltx_unified_model_bundle.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "prepare_ltx_unified_model_bundle", SCRIPT
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unified_manifest_deduplicates_shared_models_and_excludes_full_checkpoints(
    tmp_path: Path,
):
    module = _load_module()
    registry = ModelRegistry(tmp_path / "registry")
    registry.ensure_layout()
    shared_sha = "a" * 64
    video_sha = "b" * 64
    t2v_sha = "c" * 64
    for sha, payload in (
        (shared_sha, b"shared"),
        (video_sha, b"video"),
        (t2v_sha, b"t2v"),
    ):
        blob = registry.blob_path(sha)
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(payload)

    registry.write_bundle_manifest(
        bundle="ltx_video_baseline",
        version="2026-06-10",
        profiles=["ltx_video"],
        source={},
        files=[
            {
                "relative_path": "clip/shared.safetensors",
                "sha256": shared_sha,
                "size_bytes": 6,
            },
            {
                "relative_path": "loras/video.safetensors",
                "sha256": video_sha,
                "size_bytes": 5,
            },
            {
                "relative_path": next(iter(module.EXCLUDED_FULL_CHECKPOINTS)),
                "sha256": "d" * 64,
                "size_bytes": 10,
            },
        ],
    )
    registry.write_bundle_manifest(
        bundle="ltx_t2v_runtime",
        version="2026-07-22",
        profiles=["ltx_t2v"],
        source={},
        files=[
            {
                "relative_path": "clip/shared.safetensors",
                "sha256": shared_sha,
                "size_bytes": 6,
            },
            {
                "relative_path": "loras/t2v.safetensors",
                "sha256": t2v_sha,
                "size_bytes": 4,
            },
        ],
    )

    files = module.build_manifest_files(
        registry,
        extracted_lora={
            "relative_path": module.EXTRACTED_LORA["relative_path"],
            "sha256": "e" * 64,
            "size_bytes": 3,
        },
        require_blobs=False,
    )

    assert [item["relative_path"] for item in files] == sorted(
        [
            "clip/shared.safetensors",
            "loras/video.safetensors",
            "loras/t2v.safetensors",
            module.EXTRACTED_LORA["relative_path"],
        ]
    )
    assert not set(item["relative_path"] for item in files) & set(
        module.EXCLUDED_FULL_CHECKPOINTS
    )


def test_unified_release_constants_pin_the_approved_extracted_lora():
    module = _load_module()

    assert module.BUNDLE == "ltx_unified_runtime"
    assert module.VERSION == "2026-07-29"
    assert (
        module.EXTRACTED_LORA["sha256"]
        == "ac98553c007ea949603765d0e2a4ed97c6d5758bb2bb4d5e0c2cfdce0e4b3e76"
    )
    assert module.EXTRACTED_LORA["size_bytes"] == 3_162_331_448
    assert "7170ebca094fcb73e8f621e88ee38fc0524c9fcf" in module.EXTRACTED_LORA[
        "url"
    ]

