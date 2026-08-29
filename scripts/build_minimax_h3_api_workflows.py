#!/usr/bin/env python3
"""Build deterministic API-format workflows for the split MiniMax H3 stack."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


TEN_EROS_V3_MODEL = "MiniMaxH3/10Eros_Max_h3_TURBO-hybrid_beta3.safetensors"
CLIP = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VIDEO_VAE = "MiniMaxH3/minimax_h3_video_vae_fp16.safetensors"
AUDIO_VAE = "MiniMaxH3/minimax_h3_audio_vae_fp32.safetensors"
LIGHTX2V_LORA = (
    "MiniMaxH3/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
)
REF2V_SIGMAS = "1.00, 0.94, 0.83, 0.72, 0.55, 0.30, 0.10, 0.00"
FILENAMES = {
    "minimax_h3_t2v": "MiniMax H3 T2V.api.json",
    "minimax_h3_i2v": "MiniMax H3 I2V.api.json",
    "minimax_h3_flf2v": "MiniMax H3 FLF2V.api.json",
    "minimax_h3_ref2v": "MiniMax H3 REF2V.api.json",
}


def _node(class_type: str, **inputs):
    return {"inputs": inputs, "class_type": class_type}


def build(task_type: str) -> dict:
    if task_type not in FILENAMES:
        raise ValueError("unsupported public MiniMax H3 task type")
    is_ref2v = task_type == "minimax_h3_ref2v"
    # 10Eros v3 is a native TURBO hybrid for both FL2VA and REF2VA. Keep the
    # LightX2V node available only for the selectable official FL2VA model;
    # the default v3 graph bypasses it and uses the author's preferred 7-step
    # er_sde sigma schedule.
    base_model_input = ["1", 0]
    workflow = {
        "1": _node(
            "UNETLoader",
            unet_name=TEN_EROS_V3_MODEL,
            weight_dtype="default",
        ),
        "2": _node(
            "ModelAttentionBackend",
            model=base_model_input,
            attention="pytorch attention" if is_ref2v else "comfy kitchen attention",
        ),
        "3": _node(
            "MiniMaxH3SigmaShift",
            model=["2", 0],
            shift_video=11.0 if is_ref2v else 12.0,
            shift_audio=4.0 if is_ref2v else 3.0,
        ),
        "7": _node(
            "ReservedVRAMSetter",
            anything=["3", 0],
            reserved=2.0,
            mode="auto",
            seed=0,
            auto_max_reserved=3.0,
            clean_gpu_before=True,
        ),
        "4": _node("CLIPLoader", clip_name=CLIP, type="minimax", device="default"),
        "5": _node("VAELoader", vae_name=VIDEO_VAE),
        "6": _node("VAELoader", vae_name=AUDIO_VAE),
        "30": _node(
            "MiniMaxH3ReferenceToVideo" if is_ref2v else "MiniMaxH3ImageToVideo",
            clip=["4", 0],
            vae=["5", 0],
            **({"audio_vae": ["6", 0], "ref_image_size": "match"} if is_ref2v else {}),
            prompt="",
            width=736,
            height=416,
            length=124,
        ),
        "31": _node("RandomNoise", noise_seed=1),
        "32": _node("BasicGuider", model=["7", 0], conditioning=["30", 0]),
        "33": _node("KSamplerSelect", sampler_name="er_sde"),
        "34": _node(
            "ManualSigmas",
            sigmas=REF2V_SIGMAS,
        ),
        "35": _node(
            "SamplerCustomAdvanced",
            noise=["31", 0],
            guider=["32", 0],
            sampler=["33", 0],
            sigmas=["34", 0],
            latent_image=["30", 1],
        ),
        "36": _node("VAEDecode", samples=["35", 0], vae=["5", 0]),
        "37": _node("VAEDecodeAudio", samples=["35", 0], vae=["6", 0]),
        "38": _node(
            "VHS_VideoCombine",
            frame_rate=24.0,
            loop_count=0,
            filename_prefix=task_type,
            format="video/h264-mp4",
            pix_fmt="yuv420p",
            crf=20,
            save_metadata=True,
            trim_to_audio=False,
            pingpong=False,
            save_output=True,
            images=["36", 0],
            audio=["37", 0],
        ),
        # ImageFromBatch clamps to the final available frame. 4095 is its schema max.
        "39": _node("ImageFromBatch", batch_index=4095, length=1, image=["36", 0]),
        "40": _node(
            "SaveImage",
            filename_prefix=f"{task_type}_last_frame",
            images=["39", 0],
        ),
    }
    if not is_ref2v:
        workflow["8"] = _node(
            "LoraLoaderModelOnly",
            model=["1", 0],
            lora_name=LIGHTX2V_LORA,
            strength_model=1.0,
        )
    else:
        workflow["25"] = _node("LoadAudio", audio="minimax_h3_reference_audio.m4a")
        workflow["30"]["inputs"]["ref_audios.ref_audio_0"] = ["25", 0]
    count = {"minimax_h3_t2v": 0, "minimax_h3_i2v": 1, "minimax_h3_flf2v": 2, "minimax_h3_ref2v": 5}[
        task_type
    ]
    for index in range(1, count + 1):
        node_id = str(19 + index)
        workflow[node_id] = _node(
            "LoadImage", image=f"minimax_h3_reference_{index}.png"
        )
        if is_ref2v:
            workflow["30"]["inputs"][f"ref_images.ref_image_{index - 1}"] = [node_id, 0]
        else:
            workflow["30"]["inputs"][
                "first_frame" if index == 1 else "last_frame"
            ] = [node_id, 0]
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
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("workers/comfy_agent/workflows"),
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for task_type, filename in FILENAMES.items():
        target = args.output_dir / filename
        target.write_text(
            json.dumps(build(task_type), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
