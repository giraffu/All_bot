import importlib.util
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/prepare_ltx_t2v_model_bundle.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "prepare_ltx_t2v_model_bundle", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_ltx_t2v_manifest_matches_download_script_and_uses_gated_token():
    module = _load_module()
    manifest = yaml.safe_load(
        (ROOT / "ops/gpu_pool_controller/config/model_bundles.yml").read_text()
    )["bundles"]["ltx_t2v_runtime"]
    expected = {
        item["relative_path"]: (item["sha256"], item["size_bytes"])
        for item in manifest["files"]
    }
    actual = {
        item["relative_path"]: (item["sha256"], item["size_bytes"])
        for item in (
            *module.FILES,
            *(
                {
                    "relative_path": path,
                    "sha256": sha256,
                    "size_bytes": size,
                }
                for path, sha256, size in module.REUSED
            ),
        )
    }

    assert actual == expected
    ingredients = next(item for item in module.FILES if item["gated"])
    assert "08896e49f7620d7d250c37a3a1e7b1edd7322bd4" in ingredients["url"]
    distilled_checkpoint = next(
        item
        for item in module.FILES
        if item["relative_path"].endswith("ltx-2.3-22b-distilled-fp8.safetensors")
    )
    assert distilled_checkpoint == {
        "relative_path": ("checkpoints/LTX 2.3/ltx-2.3-22b-distilled-fp8.safetensors"),
        "sha256": "d9646b6f2d5c42d337b23671634c43bfeece6989644f51b4a3aa088465ccd3b2",
        "size_bytes": 29_531_884_062,
        "url": (
            "https://huggingface.co/Lightricks/LTX-2.3-fp8/resolve/"
            "1d756cd27fa11c0896c4dfee093cd1bf36c7f7a1/"
            "ltx-2.3-22b-distilled-fp8.safetensors"
        ),
        "gated": False,
    }
    fast_text_encoder = next(
        item
        for item in module.FILES
        if item["relative_path"].endswith("gemma_3_12B_it_fp4_mixed.safetensors")
    )
    assert fast_text_encoder["sha256"] == (
        "aaca463d11e6d8d2a4bdb0d6299214c15ef78a3f73e0ef8113d5a9d0219b3f6d"
    )
    assert fast_text_encoder["size_bytes"] == 9_447_702_218
    source = SCRIPT.read_text()
    assert "Authorization" in source
    assert "print(token)" not in source
    assert module.MIN_FREE_BYTES == 115 * 1024**3


def test_ltx_t2v_dockerfiles_keep_weights_external_and_pin_runtime():
    ltx = (ROOT / "workers/runpod_profiles/ltx_t2v/Dockerfile").read_text()
    pornmaster = (
        ROOT / "workers/runpod_profiles/pornmaster_flux2_edit/Dockerfile"
    ).read_text()

    assert "7bf8bfcd078c7f4ae50ca5149c9ff7d8613e1fb1" in ltx
    assert "aceeae9635f6d493f2893ba3c411a1c36031788a" in ltx
    assert "LTXICLoRALoaderModelOnly" in ltx
    assert "LTXAddVideoICLoRAGuide" in ltx
    assert "GetICLoRAParameters" in ltx
    assert "LTXVAddGuide" in ltx
    assert "LTXVImgToVideoInplace" in ltx
    assert 'find "${comfyui_dir}/models" -type f -name "*.safetensors"' in ltx
    assert "COPY shared /opt/allbot/runtime/runpod_worker/shared" in pornmaster
    assert "from shared.image_aspect import adapt_image_to_aspect" in pornmaster
    assert 'find "$(cat /opt/allbot-comfyui-dir)/models"' in pornmaster


def test_ltx_unified_dockerfile_supports_all_ltx_tasks_without_weights():
    dockerfile = (ROOT / "workers/runpod_profiles/ltx_unified/Dockerfile").read_text()

    assert (
        "ARG BASE_IMAGE=192.168.1.115:5000/allbot/comfy-runpod-ltx-t2v@sha256:"
        in dockerfile
    )
    assert (
        '{"ltx_video","ltx_video_flf2v","ltx_video_v2v_audio","ltx_t2v","ltx_t2v_ic"}'
        in dockerfile
    )
    assert "LTX 2.3 I2V 10Eros LoRA.json" in dockerfile
    assert "94a52bfec735ff6f802c480f7fe8fdac1d279a7f" in dockerfile
    assert "5fc6db6b39638a692f114c4bb5b6949f801b4efa" in dockerfile
    assert "ComfyUI-KJNodes" in dockerfile
    assert "ComfyUI-Licon-MSR" in dockerfile
    assert 'assert "LiconMSR" in m.NODE_CLASS_MAPPINGS' in dockerfile
    assert 'find "${comfyui_dir}/models" -type f -name "*.safetensors"' in dockerfile
    assert "--filter=blob:none" not in dockerfile


def test_lan_all_dockerfile_includes_pinned_msr_node_runtime():
    dockerfile = (ROOT / "workers/runpod_profiles/all/Dockerfile").read_text()
    min_nodes = (
        ROOT
        / "workers/runpod_profiles/ltx_unified/allbot_ltx_min_nodes/__init__.py"
    ).read_text()

    assert "94a52bfec735ff6f802c480f7fe8fdac1d279a7f" in dockerfile
    assert "ComfyUI-Licon-MSR" in dockerfile
    assert 'assert "LiconMSR" in m.NODE_CLASS_MAPPINGS' in dockerfile
    assert '"MathExpression|pysssss","LiconMSR"' in dockerfile
    assert "_load_licon_msr_class" in min_nodes
    assert 'NODE_CLASS_MAPPINGS["LiconMSR"]' in min_nodes


def test_runpod_profile_staging_includes_shared_aspect_adapter():
    build_script = (ROOT / "scripts/build_runpod_profile_image.sh").read_text(
        encoding="utf-8"
    )

    assert 'cp -a shared/. "${destination}/shared/"' in build_script
