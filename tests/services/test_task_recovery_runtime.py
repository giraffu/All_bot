from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.task_service_types import BotTaskCompletionContext
from src.services import task_recovery_runtime


def test_build_recovered_message_spec_uses_recovery_specific_translated_fields(
    monkeypatch,
):
    monkeypatch.setattr(
        "src.services.task_recovery_runtime.resolve_display_mode_name",
        lambda *args, **kwargs: "恢复模式",
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime.translate_context_text",
        lambda _context, key, **kwargs: f"{key}:{kwargs}" if kwargs else key,
    )

    spec = task_recovery_runtime._build_recovered_message_spec(
        context=SimpleNamespace(lang="zh"),
        task_type="image",
    )

    assert spec.completion_caption == "task.status_completion_mode:{'mode_name': '恢复模式'}"
    assert spec.missing_output_message == "task.status_missing_output_refunded"
    assert spec.cancellation_message_template == (
        "task.status_cancelled_refunded:{'cost': '{cost}'}"
    )


def test_build_recovered_completion_context_uses_completion_dataclass_shape():
    completion = task_recovery_runtime._build_recovered_completion_context(
        context=SimpleNamespace(bot=MagicMock(), bot_data={}),
        chat_id=123,
        internal_user_id=456,
        username="tester",
        prompt="prompt",
        task_type="image",
        registry_task_id="registry-1",
        backend_task_id="backend-1",
        saved_input_images=["input.png"],
        is_video=False,
        send_result=True,
        reply_markup=None,
        status_msg=MagicMock(),
        delete_status=True,
        allow_contribute=False,
        billing_resolution="1024",
        requested_duration=None,
        final_info={"status": "done"},
    )

    assert isinstance(completion, BotTaskCompletionContext)
    assert completion.registry_task_id == "registry-1"
    assert completion.backend_task_id == "backend-1"
    assert completion.runtime_state.registry_task_id == "registry-1"
    assert completion.runtime_state.backend_task_id == "backend-1"
    assert completion.runtime_state.task_submitted is True
    assert completion.final_info == {"status": "done"}
    assert completion.billing_resolution == "1024"
    assert completion.send_result is True
    assert completion.message_spec.completion_caption
    assert completion.message_spec.missing_output_message


@pytest.mark.asyncio
async def test_handle_recovered_task_completion_delegates_to_complete_monitored_bot_task(
    monkeypatch,
):
    completion_mock = AsyncMock(return_value=(b"image-bytes", "saved-output.png"))
    monkeypatch.setattr(
        "src.services.task_recovery_runtime.complete_monitored_bot_task",
        completion_mock,
    )

    completion = BotTaskCompletionContext(
        context=SimpleNamespace(bot=MagicMock(), bot_data={}),
        chat_id=123,
        status_msg=MagicMock(),
        runtime_state=SimpleNamespace(
            registry_task_id="task-1",
            backend_task_id="task-1",
            task_submitted=True,
            actual_cost=0,
        ),
        internal_user_id=456,
        username="tester",
        prompt="prompt",
        task_type="image",
        registry_task_id="task-1",
        backend_task_id="task-1",
        saved_input_images=["input.png"],
        final_info={"status": "done"},
        is_video=False,
        message_spec=SimpleNamespace(
            completion_caption=None,
            missing_output_message="missing",
        ),
    )

    result = await task_recovery_runtime._handle_recovered_task_completion(
        completion=completion
    )

    assert result == (b"image-bytes", "saved-output.png")
    completion_mock.assert_awaited_once_with(completion=completion)


