from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.constants import (
    MODE_CUSTOM_VIDEO,
    MODE_DOGGY_STYLE,
    MODE_IMAGE_TO_VIDEO,
    MODE_WAN22_VIDEO_V2,
)
from src.services.qqcc_config_service import (
    SCENE_PRESET_VERSION,
    normalize_qqcc_config,
)
from src.services.quick_video_submission_service import (
    QuickVideoSubmissionKind,
    QuickVideoSubmissionRejectReason,
    QuickVideoSettingsReject,
    QuickVideoSettingsUpdate,
    build_quick_video_settings_update,
    build_quick_video_submission_plan,
    run_quick_video_submission_plan,
)


def test_main_bot_legacy_mode_builds_plan_without_qqcc_prompt_override():
    plan = build_quick_video_submission_plan(
        fsm_data={
            "mode": MODE_DOGGY_STYLE,
            "resolution": "1024p",
            "duration": "10s",
        },
        qqcc_config=None,
        allowed_resolutions=None,
    )

    assert plan.kind == QuickVideoSubmissionKind.LEGACY_VIDEO
    assert plan.mode == MODE_DOGGY_STYLE
    assert plan.resolution == "720p"
    assert plan.duration == "10s"
    assert plan.total_cost == 60
    assert plan.default_prompt_key == "doggy_style"
    assert plan.default_prompt_text == "doggy style sex"
    assert plan.prompt_override is None
    assert plan.tail_draw_chain == []


def test_quick_video_settings_update_resolves_resolution_duration_conflict():
    result = build_quick_video_settings_update(
        callback_data="set_res_1024p",
        resolution="720p",
        duration="10s",
        qqcc_config_present=False,
    )

    assert result == QuickVideoSettingsUpdate(
        resolution="1024p",
        duration="8s",
        alert_key="fsm.quick_video.res_dur_conflict",
    )


def test_quick_video_settings_update_resolves_duration_resolution_conflict():
    result = build_quick_video_settings_update(
        callback_data="set_dur_10s",
        resolution="1024p",
        duration="8s",
        qqcc_config_present=False,
    )

    assert result == QuickVideoSettingsUpdate(
        resolution="720p",
        duration="10s",
        alert_key="fsm.quick_video.dur_res_conflict",
    )


def test_qqcc_quick_video_settings_rejects_duration_button():
    result = build_quick_video_settings_update(
        callback_data="set_dur_8s",
        resolution="512p",
        duration="5s",
        qqcc_config_present=True,
        allowed_resolutions=["512p", "720p"],
    )

    assert result == QuickVideoSettingsReject(
        QuickVideoSubmissionRejectReason.FEATURE_DISABLED
    )


def test_qqcc_quick_video_settings_rejects_disallowed_resolution():
    result = build_quick_video_settings_update(
        callback_data="set_res_1024p",
        resolution="512p",
        duration="10s",
        qqcc_config_present=True,
        allowed_resolutions=["512p", "720p"],
    )

    assert result == QuickVideoSettingsReject(
        QuickVideoSubmissionRejectReason.FEATURE_DISABLED
    )


def test_qqcc_quick_video_settings_rejects_empty_allowed_resolutions():
    result = build_quick_video_settings_update(
        callback_data="set_res_720p",
        resolution="512p",
        duration="10s",
        qqcc_config_present=True,
        allowed_resolutions=[],
    )

    assert result == QuickVideoSettingsReject(
        QuickVideoSubmissionRejectReason.INVALID_SETTINGS
    )


def test_qqcc_image_to_video_lora_scene_builds_legacy_video_plan():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "video_scenes": [
                {
                    "id": "lora_scene",
                    "name": "模型动图",
                    "prompt": "lora scene prompt",
                    "duration": "5s",
                    "engine": "image_to_video",
                    "lora_name": "BreastGrow",
                }
            ],
        }
    )

    plan = build_quick_video_submission_plan(
        fsm_data={
            "mode": MODE_CUSTOM_VIDEO,
            "scene_id": "lora_scene",
            "resolution": "720p",
            "duration": "5s",
        },
        qqcc_config=config,
        allowed_resolutions=["512p", "720p"],
    )

    assert plan.kind == QuickVideoSubmissionKind.LEGACY_VIDEO
    assert plan.mode == MODE_IMAGE_TO_VIDEO
    assert plan.default_prompt_key == MODE_CUSTOM_VIDEO
    assert plan.default_prompt_text == "lora scene prompt"
    assert plan.prompt_override == "lora scene prompt"
    assert plan.display_mode_name == "模型动图"
    assert plan.lora_name == "BreastGrow"


