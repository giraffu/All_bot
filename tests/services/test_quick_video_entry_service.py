from src.constants import MODE_CUSTOM_VIDEO, MODE_DOGGY_STYLE
from src.services.qqcc_config_service import SCENE_PRESET_VERSION, normalize_qqcc_config
from src.services.quick_video_entry_service import (
    QuickVideoEntryReject,
    QuickVideoEntryRejectReason,
    build_quick_video_entry_plan,
)


def test_main_bot_legacy_entry_redirects_to_lazy_bot():
    result = build_quick_video_entry_plan(
        mode=MODE_DOGGY_STYLE,
        mode_name="动图后入",
        route_key="menu.video_edit_doggy",
        scene_id=None,
        scene_kind="video",
        qqcc_config=None,
    )

    assert result == QuickVideoEntryReject(
        QuickVideoEntryRejectReason.REDIRECT_TO_LAZY_BOT
    )


def test_qqcc_video_scene_builds_fsm_seed_from_runtime_config():
    config = normalize_qqcc_config(
        {
            "main_buttons": {"video_edit_v2": True},
            "video_scenes_v2": [
                {
                    "id": "kiss",
                    "name": "亲吻",
                    "prompt": "kissing prompt",
                    "duration": "8s",
                    "credit_cost": 9,
                }
            ],
        }
    )

    result = build_quick_video_entry_plan(
        mode=None,
        mode_name="",
        route_key=None,
        scene_id="kiss",
        scene_kind="video",
        qqcc_config=config,
    )

    assert result.mode == "wan22_video_v2"
    assert result.mode_name == "亲吻"
    assert result.scene == config["video_scenes_v2"][0]
    assert result.scene_kind == "video"
    assert result.scene_version == "v2"
    assert result.fsm_data == {
        "mode": "wan22_video_v2",
        "scene_id": "kiss",
        "mode_name": "亲吻",
        "prompt_override": "kissing prompt",
        "credit_cost": 9,
        "default_prompt_key": MODE_CUSTOM_VIDEO,
        "default_prompt_text": "kissing prompt",
        "engine": "wan22_video_v2",
        "lora_name": "",
        "end_frame_draw_scene_id": "",
        "resolution": "720p",
        "duration": "8s",
        "image_path": None,
        "scene_version": "v2",
    }


def test_removed_legacy_scene_is_rejected_as_disabled():
    config = normalize_qqcc_config(
        {
            "main_buttons": {"video_edit_v2": True},
            "video_scenes_v2": [
                {
                    "id": "kiss",
                    "name": "亲吻",
                    "prompt": "kissing prompt",
                    "duration": "8s",
                }
            ],
        }
    )

    result = build_quick_video_entry_plan(
        mode=MODE_DOGGY_STYLE,
        mode_name="动图后入",
        route_key="menu.video_edit_doggy",
        scene_id=None,
        scene_kind="video",
        qqcc_config=config,
    )

    assert result == QuickVideoEntryReject(QuickVideoEntryRejectReason.FEATURE_DISABLED)


def test_v1_scene_entry_projects_v1_collection_into_fsm_seed():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "main_buttons": {"video_edit_v1": True, "video_edit_v2": True},
            "video_scenes_v1": [
                {
                    "id": "classic",
                    "name": "经典动图",
                    "prompt": "classic prompt",
                    "duration": "5s",
                    "engine": "image_to_video",
                }
            ],
            "video_scenes_v2": [
                {
                    "id": "modern",
                    "name": "新版动图",
                    "prompt": "modern prompt",
                    "duration": "8s",
                }
            ],
        }
    )

    result = build_quick_video_entry_plan(
        mode=None,
        mode_name="",
        route_key=None,
        scene_id="classic",
        scene_kind="video_v1",
        qqcc_config=config,
    )

    assert result.scene_version == "v1"
    assert result.scene_kind == "video"
    assert result.scene["id"] == "classic"
    assert result.qqcc_config["video_scenes"][0]["id"] == "classic"
    assert result.fsm_data["scene_version"] == "v1"
