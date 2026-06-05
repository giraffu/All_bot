from typing import Any, Callable

from src.domain_config.wan22_aio_video import (
    WAN22_LEGACY_IMAGE_TO_VIDEO_MODEL_PROFILE,
    WAN22_VIDEO_V2_MODEL_PROFILE,
    WAN22_VIDEO_V2_RESOLUTION_PRESETS,
    normalize_wan22_video_v2_duration_seconds,
    normalize_wan22_video_v2_resolution_preset,
    resolve_wan22_model_profile,
)
from src.lora_catalog import normalize_ltx_video_lora_items

LTX_VIDEO_ADDITIONAL_LORA_NODE_IDS = ("256",)
LTX_VIDEO_FIRST_PASS_MODEL_NODE_ID = "191"
LTX_VIDEO_FIRST_PASS_CLIP_NODE_ID = "189"
LTX_VIDEO_MAX_LORA_SLOTS = 10
# `Wan22AioV82.json` keeps the old prune output node, but the worker stores
# video and last-frame outputs explicitly.
WAN22_VIDEO_V2_REMOVABLE_NODE_IDS = ("9",)
WAN22_VIDEO_V2_DURATION_SECONDS_NODE_ID = "2578"
WAN22_VIDEO_V2_SINGLE_FRAME_SWITCH_NODE_ID = "2558"
WAN22_VIDEO_V2_RESOLUTION_NODE_ID = "2612"
WAN22_VIDEO_V2_FRAME_RATE_EXPRESSION_NODE_ID = "2623"
WAN22_VIDEO_V2_BASE_FRAMES_REF = ["2603", 0]
WAN22_VIDEO_V2_RIFE_NODE_ID = "265"
WAN22_VIDEO_V2_FRAME_COUNT_NODE_ID = "2575"
WAN22_VIDEO_V2_LAST_FRAME_NODE_ID = "2607"
WAN22_HIGH_UNET_NODE_ID = "2616"
WAN22_LOW_UNET_NODE_ID = "2617"
WAN22_HIGH_LORA_NODE_ID = "26"
WAN22_LOW_LORA_NODE_ID = "18"
WAN22_MAX_LORA_SLOTS = 10
WAN22_VIDEO_V2_PRECISION_PRESET_BY_KEY = {
    key: str(preset["precision_preset"])
    for key, preset in WAN22_VIDEO_V2_RESOLUTION_PRESETS.items()
}


def _normalize_wan22_video_v2_precision_preset(value: Any) -> str:
    normalized = normalize_wan22_video_v2_resolution_preset(value)
    if normalized in WAN22_VIDEO_V2_PRECISION_PRESET_BY_KEY:
        return WAN22_VIDEO_V2_PRECISION_PRESET_BY_KEY[normalized]
    return WAN22_VIDEO_V2_PRECISION_PRESET_BY_KEY["preview"]


def _resolve_wan22_duration_seconds(params: dict[str, Any]) -> int:
    for key in ("length", "duration", "requested_duration"):
        value = params.get(key)
        if value is not None:
            return normalize_wan22_video_v2_duration_seconds(value)
    return normalize_wan22_video_v2_duration_seconds(None)


def _set_wan22_model_profile(
    workflow: dict[str, Any],
    *,
    profile_name: str | None,
    set_node_input: Callable[..., None],
) -> None:
    profile = resolve_wan22_model_profile(profile_name)
    set_node_input(
        workflow,
        node_id=WAN22_HIGH_UNET_NODE_ID,
        input_name="unet_name",
        value=profile["high"],
    )
    set_node_input(
        workflow,
        node_id=WAN22_LOW_UNET_NODE_ID,
        input_name="unet_name",
        value=profile["low"],
    )


def _clear_wan22_lora_slots(workflow: dict[str, Any]) -> None:
    for node_id in (WAN22_HIGH_LORA_NODE_ID, WAN22_LOW_LORA_NODE_ID):
        node = workflow.get(node_id)
        if not isinstance(node, dict):
            continue
        inputs = node.setdefault("inputs", {})
        for slot_index in range(1, WAN22_MAX_LORA_SLOTS + 1):
            inputs.pop(f"lora_{slot_index}", None)


def _patch_wan22_lora(
    workflow: dict[str, Any],
    *,
    lora_name: str | None,
    allow_lora: bool,
) -> None:
    _clear_wan22_lora_slots(workflow)
    normalized_lora_name = str(lora_name or "").strip()
    if not allow_lora or not normalized_lora_name:
        return

    high_node = workflow.get(WAN22_HIGH_LORA_NODE_ID)
    if isinstance(high_node, dict):
        high_node.setdefault("inputs", {})["lora_1"] = {
            "on": True,
            "lora": f"{normalized_lora_name}_high_noise.safetensors",
            "strength": 1,
        }

    low_node = workflow.get(WAN22_LOW_LORA_NODE_ID)
    if isinstance(low_node, dict):
        low_node.setdefault("inputs", {})["lora_1"] = {
            "on": True,
            "lora": f"{normalized_lora_name}_low_noise.safetensors",
            "strength": 1,
        }


