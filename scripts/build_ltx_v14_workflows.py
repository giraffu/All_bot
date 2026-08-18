#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIRS = (ROOT / "workers/comfy_agent/workflows",)
MODEL = "LTX 2.3/10Eros_v1.4_DMD_int8_convrot.safetensors"
FIRST_SIGMAS = "1.000,0.955,0.893,0.812,0.715,0.603,0.482,0.241,0.121,0.0"
FINAL_SIGMAS = "0.92,0.725,0.421875,0.0"
SPECS = (
    (
        "LTX 2.3 10Eros v1.2 I2V 6.1.json",
        "LTX 2.3 10Eros v1.4 DMD I2V.json",
        "ltx_video_v2",
        "ltx_video",
    ),
    (
        "LTX 2.3 10Eros v1.2 FLF2V 6.1.json",
        "LTX 2.3 10Eros v1.4 DMD FLF2V.json",
        "ltx_video_v2_flf2v",
        "ltx_video_flf2v",
    ),
)


def transform(workflow: dict) -> dict:
    workflow = json.loads(json.dumps(workflow))
    workflow["257"] = {
        "inputs": {"unet_name": MODEL, "weight_dtype": "default"},
        "class_type": "UNETLoader",
        "_meta": {"title": "10Eros v1.4 DMD INT8"},
    }
    workflow["210"]["inputs"]["model"] = ["191", 0]
    workflow["26:299"]["inputs"]["model"] = ["8", 0]
    workflow["26:300"]["inputs"]["model"] = ["8", 0]
    workflow["26:50"]["inputs"]["sampler_name"] = "euler_ancestral"
    workflow["26:169"]["inputs"]["sampler_name"] = "euler_ancestral_cfg_pp"
    workflow["225"]["inputs"]["sigmas"] = FIRST_SIGMAS
    workflow["226"]["inputs"]["sigmas"] = FINAL_SIGMAS
    workflow["26:292"]["inputs"]["switch"] = True
    workflow.pop("7", None)
    workflow.pop("256", None)
    workflow.pop("260", None)
    return workflow


def main() -> None:
    for directory in WORKFLOW_DIRS:
        mappings_path = directory / "mappings.json"
        mappings = json.loads(mappings_path.read_text())
        for source_name, target_name, task_type, source_task_type in SPECS:
            source = json.loads((directory / source_name).read_text())
            output = transform(source)
            (directory / target_name).write_text(
                json.dumps(output, ensure_ascii=False, indent=2) + "\n"
            )
            mappings[task_type] = mappings[source_task_type]
        mappings_path.write_text(
            json.dumps(mappings, ensure_ascii=False, indent=4) + "\n"
        )


if __name__ == "__main__":
    main()
