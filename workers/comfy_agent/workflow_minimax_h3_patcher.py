from __future__ import annotations

import os
import re
from typing import Any

from src.domain_config.minimax_h3 import (
    MINIMAX_H3_ADDON_MODELS,
    MiniMaxH3ValidationError,
    build_minimax_h3_spec,
    normalize_minimax_h3_addon_items,
)

_COUNTS = {
    "minimax_h3_t2v": (0, 0),
    "minimax_h3_i2v": (1, 1),
    "minimax_h3_flf2v": (2, 2),
    "minimax_h3_ref2v": (0, 5),
}
_PRECISION_PRESETS = {
    "preview": "0.26 MP - Preview",
    "small": "0.36 MP - Small",
    "standard": "0.52 MP - SD",
    "hd": "0.65 MP - Balanced",
}
_FRAME_COUNT_BY_DURATION = {5: 124, 10: 243, 15: 362}
_TEN_EROS_EXECUTION_PROFILE = {
    "model_input": ["1", 0],
    "sampler_name": "euler",
    "scheduler": "simple",
    "steps": 8,
    "shift_video": 12.0,
    "shift_audio": 7.0,
}
_FORBIDDEN_OVERRIDES = (
    "model_name",
    "checkpoint",
    "timeline_data",
    "sampler_name",
    "scheduler",
    "steps",
    "sigmas",
    "ref_image_size",
    "ref_videos",
    "ref_video_audios",
    "ref_audios",
)


def _frame_count(params: dict[str, Any]) -> int:
    raw_frames = params.get("frame_count")
    if raw_frames not in (None, ""):
        try:
            frames = int(raw_frames)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid MiniMax H3 frame count") from exc
        if frames in _FRAME_COUNT_BY_DURATION.values():
            return frames
    raw_duration = params.get("duration")
    try:
        duration = int(
            str(raw_duration if raw_duration not in (None, "") else 5).removesuffix("s")
        )
        return _FRAME_COUNT_BY_DURATION[duration]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid MiniMax H3 duration") from exc


def _apply_execution_profile(
    workflow: dict[str, Any], *, task_type: str
) -> list[Any]:
    workflow.pop("8", None)
    workflow.pop("9", None)
    profile = _TEN_EROS_EXECUTION_PROFILE
    workflow["3"]["inputs"]["shift_video"] = profile["shift_video"]
    workflow["3"]["inputs"]["shift_audio"] = profile["shift_audio"]
    workflow["33"] = {
        "inputs": {"sampler_name": profile["sampler_name"]},
        "class_type": "KSamplerSelect",
    }
    workflow["34"] = {
        "inputs": {
            "model": ["7", 0],
            "scheduler": profile["scheduler"],
            "steps": profile["steps"],
            "denoise": 1.0,
        },
        "class_type": "BasicScheduler",
    }
    if task_type == "minimax_h3_ref2v":
        workflow["30"]["inputs"]["ref_image_size"] = "match"
    return list(profile["model_input"])


def _build_spec_and_addons(task_type: str, params: dict[str, Any]):
    try:
        spec = build_minimax_h3_spec(
            task_type,
            {
                **params,
                "images": [name for name in _ordered_image_names(params) if name],
            },
        )
        addons = normalize_minimax_h3_addon_items(
            params, mode=task_type.removeprefix("minimax_h3_")
        )
        return spec, addons
    except MiniMaxH3ValidationError as exc:
        message = str(exc)
        if "主模型" in message:
            raise ValueError(f"invalid MiniMax H3 main model: {message}") from exc
        raise ValueError(f"invalid MiniMax H3 addon configuration: {message}") from exc


