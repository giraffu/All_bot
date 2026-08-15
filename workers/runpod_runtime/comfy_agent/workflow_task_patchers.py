import re
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
LTX_T2V_MSR_LORA = "ltx2.3/LTX2.3-Licon-MSR-test_version.safetensors"
LTX_T2V_EROS_V14_MODEL = "LTX 2.3/10Eros_v1.4_DMD_int8_convrot.safetensors"
LTX_T2V_INGREDIENTS_FAST_CHECKPOINT = "LTX 2.3/ltx-2.3-22b-distilled-fp8.safetensors"
LTX_T2V_INGREDIENTS_FAST_TEXT_ENCODER = "LTX 2.3/gemma_3_12B_it_fp4_mixed.safetensors"
LTX_T2V_INGREDIENTS_NEGATIVE = (
    "worst quality, inconsistent motion, blurry, jittery, distorted"
)


_LTX_REFERENCE_LAYOUT_MARKERS = (
    "background",
    "panel",
    "turnaround view",
    "reference sheet",
    "背景",
    "左侧",
    "右侧",
    "面板",
    "画面",
    "参考表",
    "参考图",
)


def _identity_only_description(character_description: str) -> str:
    sentences = [
        part.strip()
        for part in re.split(r"(?<=[.!?。！？；;])\s*", character_description)
        if part.strip()
    ]
    identity_sentences = [
        sentence
        for sentence in sentences
        if not any(
            marker in sentence.casefold() for marker in _LTX_REFERENCE_LAYOUT_MARKERS
        )
    ]
    return " ".join(identity_sentences) or character_description


