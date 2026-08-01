#!/usr/bin/env python3
"""Build deterministic API-format LTX T2V and six-view character workflows."""

from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "workers/comfy_agent/workflows"
REMOTE = ROOT / "workers/runpod_runtime/comfy_agent/workflows"
VALIDATION = ROOT / "ops/gpu_pool_controller/validation_workflows/ltx_t2v"

T2V_NAME = "LTX 2.3 Sulphur T2V.json"
IC_NAME = "LTX 2.3 Sulphur Ingredients T2V.json"
CHARACTER_NAME = "Character Reference Six Views.json"

DEV_MODEL = "LTX 2.3/ltx-2.3-22b-dev-fp8.safetensors"
OFFICIAL_FAST_CHECKPOINT = "LTX 2.3/ltx-2.3-22b-distilled-fp8.safetensors"
OFFICIAL_FAST_TEXT_ENCODER = "LTX 2.3/gemma_3_12B_it_fp4_mixed.safetensors"
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


def build_ingredients_t2v(*, sulphur: bool) -> dict:
    """Build the Comfy official fast Ingredients graph.

    The character-sheet loader/resize remains AllBot-owned. Model loading, IC-LoRA
    parameter extraction, guide injection and sampling mirror the Comfy template;
    VHS remains the worker delivery adapter.
    """
    model_before_ingredients = "258" if sulphur else "127"
    workflow = {
        "127": {
            "inputs": {"ckpt_name": OFFICIAL_FAST_CHECKPOINT},
            "class_type": "CheckpointLoaderSimple",
        },
        "126": {
            "inputs": {"ckpt_name": OFFICIAL_FAST_CHECKPOINT},
            "class_type": "LTXVAudioVAELoader",
        },
        "103": {
            "inputs": {
                "text_encoder": OFFICIAL_FAST_TEXT_ENCODER,
                "ckpt_name": OFFICIAL_FAST_CHECKPOINT,
                "device": "default",
            },
            "class_type": "LTXAVTextEncoderLoader",
        },
        "195": {
            "inputs": {
                "model": [model_before_ingredients, 0],
                "lora_name": INGREDIENTS,
                "strength_model": 1.0,
            },
            "class_type": "LoraLoaderModelOnly",
        },
        "196": {
            "inputs": {"iclora_model": ["195", 0]},
            "class_type": "GetICLoRAParameters",
        },
        "28": {
            "inputs": {"text": "scene", "clip": ["103", 0]},
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "Positive Video"},
        },
        "29": {
            "inputs": {
                "text": "worst quality, inconsistent motion, blurry, jittery, distorted",
                "clip": ["103", 0],
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "Negative Video"},
        },
        "26:46": {
            "inputs": {
                "frame_rate": 24.0,
                "positive": ["28", 0],
                "negative": ["29", 0],
            },
            "class_type": "LTXVConditioning",
        },
        "270": {
            "inputs": {"image": "character_reference.png"},
            "class_type": "LoadImage",
            "_meta": {"title": "Ingredients reference sheet"},
        },
        "274": {
            "inputs": {
                "input": ["270", 0],
                "resize_type": "scale shorter dimension",
                "resize_type.shorter_size": 448,
                "scale_method": "lanczos",
            },
            "class_type": "ResizeImageMaskNode",
            "_meta": {"title": "Preserve reference-sheet aspect ratio"},
        },
        "5100": {
            "inputs": {"image": ["274", 0]},
            "class_type": "GetImageSize",
        },
        "273": {
            "inputs": {"image": ["274", 0], "amount": 121},
            "class_type": "RepeatImageBatch",
            "_meta": {"title": "Static reference video"},
        },
        "712": {
            "inputs": {"width": 512, "height": 512, "batch_size": 1, "color": 0},
            "class_type": "EmptyImage",
        },
        "26:39": {
            "inputs": {
                "width": ["5100", 0],
                "height": ["5100", 1],
                "length": 121,
                "batch_size": 1,
            },
            "class_type": "EmptyLTXVLatentVideo",
        },
        "198": {
            "inputs": {
                "vae": ["127", 2],
                "image": ["712", 0],
                "latent": ["26:39", 0],
                "strength": 1.0,
                "bypass": True,
            },
            "class_type": "LTXVImgToVideoInplace",
        },
        "115": {
            "inputs": {
                "positive": ["26:46", 0],
                "negative": ["26:46", 1],
                "vae": ["127", 2],
                "latent": ["198", 0],
                "image": ["273", 0],
                "frame_idx": 0,
                "strength": 1.0,
                "iclora_parameters": ["196", 0],
            },
            "class_type": "LTXVAddGuide",
        },
        "26:40": {
            "inputs": {
                "frames_number": 121,
                "frame_rate": 24,
                "batch_size": 1,
                "audio_vae": ["126", 0],
            },
            "class_type": "LTXVEmptyLatentAudio",
        },
        "119": {
            "inputs": {
                "video_latent": ["115", 2],
                "audio_latent": ["26:40", 0],
            },
            "class_type": "LTXVConcatAVLatent",
        },
        "704": {
            "inputs": {
                "model": ["195", 0],
                "positive": ["115", 0],
                "negative": ["115", 1],
                "latent_image": ["119", 0],
                "seed": -1,
                "steps": 8,
                "cfg": 1.0,
                "sampler_name": "euler_ancestral",
                "scheduler": "linear_quadratic",
                "denoise": 1.0,
            },
            "class_type": "KSampler",
        },
        "121": {
            "inputs": {"av_latent": ["704", 0]},
            "class_type": "LTXVSeparateAVLatent",
        },
        "106": {
            "inputs": {
                "positive": ["115", 0],
                "negative": ["115", 1],
                "latent": ["121", 0],
            },
            "class_type": "LTXVCropGuides",
        },
        "107": {
            "inputs": {"samples": ["121", 1], "audio_vae": ["126", 0]},
            "class_type": "LTXVAudioVAEDecode",
        },
        "105": {
            "inputs": {
                "samples": ["106", 2],
                "vae": ["127", 2],
                "tile_size": 768,
                "overlap": 64,
                "temporal_size": 4096,
                "temporal_overlap": 64,
            },
            "class_type": "VAEDecodeTiled",
        },
        "61": {
            "inputs": {
                "frame_rate": 24.0,
                "loop_count": 0,
                "filename_prefix": "ltx_t2v_ic",
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": 14,
                "save_metadata": True,
                "trim_to_audio": False,
                "pingpong": False,
                "save_output": True,
                "images": ["105", 0],
                "audio": ["107", 0],
            },
            "class_type": "VHS_VideoCombine",
        },
    }
    if sulphur:
        workflow["258"] = {
            "inputs": {
                "model": ["127", 0],
                "lora_name": SULPHUR,
                "strength_model": 1.0,
            },
            "class_type": "LoraLoaderModelOnly",
            "_meta": {"title": "Sulphur LoRA 1.0"},
        }
    return workflow


def build_t2v(*, ingredients: bool, sulphur: bool = True) -> dict:
    if ingredients:
        return build_ingredients_t2v(sulphur=sulphur)
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

    # Plain T2V retains the fixed x2 spatial pass.
    for node_id in ("26:93", "26:65", "26:39"):
        workflow[node_id]["inputs"]["width"] = 640
        workflow[node_id]["inputs"]["height"] = 352
    workflow["26:45"]["inputs"]["video_latent"] = ["26:39", 0]
    workflow["26:88"]["inputs"]["video_latent"] = ["26:89", 0]
    workflow["61"]["inputs"]["filename_prefix"] = "ltx_t2v"

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
        # Keep the user-facing IC workflow on the validated official stack.
        # Sulphur remains in validation 04 so compatibility can be rechecked
        # without silently changing the production Ingredients graph.
        IC_NAME: build_t2v(ingredients=True, sulphur=False),
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
