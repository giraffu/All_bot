from typing import Any, Callable

from src.lora_catalog import normalize_ltx_video_lora_items

LTX_VIDEO_ADDITIONAL_LORA_NODE_IDS = ("256",)
LTX_VIDEO_FIRST_PASS_MODEL_NODE_ID = "191"
LTX_VIDEO_FIRST_PASS_CLIP_NODE_ID = "189"
LTX_VIDEO_MAX_LORA_SLOTS = 10
# `WAN 2.2 i2v -AiO-new.json` already prunes the old debug/preview branch nodes.
WAN22_VIDEO_V2_REMOVABLE_NODE_IDS = ("9",)
WAN22_VIDEO_V2_PRECISION_PRESET_BY_KEY = {
    "fast": "0.36 MP - Small",
    "standard": "0.52 MP - SD",
    "hd": "0.65 MP - Balanced",
}


def _normalize_wan22_video_v2_precision_preset(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized in WAN22_VIDEO_V2_PRECISION_PRESET_BY_KEY:
        return WAN22_VIDEO_V2_PRECISION_PRESET_BY_KEY[normalized]
    if normalized in WAN22_VIDEO_V2_PRECISION_PRESET_BY_KEY.values():
        return normalized
    return WAN22_VIDEO_V2_PRECISION_PRESET_BY_KEY["standard"]


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


def patch_wan22_video_v2_workflow(
    workflow: dict[str, Any],
    *,
    params: dict[str, Any],
    set_node_input: Callable[..., None],
    unique_id: Any,
    **_: Any,
) -> None:
    for node_id in WAN22_VIDEO_V2_REMOVABLE_NODE_IDS:
        workflow.pop(node_id, None)

    set_node_input(workflow, node_id="2586", input_name="value", value=5)
    set_node_input(
        workflow,
        node_id="2581",
        input_name="expression",
        value="max(1, round(( a - 1 ) / b))",
    )

    use_end_frame = bool(params.get("use_end_frame")) and bool(params.get("end_image"))
    set_node_input(
        workflow,
        node_id="2557",
        input_name="value",
        value=not use_end_frame,
    )
    set_node_input(
        workflow,
        node_id="2621",
        input_name="precision_presets",
        value=_normalize_wan22_video_v2_precision_preset(
            params.get("resolution_preset")
        ),
    )

    start_image = params.get("image")
    if not use_end_frame and start_image:
        set_node_input(workflow, node_id="24", input_name="image", value=start_image)

    decoded_frames_ref = ["2612", 0]
    set_node_input(
        workflow,
        node_id="2542",
        input_name="clip_frames",
        value=decoded_frames_ref,
    )

    set_node_input(
        workflow,
        node_id="2563",
        input_name="image",
        value=decoded_frames_ref,
    )
    set_node_input(
        workflow,
        node_id="2575",
        input_name="image",
        value=decoded_frames_ref,
    )

    final_frames_ref = decoded_frames_ref

    set_node_input(
        workflow,
        node_id="2700",
        input_name="batch_index",
        value=16384,
    )
    set_node_input(workflow, node_id="2700", input_name="length", value=1)
    set_node_input(
        workflow,
        node_id="2700",
        input_name="image",
        value=final_frames_ref,
    )
    set_node_input(
        workflow,
        node_id="2503",
        input_name="images",
        value=["2700", 0],
    )

    safe_unique_id = unique_id or "wan22"
    set_node_input(
        workflow,
        node_id="28",
        input_name="filename_prefix",
        value=f"wan22_video_v2_{safe_unique_id}_video",
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
        value=f"wan22_video_v2_{safe_unique_id}_last_frame",
    )


TASK_SPECIFIC_PATCHERS = {
    "img2img": patch_img2img_workflow,
    "img2img_lora": patch_img2img_workflow,
    "i2i_draw": patch_i2i_draw_workflow,
    "ltx_video": patch_ltx_video_workflow,
    "wan22_video_v2": patch_wan22_video_v2_workflow,
}
