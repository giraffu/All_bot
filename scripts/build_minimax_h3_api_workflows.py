#!/usr/bin/env python3
"""Build deterministic API-format MiniMax H3 workflows derived from DaSiWa defaults."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SOURCE_SHA256 = "c54e107382b65e4a897615b6a7d2f0a89ddab99b214e890aa93deab100640cdc"
FL_MODEL = "MiniMaxH3/minimax_h3_fl2va_pruned_bf16.safetensors"
REF_MODEL = "MiniMaxH3/minimax_h3_ref2va_pruned_int8_convrot.safetensors"
CLIP = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VIDEO_VAE = "MiniMaxH3/minimax_h3_video_vae_fp16.safetensors"
AUDIO_VAE = "MiniMaxH3/minimax_h3_audio_vae_fp32.safetensors"
HMNSFW_LORA = "MiniMaxH3/HMNSFW_AIO_V2.safetensors"
HMBREASTS_LORA = "MiniMaxH3/HMBreasts_085e0750_e40.safetensors"
VAGASSIST_LORA = "MiniMaxH3/vagassist_e40.safetensors"
HMPUSSY_MOTION_LORA = "MiniMaxH3/hmpussy_v6_epoch30.safetensors"
HMPENIS_LORA = "MiniMaxH3/HMPenis_v2_e35.safetensors"
LIGHTX2V_LORA = "MiniMaxH3/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
FILENAMES = {
    "minimax_h3_t2v": "MiniMax H3 T2V.api.json",
    "minimax_h3_i2v": "MiniMax H3 I2V.api.json",
    "minimax_h3_flf2v": "MiniMax H3 FLF2V.api.json",
    "minimax_h3_ref2v": "MiniMax H3 REF2V.api.json",
}


def _node(class_type: str, **inputs):
    return {"inputs": inputs, "class_type": class_type}


def build(task_type: str) -> dict:
    is_ref = task_type == "minimax_h3_ref2v"
    use_optimized_loras = task_type in {"minimax_h3_t2v", "minimax_h3_i2v"}
    patched_model = ["14", 0] if use_optimized_loras else ["1", 0]
    workflow = {
        "1": _node("UNETLoader", unet_name=REF_MODEL if is_ref else FL_MODEL, weight_dtype="default"),
        "2": _node("MiniMaxH3MemoryEfficientSageAttentionPatch", model=patched_model),
        "3": _node(
            "MiniMaxH3SigmaShift",
            model=["2", 0],
            shift_video=12.0 if use_optimized_loras else 11.0,
            shift_audio=3.0 if use_optimized_loras else 4.0,
        ),
        "4": _node("CLIPLoader", clip_name=CLIP, type="minimax", device="default"),
        "5": _node("VAELoader", vae_name=VIDEO_VAE),
        "6": _node("VAELoader", vae_name=AUDIO_VAE),
        "30": _node(
            "MiniMaxH3ReferenceToVideo" if is_ref else "MiniMaxH3ImageToVideo",
            clip=["4", 0], vae=["5", 0], prompt="", width=736, height=416, length=124,
            **({"audio_vae": ["6", 0], "ref_image_size": "match"} if is_ref else {}),
        ),
        "31": _node("RandomNoise", noise_seed=1),
        "32": _node("BasicGuider", model=["3", 0], conditioning=["30", 0]),
        "33": (
            _node("MiniMaxH3TurboSampler")
            if use_optimized_loras
            else _node("KSamplerSelect", sampler_name="res_multistep")
        ),
        "34": _node("BasicScheduler", model=["3", 0], scheduler="simple", steps=8 if use_optimized_loras else 25, denoise=1.0),
        "35": _node("SamplerCustomAdvanced", noise=["31", 0], guider=["32", 0], sampler=["33", 0], sigmas=["34", 0], latent_image=["30", 1]),
        "36": _node("VAEDecode", samples=["35", 0], vae=["5", 0]),
        "37": _node("VAEDecodeAudio", samples=["35", 0], vae=["6", 0]),
        "38": _node("VHS_VideoCombine", frame_rate=24.0, loop_count=0, filename_prefix=task_type, format="video/h264-mp4", pix_fmt="yuv420p", crf=20, save_metadata=True, trim_to_audio=False, pingpong=False, save_output=True, images=["36", 0], audio=["37", 0]),
        # ImageFromBatch clamps to the final available frame. 4095 is its schema max.
        "39": _node("ImageFromBatch", batch_index=4095, length=1, image=["36", 0]),
        "40": _node("SaveImage", filename_prefix=f"{task_type}_last_frame", images=["39", 0]),
    }
    if use_optimized_loras:
        workflow["14"] = _node(
            "LoraLoaderModelOnly", model=["1", 0], lora_name=LIGHTX2V_LORA, strength_model=0.75
        )
    count = {"minimax_h3_t2v": 0, "minimax_h3_i2v": 1, "minimax_h3_flf2v": 2, "minimax_h3_ref2v": 4}[task_type]
    for index in range(1, count + 1):
        node_id = str(19 + index)
        workflow[node_id] = _node("LoadImage", image=f"minimax_h3_reference_{index}.png")
        if is_ref:
            # V3 Autogrow API inputs use the dynamic container path and a
            # zero-based template suffix. ComfyUI then packs these links into
            # execute(ref_images={...}) instead of forwarding flat kwargs.
            workflow["30"]["inputs"][f"ref_images.ref_image_{index - 1}"] = [node_id, 0]
        elif index == 1:
            workflow["30"]["inputs"]["first_frame"] = [node_id, 0]
        elif index == 2:
            workflow["30"]["inputs"]["last_frame"] = [node_id, 0]
    if task_type in {"minimax_h3_i2v", "minimax_h3_flf2v"}:
        workflow["41"] = _node(
            "DaSiWa_ResolutionScaleCalculator",
            resolution_preset="0.26 MP - Preview",
            no_scale=False,
            scale_from_image=True,
            aspect_preset_when_not_image="9:16 - Social",
            swap_aspect_when_not_image=False,
            custom_aspect_width=16,
            custom_aspect_height=9,
            mode="WAN/LTX (Div32)",
            custom_divisor=8,
            image=["20", 0],
        )
        workflow["30"]["inputs"]["width"] = ["41", 0]
        workflow["30"]["inputs"]["height"] = ["41", 1]
    return workflow


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("workers/comfy_agent/workflows"))
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    if args.source:
        digest = hashlib.sha256(args.source.read_bytes()).hexdigest()
        if digest != SOURCE_SHA256:
            raise SystemExit(f"DaSiWa source SHA256 mismatch: {digest}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for task_type, filename in FILENAMES.items():
        target = args.output_dir / filename
        target.write_text(json.dumps(build(task_type), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
