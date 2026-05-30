from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import task_service_entrypoints_generation
from src.services import task_service_generation_image
from src.services import task_service_generation_video
from src.services import task_service_generation_wan22


@pytest.mark.asyncio
async def test_process_image_to_video_task_delegates_to_video_family_module(monkeypatch):
    delegate = AsyncMock(return_value=(b"video-bytes", "video-task"))
    context = SimpleNamespace()
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "process_image_to_video_generation_task",
        delegate,
    )

    result = await task_service_entrypoints_generation.process_image_to_video_task(
        context=context,
        chat_id=123,
        user_id=456,
        username="tester",
        prompt="prompt",
        images=["start.png"],
        resolution="720p",
        duration="8s",
        status_msg_id=10,
        delete_status=False,
        task_type="custom_video",
        cleanup=False,
        send_result=False,
        deduct_quota=False,
        reply_markup="markup",
        lora_name="demo-lora",
        lora_strength=0.6,
        allow_contribute=False,
        source_post_id=99,
    )

    assert result == (b"video-bytes", "video-task")
    delegate.assert_awaited_once_with(
        context=context,
        chat_id=123,
        user_id=456,
        username="tester",
        prompt="prompt",
        images=["start.png"],
        resolution="720p",
        duration="8s",
        status_msg_id=10,
        delete_status=False,
        task_type="custom_video",
        cleanup=False,
        send_result=False,
        deduct_quota=False,
        reply_markup="markup",
        lora_name="demo-lora",
        lora_strength=0.6,
        allow_contribute=False,
        source_post_id=99,
    )


@pytest.mark.asyncio
async def test_process_generation_task_delegates_to_standard_generation_module(monkeypatch):
    delegate = AsyncMock(return_value=(b"image-bytes", "image-task"))
    context = SimpleNamespace()
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "process_standard_generation_task",
        delegate,
    )

    result = await task_service_entrypoints_generation.process_generation_task(
        context=context,
        chat_id=321,
        user_id=654,
        username="tester",
        prompt="prompt",
        images=["input.png"],
        is_video=False,
        status_msg_id=11,
        delete_status=False,
        task_type="image",
        cleanup=False,
        send_result=False,
        deduct_quota=False,
        reply_markup="markup",
        lora_name="demo-lora",
        lora_strength=0.8,
        allow_contribute=False,
        source_post_id=101,
        resolution="512",
        duration="5",
    )

    assert result == (b"image-bytes", "image-task")
    delegate.assert_awaited_once_with(
        context=context,
        chat_id=321,
        user_id=654,
        username="tester",
        prompt="prompt",
        images=["input.png"],
        is_video=False,
        status_msg_id=11,
        delete_status=False,
        task_type="image",
        cleanup=False,
        send_result=False,
        deduct_quota=False,
        reply_markup="markup",
        lora_name="demo-lora",
        lora_strength=0.8,
        allow_contribute=False,
        source_post_id=101,
        resolution="512",
        duration="5",
    )


@pytest.mark.asyncio
async def test_process_wan22_video_v2_task_delegates_to_wan22_family_module(monkeypatch):
    delegate = AsyncMock(return_value=(b"video-bytes", "wan22-task"))
    context = SimpleNamespace()
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "process_wan22_video_v2_generation_task",
        delegate,
    )

    result = await task_service_entrypoints_generation.process_wan22_video_v2_task(
        context=context,
        chat_id=222,
        user_id=333,
        username="tester",
        prompt="prompt",
        negative_prompt="negative",
        images=["start.png", "end.png"],
        use_end_frame=True,
        color_match=True,
        perfect_loop=False,
        upscale=True,
        extract_last_frame=True,
        status_msg_id=12,
        delete_status=False,
        cleanup=False,
        send_result=False,
        deduct_quota=False,
        reply_markup="markup",
        allow_contribute=False,
        source_post_id=77,
    )

    assert result == (b"video-bytes", "wan22-task")
    delegate.assert_awaited_once_with(
        context=context,
        chat_id=222,
        user_id=333,
        username="tester",
        prompt="prompt",
        negative_prompt="negative",
        images=["start.png", "end.png"],
        use_end_frame=True,
        color_match=True,
        perfect_loop=False,
        upscale=True,
        extract_last_frame=True,
        status_msg_id=12,
        delete_status=False,
        task_type="wan22_video_v2",
        cleanup=False,
        send_result=False,
        deduct_quota=False,
        reply_markup="markup",
        allow_contribute=False,
        source_post_id=77,
    )


