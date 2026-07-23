from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.lora_catalog import (
    IMAGE_LORA_MODELS,
    normalize_ltx_video_lora_items,
)
from src.qqcc_ltx_lora_catalog import (
    QQCC_LTX_VIDEO_LORA_DEFAULT_STRENGTHS,
    QQCC_LTX_VIDEO_LORA_MODELS,
)
from src.qqcc_video_lora_catalog import (
    QQCC_VIDEO_LORA_DEFAULT_STRENGTHS,
    QQCC_VIDEO_LORA_MODELS,
    normalize_qqcc_video_lora_items,
)
from src.services.qqcc_demo_media_service import build_qqcc_demo_preview_url
from src.services.qqcc_video_frame_adapter import (
    QQCC_VIDEO_ASPECT_RATIOS,
    QQCC_VIDEO_ASPECT_SOURCE,
    normalize_qqcc_video_aspect_ratio,
)
from src.services.qqcc_video_scene_chain_service import (
    normalize_qqcc_video_scene_links,
    validate_qqcc_video_scene_chain_config,
)

QQCC_LAZY_BOT_CONFIG_KEY = "qqcc_lazy_bot_config:v1"
SCENE_PRESET_VERSION = 1

MAIN_BUTTON_KEYS = (
    "quick_undress",
    "quick_faceswap",
    "photo_edit",
    "ai_draw",
    "ai_filter",
    "video_edit",
    "ai_video",
    "market",
    "main_bot_link",
    "private_bot",
)
MAIN_MENU_BUTTON_ORDER = (
    "quick_faceswap",
    "ai_draw",
    "ai_filter",
    "video_edit",
    "ai_video",
    "market",
    "private_bot",
    "main_bot_link",
)
PHOTO_BUTTON_KEYS = ("masturbation", "random_faceswap")
UNDRESS_METHOD_KEYS = ("legacy", "i2i_draw")
VIDEO_BUTTON_KEYS = (
    "missionary",
    "doggy",
    "blowjob",
    "undress_tongue",
    "closeup_blowjob",
)
VIDEO_RESOLUTION_KEYS = ("512p", "720p", "1024p")
DEFAULT_VIDEO_SCENE_RESOLUTION = "720p"
VIDEO_DURATION_KEYS = ("5s", "8s", "10s")
VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO = "image_to_video"
VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2 = "wan22_video_v2"
VIDEO_SCENE_ENGINE_KEYS = (
    VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
    VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2,
)
VIDEO_SCENE_ENGINES_WITH_LORA = frozenset(VIDEO_SCENE_ENGINE_KEYS)
VIDEO_SCENE_MAX_COUNT = 20
VIDEO_SCENE_MAX_LORA_ITEMS = 5
AI_VIDEO_SCENE_ENGINE_LTX_VIDEO = "ltx_video"
AI_VIDEO_SCENE_ENGINE_KEYS = (AI_VIDEO_SCENE_ENGINE_LTX_VIDEO,)
AI_VIDEO_DURATION_KEYS = (5, 10, 15, 20)
AI_VIDEO_RESOLUTION_KEYS = ("1280x704",)
DEFAULT_AI_VIDEO_SCENE_RESOLUTION = AI_VIDEO_RESOLUTION_KEYS[0]
AI_VIDEO_SCENE_MAX_COUNT = 20
AI_VIDEO_MAX_LORA_ITEMS = 3
VIDEO_SCENE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
DRAW_SCENE_ENGINE_FREE_EDIT = "free_edit"
DRAW_SCENE_ENGINE_FREE_EDIT_V2 = "free_edit_v2"
DRAW_SCENE_ENGINE_FREE_EDIT_V3 = "free_edit_v3"
DRAW_SCENE_ENGINE_KEYS = (
    DRAW_SCENE_ENGINE_FREE_EDIT,
    DRAW_SCENE_ENGINE_FREE_EDIT_V2,
    DRAW_SCENE_ENGINE_FREE_EDIT_V3,
)
DRAW_SCENE_ENGINES_WITH_LORA = frozenset({DRAW_SCENE_ENGINE_FREE_EDIT})
FILTER_SCENE_MAX_COUNT = 20
DEFAULT_SCENE_CREDIT_COSTS = {
    "video": 6,
    "ai_video": 10,
    "draw": 2,
    "filter": 2,
}
PROMPT_KEYS = (
    "undress",
    "i2i_draw_quick_undress",
    "masturbation",
    "face_swap",
    "perfect_video_insert",
    "doggy_style",
    "blowjob",
    "undress_tongue",
    "closeup_blowjob",
)
COPYWRITING_KEYS = (
    "quick_faceswap_start",
    "ai_draw_menu",
    "ai_filter_menu",
    "video_menu",
    "ai_video_menu",
    "ai_draw_scene_start",
    "ai_filter_scene_start",
    "video_scene_start",
    "ai_video_scene_start",
)
COPYWRITING_MAX_LENGTH = 4000
VIDEO_PROMPT_KEYS = (
    "perfect_video_insert",
    "doggy_style",
    "blowjob",
    "undress_tongue",
    "closeup_blowjob",
)


class QqccSceneCreditCostError(ValueError):
    """Raised when an explicitly configured scene price is not a positive integer."""


class QqccSceneResolutionError(ValueError):
    """Raised when an explicitly configured scene resolution is unsupported."""


def _normalize_scene_credit_cost(raw_cost: Any) -> int | None:
    return (
        raw_cost
        if isinstance(raw_cost, int)
        and not isinstance(raw_cost, bool)
        and raw_cost >= 1
        else None
    )


def validate_qqcc_scene_credit_costs(raw_config: Any) -> None:
    if not isinstance(raw_config, dict):
        return
    for section in ("video_scenes", "ai_video_scenes", "draw_scenes", "filter_scenes"):
        raw_scenes = raw_config.get(section)
        if not isinstance(raw_scenes, list):
            continue
        for raw_scene in raw_scenes:
            if not isinstance(raw_scene, dict) or "credit_cost" not in raw_scene:
                continue
            raw_cost = raw_scene.get("credit_cost")
            if raw_cost is None:
                continue
            if _normalize_scene_credit_cost(raw_cost) is None:
                raise QqccSceneCreditCostError(
                    f"{section}.credit_cost must be a positive integer or null"
                )


def validate_qqcc_scene_resolutions(raw_config: Any) -> None:
    if not isinstance(raw_config, dict):
        return
    sections = (
        ("video_scenes", frozenset(VIDEO_RESOLUTION_KEYS)),
        ("ai_video_scenes", frozenset(AI_VIDEO_RESOLUTION_KEYS)),
    )
    for section, allowed in sections:
        raw_scenes = raw_config.get(section)
        if not isinstance(raw_scenes, list):
            continue
        for raw_scene in raw_scenes:
            if not isinstance(raw_scene, dict) or "resolution" not in raw_scene:
                continue
            resolution = raw_scene.get("resolution")
            if not isinstance(resolution, str) or resolution.strip() not in allowed:
                raise QqccSceneResolutionError(
                    f"{section}.resolution must be one of {sorted(allowed)}"
                )
            if (
                section == "video_scenes"
                and resolution.strip() == "1024p"
                and raw_scene.get("duration") == "10s"
            ):
                raise QqccSceneResolutionError(
                    "video_scenes resolution 1024p is incompatible with duration 10s"
                )


DRAW_PROMPT_KEYS = ("undress", "masturbation")

