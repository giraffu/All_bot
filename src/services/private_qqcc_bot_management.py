from __future__ import annotations

import copy
import json
from datetime import datetime
from typing import Any

from src.services.qqcc_config_service import (
    build_qqcc_config_options,
    normalize_qqcc_config,
)
from src.services.qqcc_demo_media_service import build_qqcc_demo_preview_url
from src.services.qqcc_video_scene_chain_service import (
    validate_qqcc_video_scene_chain_config,
)


class PrivateBotConfigVersionConflict(ValueError):
    pass


class PrivateBotConfigMediaScopeError(ValueError):
    pass


class PrivateBotConfigLimitError(ValueError):
    pass


PRIVATE_BOT_CONFIG_MAX_BYTES = 512 * 1024
PRIVATE_BOT_CONFIG_MAX_SCENES_PER_KIND = 100
PRIVATE_BOT_CONFIG_MAX_SCENES_TOTAL = 200
PRIVATE_BOT_CONFIG_MAX_SCENE_NAME_CHARS = 120
PRIVATE_BOT_CONFIG_MAX_PROMPT_CHARS = 12_000
PRIVATE_BOT_CONFIG_MAX_DRAW_CHAIN_DEPTH = 12


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def build_private_bot_status_payload(bot) -> dict[str, Any]:
    return {
        "id": int(bot.id),
        "telegram_bot_id": int(bot.telegram_bot_id),
        "telegram_username": str(bot.telegram_username or ""),
        "telegram_display_name": str(bot.telegram_display_name or ""),
        "owner_enabled": bool(bot.owner_enabled),
        "admin_enabled": bool(bot.admin_enabled),
        "runtime_status": str(bot.runtime_status),
        "last_error_code": bot.last_error_code,
        "last_error_message": bot.last_error_message,
        "last_webhook_at": _iso(bot.last_webhook_at),
        "last_update_at": _iso(bot.last_update_at),
        "updated_at": _iso(bot.updated_at),
    }


def _with_preview_urls(config: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(config)
    for section in ("video_scenes", "ai_video_scenes", "draw_scenes", "filter_scenes"):
        for scene in result.get(section, []):
            for field in ("demo_input_media", "demo_output_media"):
                media = scene.get(field)
                if not isinstance(media, dict):
                    continue
                preview_url = build_qqcc_demo_preview_url(media)
                if preview_url:
                    media["preview_url"] = preview_url
    return result


def build_private_bot_config_payload(bot) -> dict[str, Any]:
    config = normalize_qqcc_config(bot.config or {})
    return {
        "bot": build_private_bot_status_payload(bot),
        "config": _with_preview_urls(config),
        "config_version": int(bot.config_version),
        "options": build_qqcc_config_options(),
    }


def _validate_media_scope(config: dict[str, Any], *, private_bot_id: int) -> None:
    private_prefix = f"qqcc/private/{int(private_bot_id)}/demo/"
    for section in ("video_scenes", "ai_video_scenes", "draw_scenes", "filter_scenes"):
        for scene in config.get(section, []):
            for field in ("demo_input_media", "demo_output_media"):
                media = scene.get(field)
                if not isinstance(media, dict):
                    continue
                object_key = str(media.get("object_key") or "")
                if not object_key.startswith(private_prefix):
                    raise PrivateBotConfigMediaScopeError(
                        "private Bot demo media belongs to another tenant"
                    )


def _validate_draw_chain_depth(raw_config: dict[str, Any]) -> None:
    raw_scenes = raw_config.get("draw_scenes")
    if not isinstance(raw_scenes, list):
        return
    next_scene_by_id = {
        str(scene.get("id") or ""): str(
            scene.get("postprocess_draw_scene_id") or ""
        )
        for scene in raw_scenes
        if isinstance(scene, dict) and scene.get("id")
    }
    for start_scene_id in next_scene_by_id:
        seen: set[str] = set()
        current_scene_id = start_scene_id
        depth = 0
        while current_scene_id:
            if current_scene_id in seen:
                raise PrivateBotConfigLimitError(
                    "private Bot draw postprocess chain cannot contain a cycle"
                )
            seen.add(current_scene_id)
            current_scene_id = next_scene_by_id.get(current_scene_id, "")
            depth += 1
            if depth > PRIVATE_BOT_CONFIG_MAX_DRAW_CHAIN_DEPTH:
                raise PrivateBotConfigLimitError(
                    "private Bot draw postprocess chain is too deep"
                )


def validate_private_bot_config_limits(raw_config: dict[str, Any]) -> None:
    try:
        encoded = json.dumps(
            raw_config,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise PrivateBotConfigLimitError("private Bot config is invalid") from exc
    if len(encoded) > PRIVATE_BOT_CONFIG_MAX_BYTES:
        raise PrivateBotConfigLimitError("private Bot config is too large")

    scene_count = 0
    for section in ("video_scenes", "ai_video_scenes", "draw_scenes", "filter_scenes"):
        raw_scenes = raw_config.get(section, [])
        if not isinstance(raw_scenes, list):
            continue
        scene_count += len(raw_scenes)
        for scene in raw_scenes:
            if not isinstance(scene, dict):
                continue
            if len(str(scene.get("name") or "")) > PRIVATE_BOT_CONFIG_MAX_SCENE_NAME_CHARS:
                raise PrivateBotConfigLimitError("private Bot scene name is too long")
            for field in ("prompt", "negative_prompt"):
                if len(str(scene.get(field) or "")) > PRIVATE_BOT_CONFIG_MAX_PROMPT_CHARS:
                    raise PrivateBotConfigLimitError(
                        "private Bot scene prompt is too long"
                    )
    _validate_draw_chain_depth(raw_config)


def update_private_bot_config_record(
    bot,
    *,
    expected_version: int,
    raw_config: dict[str, Any],
) -> dict[str, Any]:
    if int(expected_version) != int(bot.config_version):
        raise PrivateBotConfigVersionConflict("private Bot config version is stale")
    validate_private_bot_config_limits(raw_config)
    validate_qqcc_video_scene_chain_config(raw_config)
    normalized = normalize_qqcc_config(raw_config)
    _validate_media_scope(normalized, private_bot_id=int(bot.id))
    bot.config = normalized
    bot.config_version = int(bot.config_version) + 1
    return normalized


def build_private_bot_admin_summary(bot, owner) -> dict[str, Any]:
    payload = build_private_bot_status_payload(bot)
    payload.update(
        {
            "owner": {
                "id": int(owner.id),
                "telegram_id": owner.telegram_id,
                "username": owner.username,
                "full_name": owner.full_name,
            },
            "token_fingerprint_hint": str(bot.token_fingerprint or "")[-8:],
            "created_at": _iso(bot.created_at),
        }
    )
    return payload


def build_private_bot_audit_payload(audit) -> dict[str, Any]:
    return {
        "id": int(audit.id),
        "actor_type": audit.actor_type,
        "actor_identifier": audit.actor_identifier,
        "action": audit.action,
        "before_status": audit.before_status,
        "after_status": audit.after_status,
        "details": copy.deepcopy(audit.details or {}),
        "created_at": _iso(audit.created_at),
    }
