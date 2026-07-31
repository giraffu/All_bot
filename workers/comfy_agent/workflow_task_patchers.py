from typing import Any, Callable

from src.domain_config.scail2_video import (
    SCAIL2_FIXED_HEIGHT,
    SCAIL2_FIXED_WIDTH,
    SCAIL2_FORCE_RATE,
    SCAIL2_SKIP_FIRST_FRAMES,
    get_scail2_frame_count,
    normalize_scail2_duration_seconds,
    normalize_scail2_negative_prompt,
    normalize_scail2_positive_prompt,
)
from src.domain_config.wan22_aio_video import (
    WAN22_LEGACY_IMAGE_TO_VIDEO_MODEL_PROFILE,
    WAN22_VIDEO_V2_MODEL_PROFILE,
    WAN22_VIDEO_V2_RESOLUTION_PRESETS,
    normalize_wan22_video_v2_duration_seconds,
    normalize_wan22_video_v2_resolution_preset,
    normalize_wan22_lora_items,
    resolve_wan22_model_profile,
)
from src.lora_catalog import normalize_ltx_video_lora_items
from src.wan22_explicit_lora_catalog import resolve_wan22_lora_pair

LTX_VIDEO_ADDITIONAL_LORA_NODE_IDS = ("256",)
LTX_VIDEO_FIRST_PASS_MODEL_NODE_ID = "191"
LTX_VIDEO_FIRST_PASS_CLIP_NODE_ID = "189"
LTX_VIDEO_IMAGE_TO_VIDEO_NODE_IDS = ("26:297", "26:312")
LTX_VIDEO_END_FRAME_RESIZE_NODE_ID = "26:313"
LTX_VIDEO_LAST_FRAME_INDEX_NODE_ID = "26:315"
LTX_VIDEO_LAST_FRAME_SAVE_NODE_ID = "902"
LTX_VIDEO_LOAD_VIDEO_NODE_ID = "900"
LTX_VIDEO_FPS = 24
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
WAN22_VIDEO_V2_LAST_FRAME_FALLBACK_INDEX = 4095
WAN22_HIGH_UNET_NODE_ID = "2616"
WAN22_LOW_UNET_NODE_ID = "2617"
WAN22_HIGH_LORA_NODE_ID = "26"
WAN22_LOW_LORA_NODE_ID = "18"
WAN22_MAX_LORA_SLOTS = 10
WAN22_VIDEO_V2_PRECISION_PRESET_BY_KEY = {
    key: str(preset["precision_preset"])
    for key, preset in WAN22_VIDEO_V2_RESOLUTION_PRESETS.items()
}
SCAIL2_LOAD_IMAGE_NODE_ID = "58"
SCAIL2_LOAD_VIDEO_NODE_ID = "113"
SCAIL2_POSITIVE_PROMPT_NODE_ID = "6"
SCAIL2_NEGATIVE_PROMPT_NODE_ID = "7"
SCAIL2_TO_VIDEO_NODE_ID = "101"
SCAIL2_COLORED_MASK_NODE_ID = "107"
SCAIL2_VIDEO_COMBINE_NODE_ID = "49"
SCAIL2_CONTEXT_WINDOWS_NODE_ID = "124"
PORNMASTER_FLUX2_UNET_NODE_ID = "100"
PORNMASTER_FLUX2_BF16_UNET_NAME = (
    "flux2/PornMaster_flux2_klein_9b_turbo_bf16_V4.safetensors"
)
LTX_T2V_DISTILLED_LORA = "ltx2.3/ltx-2.3-22b-distilled-lora-384-1.1.safetensors"
LTX_T2V_SULPHUR_LORA = "ltx2.3/sulphur_lora_rank_768.safetensors"
LTX_T2V_INGREDIENTS_LORA = "ltx2.3/ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors"
LTX_T2V_REFERENCE_SHEET_DESCRIPTION = (
    "This reference sheet contains one adult character in six clean panels on a "
    "black background. The top row shows front, side, and three-quarter face "
    "close-ups. The bottom row shows full-body front, side, and back turnarounds. "
    "All panels depict the same exact facial identity, facial proportions, "
    "hairstyle, skin tone, body proportions, clothing, and accessories."
)
LTX_T2V_INGREDIENTS_NEGATIVE = (
    "#Ingredients\n"
    "worst quality, inconsistent motion, blurry, jittery, distorted"
)


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
    lora_strength: Any = None,
    lora_items: Any = None,
    allow_lora: bool,
) -> None:
    _clear_wan22_lora_slots(workflow)
    normalized_items = normalize_wan22_lora_items(
        lora_items,
        lora_name=lora_name,
        lora_strength=lora_strength,
    )
    if not allow_lora or not normalized_items:
        return
    for slot_index, item in enumerate(normalized_items, start=1):
        name = str(item["name"])
        strength = float(item["strength"])
        resolved_pair = resolve_wan22_lora_pair(name)
        high_lora = (
            resolved_pair[0] if resolved_pair else f"{name}_high_noise.safetensors"
        )
        low_lora = (
            resolved_pair[1] if resolved_pair else f"{name}_low_noise.safetensors"
        )
        high_node = workflow.get(WAN22_HIGH_LORA_NODE_ID)
        if isinstance(high_node, dict):
            high_node.setdefault("inputs", {})[f"lora_{slot_index}"] = {
                "on": True,
                "lora": high_lora,
                "strength": strength,
            }
        low_node = workflow.get(WAN22_LOW_LORA_NODE_ID)
        if isinstance(low_node, dict):
            low_node.setdefault("inputs", {})[f"lora_{slot_index}"] = {
                "on": True,
                "lora": low_lora,
                "strength": strength,
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
        if (
            text_encode_node_id in workflow
            and "inputs" in workflow[text_encode_node_id]
        ):
            workflow[text_encode_node_id]["inputs"].pop("image2", None)
        workflow.pop(str(mapping.get("image2", "20")), None)
        workflow.pop("21", None)

    if "image3" not in params or not params["image3"]:
        if (
            text_encode_node_id in workflow
            and "inputs" in workflow[text_encode_node_id]
        ):
            workflow[text_encode_node_id]["inputs"].pop("image3", None)
        workflow.pop(str(mapping.get("image3", "30")), None)
        workflow.pop("31", None)


def patch_i2i_draw_workflow(workflow: dict[str, Any], **_: Any) -> None:
    if "109" in workflow and "inputs" in workflow["109"]:
        workflow["109"]["inputs"]["text"] = " "


def patch_pornmaster_flux2_edit_bf16_workflow(
    workflow: dict[str, Any],
    *,
    set_node_input: Callable[..., None],
    **_: Any,
) -> None:
    set_node_input(
        workflow,
        node_id=PORNMASTER_FLUX2_UNET_NODE_ID,
        input_name="unet_name",
        value=PORNMASTER_FLUX2_BF16_UNET_NAME,
    )


def patch_pornmaster_flux2_multi_edit_bf16_workflow(
    workflow: dict[str, Any],
    *,
    set_node_input: Callable[..., None],
    **_: Any,
) -> None:
    set_node_input(
        workflow,
        node_id="9",
        input_name="unet_name",
        value=PORNMASTER_FLUX2_BF16_UNET_NAME,
    )


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


def _resolve_ltx_duration_seconds(params: dict[str, Any]) -> int:
    for key in ("length", "duration", "requested_duration"):
        value = params.get(key)
        if value is None:
            continue
        try:
            return int(str(value).replace("s", "").strip())
        except (TypeError, ValueError):
            continue
    return 5


def _sync_ltx_slider_mirrors(workflow: dict[str, Any]) -> None:
    for node_id in ("18", "19", "181"):
        node = workflow.get(node_id)
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if isinstance(inputs, dict) and "Xi" in inputs:
            inputs["Xf"] = inputs["Xi"]


def _set_ltx_output_prefixes(
    workflow: dict[str, Any],
    *,
    unique_id: Any,
    output_task_prefix: str,
) -> None:
    safe_unique_id = unique_id or output_task_prefix
    for node_id, node in workflow.items():
        if not isinstance(node, dict) or "inputs" not in node:
            continue
        if node.get("class_type") == "VHS_VideoCombine":
            node["inputs"]["filename_prefix"] = (
                f"{output_task_prefix}_{safe_unique_id}_{node_id}"
            )
        elif (
            node_id == LTX_VIDEO_LAST_FRAME_SAVE_NODE_ID
            and node.get("class_type") == "SaveImage"
        ):
            node["inputs"]["filename_prefix"] = (
                f"{output_task_prefix}_{safe_unique_id}_last_frame"
            )


def _resolve_ltx_lora_items(params: dict[str, Any]) -> list[dict[str, Any]]:
    lora_items = normalize_ltx_video_lora_items(
        params.get("lora_items"),
        max_items=3,
    )
    if lora_items:
        return lora_items

    lora_name = str(params.get("lora_name") or "").strip()
    if not lora_name:
        return []
    return normalize_ltx_video_lora_items(
        [{"name": lora_name, "strength": params.get("lora_strength")}],
        max_items=3,
    )


def _patch_ltx_video_common(
    workflow: dict[str, Any],
    *,
    params: dict[str, Any],
    unique_id: Any,
    output_task_prefix: str,
    **_: Any,
) -> None:
    workflow.pop("210", None)
    workflow.pop("5", None)
    workflow.pop("59", None)
    if "8" in workflow and "inputs" in workflow["8"]:
        workflow["8"]["inputs"]["model"] = ["256", 0]

    _sync_ltx_slider_mirrors(workflow)
    _set_ltx_output_prefixes(
        workflow,
        unique_id=unique_id,
        output_task_prefix=output_task_prefix,
    )

    lora_items = _resolve_ltx_lora_items(params)

    if lora_items:
        _patch_ltx_video_lora(workflow, lora_items=lora_items)
    else:
        _strip_ltx_video_lora_nodes(workflow)


def patch_ltx_video_workflow(
    workflow: dict[str, Any],
    **kwargs: Any,
) -> None:
    _patch_ltx_video_common(
        workflow,
        output_task_prefix="ltx_video",
        **kwargs,
    )


def patch_ltx_video_flf2v_workflow(
    workflow: dict[str, Any],
    *,
    params: dict[str, Any],
    **kwargs: Any,
) -> None:
    _patch_ltx_video_common(
        workflow,
        params=params,
        output_task_prefix="ltx_video_flf2v",
        **kwargs,
    )

    for node_id in LTX_VIDEO_IMAGE_TO_VIDEO_NODE_IDS:
        node = workflow.get(node_id)
        if not isinstance(node, dict):
            continue
        inputs = node.setdefault("inputs", {})
        inputs["num_images"] = "2"
        inputs["num_images.image_2"] = [LTX_VIDEO_END_FRAME_RESIZE_NODE_ID, 0]
        inputs["num_images.strength_2"] = ["26:311", 0]
        inputs["num_images.index_2"] = [LTX_VIDEO_LAST_FRAME_INDEX_NODE_ID, 0]


def patch_ltx_video_v2v_audio_workflow(
    workflow: dict[str, Any],
    *,
    params: dict[str, Any],
    set_node_input: Callable[..., None],
    **kwargs: Any,
) -> None:
    _patch_ltx_video_common(
        workflow,
        params=params,
        output_task_prefix="ltx_video_v2v_audio",
        set_node_input=set_node_input,
        **kwargs,
    )
    frame_load_cap = _resolve_ltx_duration_seconds(params) * LTX_VIDEO_FPS + 1
    for input_name, value in (
        ("force_rate", LTX_VIDEO_FPS),
        ("frame_load_cap", frame_load_cap),
        ("skip_first_frames", 0),
        ("select_every_nth", 1),
    ):
        set_node_input(
            workflow,
            node_id=LTX_VIDEO_LOAD_VIDEO_NODE_ID,
            input_name=input_name,
            value=value,
        )


def _patch_ltx_t2v_workflow(
    workflow: dict[str, Any],
    *,
    params: dict[str, Any],
    unique_id: Any,
    ingredients: bool,
    **_: Any,
) -> None:
    if params.get("lora_name") or params.get("lora_items"):
        raise ValueError("ltx_t2v uses a fixed LoRA stack and rejects additional LoRA")
    duration = _resolve_ltx_duration_seconds(params)
    if duration not in {5, 10, 15, 20}:
        raise ValueError("invalid ltx_t2v duration")
    # Plain T2V uses the fixed x2 spatial pass. Ingredients follows Lightricks'
    # official single-stage conditioning path and therefore starts at final size.
    width, height = (768, 448) if ingredients else (640, 352)
    for node_id in ("26:93", "26:65", "26:39"):
        node = workflow.get(node_id)
        if isinstance(node, dict):
            node.setdefault("inputs", {})["width"] = width
            node["inputs"]["height"] = height
    for node_id in ("18",):
        node = workflow.get(node_id)
        if isinstance(node, dict):
            node.setdefault("inputs", {})["Xi"] = duration
            node["inputs"]["Xf"] = duration
    loader = workflow.get("256")
    if not isinstance(loader, dict):
        raise ValueError("fixed LTX LoRA loader node 256 missing")
    loader_inputs = loader.setdefault("inputs", {})
    loader_inputs["lora_1"] = {
        "on": True,
        "lora": LTX_T2V_DISTILLED_LORA,
        "strength": 0.5,
    }
    if ingredients:
        loader_inputs.pop("lora_2", None)
    else:
        loader_inputs["lora_2"] = {
            "on": True,
            "lora": LTX_T2V_SULPHUR_LORA,
            "strength": 1.0,
        }
    if ingredients:
        ic_loader = workflow.get("271")
        if not isinstance(ic_loader, dict):
            raise ValueError("Ingredients loader node 271 missing")
        ic_loader["inputs"]["lora_name"] = LTX_T2V_INGREDIENTS_LORA
        ic_loader["inputs"]["strength_model"] = 1.0
        sheet = str(params.get("character_sheet") or "").strip()
        if not sheet:
            raise ValueError("Ingredients character sheet missing")
        workflow["270"]["inputs"]["image"] = sheet
        sheet_scale = workflow.get("274")
        if not isinstance(sheet_scale, dict):
            raise ValueError("Ingredients sheet scale node 274 missing")
        sheet_scale["inputs"] = {
            "image": ["270", 0],
            "upscale_method": "lanczos",
            "width": width,
            "height": height,
            "crop": "disabled",
        }
        workflow.pop("277", None)
        workflow.pop("278", None)
        reference_video = workflow.get("273")
        if not isinstance(reference_video, dict):
            raise ValueError("Ingredients static reference video node 273 missing")
        reference_video["inputs"] = {
            "image": ["274", 0],
            "amount": duration * LTX_VIDEO_FPS + 1,
        }
        preprocess = workflow.get("275")
        if not isinstance(preprocess, dict):
            raise ValueError("Ingredients preprocess node 275 missing")
        preprocess["inputs"] = {
            "image": ["274", 0],
            "img_compression": 18,
        }
        image_condition = workflow.get("276")
        if not isinstance(image_condition, dict):
            raise ValueError("Ingredients image condition node 276 missing")
        image_condition["inputs"] = {
            "vae": ["283", 0],
            "image": ["275", 0],
            "latent": ["26:39", 0],
            "strength": 1.0,
            "bypass": True,
        }
        guide = workflow.get("272")
        if not isinstance(guide, dict):
            raise ValueError("Ingredients guide node 272 missing")
        guide_inputs = guide.setdefault("inputs", {})
        guide_inputs["latent"] = ["276", 0]
        guide_inputs["image"] = ["273", 0]
        guide_inputs["frame_idx"] = 0
        decoder = workflow.get("26:149")
        if not isinstance(decoder, dict):
            raise ValueError("Ingredients video decoder node 26:149 missing")
        decoder.setdefault("inputs", {})["latents"] = ["26:91", 2]
        output = workflow.get("61")
        if not isinstance(output, dict):
            raise ValueError("Ingredients output node 61 missing")
        output.setdefault("inputs", {})["audio"] = ["26:154", 0]
        prompt_node = workflow.get("28")
        if not isinstance(prompt_node, dict):
            raise ValueError("LTX prompt node 28 missing")
        target_description = str(
            prompt_node.setdefault("inputs", {}).get("text", "")
        ).strip()
        prompt_node["inputs"]["text"] = (
            f"### Reference Sheet Description\n"
            f"{LTX_T2V_REFERENCE_SHEET_DESCRIPTION}\n\n"
            f"### Target Description\n{target_description}"
        )
        negative_node = workflow.get("29")
        if not isinstance(negative_node, dict):
            raise ValueError("LTX negative prompt node 29 missing")
        negative_value = negative_node.setdefault("inputs", {}).get("text", "")
        negative_text = (
            negative_value.strip() if isinstance(negative_value, str) else ""
        )
        negative_node["inputs"]["text"] = (
            f"{negative_text}\n\n{LTX_T2V_INGREDIENTS_NEGATIVE}".strip()
        )
    audio_prompt = str(params.get("audio_prompt") or "").strip()
    if audio_prompt:
        prompt_node = workflow.get("28")
        prompt_node["inputs"]["text"] = (
            f"{prompt_node['inputs'].get('text', '')}\n\n#Audio\n{audio_prompt}"
        )
    _set_ltx_output_prefixes(
        workflow,
        unique_id=unique_id,
        output_task_prefix="ltx_t2v_ic" if ingredients else "ltx_t2v",
    )


def patch_ltx_t2v_workflow(workflow: dict[str, Any], **kwargs: Any) -> None:
    _patch_ltx_t2v_workflow(workflow, ingredients=False, **kwargs)


def patch_ltx_t2v_ic_workflow(workflow: dict[str, Any], **kwargs: Any) -> None:
    _patch_ltx_t2v_workflow(workflow, ingredients=True, **kwargs)


def patch_character_reference_build_workflow(
    workflow: dict[str, Any],
    *,
    params: dict[str, Any],
    unique_id: Any,
    **_: Any,
) -> None:
    image_path = str(params.get("image") or "").strip()
    if not image_path:
        images = params.get("images") or []
        image_path = str(images[0] if images else "").strip()
    if not image_path:
        raise ValueError("character reference source image missing")
    selected_index = int(params.get("character_view_index") or 0)
    if selected_index:
        if selected_index not in range(1, 7):
            raise ValueError("character reference view index must be between 1 and 6")
        selected_prefix = f"v{selected_index}:"
        for node_id in list(workflow):
            if not node_id.startswith(selected_prefix):
                workflow.pop(node_id)
        prompt = str(params.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("character reference view prompt missing")
        workflow[selected_prefix + "185"]["inputs"]["text"] = prompt
        workflow[selected_prefix + "100"]["inputs"]["unet_name"] = (
            PORNMASTER_FLUX2_BF16_UNET_NAME
        )
    for index in range(1, 7):
        if selected_index and index != selected_index:
            continue
        prefix = f"v{index}:"
        workflow[prefix + "15"]["inputs"]["image"] = image_path
        workflow[prefix + "28"]["inputs"]["noise_seed"] = int(
            params.get("seed") or unique_id or 1
        )
        workflow[prefix + "201"]["inputs"]["filename_prefix"] = (
            f"character_reference_view_{index:02d}_{unique_id or 'task'}"
        )


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
        lora_strength=params.get("lora_strength"),
        lora_items=params.get("lora_items"),
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
    set_node_input(
        workflow,
        node_id=WAN22_VIDEO_V2_RESOLUTION_NODE_ID,
        input_name="resolution_preset",
        value=_normalize_wan22_video_v2_precision_preset(
            params.get("resolution_preset")
        ),
    )
    set_node_input(
        workflow,
        node_id=WAN22_VIDEO_V2_RESOLUTION_NODE_ID,
        input_name="swap_aspect_when_not_image",
        value=False,
    )
    set_node_input(
        workflow,
        node_id=WAN22_VIDEO_V2_RESOLUTION_NODE_ID,
        input_name="aspect_preset_when_not_image",
        value="9:16 - Social",
    )
    set_node_input(
        workflow,
        node_id=WAN22_VIDEO_V2_RESOLUTION_NODE_ID,
        input_name="custom_aspect_width",
        value=16,
    )
    set_node_input(
        workflow,
        node_id=WAN22_VIDEO_V2_RESOLUTION_NODE_ID,
        input_name="custom_aspect_height",
        value=9,
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
        value=WAN22_VIDEO_V2_LAST_FRAME_FALLBACK_INDEX,
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
        allow_lora=True,
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


def _resolve_scail2_duration_seconds(
    params: dict[str, Any],
    *,
    task_type: str | None = None,
) -> int:
    for key in ("length", "duration", "requested_duration"):
        value = params.get(key)
        if value is not None:
            return normalize_scail2_duration_seconds(
                value,
                strict=True,
                task_type=task_type,
            )
    return normalize_scail2_duration_seconds(None, task_type=task_type)


def _patch_scail2_workflow(
    workflow: dict[str, Any],
    *,
    params: dict[str, Any],
    set_node_input: Callable[..., None],
    unique_id: Any,
    replacement_mode: bool,
    output_task_prefix: str,
    **_: Any,
) -> None:
    duration_seconds = _resolve_scail2_duration_seconds(
        params,
        task_type=output_task_prefix,
    )
    frame_count = get_scail2_frame_count(
        duration_seconds,
        strict=True,
        task_type=output_task_prefix,
    )

    if params.get("image"):
        set_node_input(
            workflow,
            node_id=SCAIL2_LOAD_IMAGE_NODE_ID,
            input_name="image",
            value=params["image"],
        )
    if params.get("video"):
        set_node_input(
            workflow,
            node_id=SCAIL2_LOAD_VIDEO_NODE_ID,
            input_name="video",
            value=params["video"],
        )

    set_node_input(
        workflow,
        node_id=SCAIL2_POSITIVE_PROMPT_NODE_ID,
        input_name="text",
        value=normalize_scail2_positive_prompt(
            output_task_prefix,
            params.get("prompt"),
        ),
    )
    set_node_input(
        workflow,
        node_id=SCAIL2_NEGATIVE_PROMPT_NODE_ID,
        input_name="text",
        value=normalize_scail2_negative_prompt(params.get("negative_prompt")),
    )

    set_node_input(
        workflow,
        node_id=SCAIL2_LOAD_VIDEO_NODE_ID,
        input_name="force_rate",
        value=SCAIL2_FORCE_RATE,
    )
    set_node_input(
        workflow,
        node_id=SCAIL2_LOAD_VIDEO_NODE_ID,
        input_name="frame_load_cap",
        value=frame_count,
    )
    set_node_input(
        workflow,
        node_id=SCAIL2_LOAD_VIDEO_NODE_ID,
        input_name="skip_first_frames",
        value=SCAIL2_SKIP_FIRST_FRAMES,
    )

    for input_name, value in (
        ("width", SCAIL2_FIXED_WIDTH),
        ("height", SCAIL2_FIXED_HEIGHT),
        ("length", frame_count),
        ("replacement_mode", replacement_mode),
    ):
        set_node_input(
            workflow,
            node_id=SCAIL2_TO_VIDEO_NODE_ID,
            input_name=input_name,
            value=value,
        )

    set_node_input(
        workflow,
        node_id=SCAIL2_COLORED_MASK_NODE_ID,
        input_name="replacement_mode",
        value=replacement_mode,
    )

    safe_unique_id = unique_id or "scail2"
    set_node_input(
        workflow,
        node_id=SCAIL2_VIDEO_COMBINE_NODE_ID,
        input_name="filename_prefix",
        value=f"{output_task_prefix}_{safe_unique_id}_video",
    )
    set_node_input(
        workflow,
        node_id=SCAIL2_VIDEO_COMBINE_NODE_ID,
        input_name="frame_rate",
        value=SCAIL2_FORCE_RATE,
    )
    set_node_input(
        workflow,
        node_id=SCAIL2_VIDEO_COMBINE_NODE_ID,
        input_name="save_output",
        value=True,
    )

    # Keep FreeNoise enabled for long motion transfer throughput.
    if output_task_prefix == "scail2_action_transfer_long":
        for input_name, value in (
            ("freenoise", True),
            ("retain_first_frame", False),
            ("split_conds_to_windows", False),
        ):
            set_node_input(
                workflow,
                node_id=SCAIL2_CONTEXT_WINDOWS_NODE_ID,
                input_name=input_name,
                value=value,
            )


def patch_scail2_action_transfer_workflow(
    workflow: dict[str, Any],
    **kwargs: Any,
) -> None:
    _patch_scail2_workflow(
        workflow,
        replacement_mode=False,
        output_task_prefix="scail2_action_transfer",
        **kwargs,
    )


def patch_scail2_action_transfer_long_workflow(
    workflow: dict[str, Any],
    **kwargs: Any,
) -> None:
    _patch_scail2_workflow(
        workflow,
        replacement_mode=False,
        output_task_prefix="scail2_action_transfer_long",
        **kwargs,
    )


def patch_scail2_video_replacement_workflow(
    workflow: dict[str, Any],
    **kwargs: Any,
) -> None:
    _patch_scail2_workflow(
        workflow,
        replacement_mode=True,
        output_task_prefix="scail2_video_replacement",
        **kwargs,
    )


def patch_scail2_face_swap_v2_workflow(
    workflow: dict[str, Any],
    **kwargs: Any,
) -> None:
    _patch_scail2_workflow(
        workflow,
        replacement_mode=True,
        output_task_prefix="scail2_face_swap_v2",
        **kwargs,
    )


TASK_SPECIFIC_PATCHERS = {
    "img2img": patch_img2img_workflow,
    "img2img_lora": patch_img2img_workflow,
    "i2i_draw": patch_i2i_draw_workflow,
    "pornmaster_flux2_edit_bf16": patch_pornmaster_flux2_edit_bf16_workflow,
    "pornmaster_flux2_multi_edit_bf16": patch_pornmaster_flux2_multi_edit_bf16_workflow,
    "ltx_video": patch_ltx_video_workflow,
    "ltx_video_flf2v": patch_ltx_video_flf2v_workflow,
    "ltx_video_v2v_audio": patch_ltx_video_v2v_audio_workflow,
    "ltx_t2v": patch_ltx_t2v_workflow,
    "ltx_t2v_ic": patch_ltx_t2v_ic_workflow,
    "character_reference_build": patch_character_reference_build_workflow,
    "video_insert": patch_image_to_video_workflow,
    "video_edit": patch_image_to_video_workflow,
    "image_to_video": patch_image_to_video_workflow,
    "wan22_video_v2": patch_wan22_video_v2_workflow,
    "scail2_action_transfer": patch_scail2_action_transfer_workflow,
    "scail2_action_transfer_long": patch_scail2_action_transfer_long_workflow,
    "scail2_video_replacement": patch_scail2_video_replacement_workflow,
    "scail2_face_swap_v2": patch_scail2_face_swap_v2_workflow,
}
