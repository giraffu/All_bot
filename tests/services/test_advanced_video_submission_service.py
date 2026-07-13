from types import SimpleNamespace
from unittest.mock import Mock

from src.constants import MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO, MODE_WAN22_VIDEO_V2
from src.services.advanced_video_submission_service import (
    AdvancedVideoSubmissionKind,
    AdvancedVideoSubmissionRejectReason,
    build_image_to_video_submission_plan,
    build_ltx_video_submission_plan,
    build_wan22_video_v2_submission_plan,
    create_image_to_video_submission_task,
    create_ltx_video_submission_task,
    create_wan22_video_v2_submission_task,
)


def test_image_to_video_plan_normalizes_settings_and_keeps_end_frame_payload():
    plan = build_image_to_video_submission_plan(
        fsm_data={
            "resolution": "1024p",
            "duration": "10s",
            "lora_name": "BreastGrow",
            "image_path": "/tmp/start.png",
            "end_image_path": "/tmp/end.png",
            "use_end_frame": True,
        },
        conversation_tag="IMAGE_TO_VIDEO",
        prompt="move gently",
    )

    assert plan.kind == AdvancedVideoSubmissionKind.IMAGE_TO_VIDEO
    assert plan.task_type == MODE_IMAGE_TO_VIDEO
    assert plan.resolution_preset == "hd"
    assert plan.duration == 10
    assert plan.cost == 90
    assert plan.images == ["/tmp/start.png", "/tmp/end.png"]
    assert plan.use_end_frame is True
    assert plan.lora_name == "BreastGrow"


def test_image_to_video_plan_uses_custom_video_task_type_for_compat_entry():
    plan = build_image_to_video_submission_plan(
        fsm_data={
            "resolution": "720p",
            "duration": "8s",
            "lora_name": "",
            "image_path": "/tmp/start.png",
        },
        conversation_tag="CUSTOM_VIDEO",
        prompt="custom prompt",
    )

    assert plan.task_type == MODE_CUSTOM_VIDEO
    assert plan.resolution_preset == "standard"
    assert plan.duration == 8
    assert plan.cost == 40


def test_image_to_video_plan_rejects_missing_start_image():
    result = build_image_to_video_submission_plan(
        fsm_data={"resolution": "720p", "duration": "5s"},
        conversation_tag="IMAGE_TO_VIDEO",
        prompt="prompt",
    )

    assert result.reason == AdvancedVideoSubmissionRejectReason.MISSING_INPUT


def test_create_image_to_video_submission_task_calls_existing_entrypoint():
    plan = build_image_to_video_submission_plan(
        fsm_data={
            "resolution": "720p",
            "duration": "8s",
            "lora_name": "BreastGrow",
            "image_path": "/tmp/start.png",
        },
        conversation_tag="IMAGE_TO_VIDEO",
        prompt="prompt",
    )
    process_task = Mock(return_value=("bg-task",))

    task = create_image_to_video_submission_task(
        plan=plan,
        context=SimpleNamespace(),
        chat_id=456,
        user_id=123,
        username="tester",
        process_image_to_video_task_func=process_task,
    )

    assert task == ("bg-task",)
    assert process_task.call_args.kwargs["task_type"] == MODE_IMAGE_TO_VIDEO
    assert process_task.call_args.kwargs["resolution"] == "standard"
    assert process_task.call_args.kwargs["duration"] == 8


def test_wan22_v2_plan_adds_extension_chain_meta():
    plan = build_wan22_video_v2_submission_plan(
        data={
            "start_image_path": "/tmp/start.png",
            "use_end_frame": False,
            "resolution_preset": "standard",
            "duration": 5,
            "prompt": "continue",
            "negative_prompt": "bad",
            "extension_prev_task_id": "task-1",
            "chain_task_ids": ["task-1"],
        }
    )

    assert plan.kind == AdvancedVideoSubmissionKind.WAN22_VIDEO_V2
    assert plan.task_type == MODE_WAN22_VIDEO_V2
    assert plan.cost == 20
    assert plan.images == ["/tmp/start.png"]
    assert plan.result_meta == {
        "wan22_prev_task_id": "task-1",
        "wan22_chain_task_ids": ["task-1"],
    }


