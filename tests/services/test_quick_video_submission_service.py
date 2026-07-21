from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import quick_video_submission_service as quick_video_service
from src.constants import (
    MODE_CUSTOM_VIDEO,
    MODE_DOGGY_STYLE,
    MODE_IMAGE_TO_VIDEO,
    MODE_LTX_VIDEO,
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
    quick_video_plan_requires_continuation,
    run_quick_video_submission_plan,
)
from src.services.qqcc_video_frame_adapter import QqccVideoFrameAdaptationError


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
    assert plan.aspect_ratio == "source"


@pytest.mark.asyncio
async def test_main_bot_legacy_runner_does_not_invoke_qqcc_frame_adapter():
    plan = build_quick_video_submission_plan(
        fsm_data={"mode": MODE_DOGGY_STYLE, "resolution": "512p", "duration": "5s"},
        qqcc_config=None,
        allowed_resolutions=None,
    )
    video_task = AsyncMock()

    def unexpected_adapter(*_args, **_kwargs):
        raise AssertionError("main bot must not use the QQCC adapter")

    await run_quick_video_submission_plan(
        plan=plan,
        context=SimpleNamespace(),
        chat_id=1,
        user_id=2,
        username=None,
        image_path="/tmp/input.png",
        status_msg_id=None,
        process_video_task_template_func=video_task,
        adapt_video_frame_file_func=unexpected_adapter,
    )

    assert video_task.await_args.kwargs["image_path"] == "/tmp/input.png"
    assert "aspect_ratio" not in video_task.await_args.kwargs


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
                    "aspect_ratio": "9:16",
                    "lora_items": [
                        {"name": "BreastGrow", "strength": 0.75},
                        {"name": "Footjob", "strength": 1.4},
                    ],
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
    assert plan.lora_name == "wan22_explicit_077"
    assert plan.lora_items == [
        {"name": "wan22_explicit_077", "strength": 0.75},
        {"name": "wan22_explicit_040", "strength": 1.4},
    ]
    assert plan.allow_contribute is False
    assert plan.aspect_ratio == "9:16"
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
                    "lora_items": [
                        {"name": "BreastGrow", "strength": 0.75},
                        {"name": "Footjob", "strength": 1.4},
                    ],
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
    assert plan.lora_name == "wan22_explicit_077"
    assert plan.lora_items == [
        {"name": "wan22_explicit_077", "strength": 0.75},
        {"name": "wan22_explicit_040", "strength": 1.4},
    ]
    assert plan.allow_contribute is False
    assert plan.result_meta == {
        "_qqcc_regenerate": {
            "kind": "quick_video",
            "mode": MODE_WAN22_VIDEO_V2,
            "scene_id": "v2_scene",
            "display_mode_name": "新版动图",
        }
    }


