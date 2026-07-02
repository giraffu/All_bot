from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

QQCC_LAZY_BOT_CONFIG_KEY = "qqcc_lazy_bot_config:v1"

MAIN_BUTTON_KEYS = (
    "quick_undress",
    "photo_edit",
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
VIDEO_SCENE_MAX_COUNT = 20
VIDEO_SCENE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
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


def _default_video_scenes() -> list[dict[str, str]]:
    return [
        {
            "id": scene["id"],
            "name": scene["name"],
            "prompt": "",
            "duration": "5s",
            "prompt_key": scene["prompt_key"],
        }
        for scene in LEGACY_VIDEO_SCENE_DEFINITIONS
    ]

DEFAULT_QQCC_LAZY_BOT_CONFIG: dict[str, Any] = {
    "global_enabled": True,
    "main_buttons": {
        "quick_undress": True,
        "photo_edit": True,
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


def _normalize_video_scene(
    raw_scene: Any,
    *,
    index: int,
    used_ids: set[str],
) -> dict[str, str] | None:
    if not isinstance(raw_scene, dict):
        return None

    name = raw_scene.get("name")
    name = name.strip() if isinstance(name, str) else ""
    if not name:
        return None

    prompt = raw_scene.get("prompt")
    prompt = prompt.strip() if isinstance(prompt, str) else ""
    prompt_key = _normalize_scene_prompt_key(raw_scene.get("prompt_key"))
    if not prompt and prompt_key is None:
        return None

    duration = raw_scene.get("duration")
    duration = duration.strip() if isinstance(duration, str) else ""
    if duration not in VIDEO_DURATION_KEYS:
        duration = "5s"

    scene = {
        "id": _build_unique_scene_id(
            raw_scene.get("id"),
            index=index,
            used_ids=used_ids,
        ),
        "name": name,
        "prompt": prompt,
        "duration": duration,
    }
    if prompt_key:
        scene["prompt_key"] = prompt_key
    return scene


def _normalize_video_scenes(raw_scenes: Any) -> list[dict[str, str]]:
    if not isinstance(raw_scenes, list):
        return []
    scenes: list[dict[str, str]] = []
    used_ids: set[str] = set()
    for index, raw_scene in enumerate(raw_scenes[:VIDEO_SCENE_MAX_COUNT]):
        scene = _normalize_video_scene(raw_scene, index=index, used_ids=used_ids)
        if scene is not None:
            scenes.append(scene)
    return scenes


def _migrate_legacy_video_scenes(raw: dict[str, Any]) -> list[dict[str, str]]:
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
        scenes.append(
            {
                "id": scene["id"],
                "name": scene["name"],
                "prompt": prompt.strip() if isinstance(prompt, str) else "",
                "duration": "5s",
                "prompt_key": prompt_key,
            }
        )
    return scenes


def normalize_qqcc_config(raw: Any | None) -> dict[str, Any]:
    """Return the effective QQCC config with unknown keys removed."""

    defaults = deepcopy(DEFAULT_QQCC_LAZY_BOT_CONFIG)
    if not isinstance(raw, dict):
        return defaults

    config = deepcopy(defaults)
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
    if "video_scenes" in raw:
        config["video_scenes"] = _normalize_video_scenes(raw.get("video_scenes"))
    else:
        config["video_scenes"] = _migrate_legacy_video_scenes(raw)

    raw_prompts = raw.get("prompts")
    if not isinstance(raw_prompts, dict):
        raw_prompts = {}
    config["prompts"] = {
        key: raw_prompts[key].strip() if isinstance(raw_prompts.get(key), str) else ""
        for key in PROMPT_KEYS
    }
    return config


def has_enabled_qqcc_values(config: dict[str, Any], section: str) -> bool:
    normalized = normalize_qqcc_config(config)
    values = normalized.get(section, {})
    return isinstance(values, dict) and any(value is True for value in values.values())


def has_enabled_qqcc_video_settings(config: dict[str, Any]) -> bool:
    normalized = normalize_qqcc_config(config)
    settings = normalized["video_settings"]
    return any(settings["resolutions"].values()) and any(settings["durations"].values())


def get_enabled_qqcc_video_scenes(config: dict[str, Any]) -> list[dict[str, str]]:
    return normalize_qqcc_config(config).get("video_scenes", [])


def has_enabled_qqcc_video_scenes(config: dict[str, Any]) -> bool:
    return bool(get_enabled_qqcc_video_scenes(config))


def get_qqcc_video_scene(
    config: dict[str, Any],
    scene_id: str | None,
) -> dict[str, str] | None:
    if not scene_id:
        return None
    for scene in get_enabled_qqcc_video_scenes(config):
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


def is_qqcc_video_button_enabled(config: dict[str, Any], key: str) -> bool:
    return is_qqcc_flag_enabled(config, "video_buttons", key)


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


def _build_config_response(
    *,
    config: dict[str, Any],
    updated_at: datetime | None,
) -> dict[str, Any]:
    return {
        "key": QQCC_LAZY_BOT_CONFIG_KEY,
        "config": normalize_qqcc_config(config),
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
