import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIRS = (
    ROOT / "workers/comfy_agent/workflows",
)


@pytest.mark.parametrize("directory", WORKFLOW_DIRS)
@pytest.mark.parametrize(
    ("task_type", "filename", "image_count"),
    [
        ("ltx_video_v2", "LTX 2.3 10Eros v1.4 DMD I2V.json", 1),
        ("ltx_video_v2_flf2v", "LTX 2.3 10Eros v1.4 DMD FLF2V.json", 2),
    ],
)
def test_ltx_v14_workflow_contract(directory, task_type, filename, image_count):
    workflow = json.loads((directory / filename).read_text())
    mappings = json.loads((directory / "mappings.json").read_text())

    assert mappings[task_type]["image"] == "15"
    assert ("end_image" in mappings[task_type]) is (image_count == 2)
    assert workflow["257"]["class_type"] == "UNETLoader"
    assert workflow["257"]["inputs"] == {
        "unet_name": "LTX 2.3/10Eros_v1.4_DMD_int8_convrot.safetensors",
        "weight_dtype": "default",
    }
    assert workflow["26:50"]["inputs"]["sampler_name"] == "euler_ancestral"
    assert (
        workflow["26:169"]["inputs"]["sampler_name"]
        == "euler_ancestral_cfg_pp"
    )
    assert workflow["225"]["inputs"]["sigmas"] == (
        "1.000,0.955,0.893,0.812,0.715,0.603,0.482,0.241,0.121,0.0"
    )
    assert workflow["226"]["inputs"]["sigmas"] == "0.92,0.725,0.421875,0.0"
    assert workflow["26:292"]["inputs"]["switch"] is True
    assert not any("Lora Loader" in node.get("class_type", "") for node in workflow.values())
    serialized = json.dumps(workflow)
    assert "distilled-lora" not in serialized
    assert "10Eros-v12_LoRA" not in serialized