def test_qqcc_ai_video_scene_builds_fixed_ltx_plan_with_negative_prompt_and_loras():
    config = normalize_qqcc_config(
        {
            "main_buttons": {"ai_video": True},
            "ai_video_scenes": [
                {
                    "id": "cinema",
                    "name": "电影运镜",
                    "prompt": "camera orbit",
                    "negative_prompt": "  blur, jitter  ",
                    "duration": 15,
                    "engine": "ltx_video",
                    "lora_items": [
                        {"path": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors", "strength": 0.75},
                    ],
                }
            ],
        }
    )

    plan = build_quick_video_submission_plan(
        fsm_data={"scene_kind": "ai_video", "scene_id": "cinema"},
        qqcc_config=config,
        allowed_resolutions=[],
    )

    assert plan.kind == QuickVideoSubmissionKind.LTX_VIDEO
    assert plan.mode == MODE_LTX_VIDEO
    assert plan.resolution == "1280x704"
    assert plan.duration == "15s"
    assert plan.total_cost == 30
    assert plan.negative_prompt == "blur, jitter"
    assert plan.lora_items == [
        {"name": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors", "strength": 0.75}
    ]
    assert plan.result_meta["_qqcc_regenerate"]["scene_kind"] == "ai_video"


def test_qqcc_ai_video_plan_submits_config_only_ltx_lora_to_worker():
    admin_only_path = "ltx2.3/SexGod_Nudity_LTX23_v2_0.safetensors"
    config = normalize_qqcc_config(
        {
            "main_buttons": {"ai_video": True},
            "ai_video_scenes": [
                {
                    "id": "admin_nudity",
                    "name": "后台写真",
                    "prompt": "LTXNUDES, natural full-body posing",
                    "duration": 5,
                    "lora_items": [{"path": admin_only_path}],
                }
            ],
        }
    )

    plan = build_quick_video_submission_plan(
        fsm_data={"scene_kind": "ai_video", "scene_id": "admin_nudity"},
        qqcc_config=config,
        allowed_resolutions=[],
    )

    assert plan.lora_items == [{"name": admin_only_path, "strength": 0.8}]


@pytest.mark.asyncio
async def test_run_qqcc_ai_video_uses_actor_service_and_omits_blank_negative_prompt():
    plan = build_quick_video_submission_plan(
        fsm_data={"scene_kind": "ai_video", "scene_id": "clean"},
        qqcc_config=normalize_qqcc_config(
            {
                "main_buttons": {"ai_video": True},
                "ai_video_scenes": [
                    {
                        "id": "clean",
                        "name": "清晰运镜",
                        "prompt": "smooth camera",
                        "negative_prompt": "   ",
                        "duration": 5,
                    }
                ],
            }
        ),
        allowed_resolutions=[],
    )
    ltx_task = AsyncMock()

    await run_quick_video_submission_plan(
        plan=plan,
        context=SimpleNamespace(),
        chat_id=456,
        user_id=123,
        username="tester",
        image_path="/tmp/input.png",
        status_msg_id=77,
        process_ltx_video_task_func=ltx_task,
    )

    assert ltx_task.await_args.kwargs["ltx_mode"] == "i2v"
    assert ltx_task.await_args.kwargs["resolution"] == "1280x704"
    assert "negative_prompt" not in ltx_task.await_args.kwargs


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
@pytest.mark.parametrize(
    ("video_engine", "expected_executor"),
    [
        ("image_to_video", "legacy_video"),
        ("wan22_video_v2", "generation"),
    ],
)
async def test_private_qqcc_tail_frame_video_uses_durable_continuation(
    monkeypatch,
    video_engine,
    expected_executor,
):
    config = normalize_qqcc_config(
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
                    "engine": video_engine,
                    "aspect_ratio": "16:9",
                    "lora_items": [
                        {"name": "BreastGrow", "strength": 0.75},
                        {"name": "Footjob", "strength": 1.4},
                    ],
                    "end_frame_draw_scene_id": "tail_pose",
                }
            ],
        }
    )
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
    image_task = AsyncMock()
    video_task = AsyncMock()
    create_checkpoint = AsyncMock(
        return_value=SimpleNamespace(chain_id="chain-video-1")
    )
    resume_checkpoint = AsyncMock()
    persist_input = AsyncMock(return_value="inputs/original.png")
    monkeypatch.setattr(
        quick_video_service,
        "create_private_qqcc_continuation",
        create_checkpoint,
    )
    monkeypatch.setattr(
        quick_video_service,
        "resume_private_qqcc_continuation",
        resume_checkpoint,
    )
    monkeypatch.setattr(
        quick_video_service,
        "persist_private_qqcc_continuation_input",
        persist_input,
    )

    assert quick_video_plan_requires_continuation(plan) is True
    context = SimpleNamespace(
        bot_data={
            "bot_client_type": "bot:qqcc-private:7",
            "private_qqcc_bot_id": 7,
        }
    )
    await run_quick_video_submission_plan(
        plan=plan,
        context=context,
        chat_id=456,
        user_id=123,
        username="tester",
        image_path="/tmp/input.png",
        status_msg_id=77,
        process_generation_task_func=image_task,
        process_video_task_template_func=video_task,
        adapt_video_frame_file_func=lambda path, **_kwargs: path,
    )

    image_task.assert_not_awaited()
    video_task.assert_not_awaited()
    stages = create_checkpoint.await_args.kwargs["stages"]
    assert create_checkpoint.await_args.kwargs["original_input_ref"] == (
        "inputs/original.png"
    )
    assert create_checkpoint.await_args.kwargs["original_input_durable"] is True
    assert len(stages) == 2
    assert stages[0]["task_kwargs"]["send_result"] is False
    assert stages[0]["task_kwargs"]["show_queue_status"] is True
    assert stages[1]["executor"] == expected_executor
    assert stages[1]["delivery_required"] is True
    assert stages[1]["task_kwargs"]["send_result"] is True
    assert stages[1]["task_kwargs"]["delete_status"] is True
    assert stages[1]["task_kwargs"]["user_cancel_allowed"] is False
    assert stages[1]["task_kwargs"]["show_queue_status"] is False
    assert stages[1]["task_kwargs"]["lora_items"] == [
        {"name": "wan22_explicit_077", "strength": 0.75},
        {"name": "wan22_explicit_040", "strength": 1.4},
    ]
    assert stages[1]["task_kwargs"]["_qqcc_aspect_ratio"] == "16:9"
    resume_checkpoint.assert_awaited_once()
    assert resume_checkpoint.await_args.kwargs["chain_id"] == "chain-video-1"
    assert callable(resume_checkpoint.await_args.kwargs["execute_stage_func"])


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
        context=SimpleNamespace(
            bot_data={
                "bot_client_type": "bot:qqcc-private:7",
                "private_qqcc_bot_id": 7,
            }
        ),
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
    assert video_task.await_args.kwargs["lora_items"] == plan.lora_items


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "expected_key"),
    [
        (QuickVideoSubmissionKind.LEGACY_VIDEO, "image_path"),
        (QuickVideoSubmissionKind.WAN22_VIDEO_V2, "images"),
    ],
)
async def test_qqcc_video_runner_adapts_input_before_task_submission(kind, expected_key):
    base_plan = build_quick_video_submission_plan(
        fsm_data={"mode": MODE_CUSTOM_VIDEO, "scene_id": "scene", "resolution": "512p"},
        qqcc_config=normalize_qqcc_config(
            {
                "video_scenes": [
                    {
                        "id": "scene",
                        "name": "动图",
                        "prompt": "move",
                        "engine": "image_to_video",
                        "aspect_ratio": "9:16",
                    }
                ]
            }
        ),
        allowed_resolutions=["512p"],
    )
    plan = replace(
        base_plan,
        kind=kind,
        mode=MODE_WAN22_VIDEO_V2 if kind == QuickVideoSubmissionKind.WAN22_VIDEO_V2 else MODE_IMAGE_TO_VIDEO,
    )
    video_task = AsyncMock()
    generation_task = AsyncMock()
    cleanup_calls = []
    adapter_calls = []

    def adapt(path, *, aspect_ratio):
        adapter_calls.append((path, aspect_ratio))
        return "/tmp/adapted.png"

    await run_quick_video_submission_plan(
        plan=plan,
        context=SimpleNamespace(),
        chat_id=1,
        user_id=2,
        username="tester",
        image_path="/tmp/input.png",
        status_msg_id=3,
        process_video_task_template_func=video_task,
        process_generation_task_func=generation_task,
        adapt_video_frame_file_func=adapt,
        cleanup_temp_files_func=lambda paths: cleanup_calls.extend(paths),
    )

    assert adapter_calls == [("/tmp/input.png", "9:16")]
    assert cleanup_calls == ["/tmp/input.png"]
    submitted = (
        video_task.await_args.kwargs[expected_key]
        if kind == QuickVideoSubmissionKind.LEGACY_VIDEO
        else generation_task.await_args.kwargs[expected_key]
    )
    assert submitted == "/tmp/adapted.png" if expected_key == "image_path" else ["/tmp/adapted.png"]


