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
    assert plan.allow_contribute is True
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
                    "negative_prompt": "video bad hands",
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
    assert plan.negative_prompt == "video bad hands"
    assert plan.display_mode_name == "模型动图"
    assert plan.lora_name == "BreastGrow"
    assert plan.allow_contribute is False
    assert plan.result_meta == {
        "_qqcc_regenerate": {
            "kind": "quick_video",
            "mode": MODE_IMAGE_TO_VIDEO,
            "scene_id": "lora_scene",
            "display_mode_name": "模型动图",
        }
    }


def test_qqcc_wan22_v2_scene_builds_v2_plan_and_normalizes_resolution():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "video_scenes": [
                {
                    "id": "v2_scene",
                    "name": "新版动图",
                    "prompt": "v2 scene prompt",
                    "negative_prompt": "v2 blur",
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
    assert plan.negative_prompt == "v2 blur"
    assert plan.display_mode_name == "新版动图"
    assert plan.lora_name == ""
    assert plan.allow_contribute is False
    assert plan.result_meta == {
        "_qqcc_regenerate": {
            "kind": "quick_video",
            "mode": MODE_WAN22_VIDEO_V2,
            "scene_id": "v2_scene",
            "display_mode_name": "新版动图",
        }
    }


def test_qqcc_tail_frame_scene_adds_draw_chain_cost():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "tail_pose",
                    "name": "尾帧姿势",
                    "prompt": "tail prompt",
                    "negative_prompt": "tail bad anatomy",
                    "original_face_swap_enabled": True,
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
                    "negative_prompt": "video blur",
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
    assert plan.tail_draw_chain[0]["negative_prompt"] == "tail bad anatomy"
    assert plan.negative_prompt == "video blur"
    assert plan.total_cost == 12
    assert plan.allow_contribute is False
    assert plan.result_meta == {
        "_qqcc_regenerate": {
            "kind": "quick_video",
            "mode": MODE_CUSTOM_VIDEO,
            "scene_id": "tail_video",
            "display_mode_name": "首尾动图",
        }
    }


@pytest.mark.asyncio
async def test_run_qqcc_legacy_video_plan_passes_scene_negative_prompt():
    plan = build_quick_video_submission_plan(
        fsm_data={
            "mode": MODE_CUSTOM_VIDEO,
            "scene_id": "lora_scene",
            "resolution": "720p",
            "duration": "5s",
        },
        qqcc_config=normalize_qqcc_config(
            {
                "scene_preset_version": SCENE_PRESET_VERSION,
                "video_scenes": [
                    {
                        "id": "lora_scene",
                        "name": "模型动图",
                        "prompt": "lora scene prompt",
                        "negative_prompt": "video bad hands",
                        "duration": "5s",
                        "engine": "image_to_video",
                        "lora_name": "BreastGrow",
                    }
                ],
            }
        ),
        allowed_resolutions=["720p"],
    )
    video_task = AsyncMock()

    await run_quick_video_submission_plan(
        plan=plan,
        context=SimpleNamespace(),
        chat_id=456,
        user_id=123,
        username="tester",
        image_path="/tmp/input.png",
        status_msg_id=77,
        process_video_task_template_func=video_task,
    )

    assert video_task.await_args.kwargs["negative_prompt"] == "video bad hands"
    assert video_task.await_args.kwargs["allow_contribute"] is False
    assert "allow_cancel" not in video_task.await_args.kwargs
    assert "user_cancel_allowed" not in video_task.await_args.kwargs
    assert "base_priority" not in video_task.await_args.kwargs
    assert video_task.await_args.kwargs["display_mode_name_override"] == "模型动图"
    assert video_task.await_args.kwargs["result_meta"] == plan.result_meta


@pytest.mark.asyncio
async def test_run_qqcc_wan22_v2_video_plan_passes_scene_negative_prompt():
    plan = build_quick_video_submission_plan(
        fsm_data={
            "mode": MODE_CUSTOM_VIDEO,
            "scene_id": "v2_scene",
            "resolution": "720p",
            "duration": "5s",
        },
        qqcc_config=normalize_qqcc_config(
            {
                "scene_preset_version": SCENE_PRESET_VERSION,
                "video_scenes": [
                    {
                        "id": "v2_scene",
                        "name": "新版动图",
                        "prompt": "v2 scene prompt",
                        "negative_prompt": "v2 blur",
                        "duration": "5s",
                        "engine": "wan22_video_v2",
                    }
                ],
            }
        ),
        allowed_resolutions=["720p"],
    )
    generation_task = AsyncMock()

    await run_quick_video_submission_plan(
        plan=plan,
        context=SimpleNamespace(),
        chat_id=456,
        user_id=123,
        username="tester",
        image_path="/tmp/input.png",
        status_msg_id=77,
        process_generation_task_func=generation_task,
    )

    assert generation_task.await_args.kwargs["negative_prompt"] == "v2 blur"
    assert generation_task.await_args.kwargs["allow_contribute"] is False
    assert "allow_cancel" not in generation_task.await_args.kwargs
    assert "user_cancel_allowed" not in generation_task.await_args.kwargs
    assert "base_priority" not in generation_task.await_args.kwargs
    assert generation_task.await_args.kwargs["display_mode_name_override"] == "新版动图"
    assert generation_task.await_args.kwargs["result_meta"] == plan.result_meta


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


@pytest.mark.asyncio
async def test_run_tail_frame_plan_keeps_tail_draw_and_video_negative_prompts_separate():
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
                        "negative_prompt": "tail blur",
                    }
                ],
                "video_scenes": [
                    {
                        "id": "tail_video",
                        "name": "首尾动图",
                        "prompt": "video prompt",
                        "negative_prompt": "video blur",
                        "duration": "5s",
                        "end_frame_draw_scene_id": "tail_pose",
                    }
                ],
            }
        ),
        allowed_resolutions=["512p"],
    )
    video_task = AsyncMock()
    draw_chains = []

    async def fake_draw_chain(**kwargs):
        draw_chains.append(kwargs["chain"])
        return SimpleNamespace(local_output_path="/tmp/end.png")

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
        execute_draw_chain_func=fake_draw_chain,
    )

    assert draw_chains[0][0]["negative_prompt"] == "tail blur"
    assert video_task.await_args.kwargs["negative_prompt"] == "video blur"
    assert video_task.await_args.kwargs["allow_contribute"] is False
    assert video_task.await_args.kwargs["allow_cancel"] is False
    assert video_task.await_args.kwargs["user_cancel_allowed"] is False
    assert video_task.await_args.kwargs["base_priority"] == 100
    assert video_task.await_args.kwargs["display_mode_name_override"] == "首尾动图"
    assert video_task.await_args.kwargs["result_meta"] == plan.result_meta