@pytest.mark.asyncio
async def test_process_image_to_video_generation_task_builds_flow_context(monkeypatch):
    captured = {}

    async def fake_run_bot_task_application(*, flow):
        captured["flow"] = flow
        return (b"video-bytes", "video-task")

    def fake_build_generation_flow_context(**kwargs):
        captured["flow_kwargs"] = kwargs
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        task_service_generation_video,
        "resolve_internal_user_id",
        AsyncMock(return_value=456),
    )
    monkeypatch.setattr(
        task_service_generation_video,
        "resolve_custom_video_settings",
        AsyncMock(return_value=("720p", "8s", 720, 8)),
    )
    monkeypatch.setattr(
        task_service_generation_video,
        "get_acceleration_notice",
        AsyncMock(return_value="notice"),
    )
    monkeypatch.setattr(
        task_service_generation_video,
        "resolve_generation_display_mode_name",
        lambda *_args, **_kwargs: "测试模式",
    )
    monkeypatch.setattr(
        task_service_generation_video,
        "build_task_inputs",
        lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(
        task_service_generation_video,
        "translate_context_text",
        lambda _context, key, **kwargs: f"{key}:{kwargs}" if kwargs else key,
    )
    monkeypatch.setattr(
        task_service_generation_video,
        "build_generation_message_spec",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        task_service_generation_video,
        "build_generation_completion_caption",
        lambda *_args, **_kwargs: "task.status_completion_mode:测试模式",
    )
    monkeypatch.setattr(
        task_service_generation_video,
        "build_log_prompt",
        lambda *_args, **_kwargs: "log-prompt",
    )
    monkeypatch.setattr(
        task_service_generation_video,
        "resolve_generation_billing_args",
        lambda **_kwargs: {
            "billing_resolution": "720p",
            "requested_duration": 8,
        },
    )
    monkeypatch.setattr(
        task_service_generation_video,
        "build_generation_submitted_status_builder",
        lambda *_args, **_kwargs: (lambda cost: f"submitted:{cost}"),
    )
    monkeypatch.setattr(
        task_service_generation_video,
        "build_generation_flow_context",
        fake_build_generation_flow_context,
    )
    monkeypatch.setattr(
        task_service_generation_video,
        "run_bot_task_application",
        fake_run_bot_task_application,
    )

    result = await task_service_generation_video.process_image_to_video_generation_task(
        context=SimpleNamespace(),
        chat_id=123,
        user_id=789,
        username="tester",
        prompt="prompt",
        images=["start.png"],
        resolution="720p",
        duration="8s",
        delete_status=False,
        cleanup=False,
        deduct_quota=False,
        allow_contribute=False,
    )

    assert result == (b"video-bytes", "video-task")
    flow = captured["flow"]
    flow_kwargs = captured["flow_kwargs"]
    assert flow.chat_id == 123
    assert flow.internal_user_id == 456
    assert flow.prompt == "log-prompt"
    assert flow.is_video is True
    assert flow.delete_status is False
    assert flow.allow_contribute is False
    assert flow.message_spec.progress_wait_text == "task.status_wait_generating_video"
    assert flow.message_spec.completion_caption == "task.status_completion_mode:测试模式"
    assert flow.billing_resolution == "720p"
    assert flow.requested_duration == 8
    assert flow.cleanup is False
    assert flow_kwargs["inputs"]["resolution"] == 720
    assert flow_kwargs["inputs"]["duration"] == 8


@pytest.mark.asyncio
async def test_process_generation_task_builds_flow_context_for_image_tasks(monkeypatch):
    captured = {}

    async def fake_run_bot_task_application(*, flow):
        captured["flow"] = flow
        return (b"image-bytes", "image-task")

    def fake_build_generation_flow_context(**kwargs):
        captured["flow_kwargs"] = kwargs
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        task_service_generation_image,
        "resolve_internal_user_id",
        AsyncMock(return_value=654),
    )
    monkeypatch.setattr(
        task_service_generation_image,
        "get_acceleration_notice",
        AsyncMock(return_value=""),
    )
    monkeypatch.setattr(
        task_service_generation_image,
        "build_task_inputs",
        lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(
        task_service_generation_image,
        "translate_context_text",
        lambda _context, key, **kwargs: f"{key}:{kwargs}" if kwargs else key,
    )
    monkeypatch.setattr(
        task_service_generation_image,
        "build_generation_message_spec",
        lambda **kwargs: SimpleNamespace(
            missing_output_message="task.status_missing_output_refunded",
            cancellation_message_template="task.status_cancelled_refunded:{cost}",
            **kwargs,
        ),
    )
    monkeypatch.setattr(
        task_service_generation_image,
        "build_generation_completion_caption",
        lambda *_args, **_kwargs: "task.status_completion_mode:image",
    )
    monkeypatch.setattr(
        task_service_generation_image,
        "build_log_prompt",
        lambda *_args, **_kwargs: "image-log",
    )
    monkeypatch.setattr(
        task_service_generation_image,
        "resolve_generation_billing_args",
        lambda **_kwargs: {
            "billing_resolution": "512",
            "requested_duration": 5,
        },
    )
    monkeypatch.setattr(
        task_service_generation_image,
        "build_generation_submitted_status_builder",
        lambda *_args, **_kwargs: (lambda cost: f"submitted:{cost}"),
    )
    monkeypatch.setattr(
        task_service_generation_image,
        "build_generation_flow_context",
        fake_build_generation_flow_context,
    )
    monkeypatch.setattr(
        task_service_generation_image,
        "run_bot_task_application",
        fake_run_bot_task_application,
    )

    result = await task_service_generation_image.process_standard_generation_task(
        context=SimpleNamespace(),
        chat_id=321,
        user_id=987,
        username="tester",
        prompt="prompt",
        images=["input.png"],
        is_video=False,
        task_type=None,
        cleanup=False,
        deduct_quota=False,
    )

    assert result == (b"image-bytes", "image-task")
    flow = captured["flow"]
    flow_kwargs = captured["flow_kwargs"]
    assert flow.chat_id == 321
    assert flow.internal_user_id == 654
    assert flow.task_type == "image"
    assert flow.prompt == "image-log"
    assert flow.is_video is False
    assert flow.message_spec.missing_output_message == "task.status_missing_output_refunded"
    assert flow.message_spec.completion_caption == "task.status_completion_mode:image"
    assert flow.message_spec.cancellation_message_template.startswith(
        "task.status_cancelled_refunded"
    )
    assert flow.billing_resolution == "512"
    assert flow.requested_duration == 5
    assert flow.cleanup is False
    assert flow_kwargs["inputs"]["images"] == ["input.png"]
    assert flow_kwargs["inputs"]["resolution"] == 512
    assert flow_kwargs["inputs"]["duration"] == 5


@pytest.mark.asyncio
async def test_process_wan22_video_v2_generation_task_builds_message_and_status_templates(
    monkeypatch,
):
    captured = {}

    async def fake_run_bot_task_application(*, flow):
        captured["flow"] = flow
        return (b"video-bytes", "wan22-task")

    def fake_build_generation_flow_context(**kwargs):
        captured["flow_kwargs"] = kwargs
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        task_service_generation_wan22,
        "resolve_internal_user_id",
        AsyncMock(return_value=777),
    )
    monkeypatch.setattr(
        task_service_generation_wan22,
        "get_acceleration_notice",
        AsyncMock(return_value="notice"),
    )
    monkeypatch.setattr(
        task_service_generation_wan22,
        "resolve_generation_display_mode_name",
        lambda *_args, **_kwargs: "WAN22",
    )
    monkeypatch.setattr(
        task_service_generation_wan22,
        "build_task_inputs",
        lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(
        task_service_generation_wan22,
        "translate_context_text",
        lambda _context, key, **kwargs: f"{key}:{kwargs}" if kwargs else key,
    )
    monkeypatch.setattr(
        task_service_generation_wan22,
        "build_generation_message_spec",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        task_service_generation_wan22,
        "build_generation_completion_caption",
        lambda *_args, **_kwargs: "task.status_completion_mode:WAN22",
    )
    monkeypatch.setattr(
        task_service_generation_wan22,
        "resolve_generation_billing_args",
        lambda **_kwargs: {
            "billing_resolution": None,
            "requested_duration": 5,
        },
    )
    monkeypatch.setattr(
        task_service_generation_wan22,
        "build_generation_submitted_status_builder",
        lambda *_args, **_kwargs: (lambda cost: f"submitted:{cost}"),
    )
    monkeypatch.setattr(
        task_service_generation_wan22,
        "build_generation_flow_context",
        fake_build_generation_flow_context,
    )
    monkeypatch.setattr(
        task_service_generation_wan22,
        "run_bot_task_application",
        fake_run_bot_task_application,
    )

    result = await task_service_generation_wan22.process_wan22_video_v2_generation_task(
        context=SimpleNamespace(),
        chat_id=222,
        user_id=333,
        username="tester",
        prompt="prompt",
        negative_prompt="negative",
        images=["start.png", "end.png"],
        use_end_frame=True,
        color_match=True,
        perfect_loop=False,
        upscale=True,
        extract_last_frame=True,
        cleanup=False,
        deduct_quota=False,
    )

    assert result == (b"video-bytes", "wan22-task")
    flow = captured["flow"]
    flow_kwargs = captured["flow_kwargs"]
    assert flow.chat_id == 222
    assert flow.internal_user_id == 777
    assert flow.prompt == "prompt"
    assert flow.inputs["negative_prompt"] == "negative"
    assert flow.message_spec.progress_wait_text == "task.status_wait_generating_video"
    assert flow.message_spec.completion_caption == "task.status_completion_mode:WAN22"
    assert flow.requested_duration == 5
    assert flow.cleanup is False
    assert flow_kwargs["inputs"]["use_end_frame"] is True
    assert flow_kwargs["inputs"]["extract_last_frame"] is True
