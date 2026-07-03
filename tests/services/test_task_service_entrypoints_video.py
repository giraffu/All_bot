from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import task_service_entrypoints_video


@pytest.mark.asyncio
async def test_process_video_task_template_allows_missing_username(monkeypatch):
    resolve_internal_user_id = AsyncMock(return_value=321)
    run_bot_task_application = AsyncMock(return_value=(b"video-bytes", "result.mp4"))

    monkeypatch.setattr(
        task_service_entrypoints_video,
        "resolve_internal_user_id",
        resolve_internal_user_id,
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "resolve_custom_video_settings",
        AsyncMock(return_value=("720p", "5s", 720, 5)),
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "load_prompts",
        lambda: {},
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "resolve_display_mode_name",
        lambda *args, **kwargs: "测试模式",
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "get_acceleration_notice",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "translate_context_text",
        lambda *args, **kwargs: "text",
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "build_status_message",
        lambda text, notice=None: text,
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "build_message_spec",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "build_task_inputs",
        lambda **kwargs: {"prompt": "patched"},
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "resolve_video_billing_args",
        lambda **kwargs: {
            "billing_resolution": "720p",
            "requested_duration": 5,
        },
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "build_log_prompt",
        lambda *args, **kwargs: "log-prompt",
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "build_translated_cost_status_builder",
        lambda *args, **kwargs: (lambda cost: f"submitted:{cost}"),
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "build_unexpected_error_log_message",
        lambda value: value,
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "build_cleanup_paths",
        lambda paths: paths,
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "run_bot_task_application",
        run_bot_task_application,
    )

    result = await task_service_entrypoints_video.process_video_task_template(
        context=SimpleNamespace(),
        mode="video_edit",
        default_prompt_key="video.prompt",
        default_prompt_text="default prompt",
        image_path="/tmp/input.png",
        chat_id=123,
        user_id=456,
        username=None,
    )

    assert result == (b"video-bytes", "result.mp4")
    resolve_internal_user_id.assert_awaited_once_with(456, None)

    flow = run_bot_task_application.await_args.kwargs["flow"]
    assert flow.request.chat_id == 123
    assert flow.request.internal_user_id == 321
    assert flow.request.username is None


@pytest.mark.asyncio
async def test_process_video_task_template_forwards_end_frame_inputs(monkeypatch):
    captured_inputs = {}

    monkeypatch.setattr(
        task_service_entrypoints_video,
        "resolve_internal_user_id",
        AsyncMock(return_value=321),
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "resolve_custom_video_settings",
        AsyncMock(return_value=("512p", "5s", 512, 5)),
    )
    monkeypatch.setattr(task_service_entrypoints_video, "load_prompts", lambda: {})
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "resolve_display_mode_name",
        lambda *args, **kwargs: "测试模式",
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "get_acceleration_notice",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "translate_context_text",
        lambda *args, **kwargs: "text",
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "build_status_message",
        lambda text, notice=None: text,
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "build_message_spec",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )

    def fake_build_task_inputs(**kwargs):
        captured_inputs.update(kwargs)
        return kwargs

    monkeypatch.setattr(
        task_service_entrypoints_video,
        "build_task_inputs",
        fake_build_task_inputs,
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "resolve_video_billing_args",
        lambda **kwargs: {
            "billing_resolution": "512p",
            "requested_duration": 5,
        },
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "build_log_prompt",
        lambda *args, **kwargs: "log-prompt",
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "build_translated_cost_status_builder",
        lambda *args, **kwargs: (lambda cost: f"submitted:{cost}"),
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "build_unexpected_error_log_message",
        lambda value: value,
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "build_cleanup_paths",
        lambda paths: paths,
    )
    monkeypatch.setattr(
        task_service_entrypoints_video,
        "run_bot_task_application",
        AsyncMock(return_value=(b"video-bytes", "result.mp4")),
    )

    await task_service_entrypoints_video.process_video_task_template(
        context=SimpleNamespace(),
        mode="video_lora",
        default_prompt_key="video.prompt",
        default_prompt_text="default prompt",
        image_path="/tmp/start.png",
        end_image_path="/tmp/end.png",
        use_end_frame=True,
        chat_id=123,
        user_id=456,
        username="tester",
    )

    assert captured_inputs["images"] == ["/tmp/start.png", "/tmp/end.png"]
    assert captured_inputs["use_end_frame"] is True

    flow = task_service_entrypoints_video.run_bot_task_application.await_args.kwargs["flow"]
    assert flow.cleanup_policy.cleanup_paths == ["/tmp/start.png", "/tmp/end.png"]


@pytest.mark.asyncio
async def test_process_video_task_template_still_requires_chat_and_user_context():
    with pytest.raises(ValueError, match="缺少用户或聊天上下文"):
        await task_service_entrypoints_video.process_video_task_template(
            context=SimpleNamespace(),
            mode="video_edit",
            default_prompt_key="video.prompt",
            default_prompt_text="default prompt",
            image_path="/tmp/input.png",
            chat_id=None,
            user_id=456,
            username=None,
        )
