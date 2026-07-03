from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.lora_catalog import IMAGE_LORA_MODELS, VIDEO_LORA_MODELS

QQCC_LAZY_BOT_CONFIG_KEY = "qqcc_lazy_bot_config:v1"
SCENE_PRESET_VERSION = 1

MAIN_BUTTON_KEYS = (
    "quick_undress",
    "quick_faceswap",
    "photo_edit",
    "ai_draw",
    "video_edit",
    "market",
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
VIDEO_DURATION_KEYS = ("5s", "8s", "10s")
VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO = "image_to_video"
VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2 = "wan22_video_v2"
VIDEO_SCENE_ENGINE_KEYS = (
    VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
    VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2,
)
VIDEO_SCENE_ENGINES_WITH_LORA = frozenset({VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO})
VIDEO_SCENE_MAX_COUNT = 20
VIDEO_SCENE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
DRAW_SCENE_ENGINE_FREE_EDIT = "free_edit"
DRAW_SCENE_ENGINE_FREE_EDIT_V2 = "free_edit_v2"
DRAW_SCENE_ENGINE_KEYS = (
    DRAW_SCENE_ENGINE_FREE_EDIT,
    DRAW_SCENE_ENGINE_FREE_EDIT_V2,
)
DRAW_SCENE_ENGINES_WITH_LORA = frozenset({DRAW_SCENE_ENGINE_FREE_EDIT})
DRAW_SCENE_MAX_COUNT = 20
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
VIDEO_PROMPT_KEYS = (
    "perfect_video_insert",
    "doggy_style",
    "blowjob",
    "undress_tongue",
    "closeup_blowjob",
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
) -> list[dict[str, str]]:
    return [
        {
            "id": scene["id"],
            "name": scene["name"],
            "prompt": _preset_prompt(scene["prompt_key"], raw_prompts),
            "duration": "5s",
            "engine": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
            "lora_name": "",
            "end_frame_draw_scene_id": "",
        }
        for scene in LEGACY_VIDEO_SCENE_DEFINITIONS
    ]


def _default_draw_scenes(
    raw_prompts: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    return [
        {
            "id": "quick_masturbation",
            "name": "快速自慰",
            "prompt": _preset_prompt("masturbation", raw_prompts),
            "engine": DRAW_SCENE_ENGINE_FREE_EDIT,
            "lora_name": "",
            "postprocess_draw_scene_id": "",
        },
        {
            "id": "quick_undress",
            "name": "快速脱衣",
            "prompt": _preset_prompt("undress", raw_prompts),
            "engine": DRAW_SCENE_ENGINE_FREE_EDIT,
            "lora_name": "",
            "postprocess_draw_scene_id": "",
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
        "video_edit": True,
        "market": True,
        "main_bot_link": True,
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
    "draw_scenes": _default_draw_scenes(),
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
    preset_scenes: list[dict[str, str]],
    max_count: int,
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
        if len(merged_scenes) >= max_count:
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
    lora_name = _normalize_scene_lora(
        raw_scene.get("lora_name"),
        engine=engine,
        lora_catalog=VIDEO_LORA_MODELS,
        engines_with_lora=VIDEO_SCENE_ENGINES_WITH_LORA,
    )

    scene = {
        "id": _build_unique_scene_id(
            raw_scene.get("id"),
            index=index,
            used_ids=used_ids,
        ),
        "name": name,
        "prompt": prompt,
        "duration": duration,
        "engine": engine,
        "lora_name": lora_name,
        "end_frame_draw_scene_id": _normalize_end_frame_draw_scene_id(
            raw_scene.get("end_frame_draw_scene_id"),
            allowed_draw_scene_ids=allowed_end_frame_draw_scene_ids,
        ),
    }
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
    scenes: list[dict[str, str]] = []
    used_ids: set[str] = set()
    for index, raw_scene in enumerate(raw_scenes[:VIDEO_SCENE_MAX_COUNT]):
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
            max_count=VIDEO_SCENE_MAX_COUNT,
        )
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

    scene = {
        "id": _build_unique_scene_id(
            raw_scene.get("id"),
            index=index,
            used_ids=used_ids,
        ),
        "name": name,
        "prompt": prompt,
        "engine": engine,
        "lora_name": lora_name,
        "postprocess_draw_scene_id": postprocess_draw_scene_id,
    }
    return scene


def _normalize_draw_scene_postprocess_refs(scenes: list[dict[str, Any]]) -> None:
    allowed_scene_ids = frozenset(str(scene.get("id") or "") for scene in scenes)
    scenes_by_id = {str(scene.get("id") or ""): scene for scene in scenes}
    for scene in scenes:
        scene_id = str(scene.get("id") or "")
        ref_id = str(scene.get("postprocess_draw_scene_id") or "").strip()
        if ref_id == scene_id or ref_id not in allowed_scene_ids:
            scene["postprocess_draw_scene_id"] = ""
        else:
            scene["postprocess_draw_scene_id"] = ref_id

    cycle_scene_ids: set[str] = set()
    for scene in scenes:
        path: list[str] = []
        seen_at: dict[str, int] = {}
        current_id = str(scene.get("id") or "")
        while current_id:
            if current_id in seen_at:
                cycle_scene_ids.update(path[seen_at[current_id]:])
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
) -> list[dict[str, Any]]:
    raw_scene_list = raw_scenes if isinstance(raw_scenes, list) else []
    normalized_raw_scenes: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for index, raw_scene in enumerate(raw_scene_list[:DRAW_SCENE_MAX_COUNT]):
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
            max_count=DRAW_SCENE_MAX_COUNT,
        )
        if seed_presets
        else normalized_raw_scenes
    )

    _normalize_draw_scene_postprocess_refs(scenes)
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
                "duration": "5s",
                "engine": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
                "lora_name": "",
                "end_frame_draw_scene_id": "",
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

    global_enabled = raw.get("global_enabled", defaults["global_enabled"])
    config["global_enabled"] = (
        global_enabled if isinstance(global_enabled, bool) else defaults["global_enabled"]
    )
    config["main_buttons"] = _normalize_bool_section(
        raw.get("main_buttons"),
        default=defaults["main_buttons"],
        keys=MAIN_BUTTON_KEYS,
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
    if "draw_scenes" in raw:
        config["draw_scenes"] = _normalize_draw_scenes(
            raw.get("draw_scenes"),
            raw_prompts=raw_prompts,
            seed_presets=seed_scene_presets,
        )
    elif seed_scene_presets:
        config["draw_scenes"] = _default_draw_scenes(raw_prompts)
    elif not seed_scene_presets:
        config["draw_scenes"] = []
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

    config["prompts"] = {
        key: raw_prompts[key].strip() if isinstance(raw_prompts.get(key), str) else ""
        for key in PROMPT_KEYS
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


def get_enabled_qqcc_draw_scenes(config: dict[str, Any]) -> list[dict[str, Any]]:
    return normalize_qqcc_config(config).get("draw_scenes", [])


def has_enabled_qqcc_draw_scenes(config: dict[str, Any]) -> bool:
    return bool(get_enabled_qqcc_draw_scenes(config))


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


def is_qqcc_photo_button_enabled(config: dict[str, Any], key: str) -> bool:
    return is_qqcc_flag_enabled(config, "photo_buttons", key)


def is_qqcc_undress_method_enabled(config: dict[str, Any], key: str) -> bool:
    return is_qqcc_flag_enabled(config, "undress_methods", key)


def get_qqcc_prompt_override(config: dict[str, Any], prompt_key: str) -> str | None:
    prompt = normalize_qqcc_config(config)["prompts"].get(prompt_key, "").strip()
    return prompt or None


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
    return [
        {"value": value, "label": label}
        for value, label in catalog.items()
    ]


def build_qqcc_config_options() -> dict[str, Any]:
    return {
        "scene_preset_version": SCENE_PRESET_VERSION,
        "default_video_engine": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
        "default_draw_engine": DRAW_SCENE_ENGINE_FREE_EDIT_V2,
        "video_engines": [
            {
                "value": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
                "supports_lora": True,
            },
            {
                "value": VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2,
                "supports_lora": False,
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
        ],
        "video_lora_models": _build_lora_model_options(VIDEO_LORA_MODELS),
        "image_lora_models": _build_lora_model_options(IMAGE_LORA_MODELS),
    }


def _build_config_response(
    *,
    config: dict[str, Any],
    updated_at: datetime | None,
) -> dict[str, Any]:
    return {
        "key": QQCC_LAZY_BOT_CONFIG_KEY,
        "config": normalize_qqcc_config(config),
        "options": build_qqcc_config_options(),
        "updated_at": updated_at,
    }


async def load_qqcc_config_payload(db: AsyncSession) -> dict[str, Any]:
    from src.database.models import RuntimeCheckpoint

    result = await db.execute(
        select(RuntimeCheckpoint).where(
            RuntimeCheckpoint.key == QQCC_LAZY_BOT_CONFIG_KEY
        )
    )
    checkpoint = result.scalar_one_or_none()
    if not checkpoint:
        return _build_config_response(config={}, updated_at=None)
    return _build_config_response(
        config=checkpoint.value or {},
        updated_at=checkpoint.updated_at,
    )


async def save_qqcc_config_payload(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    from src.database.models import RuntimeCheckpoint

    config = normalize_qqcc_config(payload)
    result = await db.execute(
        select(RuntimeCheckpoint).where(
            RuntimeCheckpoint.key == QQCC_LAZY_BOT_CONFIG_KEY
        )
    )
    checkpoint = result.scalar_one_or_none()
    if checkpoint is None:
        checkpoint = RuntimeCheckpoint(
            key=QQCC_LAZY_BOT_CONFIG_KEY,
            value=config,
        )
        db.add(checkpoint)
    else:
        checkpoint.value = config
    await db.commit()
    await db.refresh(checkpoint)
    return _build_config_response(
        config=checkpoint.value or {},
        updated_at=checkpoint.updated_at,
    )


async def load_runtime_qqcc_config() -> dict[str, Any]:
    from src.database.core import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        payload = await load_qqcc_config_payload(db)
        return payload["config"]