@pytest.mark.asyncio
async def test_run_recovered_task_uses_local_monitor_and_completion(monkeypatch):
    monitor_mock = AsyncMock(return_value={"status": "done"})
    build_completion = MagicMock(return_value="completion-context")
    completion_mock = AsyncMock()

    monkeypatch.setattr(
        "src.services.task_recovery_runtime.permission_service.get_user_identity",
        AsyncMock(return_value="外门弟子"),
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime.permission_service.get_user_group",
        AsyncMock(return_value="外门弟子"),
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime._monitor_recovered_task_progress",
        monitor_mock,
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime._build_recovered_completion_context",
        build_completion,
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime._handle_recovered_task_completion",
        completion_mock,
    )

    application = SimpleNamespace(bot=MagicMock(), bot_data={})
    recovered = await task_recovery_runtime.run_recovered_task(
        registry_task_id="registry-1",
        task_data={
            "user_id": 1,
            "username": "tester",
            "backend_task_id": "backend-1",
            "chat_id": 100,
            "message_id": 200,
            "task_type": "image",
            "prompt": "hello",
            "saved_input_images": ["input.png"],
            "is_video": False,
            "allow_contribute": True,
            "language_code": "en",
        },
        application=application,
    )

    assert recovered is True
    monitor_mock.assert_awaited_once()
    build_completion.assert_called_once()
    assert build_completion.call_args.kwargs["context"].lang == "en"
    assert build_completion.call_args.kwargs["registry_task_id"] == "registry-1"
    assert build_completion.call_args.kwargs["backend_task_id"] == "backend-1"
    assert build_completion.call_args.kwargs["final_info"] == {"status": "done"}
    completion_mock.assert_awaited_once()
    assert completion_mock.await_args.kwargs == {"completion": "completion-context"}


@pytest.mark.asyncio
async def test_private_hidden_chain_task_recovery_fails_closed_without_sending_partial_result(
    monkeypatch,
):
    monitor_mock = AsyncMock(return_value={"status": "done", "output": "partial.png"})
    completion_mock = AsyncMock()
    monkeypatch.setattr(
        "src.services.task_recovery_runtime.permission_service.get_user_identity",
        AsyncMock(return_value="外门弟子"),
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime.permission_service.get_user_group",
        AsyncMock(return_value="外门弟子"),
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime._monitor_recovered_task_progress",
        monitor_mock,
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime._handle_recovered_task_completion",
        completion_mock,
    )

    recovered = await task_recovery_runtime.run_recovered_task(
        registry_task_id="registry-hidden",
        task_data={
            "user_id": 1,
            "username": "tester",
            "backend_task_id": "backend-hidden",
            "chat_id": 100,
            "message_id": 200,
            "task_type": "edit",
            "client_type": "bot:qqcc-private:7",
            "metadata": {
                "_bot_task_recovery": {
                    "version": 1,
                    "send_result": False,
                    "requires_continuation": True,
                }
            },
        },
        application=SimpleNamespace(bot=MagicMock(), bot_data={}),
    )

    assert recovered is False
    monitor_mock.assert_awaited_once()
    completion_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_private_hidden_chain_task_with_checkpoint_completes_silently_and_advances(
    monkeypatch,
):
    monitor_mock = AsyncMock(return_value={"status": "done"})
    completion_mock = AsyncMock(return_value=(b"image", "outputs/stage-0.png"))
    checkpoint_record = AsyncMock()
    monkeypatch.setattr(
        "src.services.task_recovery_runtime.permission_service.get_user_identity",
        AsyncMock(return_value="外门弟子"),
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime.permission_service.get_user_group",
        AsyncMock(return_value="外门弟子"),
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime._monitor_recovered_task_progress",
        monitor_mock,
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime._handle_recovered_task_completion",
        completion_mock,
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime.record_private_qqcc_continuation_task_result",
        checkpoint_record,
    )
    registry_id = "e3cce65d-fake-registry"
    metadata = {
        "_bot_task_recovery": {
            "version": 1,
            "send_result": False,
            "requires_continuation": True,
        },
        "_private_qqcc_continuation": {
            "version": 1,
            "chain_id": "chain-1",
            "stage_index": 0,
            "submission_sequence": 0,
            "registry_task_id": registry_id,
            "executor_token": "executor-1",
        },
    }

    recovered = await task_recovery_runtime.run_recovered_task(
        registry_task_id=registry_id,
        task_data={
            "user_id": 1,
            "username": "tester",
            "backend_task_id": registry_id,
            "chat_id": 100,
            "message_id": 200,
            "task_type": "edit",
            "client_type": "bot:qqcc-private:7",
            "saved_input_images": ["inputs/original.png"],
            "metadata": metadata,
        },
        application=SimpleNamespace(bot=MagicMock(), bot_data={}),
    )

    assert recovered is True
    completion = completion_mock.await_args.kwargs["completion"]
    assert completion.send_result is False
    checkpoint_record.assert_awaited_once_with(
        registry_metadata=metadata,
        registry_task_id=registry_id,
        saved_inputs=["inputs/original.png"],
        output_file="outputs/stage-0.png",
    )


