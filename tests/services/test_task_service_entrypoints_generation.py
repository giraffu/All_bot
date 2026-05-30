from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import task_service_entrypoints_generation


@pytest.mark.asyncio
async def test_process_image_to_video_task_builds_common_flow_context(monkeypatch):
    captured_flow = {}

    async def fake_run_bot_task_application(*, flow):
        captured_flow["flow"] = flow
        return (b"video-bytes", "video-task")

    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "resolve_internal_user_id",
        AsyncMock(return_value=456),
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "resolve_custom_video_settings",
        AsyncMock(return_value=("720p", "8s", 720, 8)),
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "get_acceleration_notice",
        AsyncMock(return_value="notice"),
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "resolve_display_mode_name",
        lambda *args, **kwargs: "测试模式",
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_task_inputs",
        lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "translate_context_text",
        lambda _context, key, **kwargs: f"{key}:{kwargs}" if kwargs else key,
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_status_message",
        lambda text, notice=None: f"{text}|{notice}",
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_message_spec",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_log_prompt",
        lambda *args, **kwargs: "log-prompt",
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "resolve_video_billing_args",
        lambda **kwargs: {
            "billing_resolution": "720p",
            "requested_duration": 8,
        },
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_translated_cost_status_builder",
        lambda *args, **kwargs: (lambda cost: f"submitted:{cost}"),
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_unexpected_error_log_message",
        lambda value: f"log:{value}",
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_cleanup_paths",
        lambda paths: [f"clean:{path}" for path in paths],
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "run_bot_task_application",
        fake_run_bot_task_application,
    )

    result = await task_service_entrypoints_generation.process_image_to_video_task(
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
    flow = captured_flow["flow"]
    assert flow.request.chat_id == 123
    assert flow.request.internal_user_id == 456
    assert flow.request.prompt == "log-prompt"
    assert flow.request.is_video is True
    assert flow.presentation.delete_status is False
    assert flow.presentation.allow_contribute is False
    assert flow.presentation.message_spec.progress_wait_text == (
        "task.status_wait_generating_video"
    )
    assert flow.presentation.message_spec.completion_caption.startswith(
        "task.status_completion_mode"
    )
    assert flow.billing.billing_resolution == "720p"
    assert flow.billing.requested_duration == 8
    assert flow.billing.missing_output_should_refund is False
    assert flow.failure_policy.unexpected_error_log_message == (
        "log:process_image_to_video_task"
    )
    assert flow.cleanup_policy.cleanup_enabled is False
    assert flow.cleanup_policy.cleanup_paths == ["clean:start.png"]


@pytest.mark.asyncio
async def test_process_generation_task_uses_common_flow_context_for_image_tasks(
    monkeypatch,
):
    captured_flow = {}

    async def fake_run_bot_task_application(*, flow):
        captured_flow["flow"] = flow
        return (b"image-bytes", "image-task")

    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "resolve_internal_user_id",
        AsyncMock(return_value=654),
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "get_acceleration_notice",
        AsyncMock(return_value=""),
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_task_inputs",
        lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "translate_context_text",
        lambda _context, key, **kwargs: f"{key}:{kwargs}" if kwargs else key,
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_status_message",
        lambda text, notice=None: f"{text}|{notice}",
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_message_spec",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_log_prompt",
        lambda *args, **kwargs: "image-log",
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "resolve_display_mode_name",
        lambda *args, **kwargs: "图片模式",
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "resolve_video_billing_args",
        lambda **kwargs: {
            "billing_resolution": "512",
            "requested_duration": 5,
        },
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_translated_cost_status_builder",
        lambda *args, **kwargs: (lambda cost: f"submitted:{cost}"),
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_unexpected_error_log_message",
        lambda value: value,
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_cleanup_paths",
        lambda paths: [f"cleanup:{path}" for path in paths],
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "run_bot_task_application",
        fake_run_bot_task_application,
    )

    result = await task_service_entrypoints_generation.process_generation_task(
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
    flow = captured_flow["flow"]
    assert flow.request.chat_id == 321
    assert flow.request.internal_user_id == 654
    assert flow.request.task_type == "image"
    assert flow.request.prompt == "image-log"
    assert flow.request.is_video is False
    assert flow.presentation.message_spec.missing_output_message == (
        "task.status_missing_output_refunded"
    )
    assert flow.presentation.message_spec.completion_caption.startswith(
        "task.status_completion_mode"
    )
    assert flow.presentation.message_spec.cancellation_message_template.startswith(
        "task.status_cancelled_refunded"
    )
    assert flow.billing.billing_resolution == "512"
    assert flow.billing.requested_duration == 5
    assert flow.billing.missing_output_should_refund is False
    assert flow.failure_policy.unexpected_error_log_message == (
        "process_generation_task"
    )
    assert flow.cleanup_policy.cleanup_enabled is False
    assert flow.cleanup_policy.cleanup_paths == ["cleanup:input.png"]


@pytest.mark.asyncio
async def test_process_wan22_video_v2_task_builds_common_message_and_status_templates(
    monkeypatch,
):
    captured_flow = {}

    async def fake_run_bot_task_application(*, flow):
        captured_flow["flow"] = flow
        return (b"video-bytes", "wan22-task")

    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "resolve_internal_user_id",
        AsyncMock(return_value=777),
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "get_acceleration_notice",
        AsyncMock(return_value="notice"),
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "resolve_display_mode_name",
        lambda *args, **kwargs: "WAN22",
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_task_inputs",
        lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "translate_context_text",
        lambda _context, key, **kwargs: f"{key}:{kwargs}" if kwargs else key,
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_status_message",
        lambda text, notice=None: f"{text}|{notice}",
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_message_spec",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "resolve_video_billing_args",
        lambda **kwargs: {
            "billing_resolution": None,
            "requested_duration": 5,
        },
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_translated_cost_status_builder",
        lambda *args, **kwargs: (lambda cost: f"submitted:{cost}"),
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_unexpected_error_log_message",
        lambda value: value,
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_cleanup_paths",
        lambda paths: paths,
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "run_bot_task_application",
        fake_run_bot_task_application,
    )

    result = await task_service_entrypoints_generation.process_wan22_video_v2_task(
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
    flow = captured_flow["flow"]
    assert flow.request.chat_id == 222
    assert flow.request.internal_user_id == 777
    assert flow.request.prompt == "prompt"
    assert flow.request.inputs["negative_prompt"] == "negative"
    assert flow.presentation.message_spec.progress_wait_text == (
        "task.status_wait_generating_video"
    )
    assert flow.presentation.message_spec.completion_caption.startswith(
        "task.status_completion_mode"
    )
    assert flow.billing.requested_duration == 5
    assert flow.billing.missing_output_should_refund is False
