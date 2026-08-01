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
DISTILLED = "ltx2.3/ltx-2.3-22b-distilled-lora-384-1.1.safetensors"
SULPHUR = "ltx2.3/sulphur_lora_rank_768.safetensors"
INGREDIENTS = "ltx2.3/ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors"
OFFICIAL_INGREDIENTS_SIGMAS = (
    "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, "
    "0.421875, 0.0"
)


def _replace_refs(workflow: dict, old: str, new: str, output: int = 0) -> None:
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        for key, value in node.get("inputs", {}).items():
            if isinstance(value, list) and value and value[0] == old:
                node["inputs"][key] = [new, value[1] if len(value) > 1 else output]


def build_ingredients_t2v(*, sulphur: bool) -> dict:
    """Build the executable Lightricks single-stage Ingredients graph.

    The model/text/VAE loaders intentionally reuse the model layout already present
    in the AllBot GPU profiles. Everything after those loaders mirrors the official
    distilled Ingredients workflow, with VHS retained only as the delivery adapter.
    """
    source = json.loads((LOCAL / "LTX 2.3 I2V 6.1.json").read_text())
    model_after_distilled = "256"
    model_before_ingredients = "258" if sulphur else model_after_distilled
    workflow = {
        "257": copy.deepcopy(source["257"]),
        "189": copy.deepcopy(source["189"]),
        "283": copy.deepcopy(source["283"]),
        "282": copy.deepcopy(source["282"]),
        "256": {
            "inputs": {
                "model": ["257", 0],
                "lora_name": DISTILLED,
                "strength_model": 0.5,
            },
            "class_type": "LoraLoaderModelOnly",
            "_meta": {"title": "Official distilled LoRA 0.5"},
        },
        "271": {
            "inputs": {
                "model": [model_before_ingredients, 0],
                "lora_name": INGREDIENTS,
                "strength_model": 1.0,
            },
            "class_type": "LTXICLoRALoaderModelOnly",
            "_meta": {"title": "Official Ingredients IC-LoRA 1.0"},
        },
        "28": {
            "inputs": {"text": "scene", "clip": ["189", 0]},
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "Positive Video"},
        },
        "29": {
            "inputs": {
                "text": "worst quality, inconsistent motion, blurry, jittery, distorted",
                "clip": ["189", 0],
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
        "275": {
            "inputs": {"image": ["274", 0], "img_compression": 18},
            "class_type": "LTXVPreprocess",
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
        "276": {
            "inputs": {
                "vae": ["283", 0],
                "image": ["275", 0],
                "latent": ["26:39", 0],
                "strength": 1.0,
                "bypass": True,
            },
            "class_type": "LTXVImgToVideoConditionOnly",
        },
        "272": {
            "inputs": {
                "positive": ["26:46", 0],
                "negative": ["26:46", 1],
                "vae": ["283", 0],
                "latent": ["276", 0],
                "image": ["273", 0],
                "frame_idx": 0,
                "strength": 1.0,
                "latent_downscale_factor": ["271", 1],
                "crop": "disabled",
                "use_tiled_encode": False,
                "tile_size": 256,
                "tile_overlap": 64,
            },
            "class_type": "LTXAddVideoICLoRAGuide",
        },
        "26:40": {
            "inputs": {
                "frames_number": 121,
                "frame_rate": 24,
                "batch_size": 1,
                "audio_vae": ["282", 0],
            },
            "class_type": "LTXVEmptyLatentAudio",
        },
        "26:45": {
            "inputs": {
                "video_latent": ["272", 2],
                "audio_latent": ["26:40", 0],
            },
            "class_type": "LTXVConcatAVLatent",
        },
        "123": {
            "inputs": {"noise_seed": -1},
            "class_type": "RandomNoise",
        },
        "26:49": {
            "inputs": {
                "cfg": 1,
                "model": ["271", 0],
                "positive": ["272", 0],
                "negative": ["272", 1],
            },
            "class_type": "CFGGuider",
        },
        "26:50": {
            "inputs": {"sampler_name": "euler_ancestral_cfg_pp"},
            "class_type": "KSamplerSelect",
        },
        "26:292": {
            "inputs": {"sigmas": OFFICIAL_INGREDIENTS_SIGMAS},
            "class_type": "ManualSigmas",
        },
        "26:51": {
            "inputs": {
                "noise": ["123", 0],
                "guider": ["26:49", 0],
                "sampler": ["26:50", 0],
                "sigmas": ["26:292", 0],
                "latent_image": ["26:45", 0],
            },
            "class_type": "SamplerCustomAdvanced",
        },
        "26:153": {
            "inputs": {"av_latent": ["26:51", 0]},
            "class_type": "LTXVSeparateAVLatent",
        },
        "26:91": {
            "inputs": {
                "latent": ["26:153", 0],
                "output_frames": 121,
            },
            "class_type": "AllBotLTXCropGuideLatentsExact",
        },
        "26:154": {
            "inputs": {"samples": ["26:153", 1], "audio_vae": ["282", 0]},
            "class_type": "LTXVAudioVAEDecode",
        },
        "26:149": {
            "inputs": {
                "vae": ["283", 0],
                "latents": ["26:91", 0],
                "horizontal_tiles": 2,
                "vertical_tiles": 2,
                "overlap": 6,
                "last_frame_fix": False,
                "working_device": "auto",
                "working_dtype": "auto",
            },
            "class_type": "LTXVTiledVAEDecode",
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
                "images": ["26:149", 0],
                "audio": ["26:154", 0],
            },
            "class_type": "VHS_VideoCombine",
        },
    }
    if sulphur:
        workflow["258"] = {
            "inputs": {
                "model": [model_after_distilled, 0],
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
