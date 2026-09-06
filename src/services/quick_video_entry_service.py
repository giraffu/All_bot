from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.constants import (
    DEFAULT_DURATION,
    DEFAULT_RESOLUTION,
    MODE_CUSTOM_VIDEO,
    MODE_LTX_VIDEO,
)
from src.services.qqcc_config_service import (
    get_qqcc_ai_video_scene,
    get_qqcc_video_scene,
    get_qqcc_video_scene_v1,
    is_qqcc_main_button_enabled,
    project_qqcc_config_for_scene_version,
)
from src.services.qqcc_scene_billing_service import (
    resolve_qqcc_scene_fixed_credit_cost,
)
from src.services.quick_video_submission_service import (
    resolve_qqcc_video_scene_task_type,
)


QUICK_VIDEO_LEGACY_ROUTE_SCENE_IDS = {
    "menu.video_edit_missionary": "missionary",
    "menu.video_edit_doggy": "doggy",
    "menu.video_edit_blowjob": "blowjob",
    "menu.video_edit_undress_tongue": "undress_tongue",
    "menu.video_edit_closeup_blowjob": "closeup_blowjob",
}


class QuickVideoEntryRejectReason(str, Enum):
    REDIRECT_TO_LAZY_BOT = "redirect_to_lazy_bot"
    FEATURE_DISABLED = "feature_disabled"
    INVALID_ENTRY = "invalid_entry"


@dataclass(frozen=True)
class QuickVideoEntryReject:
    reason: QuickVideoEntryRejectReason


@dataclass(frozen=True)
class QuickVideoEntryPlan:
    mode: str
    mode_name: str
    scene: dict[str, Any] | None
    scene_kind: str
    scene_version: str
    qqcc_config: dict[str, Any] | None
    fsm_data: dict[str, Any]


def resolve_qqcc_scene_from_quick_video_entry(
    config: dict[str, Any],
    *,
    scene_id: str | None,
    route_key: str | None,
    scene_kind: str,
    scene_version: str = "v2",
) -> dict[str, Any] | None:
    if scene_kind == "ai_video":
        return get_qqcc_ai_video_scene(config, scene_id)
    scene_getter = (
        get_qqcc_video_scene_v1 if scene_version == "v1" else get_qqcc_video_scene
    )
    if scene_id:
        return scene_getter(config, scene_id)
    legacy_scene_id = QUICK_VIDEO_LEGACY_ROUTE_SCENE_IDS.get(route_key or "")
    return scene_getter(config, legacy_scene_id)


def sync_qqcc_scene_to_quick_video_data(
    fsm_data: dict[str, Any],
    scene: dict[str, Any],
    *,
    include_scene_id: bool = False,
    include_prompt_details: bool = False,
    scene_kind: str = "video",
) -> str:
    mode = (
        MODE_LTX_VIDEO
        if scene_kind == "ai_video"
        else resolve_qqcc_video_scene_task_type(scene)
    )
    fsm_data.update(
        {
            "mode": mode,
            "duration": scene["duration"],
            "resolution": str(
                scene.get("resolution")
                or ("1280x704" if scene_kind == "ai_video" else "720p")
            ),
            "engine": scene.get("engine"),
            "lora_name": str(scene.get("lora_name") or ""),
            "lora_items": list(scene.get("lora_items") or []),
            "end_frame_draw_scene_id": str(scene.get("end_frame_draw_scene_id") or ""),
            "scene_kind": scene_kind,
        }
    )
    if scene_kind == "ai_video":
        fsm_data.update(
            {
                "ai_video_mode": str(scene.get("mode") or "i2v"),
                "reference_images": list(scene.get("reference_images") or []),
                "reference_image_names": list(scene.get("reference_image_names") or []),
                "reference_image_telegram_file_ids": list(
                    scene.get("reference_image_telegram_file_ids") or []
                ),
                "aspect_ratio": str(scene.get("aspect_ratio") or "16:9"),
            }
        )
    fixed_credit_cost = resolve_qqcc_scene_fixed_credit_cost(scene)
    if fixed_credit_cost is None:
        fsm_data.pop("credit_cost", None)
    else:
        fsm_data["credit_cost"] = fixed_credit_cost
    if scene_kind != "ai_video":
        fsm_data.pop("ai_video_mode", None)
        fsm_data.pop("reference_images", None)
        fsm_data.pop("reference_image_names", None)
        fsm_data.pop("reference_image_telegram_file_ids", None)
        fsm_data.pop("aspect_ratio", None)
        fsm_data.pop("lora_items", None)
        fsm_data.pop("scene_kind", None)
    if include_scene_id:
        fsm_data["scene_id"] = scene["id"]
    if include_prompt_details:
        scene_prompt = str(scene.get("prompt", "")).strip()
        fsm_data.update(
            {
                "mode_name": str(scene["name"]),
                "prompt_override": scene_prompt,
                "default_prompt_key": MODE_CUSTOM_VIDEO,
                "default_prompt_text": scene_prompt,
            }
        )
    return mode


def build_quick_video_entry_plan(
    *,
    mode: str | None,
    mode_name: str,
    route_key: str | None,
    scene_id: str | None,
    scene_kind: str,
    qqcc_config: dict[str, Any] | None,
) -> QuickVideoEntryPlan | QuickVideoEntryReject:
    has_known_entry = bool(mode or route_key or scene_id)
    if qqcc_config is None:
        if has_known_entry:
            return QuickVideoEntryReject(
                QuickVideoEntryRejectReason.REDIRECT_TO_LAZY_BOT
            )
        return QuickVideoEntryReject(QuickVideoEntryRejectReason.INVALID_ENTRY)

    scene_version = "v1" if scene_kind == "video_v1" else "v2"
    effective_scene_kind = "video" if scene_kind == "video_v1" else scene_kind
    effective_config = qqcc_config
    if scene_version == "v1":
        effective_config = project_qqcc_config_for_scene_version(
            qqcc_config,
            family="video",
            version=scene_version,
        )

    scene = resolve_qqcc_scene_from_quick_video_entry(
        effective_config,
        scene_id=scene_id,
        route_key=route_key,
        scene_kind=effective_scene_kind,
        scene_version=scene_version,
    )
    button_key = (
        "ai_video"
        if effective_scene_kind == "ai_video"
        else ("video_edit_v1" if scene_version == "v1" else "video_edit_v2")
    )
    if scene is None or not is_qqcc_main_button_enabled(effective_config, button_key):
        return QuickVideoEntryReject(QuickVideoEntryRejectReason.FEATURE_DISABLED)

    fsm_data: dict[str, Any] = {
        "mode": mode,
        "resolution": DEFAULT_RESOLUTION,
        "duration": DEFAULT_DURATION,
        "image_path": None,
    }
    resolved_mode = sync_qqcc_scene_to_quick_video_data(
        fsm_data,
        scene,
        include_scene_id=True,
        include_prompt_details=True,
        scene_kind=effective_scene_kind,
    )
    if effective_scene_kind == "video":
        fsm_data["scene_version"] = scene_version

    return QuickVideoEntryPlan(
        mode=resolved_mode,
        mode_name=str(fsm_data["mode_name"]),
        scene=scene,
        scene_kind=effective_scene_kind,
        scene_version=scene_version,
        qqcc_config=effective_config,
        fsm_data=fsm_data,
    )