def _format_ltx_reference_sheet_description(character_description: str) -> str:
    """Wrap user-authored identity text in the IC-LoRA training headings."""
    identity_description = _identity_only_description(character_description)
    return (
        "**Left Panel (Character Face):** A clear front-facing close-up of "
        "one adult character. "
        f"{identity_description}\n"
        "**Right Panel (Character Turnaround):** Full-body front, side, and "
        "back views of the exact same character, preserving the same facial "
        "identity, facial proportions, hairstyle, skin tone, body shape, and "
        "body proportions."
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
    # Both paths use the workflow's fixed x2 spatial pass. The public IC result
    # is 768x448, so its first pass starts at 384x224.
    width, height = (384, 224) if ingredients else (640, 352)
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
    if ingredients:
        _patch_ltx_t2v_msr_workflow(
            workflow,
            params=params,
            duration=duration,
            width=width,
            height=height,
        )
        audio_prompt = str(params.get("audio_prompt") or "").strip()
        if audio_prompt:
            workflow["28"]["inputs"]["text"] = (
                f"{workflow['28']['inputs'].get('text', '')}\n\n#Audio\n{audio_prompt}"
            )
        _set_ltx_output_prefixes(
            workflow,
            unique_id=unique_id,
            output_task_prefix="ltx_t2v_ic",
        )
        return
    if ingredients:
        checkpoint = workflow.get("127")
        audio_vae = workflow.get("126")
        text_encoder = workflow.get("103")
        if not all(
            isinstance(node, dict) for node in (checkpoint, audio_vae, text_encoder)
        ):
            raise ValueError("Ingredients official fast loaders missing")
        checkpoint.setdefault("inputs", {})["ckpt_name"] = (
            LTX_T2V_INGREDIENTS_FAST_CHECKPOINT
        )
        audio_vae.setdefault("inputs", {})["ckpt_name"] = (
            LTX_T2V_INGREDIENTS_FAST_CHECKPOINT
        )
        text_encoder["inputs"] = {
            "text_encoder": LTX_T2V_INGREDIENTS_FAST_TEXT_ENCODER,
            "ckpt_name": LTX_T2V_INGREDIENTS_FAST_CHECKPOINT,
            "device": "default",
        }
        if params.get("character_sheets"):
            _patch_ltx_t2v_msr_workflow(
                workflow,
                params=params,
                duration=duration,
                width=width,
                height=height,
            )
            audio_prompt = str(params.get("audio_prompt") or "").strip()
            if audio_prompt:
                workflow["28"]["inputs"]["text"] = (
                    f"{workflow['28']['inputs'].get('text', '')}\n\n#Audio\n{audio_prompt}"
                )
            _set_ltx_output_prefixes(
                workflow,
                unique_id=unique_id,
                output_task_prefix="ltx_t2v_ic",
            )
            return
    else:
        loader = workflow.get("256")
        if not isinstance(loader, dict):
            raise ValueError("fixed LTX LoRA loader node 256 missing")
        loader_inputs = loader.setdefault("inputs", {})
        loader_inputs["lora_1"] = {
            "on": True,
            "lora": LTX_T2V_DISTILLED_LORA,
            "strength": 0.5,
        }
        loader_inputs["lora_2"] = {
            "on": True,
            "lora": LTX_T2V_SULPHUR_LORA,
            "strength": 1.0,
        }
    if ingredients:
        ic_loader = workflow.get("195")
        if not isinstance(ic_loader, dict):
            raise ValueError("Ingredients loader node 195 missing")
        sulphur_loader = workflow.get("258")
        ic_model_source = ["127", 0]
        if sulphur_loader is not None:
            expected_sulphur_inputs = {
                "model": ["127", 0],
                "lora_name": LTX_T2V_SULPHUR_LORA,
                "strength_model": 1.0,
            }
            if (
                not isinstance(sulphur_loader, dict)
                or sulphur_loader.get("class_type") != "LoraLoaderModelOnly"
                or sulphur_loader.get("inputs") != expected_sulphur_inputs
            ):
                raise ValueError("invalid isolated Ingredients Sulphur loader node 258")
            ic_model_source = ["258", 0]
        ic_loader["inputs"]["lora_name"] = LTX_T2V_INGREDIENTS_LORA
        ic_loader["inputs"]["model"] = ic_model_source
        ic_loader["inputs"]["strength_model"] = 1.0
        sheet = str(params.get("character_sheet") or "").strip()
        if not sheet:
            raise ValueError("Ingredients character sheet missing")
        workflow["270"]["inputs"]["image"] = sheet
        sheet_scale = workflow.get("274")
        if not isinstance(sheet_scale, dict):
            raise ValueError("Ingredients sheet scale node 274 missing")
        sheet_scale["inputs"] = {
            "input": ["270", 0],
            "resize_type": "scale shorter dimension",
            "resize_type.shorter_size": height,
            "scale_method": "lanczos",
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
        frame_count = duration * LTX_VIDEO_FPS + 1
        workflow["26:39"]["inputs"].update(
            {
                "width": ["5100", 0],
                "height": ["5100", 1],
                "length": frame_count,
            }
        )
        workflow["26:40"]["inputs"].update(
            {"frames_number": frame_count, "frame_rate": LTX_VIDEO_FPS}
        )
        image_condition = workflow.get("198")
        if not isinstance(image_condition, dict):
            raise ValueError("Ingredients image condition node 198 missing")
        image_condition["inputs"] = {
            "vae": ["127", 2],
            "image": ["712", 0],
            "latent": ["26:39", 0],
            "strength": 1.0,
            "bypass": True,
        }
        guide = workflow.get("115")
        if not isinstance(guide, dict):
            raise ValueError("Ingredients guide node 115 missing")
        guide_inputs = guide.setdefault("inputs", {})
        guide_inputs["latent"] = ["198", 0]
        guide_inputs["image"] = ["273", 0]
        guide_inputs["frame_idx"] = 0
        guide_inputs["strength"] = 1.0
        guide_inputs["iclora_parameters"] = ["196", 0]
        decoder = workflow.get("105")
        if not isinstance(decoder, dict):
            raise ValueError("Ingredients video decoder node 105 missing")
        decoder.setdefault("inputs", {})["samples"] = ["106", 2]
        output = workflow.get("61")
        if not isinstance(output, dict):
            raise ValueError("Ingredients output node 61 missing")
        output.setdefault("inputs", {})["audio"] = ["107", 0]
        prompt_node = workflow.get("28")
        if not isinstance(prompt_node, dict):
            raise ValueError("LTX prompt node 28 missing")
        target_description = str(
            prompt_node.setdefault("inputs", {}).get("text", "")
        ).strip()
        character_description = str(params.get("character_description") or "").strip()
        if not character_description:
            raise ValueError("Ingredients character description missing")
        reference_sheet_description = _format_ltx_reference_sheet_description(
            character_description
        )
        prompt_node["inputs"]["text"] = (
            f"### Reference Sheet Description\n{reference_sheet_description}\n\n"
            f"### Target Description\n{target_description}"
        )
        negative_node = workflow.get("29")
        if not isinstance(negative_node, dict):
            raise ValueError("LTX negative prompt node 29 missing")
        negative_node.setdefault("inputs", {})["text"] = LTX_T2V_INGREDIENTS_NEGATIVE
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


def _patch_ltx_t2v_msr_workflow(
    workflow: dict[str, Any],
    *,
    params: dict[str, Any],
    duration: int,
    width: int,
    height: int,
) -> None:
    """Apply the Runexx two-pass Licon MSR topology to the T2V base graph."""
    sheets = params.get("character_sheets")
    descriptions = params.get("character_descriptions")
    background = str(params.get("background_image") or "").strip()
    if not isinstance(sheets, (list, tuple)) or len(sheets) != 2:
        raise ValueError("Runexx MSR requires exactly 2 ordered character panels")
    if not isinstance(descriptions, (list, tuple)) or len(descriptions) != 2:
        raise ValueError("Runexx MSR requires exactly 2 character descriptions")
    sheets = [str(value or "").strip() for value in sheets]
    descriptions = [str(value or "").strip() for value in descriptions]
    if not all(sheets) or not all(descriptions) or not background:
        raise ValueError("Runexx MSR character panels, descriptions and background are required")
    if params.get("sulphur_strength") is not None:
        raise ValueError("Runexx 10Eros v1.4 path does not accept Sulphur")

    workflow["257"] = {
        "class_type": "UNETLoader",
        "inputs": {"unet_name": LTX_T2V_EROS_V14_MODEL, "weight_dtype": "default"},
        "_meta": {"title": "10Eros v1.4 DMD INT8"},
    }
    workflow.pop("191", None)
    workflow.pop("256", None)
    workflow["210"]["inputs"]["model"] = ["800", 0]
    workflow["800"] = {
        "class_type": "LTXICLoRALoaderModelOnly",
        "inputs": {
            "model": ["257", 0],
            "lora_name": LTX_T2V_MSR_LORA,
            "strength_model": 1.0,
        },
        "_meta": {"title": "Licon MSR IC-LoRA test version"},
    }
    output_frames = duration * LTX_VIDEO_FPS + 1
    guide_frames = 41
    raw_total = output_frames + guide_frames
    extended_length = max(9, ((raw_total - 1 + 7) // 8) * 8 + 1)
    workflow["26:39"]["inputs"].update(width=width, height=height, length=extended_length)
    workflow["26:40"]["inputs"].update(frames_number=extended_length, frame_rate=LTX_VIDEO_FPS)
    workflow["802"] = {"class_type": "LoadImage", "inputs": {"image": sheets[0]}}
    workflow["803"] = {"class_type": "LoadImage", "inputs": {"image": sheets[1]}}
    workflow["804"] = {"class_type": "LoadImage", "inputs": {"image": background}}
    workflow["801"] = {
        "class_type": "LiconMSR",
        "inputs": {"width": width * 2, "height": height * 2, "frame_count": str(guide_frames), "1": ["802", 0], "2": ["803", 0], "background": ["804", 0]},
    }
    guide_common = {"vae": ["283", 0], "image": ["801", 0], "frame_idx": 0, "strength": 1.0, "latent_downscale_factor": ["800", 1], "crop": "center", "use_tiled_encode": False, "tile_size": 256, "tile_overlap": 64}
    workflow["807"] = {"class_type": "LTXAddVideoICLoRAGuide", "inputs": {**guide_common, "positive": ["26:46", 0], "negative": ["26:46", 1], "latent": ["26:39", 0]}, "_meta": {"title": "Runexx IC-LoRA Guide First Pass"}}
    workflow["808"] = {"class_type": "LTXVAddGuideMulti", "inputs": {"num_guides": "3", "num_guides.frame_idx_1": 0, "num_guides.strength_1": 0.7, "num_guides.frame_idx_2": 0, "num_guides.strength_2": 0.7, "num_guides.frame_idx_3": 0, "num_guides.strength_3": 0.7, "positive": ["807", 0], "negative": ["807", 1], "vae": ["283", 0], "latent": ["807", 2], "num_guides.image_1": ["802", 0], "num_guides.image_2": ["803", 0], "num_guides.image_3": ["804", 0]}}
    workflow["26:45"]["inputs"]["video_latent"] = ["808", 2]
    workflow["26:49"]["inputs"].update(model=["8", 0], positive=["808", 0], negative=["808", 1])
    workflow["809"] = {"class_type": "LTXVCropGuides", "inputs": {"positive": ["808", 0], "negative": ["808", 1], "latent": ["26:153", 0]}, "_meta": {"title": "Runexx Crop Guides First Pass"}}
    workflow["26:89"]["inputs"]["samples"] = ["809", 2]
    workflow["810"] = {"class_type": "LTXAddVideoICLoRAGuide", "inputs": {**guide_common, "positive": ["809", 0], "negative": ["809", 1], "latent": ["26:89", 0]}, "_meta": {"title": "Runexx IC-LoRA Guide Final Pass"}}
    workflow["811"] = {"class_type": "LTXVAddGuideMulti", "inputs": {"num_guides": "3", "num_guides.frame_idx_1": 0, "num_guides.strength_1": 0.7, "num_guides.frame_idx_2": 1, "num_guides.strength_2": 0.7, "num_guides.frame_idx_3": 2, "num_guides.strength_3": 0.7, "positive": ["810", 0], "negative": ["810", 1], "vae": ["283", 0], "latent": ["810", 2], "num_guides.image_1": ["802", 0], "num_guides.image_2": ["803", 0], "num_guides.image_3": ["804", 0]}}
    workflow["26:88"]["inputs"]["video_latent"] = ["811", 2]
    workflow["26:90"]["inputs"].update(model=["8", 0], positive=["811", 0], negative=["811", 1])
    workflow["26:91"]["inputs"].update(positive=["811", 0], negative=["811", 1], latent=["26:95", 0])
    target_description = str(workflow["28"]["inputs"].get("text", "")).strip()
    identities = "\n".join(f"Reference character {index}: {description}" for index, description in enumerate(descriptions, start=1))
    workflow["28"]["inputs"]["text"] = f"{target_description}\n\n{identities}"


def _patch_ltx_t2v_msr_legacy_workflow(
    workflow: dict[str, Any],
    *,
    params: dict[str, Any],
    duration: int,
    width: int,
    height: int,
) -> None:
    sheets = params.get("character_sheets")
    descriptions = params.get("character_descriptions")
    if not isinstance(sheets, (list, tuple)) or not 2 <= len(sheets) <= 4:
        raise ValueError("MSR requires 2 to 4 ordered character panels")
    if not isinstance(descriptions, (list, tuple)) or len(descriptions) != len(sheets):
        raise ValueError("MSR character panels and descriptions must match")
    sheets = [str(value or "").strip() for value in sheets]
    descriptions = [str(value or "").strip() for value in descriptions]
    if not all(sheets) or not all(descriptions):
        raise ValueError("MSR character panels and descriptions cannot be blank")
    try:
        sulphur_strength = float(params.get("sulphur_strength", 0.5))
    except (TypeError, ValueError) as exc:
        raise ValueError("MSR Sulphur strength must be between 0 and 1") from exc
    if not 0 <= sulphur_strength <= 1:
        raise ValueError("MSR Sulphur strength must be between 0 and 1")

    for node_id in ("195", "196", "270", "274", "5100", "273", "712", "198", "115"):
        workflow.pop(node_id, None)
    frame_count = duration * LTX_VIDEO_FPS + 1
    workflow["26:39"]["inputs"].update(
        width=width,
        height=height,
        length=frame_count,
    )
    workflow["26:40"]["inputs"].update(
        frames_number=frame_count,
        frame_rate=LTX_VIDEO_FPS,
    )
    workflow["800"] = {
        "class_type": "LTXICLoRALoaderModelOnly",
        "inputs": {
            "model": ["127", 0],
            "lora_name": LTX_T2V_MSR_LORA,
            "strength_model": 1.0,
        },
    }
    msr_inputs: dict[str, Any] = {
        "width": width,
        "height": height,
        "frame_count": "41",
    }
    for index, sheet in enumerate(sheets, start=1):
        node_id = str(801 + index)
        workflow[node_id] = {
            "class_type": "LoadImage",
            "inputs": {"image": sheet},
        }
        msr_inputs[str(index)] = [node_id, 0]
    workflow["806"] = {
        "class_type": "EmptyImage",
        "inputs": {
            "width": width,
            "height": height,
            "batch_size": 1,
            "color": 16777215,
        },
    }
    msr_inputs["background"] = ["806", 0]
    workflow["801"] = {"class_type": "LiconMSR", "inputs": msr_inputs}
    workflow["807"] = {
        "class_type": "LTXAddVideoICLoRAGuide",
        "inputs": {
            "positive": ["26:46", 0],
            "negative": ["26:46", 1],
            "vae": ["127", 2],
            "latent": ["26:39", 0],
            "image": ["801", 0],
            "frame_idx": 0,
            "strength": 1.0,
            "latent_downscale_factor": ["800", 1],
            "crop": "center",
            "use_tiled_encode": False,
            "tile_size": 256,
            "tile_overlap": 64,
        },
    }
    model = ["800", 0]
    if sulphur_strength > 0:
        workflow["808"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["800", 0],
                "lora_name": LTX_T2V_SULPHUR_LORA,
                "strength_model": sulphur_strength,
            },
        }
        model = ["808", 0]
    else:
        workflow.pop("808", None)
    workflow["119"]["inputs"]["video_latent"] = ["807", 2]
    workflow["704"]["inputs"].update(
        model=model,
        positive=["807", 0],
        negative=["807", 1],
    )
    workflow["106"]["inputs"].update(
        positive=["807", 0],
        negative=["807", 1],
    )
    target_description = str(workflow["28"]["inputs"].get("text", "")).strip()
    identities = "\n".join(
        f"图{index}：{description}"
        for index, description in enumerate(descriptions, start=1)
    )
    workflow["28"]["inputs"]["text"] = f"{target_description}\n\n{identities}"


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


_MINIMAX_H3_COUNTS = {
    "minimax_h3_t2v": (0, 0),
    "minimax_h3_i2v": (1, 1),
    "minimax_h3_flf2v": (2, 2),
    "minimax_h3_ref2v": (1, 4),
}
_MINIMAX_H3_PRECISION_PRESETS = {
    "preview": "0.26 MP - Preview",
    "small": "0.36 MP - Small",
    "standard": "0.52 MP - SD",
    "hd": "0.65 MP - Balanced",
}
_MINIMAX_H3_FRAME_COUNT_BY_DURATION = {5: 124, 10: 243, 15: 362}


def _minimax_h3_frame_count(params: dict[str, Any]) -> int:
    raw_frames = params.get("frame_count")
    if raw_frames not in (None, ""):
        try:
            frames = int(raw_frames)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid MiniMax H3 frame count") from exc
        if frames in _MINIMAX_H3_FRAME_COUNT_BY_DURATION.values():
            return frames
    raw_duration = params.get("duration")
    try:
        duration = int(str(raw_duration if raw_duration not in (None, "") else 5).removesuffix("s"))
        return _MINIMAX_H3_FRAME_COUNT_BY_DURATION[duration]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid MiniMax H3 duration") from exc


def patch_minimax_h3_workflow(
    workflow: dict[str, Any],
    *,
    task_type: str,
    params: dict[str, Any],
    execution_id: str | None = None,
    **_: Any,
) -> None:
    task_type = str(task_type or "")
    if task_type not in _MINIMAX_H3_COUNTS:
        raise ValueError("invalid MiniMax H3 task type")
    if any(
        params.get(key) not in (None, "", [], ())
        for key in ("model_name", "checkpoint", "timeline_data", "sampler_name", "scheduler", "steps")
    ):
        raise ValueError("MiniMax H3 rejects model, sampler, and timeline overrides")
    if any(
        params.get(key) not in (None, "", [], ())
        for key in ("addon_models", "lora_items", "lora_name", "lora_strength")
    ):
        raise ValueError("MiniMax H3 uses a fixed MiniMax H3 stack and rejects addon overrides")
    for node_id in ["10", "11", "12", "13", *map(str, range(100, 120))]:
        workflow.pop(node_id, None)
    names = [str(params.get(key) or "").strip() for key in ("image", "image2", "image3", "image4")]
    count = sum(bool(name) for name in names)
    minimum, maximum = _MINIMAX_H3_COUNTS[task_type]
    if not minimum <= count <= maximum or any(not names[index] for index in range(count)):
        raise ValueError(f"invalid ordered image count for {task_type}")
    descriptions = params.get("reference_descriptions") or []
    if task_type in {"minimax_h3_i2v", "minimax_h3_flf2v"}:
        aspect_ratio = str(params.get("aspect_ratio") or "source").strip()
        if aspect_ratio != "source":
            raise ValueError("MiniMax H3 image modes require source aspect ratio")
        preset = str(params.get("resolution_preset") or "preview").strip().lower()
        precision = _MINIMAX_H3_PRECISION_PRESETS.get(preset)
        if precision is None:
            raise ValueError("invalid MiniMax H3 resolution preset")
        calculator = workflow.get("41")
        if not isinstance(calculator, dict):
            raise ValueError("MiniMax H3 source resolution calculator is missing")
        calculator["inputs"]["resolution_preset"] = precision
        calculator["inputs"]["scale_from_image"] = True
        workflow["30"]["inputs"]["width"] = ["41", 0]
        workflow["30"]["inputs"]["height"] = ["41", 1]
    guide_inputs = workflow["30"]["inputs"]
    guide_inputs["prompt"] = str(params.get("prompt") or "").strip()
    if task_type != "minimax_h3_ref2v":
        guide_inputs["length"] = _minimax_h3_frame_count(params)
    if task_type == "minimax_h3_ref2v":
        if not isinstance(descriptions, list):
            raise ValueError("reference_descriptions must be an ordered list")
        if descriptions and (len(descriptions) != count or any(not str(item).strip() for item in descriptions)):
            raise ValueError("reference descriptions must match reference images")
        if descriptions:
            prefix = "\n".join(
                f"<Picture {index}>: {str(description).strip()}"
                for index, description in enumerate(descriptions, start=1)
            )
            workflow["30"]["inputs"]["prompt"] = f"{prefix}\n\n{str(params.get('prompt') or '').strip()}"
    elif descriptions:
        raise ValueError("reference descriptions are only supported by ref2v")

    for index in range(1, 5):
        node_id = str(19 + index)
        if index <= count:
            workflow[node_id]["inputs"]["image"] = names[index - 1]
        else:
            workflow.pop(node_id, None)
            guide_inputs.pop(f"ref_images.ref_image_{index - 1}", None)
    safe_execution_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(execution_id or "")).strip("_")
    output_prefix = f"{task_type}_{safe_execution_id}" if safe_execution_id else task_type
    workflow["38"]["inputs"]["filename_prefix"] = output_prefix
    workflow["40"]["inputs"]["filename_prefix"] = f"{output_prefix}_last_frame"


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
    "minimax_h3_t2v": patch_minimax_h3_workflow,
    "minimax_h3_i2v": patch_minimax_h3_workflow,
    "minimax_h3_flf2v": patch_minimax_h3_workflow,
    "minimax_h3_ref2v": patch_minimax_h3_workflow,
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
