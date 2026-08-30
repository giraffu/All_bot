from pathlib import Path

import yaml

from scripts import prepare_ltx25_video_upscale_model_bundle as module


ROOT = Path(__file__).resolve().parents[2]


def test_ltx25_upscale_manifest_matches_pinned_gated_downloads():
    bundle = yaml.safe_load(
        (ROOT / "ops/gpu_pool_controller/config/model_bundles.yml").read_text(
            encoding="utf-8"
        )
    )["bundles"][module.BUNDLE]

    assert bundle["version"] == module.VERSION
    assert {
        item["relative_path"]: (item["sha256"], item["size_bytes"])
        for item in bundle["files"]
    } == {
        item["relative_path"]: (item["sha256"], item["size_bytes"])
        for item in module.FILES
    }
    assert module.LTX25_REVISION == "e8dc69fd26150afbfa20351f6bc9ac384257f9fd"
    assert module.IC_LORA_REVISION == "74c4e68ee7dd99f3997d5a1bb1a3784941822222"
    assert sum(item["size_bytes"] for item in module.FILES) == 39_041_416_124
    source = (ROOT / "scripts/prepare_ltx25_video_upscale_model_bundle.py").read_text()
    assert "Authorization" in source
    assert "print(token)" not in source


def test_ltx25_upscale_image_is_model_free_and_runtime_pinned():
    dockerfile = (
        ROOT / "workers/runpod_profiles/ltx25_video_upscale/Dockerfile"
    ).read_text(encoding="utf-8")

    assert "8a33128f2f8c5585c57486c07de481241e70a39c" in dockerfile
    assert "15d09abb5a187a8dcaea2fc31fe51ee96e6c9d0d" in dockerfile
    assert 'assert "ltx25_video_upscale" in p' in dockerfile
    assert "find \"${comfyui_dir}/models\" -type f -name '*.safetensors'" in dockerfile
    assert "LTXICLoRALoaderModelOnly" in dockerfile
    assert "LTXAddVideoICLoRAGuide" in dockerfile