def test_qqcc_wan22_v2_scene_builds_v2_plan_and_normalizes_resolution():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "video_scenes": [
                {
                    "id": "v2_scene",
                    "name": "新版动图",
                    "prompt": "v2 scene prompt",
                    "duration": "10s",
                    "engine": "wan22_video_v2",
                    "lora_name": "BreastGrow",
                }
            ],
        }
    )

    plan = build_quick_video_submission_plan(
        fsm_data={
            "mode": MODE_CUSTOM_VIDEO,
            "scene_id": "v2_scene",
            "resolution": "1024p",
            "duration": "10s",
        },
        qqcc_config=config,
        allowed_resolutions=["512p", "720p", "1024p"],
    )

    assert plan.kind == QuickVideoSubmissionKind.WAN22_VIDEO_V2
    assert plan.mode == MODE_WAN22_VIDEO_V2
    assert plan.resolution == "720p"
    assert plan.duration == "10s"
    assert plan.prompt_override == "v2 scene prompt"
    assert plan.lora_name == ""


def test_qqcc_tail_frame_scene_adds_draw_chain_cost():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "tail_pose",
                    "name": "尾帧姿势",
                    "prompt": "tail prompt",
                },
                {
                    "id": "tail_polish",
                    "name": "尾帧精修",
                    "prompt": "tail polish prompt",
                },
            ],
            "video_scenes": [
                {
                    "id": "tail_video",
                    "name": "首尾动图",
                    "prompt": "video prompt",
                    "duration": "5s",
                    "engine": "image_to_video",
                    "end_frame_draw_scene_id": "tail_pose",
                }
            ],
        }
    )
    tail_pose = config["draw_scenes"][0]
    tail_pose["postprocess_draw_scene_id"] = "tail_polish"

    plan = build_quick_video_submission_plan(
        fsm_data={
            "mode": MODE_CUSTOM_VIDEO,
            "scene_id": "tail_video",
            "resolution": "512p",
            "duration": "5s",
        },
        qqcc_config=config,
        allowed_resolutions=["512p"],
    )

    assert plan.kind == QuickVideoSubmissionKind.TAIL_FRAME_VIDEO
    assert plan.mode == MODE_CUSTOM_VIDEO
    assert [scene["id"] for scene in plan.tail_draw_chain] == [
        "tail_pose",
        "tail_polish",
    ]
    assert plan.total_cost == 10


@pytest.mark.parametrize(
    ("config_override", "allowed_resolutions", "reason"),
    [
        (
            {"video_scenes": []},
            ["512p"],
            QuickVideoSubmissionRejectReason.FEATURE_DISABLED,
        ),
        (
            {
                "video_scenes": [
                    {
                        "id": "missing",
                        "name": "缺失场景",
                        "prompt": "missing prompt",
                    }
                ]
            },
            ["512p"],
            QuickVideoSubmissionRejectReason.FEATURE_DISABLED,
        ),
        (
            {
                "video_scenes": [
                    {
                        "id": "scene",
                        "name": "场景",
                        "prompt": "scene prompt",
                        "duration": "10s",
                    }
                ]
            },
            ["1024p"],
            QuickVideoSubmissionRejectReason.INVALID_SETTINGS,
        ),
    ],
)
def test_qqcc_invalid_or_disabled_config_returns_reject(
    config_override,
    allowed_resolutions,
    reason,
):
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            **config_override,
        }
    )

    result = build_quick_video_submission_plan(
        fsm_data={
            "mode": MODE_CUSTOM_VIDEO,
            "scene_id": "scene",
            "resolution": "1024p",
            "duration": "10s",
        },
        qqcc_config=config,
        allowed_resolutions=allowed_resolutions,
    )

    assert result.reason == reason


@pytest.mark.asyncio
async def test_run_tail_frame_plan_skips_video_when_tail_generation_fails():
    plan = build_quick_video_submission_plan(
        fsm_data={
            "mode": MODE_CUSTOM_VIDEO,
            "scene_id": "tail_video",
            "resolution": "512p",
            "duration": "5s",
        },
        qqcc_config=normalize_qqcc_config(
            {
                "scene_preset_version": SCENE_PRESET_VERSION,
                "draw_scenes": [
                    {
                        "id": "tail_pose",
                        "name": "尾帧姿势",
                        "prompt": "tail prompt",
                    }
                ],
                "video_scenes": [
                    {
                        "id": "tail_video",
                        "name": "首尾动图",
                        "prompt": "video prompt",
                        "duration": "5s",
                        "end_frame_draw_scene_id": "tail_pose",
                    }
                ],
            }
        ),
        allowed_resolutions=["512p"],
    )
    cleanup_calls = []
    video_task = AsyncMock()

    async def fail_draw_chain(**_kwargs):
        return SimpleNamespace(local_output_path=None)

    await run_quick_video_submission_plan(
        plan=plan,
        context=SimpleNamespace(),
        chat_id=456,
        user_id=123,
        username="tester",
        image_path="/tmp/input.png",
        status_msg_id=77,
        process_video_task_template_func=video_task,
        process_generation_task_func=AsyncMock(),
        execute_draw_chain_func=fail_draw_chain,
        cleanup_temp_files_func=lambda paths: cleanup_calls.extend(paths),
    )

    video_task.assert_not_awaited()
    assert cleanup_calls == ["/tmp/input.png", None]
