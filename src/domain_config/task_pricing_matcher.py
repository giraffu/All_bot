"""Normalize submitted inputs and match one sellable pricing variant."""

from __future__ import annotations

from typing import Any

from src.domain_config.task_pricing_catalog import pricing_variants_for_task_type
from src.domain_config.wan22_aio_video import (
    normalize_wan22_video_v2_resolution_preset,
)
from src.domain_config.ltx25_video_upscale import (
    normalize_ltx25_video_upscale_resolution,
)


def _input_count(inputs: dict[str, Any]) -> str | None:
    for key in ("images", "saved_input_images", "saved_inputs"):
        values = inputs.get(key)
        if isinstance(values, (list, tuple)) and values:
            return str(min(2, len(values)))
    if inputs.get("use_end_frame") or inputs.get("end_image"):
        return "2"
    if inputs.get("image") or inputs.get("image_path"):
        return "1"
    return None


def _duration(inputs: dict[str, Any]) -> str | None:
    raw = inputs.get("duration", inputs.get("length", inputs.get("requested_duration")))
    if raw is None:
        return None
    text = str(raw).strip().lower().removesuffix("s")
    try:
        return str(int(float(text)))
    except (TypeError, ValueError):
        return None


def _resolution(task_type: str, inputs: dict[str, Any]) -> str | None:
    raw = inputs.get(
        "resolution_preset",
        inputs.get("wan22_resolution_preset", inputs.get("resolution")),
    )
    if raw is None:
        return None
    if task_type == "ltx25_video_upscale":
        try:
            return normalize_ltx25_video_upscale_resolution(raw)
        except ValueError:
            return None
    if task_type.startswith("minimax_h3_") or task_type in {
        "custom_video",
        "video_lora",
        "image_to_video",
        "wan22_video_v2",
    }:
        return normalize_wan22_video_v2_resolution_preset(raw)
    return str(raw).strip().lower().removesuffix("p")


def build_pricing_context(task_type: str, inputs: dict[str, Any]) -> dict[str, str]:
    context: dict[str, str] = {}
    count = _input_count(inputs)
    if count is not None:
        context["input_count"] = count
    duration = _duration(inputs)
    if duration is not None:
        context["duration"] = duration
    resolution = _resolution(task_type, inputs)
    if resolution is not None:
        context["resolution"] = resolution

    if task_type == "edit":
        context["engine"] = "standard"
    elif task_type == "img2img_lora":
        context["engine"] = "addon"

    mode_by_task_type = {
        "ltx_video": "i2v",
        "ltx_video_flf2v": "flf2v",
        "ltx_video_v2": "i2v",
        "ltx_video_v2_flf2v": "flf2v",
        "ltx_t2v": "standard",
        "ltx_t2v_ic": "character",
        "minimax_h3_t2v": "t2v",
        "minimax_h3_i2v": "i2v",
        "minimax_h3_flf2v": "flf2v",
        "minimax_h3_ref2v": "ref2v",
    }
    if task_type in mode_by_task_type:
        context["mode"] = mode_by_task_type[task_type]
    if task_type in {"ltx_video", "ltx_video_v2"} and inputs.get("ltx_mode") in {
        "i2v",
        "flf2v",
    }:
        context["mode"] = str(inputs["ltx_mode"])
    if task_type.startswith("minimax_h3_"):
        context["reference_audio"] = "yes" if inputs.get("reference_audio") else "no"
        context["reference_video"] = "yes" if inputs.get("reference_video") else "no"
    return context


def matching_pricing_variant(
    task_type: str, inputs: dict[str, Any]
) -> dict[str, Any] | None:
    candidates = pricing_variants_for_task_type(task_type)
    if not candidates:
        return None
    context = build_pricing_context(task_type, inputs)
    matches = [
        item
        for item in candidates
        if item["conditions"]
        and all(context.get(key) == value for key, value in item["conditions"].items())
    ]
    if len(matches) == 1:
        return matches[0]
    fixed = [item for item in candidates if not item["conditions"]]
    return fixed[0] if len(fixed) == 1 else None