@pytest.mark.asyncio
async def test_qqcc_video_adapter_failure_stops_submission_and_cleans_input():
    plan = build_quick_video_submission_plan(
        fsm_data={"mode": MODE_CUSTOM_VIDEO, "scene_id": "scene", "resolution": "512p"},
        qqcc_config=normalize_qqcc_config(
            {
                "video_scenes": [
                    {
                        "id": "scene",
                        "name": "动图",
                        "prompt": "move",
                        "aspect_ratio": "1:1",
                    }
                ]
            }
        ),
        allowed_resolutions=["512p"],
    )
    video_task = AsyncMock()
    cleanup_calls = []

    def fail_adaptation(*_args, **_kwargs):
        raise QqccVideoFrameAdaptationError("broken")

    with pytest.raises(QqccVideoFrameAdaptationError):
        await run_quick_video_submission_plan(
            plan=plan,
            context=SimpleNamespace(),
            chat_id=1,
            user_id=2,
            username=None,
            image_path="/tmp/input.png",
            status_msg_id=None,
            process_video_task_template_func=video_task,
            adapt_video_frame_file_func=fail_adaptation,
            cleanup_temp_files_func=lambda paths: cleanup_calls.extend(paths),
        )

    video_task.assert_not_awaited()
    assert cleanup_calls == ["/tmp/input.png"]


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
    assert video_task.await_args.kwargs["show_queue_status"] is False
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
                        "aspect_ratio": "1:1",
                        "lora_items": [
                            {"name": "BreastGrow", "strength": 0.75},
                            {"name": "Footjob", "strength": 1.4},
                        ],
                        "end_frame_draw_scene_id": "tail_pose",
                    }
                ],
            }
        ),
        allowed_resolutions=["720p"],
    )
    generation_task = AsyncMock()
    adapter_calls = []

    async def fake_draw_chain(**kwargs):
        assert kwargs["image_path"] == "/tmp/start-square.png"
        return SimpleNamespace(local_output_path="/tmp/end.png")

    def fake_adapter(path, *, aspect_ratio):
        adapter_calls.append((path, aspect_ratio))
        return {
            "/tmp/input.png": "/tmp/start-square.png",
            "/tmp/end.png": "/tmp/end-square.png",
        }[path]

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
        adapt_video_frame_file_func=fake_adapter,
    )

    assert generation_task.await_args.kwargs["task_type"] == MODE_WAN22_VIDEO_V2
    assert generation_task.await_args.kwargs["lora_items"] == plan.lora_items
    assert generation_task.await_args.kwargs["images"] == [
        "/tmp/start-square.png",
        "/tmp/end-square.png",
    ]
    assert adapter_calls == [
        ("/tmp/input.png", "1:1"),
        ("/tmp/end.png", "1:1"),
    ]
    assert generation_task.await_args.kwargs["allow_cancel"] is False
    assert generation_task.await_args.kwargs["user_cancel_allowed"] is False
    assert generation_task.await_args.kwargs["base_priority"] == 100
    assert generation_task.await_args.kwargs["show_queue_status"] is False


