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
    source = SCRIPT.read_text()
    assert "Authorization" in source
    assert "print(token)" not in source
    assert module.MIN_FREE_BYTES == 75 * 1024**3


def test_ltx_t2v_dockerfiles_keep_weights_external_and_pin_runtime():
    ltx = (
        ROOT / "workers/runpod_profiles/ltx_t2v/Dockerfile"
    ).read_text()
    pornmaster = (
        ROOT / "workers/runpod_profiles/pornmaster_flux2_edit/Dockerfile"
    ).read_text()

    assert "7bf8bfcd078c7f4ae50ca5149c9ff7d8613e1fb1" in ltx
    assert "aceeae9635f6d493f2893ba3c411a1c36031788a" in ltx
    assert "LTXICLoRALoaderModelOnly" in ltx
    assert "LTXAddVideoICLoRAGuide" in ltx
    assert 'find "${comfyui_dir}/models" -type f -name "*.safetensors"' in ltx
    assert 'find "$(cat /opt/allbot-comfyui-dir)/models"' in pornmaster