def _resolve_wan22_final_frames_ref(workflow: dict[str, Any]) -> list[Any]:
    node = workflow.get(WAN22_VIDEO_V2_RIFE_NODE_ID)
    if isinstance(node, dict) and node.get("class_type") == "FL_RIFE":
        inputs = node.setdefault("inputs", {})
        inputs.setdefault("images", list(WAN22_VIDEO_V2_BASE_FRAMES_REF))
        return [WAN22_VIDEO_V2_RIFE_NODE_ID, 0]
    return list(WAN22_VIDEO_V2_BASE_FRAMES_REF)


def patch_img2img_workflow(
    workflow: dict[str, Any],
    *,
    params: dict[str, Any],
    mapping: dict[str, Any],
    **_: Any,
) -> None:
    lora_name = params.get("lora_name", "")
    if lora_name and str(lora_name).strip() != "":
        if "32" in workflow and "inputs" in workflow["32"]:
            workflow["32"]["inputs"]["lora_name"] = lora_name
            if params.get("lora_strength") is not None:
                workflow["32"]["inputs"]["strength_model"] = float(
                    params["lora_strength"]
                )
    else:
        if "2" in workflow and "inputs" in workflow["2"]:
            workflow["2"]["inputs"]["model"] = ["1", 0]
        workflow.pop("32", None)

    text_encode_node_id = str(mapping.get("prompt", "3"))

    if "image2" not in params or not params["image2"]:
        if text_encode_node_id in workflow and "inputs" in workflow[text_encode_node_id]:
            workflow[text_encode_node_id]["inputs"].pop("image2", None)
        workflow.pop(str(mapping.get("image2", "20")), None)
        workflow.pop("21", None)

    if "image3" not in params or not params["image3"]:
        if text_encode_node_id in workflow and "inputs" in workflow[text_encode_node_id]:
            workflow[text_encode_node_id]["inputs"].pop("image3", None)
        workflow.pop(str(mapping.get("image3", "30")), None)
        workflow.pop("31", None)


def patch_i2i_draw_workflow(workflow: dict[str, Any], **_: Any) -> None:
    if "109" in workflow and "inputs" in workflow["109"]:
        workflow["109"]["inputs"]["text"] = " "


def _patch_ltx_video_lora(
    workflow: dict[str, Any],
    *,
    lora_items: list[dict[str, Any]],
) -> None:
    for node_id in LTX_VIDEO_ADDITIONAL_LORA_NODE_IDS:
        node = workflow.get(node_id)
        if not isinstance(node, dict):
            continue
        inputs = node.setdefault("inputs", {})
        for slot_index in range(1, LTX_VIDEO_MAX_LORA_SLOTS + 1):
            inputs.pop(f"lora_{slot_index}", None)

        for index, item in enumerate(lora_items[:LTX_VIDEO_MAX_LORA_SLOTS], start=1):
            inputs[f"lora_{index}"] = {
                "on": True,
                "lora": str(item["name"]),
                "strength": float(item["strength"]),
            }
        inputs["model"] = [LTX_VIDEO_FIRST_PASS_MODEL_NODE_ID, 0]
        inputs["clip"] = [LTX_VIDEO_FIRST_PASS_CLIP_NODE_ID, 0]


def _strip_ltx_video_lora_nodes(workflow: dict[str, Any]) -> None:
    for node_id in LTX_VIDEO_ADDITIONAL_LORA_NODE_IDS:
        workflow.pop(node_id, None)

    model_node = workflow.get("8")
    if isinstance(model_node, dict):
        inputs = model_node.get("inputs")
        if isinstance(inputs, dict):
            inputs["model"] = [LTX_VIDEO_FIRST_PASS_MODEL_NODE_ID, 0]


def patch_ltx_video_workflow(
    workflow: dict[str, Any],
    *,
    params: dict[str, Any],
    unique_id: Any,
    **_: Any,
) -> None:
    workflow.pop("210", None)
    workflow.pop("5", None)
    workflow.pop("59", None)
    if "8" in workflow and "inputs" in workflow["8"]:
        workflow["8"]["inputs"]["model"] = ["256", 0]

    safe_unique_id = unique_id or "ltx_video"
    for node_id, node in workflow.items():
        if (
            isinstance(node, dict)
            and node.get("class_type") == "VHS_VideoCombine"
            and "inputs" in node
        ):
            node["inputs"]["filename_prefix"] = f"ltx_video_{safe_unique_id}_{node_id}"

    lora_items = normalize_ltx_video_lora_items(
        params.get("lora_items"),
        max_items=3,
    )
    if not lora_items:
        lora_name = str(params.get("lora_name") or "").strip()
        if lora_name:
            lora_items = normalize_ltx_video_lora_items(
                [{"name": lora_name, "strength": params.get("lora_strength")}],
                max_items=3,
            )

    if lora_items:
        _patch_ltx_video_lora(workflow, lora_items=lora_items)
    else:
        _strip_ltx_video_lora_nodes(workflow)