@pytest.mark.asyncio
async def test_run_tail_frame_wan22_v2_final_video_is_locked_continuation():
    plan = build_quick_video_submission_plan(
        fsm_data={
            "mode": MODE_CUSTOM_VIDEO,
            "scene_id": "tail_v2_video",
            "resolution": "720p",
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
                        "id": "tail_v2_video",
                        "name": "首尾新版动图",
                        "prompt": "video prompt",
                        "negative_prompt": "video blur",
                        "duration": "5s",
                        "engine": "wan22_video_v2",
                        "end_frame_draw_scene_id": "tail_pose",
                    }
                ],
            }
        ),
        allowed_resolutions=["720p"],
    )
    generation_task = AsyncMock()

    async def fake_draw_chain(**_kwargs):
        return SimpleNamespace(local_output_path="/tmp/end.png")

    await run_quick_video_submission_plan(
        plan=plan,
        context=SimpleNamespace(),
        chat_id=456,
        user_id=123,
        username="tester",
        image_path="/tmp/input.png",
        status_msg_id=77,
        process_generation_task_func=generation_task,
        execute_draw_chain_func=fake_draw_chain,
    )

    assert generation_task.await_args.kwargs["task_type"] == MODE_WAN22_VIDEO_V2
    assert generation_task.await_args.kwargs["images"] == [
        "/tmp/input.png",
        "/tmp/end.png",
    ]
    assert generation_task.await_args.kwargs["allow_cancel"] is False
    assert generation_task.await_args.kwargs["user_cancel_allowed"] is False
    assert generation_task.await_args.kwargs["base_priority"] == 100