def _force_attention_backend(workflow: dict[str, Any]) -> None:
    if os.getenv("MINIMAX_H3_FORCE_PYTORCH_ATTENTION", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return
    attention_node = workflow.get("2")
    if (
        not isinstance(attention_node, dict)
        or attention_node.get("class_type") != "ModelAttentionBackend"
    ):
        raise ValueError("MiniMax H3 attention backend node is missing")
    attention_node.setdefault("inputs", {})["attention"] = "pytorch attention"


def _patch_addon_chain(
    workflow: dict[str, Any], *, model_input: list[Any], addon_items
) -> str:
    prompt_parts: list[str] = []
    for offset, selection in enumerate(addon_items):
        addon = MINIMAX_H3_ADDON_MODELS[selection.name]
        for part in (part.strip() for part in addon.prompt_prefix.split(",")):
            if part and part not in prompt_parts:
                prompt_parts.append(part)
        node_id = str(100 + offset)
        workflow[node_id] = {
            "inputs": {
                "model": model_input,
                "lora_name": addon.model_path,
                "strength_model": round(selection.strength, 6),
            },
            "class_type": "LoraLoaderModelOnly",
        }
        model_input = [node_id, 0]
    workflow["2"]["inputs"]["model"] = model_input
    return ", ".join(prompt_parts)


def _ordered_image_names(params: dict[str, Any]) -> list[str]:
    return [
        str(params.get(key) or "").strip()
        for key in ("image", "image2", "image3", "image4", "image5")
    ]


def _validate_image_names(task_type: str, names: list[str]) -> int:
    count = sum(bool(name) for name in names)
    minimum, maximum = _COUNTS[task_type]
    if not minimum <= count <= maximum or any(not names[index] for index in range(count)):
        raise ValueError(f"invalid ordered image count for {task_type}")
    return count


def _patch_source_resolution(
    workflow: dict[str, Any], *, task_type: str, params: dict[str, Any]
) -> None:
    if task_type not in {"minimax_h3_i2v", "minimax_h3_flf2v"}:
        return
    if str(params.get("aspect_ratio") or "source").strip() != "source":
        raise ValueError("MiniMax H3 image modes require source aspect ratio")
    preset = str(params.get("resolution_preset") or "preview").strip().lower()
    precision = _PRECISION_PRESETS.get(preset)
    if precision is None:
        raise ValueError("invalid MiniMax H3 resolution preset")
    calculator = workflow.get("41")
    if not isinstance(calculator, dict):
        raise ValueError("MiniMax H3 source resolution calculator is missing")
    calculator["inputs"].update(
        {"resolution_preset": precision, "scale_from_image": True}
    )
    workflow["30"]["inputs"].update({"width": ["41", 0], "height": ["41", 1]})


def _patch_reference_video(workflow: dict[str, Any], *, params: dict[str, Any]) -> None:
    guide_inputs = workflow["30"]["inputs"]
    reference_video = str(params.get("reference_video") or "").strip()
    if not reference_video:
        workflow.pop("26", None)
        guide_inputs.pop("ref_videos.ref_video_0", None)
        guide_inputs.pop("ref_video_audios.ref_video_audio_0", None)
        return
    workflow["26"] = {
        "inputs": {
            "video": reference_video,
            "force_rate": 24,
            "custom_width": 0,
            "custom_height": 0,
            "frame_load_cap": 120,
            "skip_first_frames": 0,
            "select_every_nth": 1,
            "format": "None",
        },
        "class_type": "VHS_LoadVideo",
    }
    guide_inputs["ref_videos.ref_video_0"] = ["26", 0]
    guide_inputs["ref_video_audios.ref_video_audio_0"] = ["26", 2]
    guide_inputs["prompt"] = (
        "<Video 1> is the final five seconds of the previous segment. "
        "Continue naturally after it while preserving the characters, scene, "
        "motion direction, camera trajectory, and audio continuity.\n\n"
        f"{guide_inputs['prompt']}"
    )


def _patch_reference_audio(workflow: dict[str, Any], *, params: dict[str, Any]) -> None:
    guide_inputs = workflow["30"]["inputs"]
    reference_audio = str(params.get("reference_audio") or "").strip()
    if reference_audio:
        workflow["25"] = {
            "inputs": {"audio": reference_audio},
            "class_type": "LoadAudio",
        }
        guide_inputs["ref_audios.ref_audio_0"] = ["25", 0]
        return
    workflow.pop("25", None)
    guide_inputs.pop("ref_audios.ref_audio_0", None)


def _patch_reference_descriptions(
    workflow: dict[str, Any], *, descriptions: Any, count: int
) -> None:
    if not isinstance(descriptions, list):
        raise ValueError("reference_descriptions must be an ordered list")
    if descriptions and (
        len(descriptions) != count or any(not str(item).strip() for item in descriptions)
    ):
        raise ValueError("reference descriptions must match reference images")
    if descriptions:
        prefix = "\n".join(
            f"<Picture {index}>: {str(description).strip()}"
            for index, description in enumerate(descriptions, start=1)
        )
        inputs = workflow["30"]["inputs"]
        inputs["prompt"] = f"{prefix}\n\n{inputs['prompt']}"


def _patch_ref2v_inputs(
    workflow: dict[str, Any], *, task_type: str, params: dict[str, Any], count: int
) -> None:
    descriptions = params.get("reference_descriptions") or []
    if task_type != "minimax_h3_ref2v":
        if descriptions:
            raise ValueError("reference descriptions are only supported by ref2v")
        return
    _patch_reference_video(workflow, params=params)
    _patch_reference_audio(workflow, params=params)
    _patch_reference_descriptions(workflow, descriptions=descriptions, count=count)


def _patch_image_nodes(
    workflow: dict[str, Any], *, names: list[str], count: int
) -> None:
    guide_inputs = workflow["30"]["inputs"]
    for index in range(1, 6):
        node_id = str(19 + index)
        if index <= count:
            workflow[node_id]["inputs"]["image"] = names[index - 1]
        else:
            workflow.pop(node_id, None)
            guide_inputs.pop(f"ref_images.ref_image_{index - 1}", None)


def _patch_output_prefixes(
    workflow: dict[str, Any], *, task_type: str, execution_id: str | None
) -> None:
    safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(execution_id or "")).strip("_")
    prefix = f"{task_type}_{safe_id}" if safe_id else task_type
    workflow["38"]["inputs"]["filename_prefix"] = prefix
    workflow["40"]["inputs"]["filename_prefix"] = f"{prefix}_last_frame"