def _patch_wan22_aio_workflow(
    workflow: dict[str, Any],
    *,
    params: dict[str, Any],
    set_node_input: Callable[..., None],
    unique_id: Any,
    default_model_profile: str,
    output_task_prefix: str,
    allow_lora: bool,
    **_: Any,
) -> None:
    for node_id in WAN22_VIDEO_V2_REMOVABLE_NODE_IDS:
        workflow.pop(node_id, None)

    _set_wan22_model_profile(
        workflow,
        profile_name=params.get("wan22_model_profile") or default_model_profile,
        set_node_input=set_node_input,
    )
    _patch_wan22_lora(
        workflow,
        lora_name=params.get("lora_name"),
        allow_lora=allow_lora,
    )

    set_node_input(
        workflow,
        node_id=WAN22_VIDEO_V2_DURATION_SECONDS_NODE_ID,
        input_name="value",
        value=_resolve_wan22_duration_seconds(params),
    )
    set_node_input(
        workflow,
        node_id=WAN22_VIDEO_V2_FRAME_RATE_EXPRESSION_NODE_ID,
        input_name="expression",
        value="max(1, round(( a - 1 ) / b))",
    )

    use_end_frame = bool(params.get("use_end_frame")) and bool(params.get("end_image"))
    set_node_input(
        workflow,
        node_id=WAN22_VIDEO_V2_SINGLE_FRAME_SWITCH_NODE_ID,
        input_name="value",
        value=not use_end_frame,
    )
    set_node_input(
        workflow,
        node_id=WAN22_VIDEO_V2_RESOLUTION_NODE_ID,
        input_name="precision_presets",
        value=_normalize_wan22_video_v2_precision_preset(
            params.get("resolution_preset")
        ),
    )

    start_image = params.get("image")
    if not use_end_frame and start_image:
        set_node_input(workflow, node_id="24", input_name="image", value=start_image)

    final_frames_ref = _resolve_wan22_final_frames_ref(workflow)

    set_node_input(
        workflow,
        node_id=WAN22_VIDEO_V2_FRAME_COUNT_NODE_ID,
        input_name="images",
        value=final_frames_ref,
    )

    set_node_input(
        workflow,
        node_id=WAN22_VIDEO_V2_LAST_FRAME_NODE_ID,
        input_name="batch_index",
        value=16384,
    )
    set_node_input(
        workflow,
        node_id=WAN22_VIDEO_V2_LAST_FRAME_NODE_ID,
        input_name="length",
        value=1,
    )
    set_node_input(
        workflow,
        node_id=WAN22_VIDEO_V2_LAST_FRAME_NODE_ID,
        input_name="image",
        value=final_frames_ref,
    )
    set_node_input(
        workflow,
        node_id="2503",
        input_name="images",
        value=[WAN22_VIDEO_V2_LAST_FRAME_NODE_ID, 0],
    )

    safe_unique_id = unique_id or "wan22"
    set_node_input(
        workflow,
        node_id="28",
        input_name="filename_prefix",
        value=f"{output_task_prefix}_{safe_unique_id}_video",
    )
    set_node_input(
        workflow,
        node_id="28",
        input_name="images",
        value=final_frames_ref,
    )
    set_node_input(
        workflow,
        node_id="2503",
        input_name="filename_prefix",
        value=f"{output_task_prefix}_{safe_unique_id}_last_frame",
    )


def patch_wan22_video_v2_workflow(
    workflow: dict[str, Any],
    **kwargs: Any,
) -> None:
    _patch_wan22_aio_workflow(
        workflow,
        default_model_profile=WAN22_VIDEO_V2_MODEL_PROFILE,
        output_task_prefix="wan22_video_v2",
        allow_lora=False,
        **kwargs,
    )


def patch_image_to_video_workflow(
    workflow: dict[str, Any],
    **kwargs: Any,
) -> None:
    _patch_wan22_aio_workflow(
        workflow,
        default_model_profile=WAN22_LEGACY_IMAGE_TO_VIDEO_MODEL_PROFILE,
        output_task_prefix="image_to_video",
        allow_lora=True,
        **kwargs,
    )


TASK_SPECIFIC_PATCHERS = {
    "img2img": patch_img2img_workflow,
    "img2img_lora": patch_img2img_workflow,
    "i2i_draw": patch_i2i_draw_workflow,
    "ltx_video": patch_ltx_video_workflow,
    "image_to_video": patch_image_to_video_workflow,
    "wan22_video_v2": patch_wan22_video_v2_workflow,
}