QQCC_SCENE_PRESET_PROMPTS = {
    "undress": "全身广角镜头(full body shot)，确保人物完整的头部和脸部保留在画面中，绝不裁剪头部。给她的衣服脱掉，赤身裸体,露出质感自然的乳房和奶头和乳晕，完全展现她的身体曲线和隐私部位，私处肤色自然且有微微色素沉积，保持面部五官完全一致，不改变动作、身材、脸型、发型、表情和肤色。图中人物的视线要指向镜头中心，不要指向其他方向。",
    "masturbation": "全身广角镜头(full body shot)，确保人物完整的头部和脸部保留在画面中，绝不裁剪头部。让图片中的人物赤身裸体，露出乳房，注意不要太夸张，双腿叉开，对着镜头露出私处，阴道微张，阴毛稀疏不要太长，遍布三角区域，小穴流出一些白色半透明的粘稠体液，私处不要粉色的动漫感，要真实的成年女性私处，稍微偏褐色。自己用手使劲揉捏自己的乳房。头部保持原样，不要改变五官和发型，表情千万不要动，嘴巴不要张开。图中人物的视线要指向镜头中心，不要指向其他方向。",
    "perfect_video_insert": "女人快速脱掉身上所有衣服，清晰的露出奶子和阴部，浑身赤裸，女子快速躺下，双腿分开，女人始终看向镜头；一名男子从下方探入。他握着勃起的阴茎，缓缓插入她阴道。",
    "doggy_style": "女人快速脱掉身上所有衣服，清晰的露出奶子和阴部，浑身赤裸，她朝向右侧趴下，翘起屁股，四肢趴地，始终看着镜头。左侧出现一名裸体男子，他握着勃起的阴茎，随后阴茎缓缓插入女子的阴道（侧视图）。",
    "blowjob": "图中的人往下扒衣服，漏出乳房，注意不要太夸张。一个黑人从左边漏出阴茎，图中的人用手握住他的阴茎，同时用嘴进行口交。注意脸部不要有变化",
    "undress_tongue": "女人往下扒衣服，漏出胸脯和奶头，妖娆的吐出舌头，口水滴下，并且开始翻白眼，阿颜黑",
    "closeup_blowjob": "0-1秒：女性直视镜头，往下扒衣服，漏出乳房，注意不要太夸张；1-2秒：突然脱光衣服，一丝不挂，张大嘴巴，伸出舌头；2-3秒：POV高角度拍摄，双手紧紧抓住她的脸颊，强迫她口交；3-4秒：一根粗硬的阴茎快速而猛烈地在她口中抽插，喷射出液体，节奏疯狂，镜头随着口交的特写镜头而晃动；4-5秒：女性忍不住痛苦嘔吐出來。",
}

DRAW_SCENE_PRESET_PROMPT_KEYS_BY_ID = {
    "quick_masturbation": "masturbation",
    "quick_undress": "undress",
}

LEGACY_VIDEO_SCENE_DEFINITIONS = (
    {
        "id": "missionary",
        "name": "🛌 动图传教士",
        "button_key": "missionary",
        "prompt_key": "perfect_video_insert",
    },
    {
        "id": "doggy",
        "name": "🎬 动图后入",
        "button_key": "doggy",
        "prompt_key": "doggy_style",
    },
    {
        "id": "blowjob",
        "name": "🎬 口交黑人",
        "button_key": "blowjob",
        "prompt_key": "blowjob",
    },
    {
        "id": "undress_tongue",
        "name": "🎬 脱衣吐舌",
        "button_key": "undress_tongue",
        "prompt_key": "undress_tongue",
    },
    {
        "id": "closeup_blowjob",
        "name": "🎬 特写口交",
        "button_key": "closeup_blowjob",
        "prompt_key": "closeup_blowjob",
    },
)

VIDEO_SCENE_PRESET_PROMPT_KEYS_BY_ID = {
    scene["id"]: scene["prompt_key"] for scene in LEGACY_VIDEO_SCENE_DEFINITIONS
}


def _preset_prompt(prompt_key: str, raw_prompts: dict[str, Any] | None = None) -> str:
    if raw_prompts:
        prompt = raw_prompts.get(prompt_key)
        if isinstance(prompt, str) and prompt.strip():
            return prompt.strip()
    return QQCC_SCENE_PRESET_PROMPTS[prompt_key]