def patch_minimax_h3_workflow(
    workflow: dict[str, Any],
    *,
    task_type: str,
    params: dict[str, Any],
    execution_id: str | None = None,
    **_: Any,
) -> None:
    task_type = str(task_type or "")
    if task_type not in _COUNTS:
        raise ValueError("invalid MiniMax H3 task type")
    if any(params.get(key) not in (None, "", [], ()) for key in _FORBIDDEN_OVERRIDES):
        raise ValueError("MiniMax H3 rejects model, sampler, and timeline overrides")
    for node_id in ["10", "11", "12", "13", *map(str, range(100, 120))]:
        workflow.pop(node_id, None)

    spec, addon_items = _build_spec_and_addons(task_type, params)
    workflow["1"]["inputs"]["unet_name"] = spec.model_name
    _force_attention_backend(workflow)
    prompt_prefix = _patch_addon_chain(
        workflow,
        model_input=_apply_execution_profile(workflow, task_type=task_type),
        addon_items=addon_items,
    )
    names = _ordered_image_names(params)
    count = _validate_image_names(task_type, names)
    _patch_source_resolution(workflow, task_type=task_type, params=params)
    inputs = workflow["30"]["inputs"]
    prompt = str(params.get("prompt") or "").strip()
    inputs["prompt"] = f"{prompt_prefix}, {prompt}" if prompt_prefix else prompt
    inputs["length"] = _frame_count(params)
    _patch_ref2v_inputs(workflow, task_type=task_type, params=params, count=count)
    _patch_image_nodes(workflow, names=names, count=count)
    _patch_output_prefixes(
        workflow, task_type=task_type, execution_id=execution_id
    )