@pytest.mark.asyncio
async def test_private_final_task_recovery_restores_persisted_presentation(monkeypatch):
    monitor_mock = AsyncMock(return_value={"status": "done"})
    completion_context = MagicMock()
    build_completion = MagicMock(return_value=completion_context)
    completion_mock = AsyncMock(return_value=(b"video", "result.mp4"))
    monkeypatch.setattr(
        "src.services.task_recovery_runtime.permission_service.get_user_identity",
        AsyncMock(return_value="外门弟子"),
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime.permission_service.get_user_group",
        AsyncMock(return_value="外门弟子"),
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime._monitor_recovered_task_progress",
        monitor_mock,
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime._build_recovered_completion_context",
        build_completion,
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime._handle_recovered_task_completion",
        completion_mock,
    )

    recovered = await task_recovery_runtime.run_recovered_task(
        registry_task_id="registry-final",
        task_data={
            "user_id": 1,
            "username": "tester",
            "backend_task_id": "backend-final",
            "chat_id": 100,
            "message_id": 200,
            "task_type": "face_swap",
            "prompt": "internal prompt",
            "saved_input_images": ["body.png", "original.png"],
            "client_type": "bot:qqcc-private:7",
            "metadata": {
                "_bot_task_recovery": {
                    "version": 1,
                    "send_result": True,
                    "requires_continuation": False,
                    "delete_status": True,
                    "allow_contribute": False,
                    "result_task_type": "edit",
                    "result_prompt": "visible prompt",
                    "result_input_image_indices": [1],
                    "result_meta": {"_qqcc_regenerate": {"kind": "quick_image"}},
                    "completion_caption": "✅ 私有绘图完成",
                    "show_queue_status": False,
                }
            },
        },
        application=SimpleNamespace(bot=MagicMock(), bot_data={}),
    )

    assert recovered is True
    assert monitor_mock.await_args.kwargs["show_queue_status"] is False
    kwargs = build_completion.call_args.kwargs
    assert kwargs["task_type"] == "edit"
    assert kwargs["prompt"] == "visible prompt"
    assert kwargs["saved_input_images"] == ["original.png"]
    assert kwargs["send_result"] is True
    assert kwargs["allow_contribute"] is False
    assert kwargs["caption"] == "✅ 私有绘图完成"
    assert kwargs["result_meta"] == {
        "_qqcc_regenerate": {"kind": "quick_image"}
    }
    completion_mock.assert_awaited_once_with(completion=completion_context)


@pytest.mark.asyncio
async def test_private_legacy_task_without_recovery_contract_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "src.services.task_recovery_runtime.permission_service.get_user_identity",
        AsyncMock(return_value="外门弟子"),
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime.permission_service.get_user_group",
        AsyncMock(return_value="外门弟子"),
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime._monitor_recovered_task_progress",
        AsyncMock(return_value={"status": "done"}),
    )
    completion_mock = AsyncMock()
    monkeypatch.setattr(
        "src.services.task_recovery_runtime._handle_recovered_task_completion",
        completion_mock,
    )

    recovered = await task_recovery_runtime.run_recovered_task(
        registry_task_id="registry-legacy-private",
        task_data={
            "user_id": 1,
            "backend_task_id": "backend-legacy-private",
            "chat_id": 100,
            "task_type": "edit",
            "client_type": "bot:qqcc-private:7",
        },
        application=SimpleNamespace(bot=MagicMock(), bot_data={}),
    )

    assert recovered is False
    completion_mock.assert_not_awaited()