@pytest.mark.asyncio
async def test_run_tail_frame_ltx_final_video_hides_continuation_queue_status():
    plan = build_quick_video_submission_plan(
        fsm_data={"scene_kind": "ai_video", "scene_id": "cinema_tail"},
        qqcc_config=normalize_qqcc_config(
            {
                "main_buttons": {"ai_video": True},
                "draw_scenes": [
                    {
                        "id": "tail_pose",
                        "name": "尾帧姿势",
                        "prompt": "tail prompt",
                    }
                ],
                "ai_video_scenes": [
                    {
                        "id": "cinema_tail",
                        "name": "电影首尾",
                        "prompt": "camera orbit",
                        "duration": 5,
                        "engine": "ltx_video",
                        "end_frame_draw_scene_id": "tail_pose",
                    }
                ],
            }
        ),
        allowed_resolutions=[],
    )
    ltx_task = AsyncMock()

    async def fake_draw_chain(**_kwargs):
        return SimpleNamespace(local_output_path="/tmp/end.png")

    assert plan.kind == QuickVideoSubmissionKind.LTX_TAIL_FRAME_VIDEO

    await run_quick_video_submission_plan(
        plan=plan,
        context=SimpleNamespace(),
        chat_id=456,
        user_id=123,
        username="tester",
        image_path="/tmp/input.png",
        status_msg_id=77,
        process_ltx_video_task_func=ltx_task,
        process_generation_task_func=AsyncMock(),
        execute_draw_chain_func=fake_draw_chain,
    )

    assert ltx_task.await_args.kwargs["ltx_mode"] == "flf2v"
    assert ltx_task.await_args.kwargs["end_image_path"] == "/tmp/end.png"
    assert ltx_task.await_args.kwargs["allow_cancel"] is False
    assert ltx_task.await_args.kwargs["user_cancel_allowed"] is False
    assert ltx_task.await_args.kwargs["base_priority"] == 100
    assert ltx_task.await_args.kwargs["show_queue_status"] is False