def test_wan22_legacy_extension_plan_routes_to_image_to_video_entrypoint():
    plan = build_wan22_video_v2_submission_plan(
        data={
            "start_image_path": "/tmp/start.png",
            "use_end_frame": False,
            "resolution_preset": "standard",
            "duration": 5,
            "prompt": "continue",
            "negative_prompt": "bad",
            "extension_prev_task_id": "task-1",
            "extension_task_type": MODE_IMAGE_TO_VIDEO,
            "chain_task_ids": ["task-1"],
            "lora_name": "BreastGrow",
            "lora_strength": 1.2,
        }
    )

    assert plan.kind == AdvancedVideoSubmissionKind.LEGACY_WAN22_IMAGE_TO_VIDEO
    assert plan.task_type == MODE_IMAGE_TO_VIDEO
    assert plan.wan22_prev_task_id == "task-1"
    assert plan.wan22_chain_task_ids == ["task-1"]
    assert plan.lora_name == "BreastGrow"
    assert plan.lora_strength == 1.2


def test_create_wan22_submission_task_uses_legacy_or_v2_entrypoint():
    legacy_plan = build_wan22_video_v2_submission_plan(
        data={
            "start_image_path": "/tmp/start.png",
            "resolution_preset": "preview",
            "duration": 5,
            "prompt": "legacy",
            "extension_task_type": MODE_IMAGE_TO_VIDEO,
        }
    )
    v2_task = Mock(return_value=("v2-task",))
    legacy_task = Mock(return_value=("legacy-task",))

    task = create_wan22_video_v2_submission_task(
        plan=legacy_plan,
        context=SimpleNamespace(),
        chat_id=456,
        user_id=123,
        username="tester",
        process_wan22_video_v2_task_func=v2_task,
        process_image_to_video_task_func=legacy_task,
    )

    assert task == ("legacy-task",)
    v2_task.assert_not_called()
    assert legacy_task.call_args.kwargs["task_type"] == MODE_IMAGE_TO_VIDEO


def test_ltx_plan_keeps_lora_items_and_extension_chain_context():
    plan = build_ltx_video_submission_plan(
        fsm_data={
            "resolution": "1280x704",
            "duration": "10s",
            "ltx_mode": "i2v",
            "prompt": "continue motion",
            "image_path": "/tmp/start.png",
            "extension_prev_task_id": "ltx-task-2",
            "chain_task_ids": ["ltx-task-1", "ltx-task-2"],
            "lora_items": [
                {
                    "name": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
                    "strength": 0.8,
                }
            ],
        }
    )

    assert plan.kind == AdvancedVideoSubmissionKind.LTX_VIDEO
    assert plan.cost == 20
    assert plan.ltx_mode == "i2v"
    assert plan.image_path == "/tmp/start.png"
    assert plan.ltx_prev_task_id == "ltx-task-2"
    assert plan.ltx_chain_task_ids == ["ltx-task-1", "ltx-task-2"]
    assert plan.lora_name == "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors"
    assert plan.lora_strength == 0.8
    assert plan.lora_items == [
        {
            "name": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
            "strength": 0.8,
        }
    ]


def test_ltx_plan_rejects_disabled_video_audio_mode_before_quota():
    result = build_ltx_video_submission_plan(
        fsm_data={
            "resolution": "1280x704",
            "duration": "5s",
            "ltx_mode": "v2v_audio",
            "prompt": "talk",
            "video_path": "/tmp/input.mp4",
        }
    )

    assert result.reason == AdvancedVideoSubmissionRejectReason.DISABLED_MODE


def test_create_ltx_submission_task_calls_existing_entrypoint():
    plan = build_ltx_video_submission_plan(
        fsm_data={
            "resolution": "1280x704",
            "duration": "5s",
            "ltx_mode": "flf2v",
            "prompt": "bridge",
            "image_path": "/tmp/start.png",
            "end_image_path": "/tmp/end.png",
        }
    )
    process_task = Mock(return_value=("ltx-task",))
    update = SimpleNamespace()
    context = SimpleNamespace()

    task = create_ltx_video_submission_task(
        plan=plan,
        update=update,
        context=context,
        process_ltx_video_task_func=process_task,
    )

    assert task == ("ltx-task",)
    assert process_task.call_args.kwargs["ltx_mode"] == "flf2v"
    assert process_task.call_args.kwargs["resolution"] == "1280x704"
    assert process_task.call_args.kwargs["duration"] == "5s"
    assert process_task.call_args.kwargs["image_path"] == "/tmp/start.png"
    assert process_task.call_args.kwargs["end_image_path"] == "/tmp/end.png"