def _default_video_scenes(
    raw_prompts: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return [
        {
            "id": scene["id"],
            "name": scene["name"],
            "prompt": _preset_prompt(scene["prompt_key"], raw_prompts),
            "negative_prompt": "",
            "duration": "5s",
            "resolution": DEFAULT_VIDEO_SCENE_RESOLUTION,
            "aspect_ratio": QQCC_VIDEO_ASPECT_SOURCE,
            "engine": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
            "lora_name": "",
            "lora_strength": 1.0,
            "lora_items": [],
            "end_frame_draw_scene_id": "",
            "credit_cost": None,
            "next_scene_id": None,
        }
        for scene in LEGACY_VIDEO_SCENE_DEFINITIONS
    ]


def _default_draw_scenes(
    raw_prompts: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return [
        {
            "id": "quick_masturbation",
            "name": "快速自慰",
            "prompt": _preset_prompt("masturbation", raw_prompts),
            "negative_prompt": "",
            "engine": DRAW_SCENE_ENGINE_FREE_EDIT,
            "lora_name": "",
            "postprocess_draw_scene_id": "",
            "postprocess_filter_scene_id": "",
            "original_face_swap_enabled": False,
            "credit_cost": None,
        },
        {
            "id": "quick_undress",
            "name": "快速脱衣",
            "prompt": _preset_prompt("undress", raw_prompts),
            "negative_prompt": "",
            "engine": DRAW_SCENE_ENGINE_FREE_EDIT,
            "lora_name": "",
            "postprocess_draw_scene_id": "",
            "postprocess_filter_scene_id": "",
            "original_face_swap_enabled": False,
            "credit_cost": None,
        },
    ]


DEFAULT_QQCC_LAZY_BOT_CONFIG: dict[str, Any] = {
    "scene_preset_version": SCENE_PRESET_VERSION,
    "global_enabled": True,
    "main_buttons": {
        "quick_undress": False,
        "quick_faceswap": True,
        "photo_edit": False,
        "ai_draw": True,
        "ai_filter": True,
        "video_edit": True,
        "ai_video": True,
        "market": True,
        "main_bot_link": True,
        "private_bot": True,
    },
    "main_menu_layout": {
        "buttons_per_row": None,
        "button_order": list(MAIN_MENU_BUTTON_ORDER),
    },
    "photo_buttons": {
        "masturbation": True,
        "random_faceswap": True,
    },
    "undress_methods": {
        "legacy": True,
        "i2i_draw": True,
    },
    "video_buttons": {
        "missionary": True,
        "doggy": True,
        "blowjob": True,
        "undress_tongue": True,
        "closeup_blowjob": True,
    },
    "video_settings": {
        "resolutions": {
            "512p": True,
            "720p": True,
            "1024p": True,
        },
        "durations": {
            "5s": True,
            "8s": True,
            "10s": True,
        },
    },
    "video_scenes": _default_video_scenes(),
    "ai_video_scenes": [],
    "draw_scenes": _default_draw_scenes(),
    "filter_scenes": [],
    "prompts": {
        "undress": "",
        "i2i_draw_quick_undress": "",
        "masturbation": "",
        "face_swap": "",
        "perfect_video_insert": "",
        "doggy_style": "",
        "blowjob": "",
        "undress_tongue": "",
        "closeup_blowjob": "",
    },
    "copywriting": {
        "quick_faceswap_start": "",
        "ai_draw_menu": "",
        "ai_filter_menu": "",
        "video_menu": "",
        "ai_video_menu": "",
        "ai_draw_scene_start": "",
        "ai_filter_scene_start": "",
        "video_scene_start": "",
        "ai_video_scene_start": "",
    },
}


def _normalize_bool_section(
    raw: Any,
    *,
    default: dict[str, bool],
    keys: tuple[str, ...],
) -> dict[str, bool]:
    if not isinstance(raw, dict):
        raw = {}
    normalized: dict[str, bool] = {}
    for key in keys:
        value = raw.get(key, default[key])
        normalized[key] = value if isinstance(value, bool) else default[key]
    return normalized


def _normalize_main_menu_layout(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}

    raw_buttons_per_row = raw.get("buttons_per_row")
    buttons_per_row = (
        raw_buttons_per_row
        if (
            isinstance(raw_buttons_per_row, int)
            and not isinstance(raw_buttons_per_row, bool)
            and 1 <= raw_buttons_per_row <= 4
        )
        else None
    )

    button_order: list[str] = []
    raw_button_order = raw.get("button_order")
    if isinstance(raw_button_order, list):
        for key in raw_button_order:
            if (
                isinstance(key, str)
                and key in MAIN_MENU_BUTTON_ORDER
                and key not in button_order
            ):
                button_order.append(key)
    button_order.extend(
        key for key in MAIN_MENU_BUTTON_ORDER if key not in button_order
    )
    return {
        "buttons_per_row": buttons_per_row,
        "button_order": button_order,
    }


def _build_unique_scene_id(
    raw_id: Any,
    *,
    index: int,
    used_ids: set[str],
) -> str:
    scene_id = raw_id.strip() if isinstance(raw_id, str) else ""
    if not VIDEO_SCENE_ID_PATTERN.fullmatch(scene_id) or scene_id in used_ids:
        base_id = f"scene_{index + 1}"
        scene_id = base_id
        suffix = 2
        while scene_id in used_ids:
            scene_id = f"{base_id}_{suffix}"
            suffix += 1
    used_ids.add(scene_id)
    return scene_id


def _normalize_scene_prompt_key(raw_prompt_key: Any) -> str | None:
    if not isinstance(raw_prompt_key, str):
        return None
    prompt_key = raw_prompt_key.strip()
    return prompt_key if prompt_key in VIDEO_PROMPT_KEYS else None


def _normalize_draw_scene_prompt_key(raw_prompt_key: Any) -> str | None:
    if not isinstance(raw_prompt_key, str):
        return None
    prompt_key = raw_prompt_key.strip()
    return prompt_key if prompt_key in DRAW_PROMPT_KEYS else None


def _normalize_scene_preset_version(raw_version: Any) -> int:
    return (
        raw_version
        if (
            isinstance(raw_version, int)
            and not isinstance(raw_version, bool)
            and raw_version >= 1
        )
        else 0
    )


def _get_legacy_prompt_override(
    raw_prompts: dict[str, Any],
    prompt_key: str | None,
) -> str:
    if not prompt_key:
        return ""
    return _preset_prompt(prompt_key, raw_prompts)


def _merge_seeded_scene_presets(
    *,
    scenes: list[dict[str, Any]],
    preset_scenes: list[dict[str, Any]],
    max_count: int | None,
) -> list[dict[str, Any]]:
    scenes_by_id = {str(scene.get("id") or ""): scene for scene in scenes}
    merged_scenes: list[dict[str, Any]] = []
    included_ids: set[str] = set()
    for preset_scene in preset_scenes:
        scene_id = preset_scene["id"]
        raw_scene = scenes_by_id.get(scene_id)
        if raw_scene is None:
            scene = deepcopy(preset_scene)
        else:
            scene = deepcopy(preset_scene)
            scene.update(raw_scene)
            scene["id"] = scene_id
            if not str(scene.get("name") or "").strip():
                scene["name"] = preset_scene["name"]
            if not str(scene.get("prompt") or "").strip():
                scene["prompt"] = preset_scene["prompt"]
        merged_scenes.append(scene)
        included_ids.add(scene_id)

    for scene in scenes:
        scene_id = str(scene.get("id") or "")
        if scene_id in included_ids:
            continue
        if max_count is not None and len(merged_scenes) >= max_count:
            break
        merged_scenes.append(scene)
        included_ids.add(scene_id)
    return merged_scenes


def _normalize_scene_engine(
    raw_engine: Any,
    *,
    allowed: tuple[str, ...],
    default: str,
) -> str:
    engine = raw_engine.strip() if isinstance(raw_engine, str) else ""
    return engine if engine in allowed else default


def _normalize_scene_lora(
    raw_lora_name: Any,
    *,
    engine: str,
    lora_catalog: dict[str, str],
    engines_with_lora: frozenset[str],
) -> str:
    if engine not in engines_with_lora:
        return ""
    lora_name = raw_lora_name.strip() if isinstance(raw_lora_name, str) else ""
    return lora_name if lora_name in lora_catalog else ""


def _normalize_scene_negative_prompt(raw_negative_prompt: Any) -> str:
    return raw_negative_prompt.strip() if isinstance(raw_negative_prompt, str) else ""


def _normalize_scene_demo_media(
    raw_media: Any,
    *,
    scene_kind: str,
    scene_id: str,
    slot: str,
    media_type: str,
) -> dict[str, Any] | None:
    if not isinstance(raw_media, dict):
        return None
    expected_object_key = f"qqcc/demo/{scene_kind}/{scene_id}/{slot}"
    private_object_key_pattern = re.compile(
        rf"^qqcc/private/[1-9][0-9]*/demo/{re.escape(scene_kind)}/"
        rf"{re.escape(scene_id)}/{re.escape(slot)}$"
    )
    generated_object_key_pattern = re.compile(
        rf"^(?:qqcc/demo|qqcc/private/[1-9][0-9]*/demo)/{re.escape(scene_kind)}/"
        rf"{re.escape(scene_id)}/generated/[A-Za-z0-9][A-Za-z0-9_-]{{0,127}}/"
        rf"{re.escape(slot)}$"
    )
    object_key = str(raw_media.get("object_key") or "").strip()
    normalized_media_type = str(raw_media.get("media_type") or "").strip()
    mime_type = str(raw_media.get("mime_type") or "").strip().lower()
    allowed_mime_types = (
        {"image/jpeg", "image/png"} if media_type == "image" else {"video/mp4"}
    )
    if (
        (
            object_key != expected_object_key
            and private_object_key_pattern.fullmatch(object_key) is None
            and generated_object_key_pattern.fullmatch(object_key) is None
        )
        or normalized_media_type != media_type
        or mime_type not in allowed_mime_types
    ):
        return None

    file_name = str(raw_media.get("file_name") or "").strip()[:255]
    content_sha256 = str(raw_media.get("content_sha256") or "").strip().lower()
    raw_file_ids = raw_media.get("telegram_file_ids")
    telegram_file_ids: dict[str, str] = {}
    if isinstance(raw_file_ids, dict):
        for raw_bot_id, raw_file_id in raw_file_ids.items():
            bot_id = str(raw_bot_id).strip()
            file_id = str(raw_file_id).strip() if isinstance(raw_file_id, str) else ""
            if bot_id.isdigit() and file_id:
                telegram_file_ids[bot_id] = file_id[:512]
            if len(telegram_file_ids) >= 4:
                break

    media = {
        "object_key": object_key,
        "media_type": media_type,
        "mime_type": mime_type,
        "file_name": file_name,
        "telegram_file_ids": telegram_file_ids,
    }
    if re.fullmatch(r"[0-9a-f]{64}", content_sha256):
        media["content_sha256"] = content_sha256
    return media


def _attach_scene_demo_media(
    scene: dict[str, Any],
    raw_scene: dict[str, Any],
    *,
    scene_kind: str,
    output_media_type: str,
) -> None:
    scene_id = str(scene["id"])
    for slot, media_type in (("input", "image"), ("output", output_media_type)):
        field = f"demo_{slot}_media"
        media = _normalize_scene_demo_media(
            raw_scene.get(field),
            scene_kind=scene_kind,
            scene_id=scene_id,
            slot=slot,
            media_type=media_type,
        )
        if media is not None:
            scene[field] = media


def _normalize_end_frame_draw_scene_id(
    raw_scene_id: Any,
    *,
    allowed_draw_scene_ids: frozenset[str],
) -> str:
    scene_id = raw_scene_id.strip() if isinstance(raw_scene_id, str) else ""
    return scene_id if scene_id in allowed_draw_scene_ids else ""


def _normalize_video_scene(
    raw_scene: Any,
    *,
    index: int,
    used_ids: set[str],
    allowed_end_frame_draw_scene_ids: frozenset[str],
    raw_prompts: dict[str, Any],
    migrate_legacy_prompt_keys: bool,
) -> dict[str, Any] | None:
    if not isinstance(raw_scene, dict):
        return None

    name = raw_scene.get("name")
    name = name.strip() if isinstance(name, str) else ""
    if not name:
        return None

    prompt = raw_scene.get("prompt")
    prompt = prompt.strip() if isinstance(prompt, str) else ""
    prompt_key = _normalize_scene_prompt_key(raw_scene.get("prompt_key"))
    if not prompt and migrate_legacy_prompt_keys:
        scene_id = raw_scene.get("id")
        scene_id = scene_id.strip() if isinstance(scene_id, str) else ""
        prompt = _get_legacy_prompt_override(
            raw_prompts,
            prompt_key or VIDEO_SCENE_PRESET_PROMPT_KEYS_BY_ID.get(scene_id),
        )
    if not prompt:
        return None

    duration = raw_scene.get("duration")
    duration = duration.strip() if isinstance(duration, str) else ""
    if duration not in VIDEO_DURATION_KEYS:
        duration = "5s"

    engine = _normalize_scene_engine(
        raw_scene.get("engine"),
        allowed=VIDEO_SCENE_ENGINE_KEYS,
        default=VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
    )
    lora_items = normalize_qqcc_video_lora_items(
        raw_scene.get("lora_items"),
        legacy_name=raw_scene.get("lora_name"),
        legacy_strength=raw_scene.get("lora_strength"),
        max_items=VIDEO_SCENE_MAX_LORA_ITEMS,
    )
    first_lora = lora_items[0] if lora_items else None

    scene = {
        "id": _build_unique_scene_id(
            raw_scene.get("id"),
            index=index,
            used_ids=used_ids,
        ),
        "name": name,
        "prompt": prompt,
        "negative_prompt": _normalize_scene_negative_prompt(
            raw_scene.get("negative_prompt")
        ),
        "duration": duration,
        "resolution": (
            raw_scene.get("resolution").strip()
            if isinstance(raw_scene.get("resolution"), str)
            and raw_scene.get("resolution").strip() in VIDEO_RESOLUTION_KEYS
            else DEFAULT_VIDEO_SCENE_RESOLUTION
        ),
        "aspect_ratio": normalize_qqcc_video_aspect_ratio(
            raw_scene.get("aspect_ratio")
        ),
        "engine": engine,
        "lora_name": first_lora["name"] if first_lora else "",
        "lora_strength": first_lora["strength"] if first_lora else 1.0,
        "lora_items": lora_items,
        "credit_cost": _normalize_scene_credit_cost(raw_scene.get("credit_cost")),
        "end_frame_draw_scene_id": _normalize_end_frame_draw_scene_id(
            raw_scene.get("end_frame_draw_scene_id"),
            allowed_draw_scene_ids=allowed_end_frame_draw_scene_ids,
        ),
        "next_scene_id": (
            str(raw_scene.get("next_scene_id")).strip()
            if isinstance(raw_scene.get("next_scene_id"), str)
            and str(raw_scene.get("next_scene_id")).strip()
            else None
        ),
    }
    _attach_scene_demo_media(
        scene,
        raw_scene,
        scene_kind="video",
        output_media_type="video",
    )
    return scene


def _normalize_video_scenes(
    raw_scenes: Any,
    *,
    allowed_end_frame_draw_scene_ids: frozenset[str],
    raw_prompts: dict[str, Any],
    seed_presets: bool,
) -> list[dict[str, Any]]:
    if not isinstance(raw_scenes, list):
        return []
    scenes: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for index, raw_scene in enumerate(raw_scenes):
        scene = _normalize_video_scene(
            raw_scene,
            index=index,
            used_ids=used_ids,
            allowed_end_frame_draw_scene_ids=allowed_end_frame_draw_scene_ids,
            raw_prompts=raw_prompts,
            migrate_legacy_prompt_keys=seed_presets,
        )
        if scene is not None:
            scenes.append(scene)
    if seed_presets:
        scenes = _merge_seeded_scene_presets(
            scenes=scenes,
            preset_scenes=_default_video_scenes(raw_prompts),
            max_count=None,
        )
    return scenes


def _normalize_ai_video_scene(
    raw_scene: Any,
    *,
    index: int,
    used_ids: set[str],
    allowed_end_frame_draw_scene_ids: frozenset[str],
) -> dict[str, Any] | None:
    if not isinstance(raw_scene, dict):
        return None

    name = raw_scene.get("name")
    name = name.strip() if isinstance(name, str) else ""
    prompt = raw_scene.get("prompt")
    prompt = prompt.strip() if isinstance(prompt, str) else ""
    if not name or not prompt:
        return None

    raw_duration = raw_scene.get("duration")
    try:
        duration = int(str(raw_duration).strip().removesuffix("s"))
    except (TypeError, ValueError):
        duration = AI_VIDEO_DURATION_KEYS[0]
    if duration not in AI_VIDEO_DURATION_KEYS:
        duration = AI_VIDEO_DURATION_KEYS[0]

    raw_lora_items = raw_scene.get("lora_items")
    allowed_lora_items = [
        {
            "name": item.get("path"),
            "strength": item.get("strength")
            if item.get("strength") is not None
            else QQCC_LTX_VIDEO_LORA_DEFAULT_STRENGTHS.get(item.get("path"), 1.0),
        }
        for item in (raw_lora_items if isinstance(raw_lora_items, list) else [])
        if isinstance(item, dict)
        and isinstance(item.get("path"), str)
        and item.get("path") in QQCC_LTX_VIDEO_LORA_MODELS
        and item.get("path")
    ]
    normalized_lora_items = normalize_ltx_video_lora_items(
        allowed_lora_items,
        max_items=AI_VIDEO_MAX_LORA_ITEMS,
    )
    lora_items = [
        {"path": item["name"], "strength": item["strength"]}
        for item in normalized_lora_items
    ]

    scene = {
        "id": _build_unique_scene_id(
            raw_scene.get("id"),
            index=index,
            used_ids=used_ids,
        ),
        "name": name,
        "prompt": prompt,
        "negative_prompt": _normalize_scene_negative_prompt(
            raw_scene.get("negative_prompt")
        ),
        "duration": duration,
        "resolution": (
            raw_scene.get("resolution").strip()
            if isinstance(raw_scene.get("resolution"), str)
            and raw_scene.get("resolution").strip() in AI_VIDEO_RESOLUTION_KEYS
            else DEFAULT_AI_VIDEO_SCENE_RESOLUTION
        ),
        "engine": AI_VIDEO_SCENE_ENGINE_LTX_VIDEO,
        "lora_items": lora_items,
        "credit_cost": _normalize_scene_credit_cost(raw_scene.get("credit_cost")),
        "end_frame_draw_scene_id": _normalize_end_frame_draw_scene_id(
            raw_scene.get("end_frame_draw_scene_id"),
            allowed_draw_scene_ids=allowed_end_frame_draw_scene_ids,
        ),
        "next_scene_id": (
            str(raw_scene.get("next_scene_id")).strip()
            if isinstance(raw_scene.get("next_scene_id"), str)
            and str(raw_scene.get("next_scene_id")).strip()
            else None
        ),
    }
    _attach_scene_demo_media(
        scene,
        raw_scene,
        scene_kind="ai_video",
        output_media_type="video",
    )
    return scene


def _normalize_ai_video_scenes(
    raw_scenes: Any,
    *,
    allowed_end_frame_draw_scene_ids: frozenset[str],
) -> list[dict[str, Any]]:
    if not isinstance(raw_scenes, list):
        return []
    scenes: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for index, raw_scene in enumerate(raw_scenes):
        scene = _normalize_ai_video_scene(
            raw_scene,
            index=index,
            used_ids=used_ids,
            allowed_end_frame_draw_scene_ids=allowed_end_frame_draw_scene_ids,
        )
        if scene is not None:
            scenes.append(scene)
    return scenes


def _normalize_draw_scene(
    raw_scene: Any,
    *,
    index: int,
    used_ids: set[str],
    raw_prompts: dict[str, Any],
    migrate_legacy_prompt_keys: bool,
) -> dict[str, Any] | None:
    if not isinstance(raw_scene, dict):
        return None

    name = raw_scene.get("name")
    name = name.strip() if isinstance(name, str) else ""
    prompt = raw_scene.get("prompt")
    prompt = prompt.strip() if isinstance(prompt, str) else ""
    prompt_key = _normalize_draw_scene_prompt_key(raw_scene.get("prompt_key"))
    if not prompt and migrate_legacy_prompt_keys:
        scene_id = raw_scene.get("id")
        scene_id = scene_id.strip() if isinstance(scene_id, str) else ""
        prompt = _get_legacy_prompt_override(
            raw_prompts,
            prompt_key or DRAW_SCENE_PRESET_PROMPT_KEYS_BY_ID.get(scene_id),
        )
    if not name or not prompt:
        return None

    engine = _normalize_scene_engine(
        raw_scene.get("engine"),
        allowed=DRAW_SCENE_ENGINE_KEYS,
        default=DRAW_SCENE_ENGINE_FREE_EDIT_V2,
    )
    lora_name = _normalize_scene_lora(
        raw_scene.get("lora_name"),
        engine=engine,
        lora_catalog=IMAGE_LORA_MODELS,
        engines_with_lora=DRAW_SCENE_ENGINES_WITH_LORA,
    )

    postprocess_draw_scene_id = raw_scene.get("postprocess_draw_scene_id")
    postprocess_draw_scene_id = (
        postprocess_draw_scene_id.strip()
        if isinstance(postprocess_draw_scene_id, str)
        else ""
    )
    postprocess_filter_scene_id = raw_scene.get("postprocess_filter_scene_id")
    postprocess_filter_scene_id = (
        postprocess_filter_scene_id.strip()
        if isinstance(postprocess_filter_scene_id, str)
        else ""
    )

    scene = {
        "id": _build_unique_scene_id(
            raw_scene.get("id"),
            index=index,
            used_ids=used_ids,
        ),
        "name": name,
        "prompt": prompt,
        "negative_prompt": _normalize_scene_negative_prompt(
            raw_scene.get("negative_prompt")
        ),
        "engine": engine,
        "lora_name": lora_name,
        "postprocess_draw_scene_id": postprocess_draw_scene_id,
        "postprocess_filter_scene_id": postprocess_filter_scene_id,
        "original_face_swap_enabled": raw_scene.get("original_face_swap_enabled")
        is True,
        "credit_cost": _normalize_scene_credit_cost(raw_scene.get("credit_cost")),
    }
    _attach_scene_demo_media(
        scene,
        raw_scene,
        scene_kind="draw",
        output_media_type="image",
    )
    return scene


def _normalize_filter_scene(
    raw_scene: Any,
    *,
    index: int,
    used_ids: set[str],
) -> dict[str, Any] | None:
    if not isinstance(raw_scene, dict):
        return None

    name = raw_scene.get("name")
    name = name.strip() if isinstance(name, str) else ""
    prompt = raw_scene.get("prompt")
    prompt = prompt.strip() if isinstance(prompt, str) else ""
    if not name or not prompt:
        return None

    engine = _normalize_scene_engine(
        raw_scene.get("engine"),
        allowed=DRAW_SCENE_ENGINE_KEYS,
        default=DRAW_SCENE_ENGINE_FREE_EDIT_V2,
    )
    lora_name = _normalize_scene_lora(
        raw_scene.get("lora_name"),
        engine=engine,
        lora_catalog=IMAGE_LORA_MODELS,
        engines_with_lora=DRAW_SCENE_ENGINES_WITH_LORA,
    )

    scene = {
        "id": _build_unique_scene_id(
            raw_scene.get("id"),
            index=index,
            used_ids=used_ids,
        ),
        "name": name,
        "prompt": prompt,
        "negative_prompt": _normalize_scene_negative_prompt(
            raw_scene.get("negative_prompt")
        ),
        "engine": engine,
        "lora_name": lora_name,
        "original_face_swap_enabled": raw_scene.get("original_face_swap_enabled")
        is True,
        "credit_cost": _normalize_scene_credit_cost(raw_scene.get("credit_cost")),
    }
    _attach_scene_demo_media(
        scene,
        raw_scene,
        scene_kind="filter",
        output_media_type="image",
    )
    return scene


def _normalize_filter_scenes(raw_scenes: Any) -> list[dict[str, Any]]:
    raw_scene_list = raw_scenes if isinstance(raw_scenes, list) else []
    scenes: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for index, raw_scene in enumerate(raw_scene_list[:FILTER_SCENE_MAX_COUNT]):
        scene = _normalize_filter_scene(
            raw_scene,
            index=index,
            used_ids=used_ids,
        )
        if scene is not None:
            scenes.append(scene)
    return scenes


def _normalize_draw_scene_postprocess_refs(
    scenes: list[dict[str, Any]],
    *,
    allowed_filter_scene_ids: frozenset[str],
) -> None:
    allowed_scene_ids = frozenset(str(scene.get("id") or "") for scene in scenes)
    scenes_by_id = {str(scene.get("id") or ""): scene for scene in scenes}
    for scene in scenes:
        scene_id = str(scene.get("id") or "")
        ref_id = str(scene.get("postprocess_draw_scene_id") or "").strip()
        if ref_id == scene_id or ref_id not in allowed_scene_ids:
            scene["postprocess_draw_scene_id"] = ""
        else:
            scene["postprocess_draw_scene_id"] = ref_id
            scene["postprocess_filter_scene_id"] = ""
            continue

        filter_ref_id = str(scene.get("postprocess_filter_scene_id") or "").strip()
        scene["postprocess_filter_scene_id"] = (
            filter_ref_id if filter_ref_id in allowed_filter_scene_ids else ""
        )

    cycle_scene_ids: set[str] = set()
    for scene in scenes:
        path: list[str] = []
        seen_at: dict[str, int] = {}
        current_id = str(scene.get("id") or "")
        while current_id:
            if current_id in seen_at:
                cycle_scene_ids.update(path[seen_at[current_id] :])
                break
            current_scene = scenes_by_id.get(current_id)
            if current_scene is None:
                break
            seen_at[current_id] = len(path)
            path.append(current_id)
            current_id = str(current_scene.get("postprocess_draw_scene_id") or "")

    for scene_id in cycle_scene_ids:
        scenes_by_id[scene_id]["postprocess_draw_scene_id"] = ""


def _normalize_draw_scenes(
    raw_scenes: Any,
    *,
    raw_prompts: dict[str, Any],
    seed_presets: bool,
    allowed_filter_scene_ids: frozenset[str],
) -> list[dict[str, Any]]:
    raw_scene_list = raw_scenes if isinstance(raw_scenes, list) else []
    normalized_raw_scenes: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for index, raw_scene in enumerate(raw_scene_list):
        scene = _normalize_draw_scene(
            raw_scene,
            index=index,
            used_ids=used_ids,
            raw_prompts=raw_prompts,
            migrate_legacy_prompt_keys=seed_presets,
        )
        if scene is not None:
            normalized_raw_scenes.append(scene)
    scenes = (
        _merge_seeded_scene_presets(
            scenes=normalized_raw_scenes,
            preset_scenes=_default_draw_scenes(raw_prompts),
            max_count=None,
        )
        if seed_presets
        else normalized_raw_scenes
    )

    _normalize_draw_scene_postprocess_refs(
        scenes,
        allowed_filter_scene_ids=allowed_filter_scene_ids,
    )
    return scenes


def _migrate_legacy_video_scenes(raw: dict[str, Any]) -> list[dict[str, Any]]:
    raw_buttons = raw.get("video_buttons")
    if not isinstance(raw_buttons, dict):
        raw_buttons = {}
    raw_prompts = raw.get("prompts")
    if not isinstance(raw_prompts, dict):
        raw_prompts = {}

    scenes = []
    for scene in LEGACY_VIDEO_SCENE_DEFINITIONS:
        button_key = scene["button_key"]
        enabled = raw_buttons.get(button_key, True)
        if enabled is not True:
            continue
        prompt_key = scene["prompt_key"]
        prompt = raw_prompts.get(prompt_key)
        prompt = (
            prompt.strip()
            if isinstance(prompt, str) and prompt.strip()
            else _preset_prompt(prompt_key)
        )
        scenes.append(
            {
                "id": scene["id"],
                "name": scene["name"],
                "prompt": prompt,
                "negative_prompt": "",
                "duration": "5s",
                "resolution": DEFAULT_VIDEO_SCENE_RESOLUTION,
                "aspect_ratio": QQCC_VIDEO_ASPECT_SOURCE,
                "engine": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
                "lora_name": "",
                "lora_strength": 1.0,
                "lora_items": [],
                "end_frame_draw_scene_id": "",
                "credit_cost": None,
                "next_scene_id": None,
            }
        )
    return scenes


def normalize_qqcc_config(raw: Any | None) -> dict[str, Any]:
    """Return the effective QQCC config with unknown keys removed."""

    defaults = deepcopy(DEFAULT_QQCC_LAZY_BOT_CONFIG)
    if not isinstance(raw, dict):
        return defaults

    config = deepcopy(defaults)
    raw_scene_preset_version = _normalize_scene_preset_version(
        raw.get("scene_preset_version")
    )
    seed_scene_presets = raw_scene_preset_version < SCENE_PRESET_VERSION
    config["scene_preset_version"] = SCENE_PRESET_VERSION

    raw_prompts = raw.get("prompts")
    if not isinstance(raw_prompts, dict):
        raw_prompts = {}
    raw_copywriting = raw.get("copywriting")
    if not isinstance(raw_copywriting, dict):
        raw_copywriting = {}

    global_enabled = raw.get("global_enabled", defaults["global_enabled"])
    config["global_enabled"] = (
        global_enabled
        if isinstance(global_enabled, bool)
        else defaults["global_enabled"]
    )
    config["main_buttons"] = _normalize_bool_section(
        raw.get("main_buttons"),
        default=defaults["main_buttons"],
        keys=MAIN_BUTTON_KEYS,
    )
    config["main_menu_layout"] = _normalize_main_menu_layout(
        raw.get("main_menu_layout")
    )
    config["photo_buttons"] = _normalize_bool_section(
        raw.get("photo_buttons"),
        default=defaults["photo_buttons"],
        keys=PHOTO_BUTTON_KEYS,
    )
    config["undress_methods"] = _normalize_bool_section(
        raw.get("undress_methods"),
        default=defaults["undress_methods"],
        keys=UNDRESS_METHOD_KEYS,
    )
    config["video_buttons"] = _normalize_bool_section(
        raw.get("video_buttons"),
        default=defaults["video_buttons"],
        keys=VIDEO_BUTTON_KEYS,
    )

    raw_video_settings = raw.get("video_settings")
    if not isinstance(raw_video_settings, dict):
        raw_video_settings = {}
    config["video_settings"] = {
        "resolutions": _normalize_bool_section(
            raw_video_settings.get("resolutions"),
            default=defaults["video_settings"]["resolutions"],
            keys=VIDEO_RESOLUTION_KEYS,
        ),
        "durations": _normalize_bool_section(
            raw_video_settings.get("durations"),
            default=defaults["video_settings"]["durations"],
            keys=VIDEO_DURATION_KEYS,
        ),
    }
    config["filter_scenes"] = _normalize_filter_scenes(raw.get("filter_scenes"))
    allowed_filter_scene_ids = frozenset(
        str(scene.get("id") or "") for scene in config["filter_scenes"]
    )
    if "draw_scenes" in raw:
        config["draw_scenes"] = _normalize_draw_scenes(
            raw.get("draw_scenes"),
            raw_prompts=raw_prompts,
            seed_presets=seed_scene_presets,
            allowed_filter_scene_ids=allowed_filter_scene_ids,
        )
    elif seed_scene_presets:
        config["draw_scenes"] = _default_draw_scenes(raw_prompts)
    elif not seed_scene_presets:
        config["draw_scenes"] = []
    _normalize_draw_scene_postprocess_refs(
        config["draw_scenes"],
        allowed_filter_scene_ids=allowed_filter_scene_ids,
    )
    allowed_end_frame_draw_scene_ids = frozenset(
        str(scene.get("id") or "") for scene in config["draw_scenes"]
    )
    if "video_scenes" in raw:
        config["video_scenes"] = _normalize_video_scenes(
            raw.get("video_scenes"),
            allowed_end_frame_draw_scene_ids=allowed_end_frame_draw_scene_ids,
            raw_prompts=raw_prompts,
            seed_presets=seed_scene_presets,
        )
    elif seed_scene_presets:
        config["video_scenes"] = _migrate_legacy_video_scenes(raw)
    else:
        config["video_scenes"] = []
    config["ai_video_scenes"] = _normalize_ai_video_scenes(
        raw.get("ai_video_scenes"),
        allowed_end_frame_draw_scene_ids=allowed_end_frame_draw_scene_ids,
    )
    normalize_qqcc_video_scene_links(config["video_scenes"])
    normalize_qqcc_video_scene_links(config["ai_video_scenes"])

    config["prompts"] = {
        key: raw_prompts[key].strip() if isinstance(raw_prompts.get(key), str) else ""
        for key in PROMPT_KEYS
    }
    config["copywriting"] = {
        key: raw_copywriting[key].strip()[:COPYWRITING_MAX_LENGTH]
        if isinstance(raw_copywriting.get(key), str)
        else ""
        for key in COPYWRITING_KEYS
    }
    return config


def get_enabled_qqcc_video_scenes(config: dict[str, Any]) -> list[dict[str, Any]]:
    return normalize_qqcc_config(config).get("video_scenes", [])


def has_enabled_qqcc_video_scenes(config: dict[str, Any]) -> bool:
    return bool(get_enabled_qqcc_video_scenes(config))


def get_qqcc_video_scene(
    config: dict[str, Any],
    scene_id: str | None,
) -> dict[str, Any] | None:
    if not scene_id:
        return None
    for scene in get_enabled_qqcc_video_scenes(config):
        if scene.get("id") == scene_id:
            return scene
    return None


def get_enabled_qqcc_ai_video_scenes(config: dict[str, Any]) -> list[dict[str, Any]]:
    return normalize_qqcc_config(config).get("ai_video_scenes", [])


def has_enabled_qqcc_ai_video_scenes(config: dict[str, Any]) -> bool:
    return bool(get_enabled_qqcc_ai_video_scenes(config))


def get_qqcc_ai_video_scene(
    config: dict[str, Any],
    scene_id: str | None,
) -> dict[str, Any] | None:
    if not scene_id:
        return None
    for scene in get_enabled_qqcc_ai_video_scenes(config):
        if scene.get("id") == scene_id:
            return scene
    return None


def get_enabled_qqcc_draw_scenes(config: dict[str, Any]) -> list[dict[str, Any]]:
    return normalize_qqcc_config(config).get("draw_scenes", [])


def has_enabled_qqcc_draw_scenes(config: dict[str, Any]) -> bool:
    return bool(get_enabled_qqcc_draw_scenes(config))


def get_enabled_qqcc_filter_scenes(config: dict[str, Any]) -> list[dict[str, Any]]:
    return normalize_qqcc_config(config).get("filter_scenes", [])


def has_enabled_qqcc_filter_scenes(config: dict[str, Any]) -> bool:
    return bool(get_enabled_qqcc_filter_scenes(config))


def get_qqcc_draw_scene(
    config: dict[str, Any],
    scene_id: str | None,
) -> dict[str, Any] | None:
    if not scene_id:
        return None
    for scene in get_enabled_qqcc_draw_scenes(config):
        if scene.get("id") == scene_id:
            return scene
    return None


def get_qqcc_filter_scene(
    config: dict[str, Any],
    scene_id: str | None,
) -> dict[str, Any] | None:
    if not scene_id:
        return None
    for scene in get_enabled_qqcc_filter_scenes(config):
        if scene.get("id") == scene_id:
            return scene
    return None


def is_qqcc_global_enabled(config: dict[str, Any]) -> bool:
    return normalize_qqcc_config(config)["global_enabled"] is True


def is_qqcc_flag_enabled(
    config: dict[str, Any],
    section: str,
    key: str,
    *,
    require_global: bool = True,
) -> bool:
    normalized = normalize_qqcc_config(config)
    if require_global and not normalized["global_enabled"]:
        return False
    values = normalized.get(section, {})
    return isinstance(values, dict) and values.get(key) is True


def is_qqcc_main_button_enabled(config: dict[str, Any], key: str) -> bool:
    return is_qqcc_flag_enabled(config, "main_buttons", key)


def is_qqcc_main_bot_link_enabled(config: dict[str, Any]) -> bool:
    return is_qqcc_flag_enabled(
        config,
        "main_buttons",
        "main_bot_link",
        require_global=False,
    )


def is_qqcc_private_bot_entry_enabled(config: dict[str, Any]) -> bool:
    return is_qqcc_flag_enabled(
        config,
        "main_buttons",
        "private_bot",
        require_global=False,
    )


def is_qqcc_photo_button_enabled(config: dict[str, Any], key: str) -> bool:
    return is_qqcc_flag_enabled(config, "photo_buttons", key)


def is_qqcc_undress_method_enabled(config: dict[str, Any], key: str) -> bool:
    return is_qqcc_flag_enabled(config, "undress_methods", key)


def get_qqcc_prompt_override(config: dict[str, Any], prompt_key: str) -> str | None:
    prompt = normalize_qqcc_config(config)["prompts"].get(prompt_key, "").strip()
    return prompt or None


def get_qqcc_copywriting_override(config: dict[str, Any], key: str) -> str | None:
    """Return a configured QQCC interaction message, if one is set."""

    copywriting = normalize_qqcc_config(config)["copywriting"]
    text = copywriting.get(key, "").strip()
    return text or None


def render_qqcc_copywriting(
    template: str | None,
    button_name: str,
    *,
    cost: int | None = None,
) -> str | None:
    """Render documented scene placeholders in a configured message."""

    if not template:
        return None
    name = str(button_name or "")
    rendered = template.replace("{butten}", name).replace("{button}", name)
    return rendered.replace("{cost}", str(cost)) if cost is not None else rendered


def resolve_qqcc_prompt(
    config: dict[str, Any],
    prompt_key: str,
    prompts_config: dict[str, str],
    fallback_text: str,
) -> str:
    return (
        get_qqcc_prompt_override(config, prompt_key)
        or prompts_config.get(prompt_key)
        or fallback_text
    )


def _build_lora_model_options(catalog: dict[str, str]) -> list[dict[str, str]]:
    return [{"value": value, "label": label} for value, label in catalog.items()]


def build_qqcc_config_options() -> dict[str, Any]:
    return {
        "scene_preset_version": SCENE_PRESET_VERSION,
        "default_video_engine": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
        "default_draw_engine": DRAW_SCENE_ENGINE_FREE_EDIT_V2,
        "default_ai_video_engine": AI_VIDEO_SCENE_ENGINE_LTX_VIDEO,
        "default_video_resolution": DEFAULT_VIDEO_SCENE_RESOLUTION,
        "default_ai_video_resolution": DEFAULT_AI_VIDEO_SCENE_RESOLUTION,
        "video_resolutions": [
            {"value": value, "label": value} for value in VIDEO_RESOLUTION_KEYS
        ],
        "ai_video_resolutions": [
            {"value": DEFAULT_AI_VIDEO_SCENE_RESOLUTION, "label": "1280×704"}
        ],
        "default_scene_credit_costs": dict(DEFAULT_SCENE_CREDIT_COSTS),
        "video_aspect_ratios": list(QQCC_VIDEO_ASPECT_RATIOS),
        "video_engines": [
            {
                "value": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
                "supports_lora": True,
            },
            {
                "value": VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2,
                "supports_lora": True,
            },
        ],
        "draw_engines": [
            {
                "value": DRAW_SCENE_ENGINE_FREE_EDIT,
                "supports_lora": True,
            },
            {
                "value": DRAW_SCENE_ENGINE_FREE_EDIT_V2,
                "supports_lora": False,
            },
            {
                "value": DRAW_SCENE_ENGINE_FREE_EDIT_V3,
                "supports_lora": False,
            },
        ],
        "ai_video_engines": [
            {
                "value": AI_VIDEO_SCENE_ENGINE_LTX_VIDEO,
                "supports_lora": True,
            }
        ],
        "video_lora_models": [
            {
                "value": value,
                "label": label,
                "default_strength": QQCC_VIDEO_LORA_DEFAULT_STRENGTHS[value],
            }
            for value, label in QQCC_VIDEO_LORA_MODELS.items()
        ],
        "image_lora_models": _build_lora_model_options(IMAGE_LORA_MODELS),
        "ltx_video_lora_models": [
            {
                "value": value,
                "label": label,
                "default_strength": QQCC_LTX_VIDEO_LORA_DEFAULT_STRENGTHS.get(
                    value, 1.0
                ),
            }
            for value, label in QQCC_LTX_VIDEO_LORA_MODELS.items()
            if value
        ],
    }


def _build_config_response(
    *,
    config: dict[str, Any],
    updated_at: datetime | None,
    include_preview_urls: bool = True,
) -> dict[str, Any]:
    normalized_config = normalize_qqcc_config(config)
    if include_preview_urls:
        for section in (
            "video_scenes",
            "ai_video_scenes",
            "draw_scenes",
            "filter_scenes",
        ):
            for scene in normalized_config[section]:
                for field in ("demo_input_media", "demo_output_media"):
                    media = scene.get(field)
                    if not isinstance(media, dict):
                        continue
                    preview_url = build_qqcc_demo_preview_url(media)
                    if preview_url:
                        media["preview_url"] = preview_url
    return {
        "key": QQCC_LAZY_BOT_CONFIG_KEY,
        "config": normalized_config,
        "options": build_qqcc_config_options(),
        "updated_at": updated_at,
    }


async def load_qqcc_config_payload(
    db: AsyncSession,
    *,
    include_preview_urls: bool = True,
) -> dict[str, Any]:
    from src.database.models import RuntimeCheckpoint

    result = await db.execute(
        select(RuntimeCheckpoint).where(
            RuntimeCheckpoint.key == QQCC_LAZY_BOT_CONFIG_KEY
        )
    )
    checkpoint = result.scalar_one_or_none()
    if not checkpoint:
        return _build_config_response(
            config={},
            updated_at=None,
            include_preview_urls=include_preview_urls,
        )
    return _build_config_response(
        config=checkpoint.value or {},
        updated_at=checkpoint.updated_at,
        include_preview_urls=include_preview_urls,
    )


def _merge_qqcc_demo_telegram_caches(
    config: dict[str, Any],
    existing_config: dict[str, Any],
) -> None:
    for section in ("video_scenes", "ai_video_scenes", "draw_scenes", "filter_scenes"):
        existing_by_id = {
            str(scene.get("id") or ""): scene
            for scene in existing_config.get(section, [])
        }
        for scene in config.get(section, []):
            existing_scene = existing_by_id.get(str(scene.get("id") or ""))
            if not isinstance(existing_scene, dict):
                continue
            for field in ("demo_input_media", "demo_output_media"):
                media = scene.get(field)
                existing_media = existing_scene.get(field)
                if (
                    not isinstance(media, dict)
                    or not isinstance(existing_media, dict)
                    or media.get("object_key") != existing_media.get("object_key")
                    or media.get("content_sha256")
                    != existing_media.get("content_sha256")
                ):
                    continue
                existing_file_ids = existing_media.get("telegram_file_ids")
                if isinstance(existing_file_ids, dict):
                    media["telegram_file_ids"] = dict(existing_file_ids)


async def save_qqcc_config_payload(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    from src.database.models import RuntimeCheckpoint

    validate_qqcc_video_scene_chain_config(payload)
    validate_qqcc_scene_credit_costs(payload)
    validate_qqcc_scene_resolutions(payload)
    config = normalize_qqcc_config(payload)
    result = await db.execute(
        select(RuntimeCheckpoint)
        .where(RuntimeCheckpoint.key == QQCC_LAZY_BOT_CONFIG_KEY)
        .with_for_update()
    )
    checkpoint = result.scalar_one_or_none()
    if checkpoint is None:
        checkpoint = RuntimeCheckpoint(
            key=QQCC_LAZY_BOT_CONFIG_KEY,
            value=config,
        )
        db.add(checkpoint)
    else:
        _merge_qqcc_demo_telegram_caches(
            config,
            normalize_qqcc_config(checkpoint.value or {}),
        )
        checkpoint.value = config
    await db.commit()
    await db.refresh(checkpoint)
    return _build_config_response(
        config=checkpoint.value or {},
        updated_at=checkpoint.updated_at,
    )


async def cache_qqcc_demo_telegram_file_ids(
    *,
    scene_kind: str,
    scene_id: str,
    bot_id: str,
    updates: list[dict[str, str]],
    private_bot_id: int | None = None,
    db: AsyncSession | None = None,
) -> int:
    from src.database.models import PrivateQqccBot, RuntimeCheckpoint

    if private_bot_id is not None and int(private_bot_id) <= 0:
        return 0
    private_prefix = (
        f"qqcc/private/{int(private_bot_id)}/demo/"
        if private_bot_id is not None
        else None
    )
    update_keys = [str(item.get("object_key") or "") for item in updates]
    if private_prefix is not None:
        if any(not key.startswith(private_prefix) for key in update_keys):
            return 0
    elif any(key.startswith("qqcc/private/") for key in update_keys):
        # Tenant selection must come from the trusted Application context rather
        # than from an object key supplied inside mutable configuration JSON.
        return 0

    def _apply_updates(config: dict[str, Any]) -> int:
        section = {
            "video": "video_scenes",
            "ai_video": "ai_video_scenes",
            "draw": "draw_scenes",
            "filter": "filter_scenes",
        }.get(scene_kind)
        if section is None or not str(bot_id).isdigit():
            return 0
        scene = next(
            (item for item in config[section] if item.get("id") == scene_id),
            None,
        )
        if scene is None:
            return 0

        updated = 0
        for item in updates:
            slot = str(item.get("slot") or "")
            object_key = str(item.get("object_key") or "")
            content_sha256 = str(item.get("content_sha256") or "")
            file_id = str(item.get("file_id") or "").strip()[:512]
            media = scene.get(f"demo_{slot}_media")
            if (
                slot not in {"input", "output"}
                or not isinstance(media, dict)
                or media.get("object_key") != object_key
                or str(media.get("content_sha256") or "") != content_sha256
                or not file_id
            ):
                continue
            file_ids = media.setdefault("telegram_file_ids", {})
            file_ids[str(bot_id)] = file_id
            updated += 1
        return updated

    async def _update(session: AsyncSession) -> int:
        if private_bot_id is not None:
            result = await session.execute(
                select(PrivateQqccBot)
                .where(PrivateQqccBot.id == private_bot_id)
                .with_for_update()
            )
            private_bot = result.scalar_one_or_none()
            if private_bot is None:
                return 0
            config = normalize_qqcc_config(private_bot.config or {})
            updated = _apply_updates(config)
            if updated:
                private_bot.config = config
                await session.commit()
            return updated

        result = await session.execute(
            select(RuntimeCheckpoint)
            .where(RuntimeCheckpoint.key == QQCC_LAZY_BOT_CONFIG_KEY)
            .with_for_update()
        )
        checkpoint = result.scalar_one_or_none()
        if checkpoint is None:
            return 0
        config = normalize_qqcc_config(checkpoint.value or {})
        updated = _apply_updates(config)
        if updated:
            checkpoint.value = config
            await session.commit()
        return updated

    if db is not None:
        return await _update(db)

    from src.database.core import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return await _update(session)


async def load_runtime_qqcc_config() -> dict[str, Any]:
    from src.database.core import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        payload = await load_qqcc_config_payload(db, include_preview_urls=False)
        return payload["config"]
