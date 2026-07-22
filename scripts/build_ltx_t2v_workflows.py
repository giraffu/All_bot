#!/usr/bin/env python3
"""Build deterministic API-format LTX T2V and six-view character workflows."""

from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "workers/comfy_agent/workflows"
REMOTE = ROOT / "remote_workers/comfy_agent/workflows"
VALIDATION = ROOT / "ops/gpu_pool_controller/validation_workflows/ltx_t2v"

T2V_NAME = "LTX 2.3 Sulphur T2V.json"
IC_NAME = "LTX 2.3 Sulphur Ingredients T2V.json"
CHARACTER_NAME = "Character Reference Six Views.json"

DEV_MODEL = "LTX 2.3/ltx-2.3-22b-dev-fp8.safetensors"
DISTILLED = "ltx2.3/ltx-2.3-22b-distilled-lora-384-1.1.safetensors"
SULPHUR = "ltx2.3/sulphur_lora_rank_768.safetensors"
INGREDIENTS = "ltx2.3/ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors"


def _replace_refs(workflow: dict, old: str, new: str, output: int = 0) -> None:
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        for key, value in node.get("inputs", {}).items():
            if isinstance(value, list) and value and value[0] == old:
                node["inputs"][key] = [new, value[1] if len(value) > 1 else output]


def build_t2v(*, ingredients: bool, sulphur: bool = True) -> dict:
    workflow = json.loads((LOCAL / "LTX 2.3 I2V 6.1.json").read_text())
    workflow["257"]["inputs"]["model_name"] = DEV_MODEL
    workflow["257"]["inputs"]["weight_dtype"] = "fp8_e4m3fn"
    fixed_loras = workflow["256"]["inputs"]
    fixed_loras["lora_1"] = {"on": True, "lora": DISTILLED, "strength": 0.5}
    fixed_loras.pop("lora_2", None)
    if sulphur:
        fixed_loras["lora_2"] = {"on": True, "lora": SULPHUR, "strength": 1.0}
    workflow["26:299"]["inputs"]["model"] = ["8", 0]
    workflow["26:300"]["inputs"]["model"] = ["8", 0]

    # Node 26:89 applies the fixed x2 spatial upscaler. These are latent/mask
    # dimensions; the public final outputs remain 768x448 (IC) or 1280x704.
    for node_id in ("26:93", "26:65", "26:39"):
        workflow[node_id]["inputs"]["width"] = 384 if ingredients else 640
        workflow[node_id]["inputs"]["height"] = 224 if ingredients else 352
    workflow["26:45"]["inputs"]["video_latent"] = ["26:39", 0]
    workflow["26:88"]["inputs"]["video_latent"] = ["26:89", 0]
    workflow["61"]["inputs"]["filename_prefix"] = (
        "ltx_t2v_ic" if ingredients else "ltx_t2v"
    )

    removable = {
        "15",
        "26:177",
        "26:176",
        "26:178",
        "26:179",
        "26:37",
        "26:297",
        "26:312",
        "26:311",
        "7",
        "260",
    }
    for node_id in removable:
        workflow.pop(node_id, None)

    if ingredients:
        workflow["270"] = {
            "inputs": {"image": "character_reference.png"},
            "class_type": "LoadImage",
            "_meta": {"title": "Ingredients character sheet"},
        }
        workflow["271"] = {
            "inputs": {
                "model": ["256", 0],
                "lora_name": INGREDIENTS,
                "strength_model": 1.0,
            },
            "class_type": "LTXICLoRALoaderModelOnly",
            "_meta": {"title": "Ingredients IC LoRA (fixed 1.0)"},
        }
        workflow["210"]["inputs"]["model"] = ["271", 0]
        workflow["272"] = {
            "inputs": {
                "positive": ["26:46", 0],
                "negative": ["26:46", 1],
                "vae": ["283", 0],
                "latent": ["26:39", 0],
                "image": ["270", 0],
                "frame_idx": 0,
                "strength": 1.0,
                "latent_downscale_factor": ["271", 1],
                "crop": "center",
                "use_tiled_encode": False,
                "tile_size": 256,
                "tile_overlap": 64,
            },
            "class_type": "LTXAddVideoICLoRAGuide",
            "_meta": {"title": "Ingredients reference guide"},
        }
        workflow["26:45"]["inputs"]["video_latent"] = ["272", 2]
        workflow["26:49"]["inputs"]["positive"] = ["272", 0]
        workflow["26:49"]["inputs"]["negative"] = ["272", 1]
        # IC-LoRA appends one guide latent frame. Crop it before the fixed x2
        # spatial upscaler; cropping after upscaling miscounts guide tokens and
        # leaks eight extra decoded frames (129 instead of 121 at five seconds).
        workflow["26:91"]["inputs"].update(
            {
                "positive": ["272", 0],
                "negative": ["272", 1],
                "latent": ["26:153", 0],
            }
        )
        workflow["26:89"]["inputs"]["samples"] = ["26:91", 2]
        workflow["26:90"]["inputs"]["positive"] = ["26:91", 0]
        workflow["26:90"]["inputs"]["negative"] = ["26:91", 1]
        workflow["26:149"]["inputs"]["latents"] = ["26:95", 0]
    return workflow


VIEW_PROMPTS = (
    "front close-up face portrait, looking at camera",
    "three-quarter close-up face portrait",
    "front waist-up portrait",
    "front full-body standing view",
    "side full-body standing profile",
    "back full-body standing view",
)


def build_character() -> dict:
    source = json.loads(
        (
            LOCAL
            / "PornMaster_F2K_9B_Turbo_Single-image-editing_Automatic_V1_2026_05_27.api.json"
        ).read_text()
    )
    result: dict = {}
    for index, view in enumerate(VIEW_PROMPTS, start=1):
        prefix = f"v{index}:"
        branch = copy.deepcopy(source)
        for old_id, node in branch.items():
            new_node = copy.deepcopy(node)
            for input_name, value in new_node.get("inputs", {}).items():
                if isinstance(value, list) and value and isinstance(value[0], str):
                    new_node["inputs"][input_name] = [prefix + value[0], *value[1:]]
            result[prefix + old_id] = new_node
        prompt = (
            "Same adult person as the source image; preserve exact identity, face, hairstyle, "
            "skin tone, body shape, clothing and accessories. "
            + view
            + ". Single view, pure black background, no text, no labels, no border."
        )
        result[prefix + "185"]["inputs"]["text"] = prompt
        result[prefix + "201"]["inputs"]["filename_prefix"] = (
            f"character_reference_view_{index:02d}"
        )
    return result


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    generated = {
        T2V_NAME: build_t2v(ingredients=False),
        IC_NAME: build_t2v(ingredients=True),
        CHARACTER_NAME: build_character(),
    }
    for directory in (LOCAL, REMOTE):
        directory.mkdir(parents=True, exist_ok=True)
        for filename, workflow in generated.items():
            write_json(directory / filename, workflow)
    validation = {
        "01_dev_distilled_t2v.json": build_t2v(ingredients=False, sulphur=False),
        "02_dev_distilled_sulphur_t2v.json": build_t2v(ingredients=False, sulphur=True),
        "03_dev_distilled_ingredients_t2v.json": build_t2v(
            ingredients=True, sulphur=False
        ),
        "04_dev_distilled_sulphur_ingredients_t2v.json": build_t2v(
            ingredients=True, sulphur=True
        ),
    }
    VALIDATION.mkdir(parents=True, exist_ok=True)
    for filename, workflow in validation.items():
        write_json(VALIDATION / filename, workflow)


if __name__ == "__main__":
    main()
