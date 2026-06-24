from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from asgi_correlation_id import correlation_id

from src.services import task_service_flow
from src.services.task_service_types import BotTaskMessageSpec, BotTaskSubmissionContext


@pytest.mark.asyncio
async def test_submit_bot_task_sets_runtime_state_and_returns_saved_inputs(monkeypatch):
    process_submit = AsyncMock(
        return_value={
            "cost": 18,
            "registry_task_id": "registry-1",
            "backend_task_id": "backend-1",
            "saved_inputs": ["input-a.png"],
        }
    )
    monkeypatch.setattr(task_service_flow, "process_and_submit_task", process_submit)
    runtime_state = SimpleNamespace(
        task_submitted=False,
        actual_cost=0,
        registry_task_id=None,
        backend_task_id=None,
    )

    token = correlation_id.set(None)
    try:
        task_id, backend_task_id, saved_inputs = await task_service_flow.submit_bot_task(
            submission=BotTaskSubmissionContext(
                runtime_state=runtime_state,
                internal_user_id=456,
                username="tester",
                task_type="ltx_video",
                inputs={"prompt": "hello"},
                source_post_id=9,
                deduct_quota=False,
            ),
        )
        assert correlation_id.get() == task_id
    finally:
        correlation_id.reset(token)

    assert isinstance(task_id, str)
    assert backend_task_id == "backend-1"
    assert saved_inputs == ["input-a.png"]
    assert runtime_state.task_submitted is True
    assert runtime_state.actual_cost == 18
    assert runtime_state.registry_task_id == "registry-1"
    assert runtime_state.backend_task_id == "backend-1"
    process_submit.assert_awaited_once()
    kwargs = process_submit.await_args.kwargs
    assert kwargs["user_id"] == 456
    assert kwargs["username"] == "tester"
    assert kwargs["task_type"] == "ltx_video"
    assert kwargs["inputs"] == {"prompt": "hello"}
    assert kwargs["task_id"] == task_id
    assert kwargs["client_type"] == "bot"
    assert kwargs["source_post_id"] == 9
    assert kwargs["deduct_quota"] is False


@pytest.mark.asyncio
async def test_submit_bot_task_uses_submission_client_type(monkeypatch):
    process_submit = AsyncMock(
        return_value={
            "cost": 6,
            "registry_task_id": "registry-qqcc",
            "backend_task_id": "backend-qqcc",
            "saved_inputs": [],
        }
    )
    monkeypatch.setattr(task_service_flow, "process_and_submit_task", process_submit)

    await task_service_flow.submit_bot_task(
        submission=BotTaskSubmissionContext(
            runtime_state=SimpleNamespace(
                task_submitted=False,
                actual_cost=0,
                registry_task_id=None,
                backend_task_id=None,
            ),
            internal_user_id=789,
            username="qqcc",
            task_type="quick_image",
            inputs={"prompt": "lazy"},
            client_type="bot:qqcc",
        ),
    )

    assert process_submit.await_args.kwargs["client_type"] == "bot:qqcc"


@pytest.mark.asyncio
async def test_send_initial_task_status_uses_reply_text_when_update_present(monkeypatch):
    reply_text = AsyncMock(return_value="sent")
    monkeypatch.setattr(task_service_flow, "robust_reply_text", reply_text)

    update = SimpleNamespace(effective_message=object())
    spec = BotTaskMessageSpec(initial_status_text="正在提交")

    result = await task_service_flow.send_initial_task_status(
        context=object(),
        update=update,
        chat_id=123,
        status_msg_id=None,
        message_spec=spec,
    )

    assert result == "sent"
    reply_text.assert_awaited_once_with(update.effective_message, "正在提交")


@pytest.mark.asyncio
async def test_update_submitted_task_status_prefers_submitted_text(monkeypatch):
    edit_text = AsyncMock()
    monkeypatch.setattr(task_service_flow, "robust_edit_text", edit_text)
    cancel_markup = object()
    build_cancel_markup = Mock(return_value=cancel_markup)
    monkeypatch.setattr(
        task_service_flow,
        "build_cancel_task_markup",
        build_cancel_markup,
    )

    status_msg = object()
    spec = BotTaskMessageSpec(
        initial_status_text="正在提交",
        submitted_status_text="已提交",
        progress_wait_text="请稍候",
    )

    await task_service_flow.update_submitted_task_status(
        status_msg=status_msg,
        message_spec=spec,
        registry_task_id="registry-1",
    )

    build_cancel_markup.assert_called_once_with("registry-1")
    edit_text.assert_awaited_once_with(
        status_msg,
        "已提交",
        reply_markup=cancel_markup,
    )


@pytest.mark.asyncio
async def test_prepare_and_submit_bot_task_updates_status_through_helpers(monkeypatch):
    send_initial = AsyncMock(return_value="status-msg")
    submit_bot_task = AsyncMock(return_value=("registry-1", "backend-1", ["input.png"]))
    update_submitted = AsyncMock()
    runtime_state = SimpleNamespace(actual_cost=18)
    spec = BotTaskMessageSpec(
        initial_status_text="正在提交",
        submitted_status_text="已提交",
        progress_wait_text="请稍候",
    )

    monkeypatch.setattr(task_service_flow, "send_initial_task_status", send_initial)
    monkeypatch.setattr(task_service_flow, "submit_bot_task", submit_bot_task)
    monkeypatch.setattr(
        task_service_flow,
        "update_submitted_task_status",
        update_submitted,
    )

    status_msg, registry_task_id, backend_task_id, saved_inputs, returned_spec = (
        await task_service_flow.prepare_and_submit_bot_task(
            context=object(),
            update=None,
            chat_id=123,
            message_spec=spec,
            submission=BotTaskSubmissionContext(
                runtime_state=runtime_state,
                internal_user_id=456,
                username="tester",
                task_type="image",
                inputs={"prompt": "hello"},
            ),
        )
    )

    assert status_msg == "status-msg"
    assert registry_task_id == "registry-1"
    assert backend_task_id == "backend-1"
    assert saved_inputs == ["input.png"]
    assert returned_spec is spec
    send_initial.assert_awaited_once()
    submit_bot_task.assert_awaited_once_with(
        submission=BotTaskSubmissionContext(
            runtime_state=runtime_state,
            internal_user_id=456,
            username="tester",
            task_type="image",
            inputs={"prompt": "hello"},
        ),
    )
    update_submitted.assert_awaited_once_with(
        status_msg="status-msg",
        message_spec=spec,
        registry_task_id="registry-1",
    )


@pytest.mark.asyncio
async def test_run_bot_task_application_monitors_with_backend_task_id_and_completes_with_split_ids(
    monkeypatch,
):
    submission_stage = AsyncMock(
        return_value=(
            "status-msg",
            "registry-123",
            "backend-456",
            ["input.png"],
            BotTaskMessageSpec(initial_status_text="提交中"),
        )
    )
    monitor_stage = AsyncMock(return_value={"status": "done"})
    completion_stage = AsyncMock(return_value=(b"media", "output.png"))

    monkeypatch.setattr(
        task_service_flow,
        "run_bot_task_submission_stage",
        submission_stage,
    )
    monkeypatch.setattr(
        task_service_flow,
        "run_bot_task_monitor_stage",
        monitor_stage,
    )
    monkeypatch.setattr(
        task_service_flow,
        "run_bot_task_completion_stage",
        completion_stage,
    )
    monkeypatch.setattr(
        task_service_flow,
        "cleanup_bot_task_flow",
        AsyncMock(),
    )

    flow = SimpleNamespace(
        runtime_state=SimpleNamespace(
            registry_task_id="registry-123",
            backend_task_id="backend-456",
            task_submitted=True,
            actual_cost=0,
            terminal_state_finalized=False,
        ),
        request=SimpleNamespace(
            context=SimpleNamespace(),
            update=None,
            chat_id=100,
            status_msg_id=None,
            internal_user_id=200,
            username="tester",
            task_type="txt2img",
            inputs={"prompt": "hello"},
            prompt="hello",
            is_video=False,
            source_post_id=None,
            deduct_quota=True,
        ),
        presentation=SimpleNamespace(
            message_spec=BotTaskMessageSpec(initial_status_text="提交中"),
            submitted_status_builder=None,
            send_result=True,
            reply_markup=None,
            result_meta=None,
            delete_status=True,
            allow_contribute=True,
            prefer_edit_status=False,
        ),
        billing=SimpleNamespace(
            billing_resolution=None,
            requested_duration=None,
            missing_output_should_refund=True,
        ),
        failure_policy=SimpleNamespace(
            unexpected_error_log_message="err {error}",
            unexpected_error_prefix="出错了",
            refund_suffix_mode="if_refunded",
            unexpected_should_refund=None,
        ),
        cleanup_policy=SimpleNamespace(
            cleanup_paths=[],
            cleanup_enabled=False,
            cleanup_files_func=lambda *_args, **_kwargs: None,
        ),
    )

    result = await task_service_flow.run_bot_task_application(flow=flow)

    assert result == (b"media", "output.png")
    monitor_stage.assert_awaited_once()
    assert monitor_stage.await_args.kwargs["backend_task_id"] == "backend-456"
    completion_stage.assert_awaited_once()
    assert completion_stage.await_args.kwargs["registry_task_id"] == "registry-123"
    assert completion_stage.await_args.kwargs["backend_task_id"] == "backend-456"


@pytest.mark.asyncio
async def test_run_bot_task_application_reads_client_type_from_bot_data(monkeypatch):
    submission_stage = AsyncMock(
        return_value=(
            "status-msg",
            "registry-qqcc",
            "backend-qqcc",
            [],
            BotTaskMessageSpec(initial_status_text="提交中"),
        )
    )
    monkeypatch.setattr(
        task_service_flow,
        "run_bot_task_submission_stage",
        submission_stage,
    )
    monkeypatch.setattr(
        task_service_flow,
        "run_bot_task_monitor_stage",
        AsyncMock(return_value={"status": "done"}),
    )
    monkeypatch.setattr(
        task_service_flow,
        "run_bot_task_completion_stage",
        AsyncMock(return_value=(b"media", "output.png")),
    )
    monkeypatch.setattr(task_service_flow, "cleanup_bot_task_flow", AsyncMock())

    flow = SimpleNamespace(
        runtime_state=SimpleNamespace(
            registry_task_id=None,
            backend_task_id=None,
            task_submitted=False,
            actual_cost=0,
            terminal_state_finalized=False,
        ),
        request=SimpleNamespace(
            context=SimpleNamespace(bot_data={"bot_client_type": "bot:qqcc"}),
            update=None,
            chat_id=100,
            status_msg_id=None,
            internal_user_id=200,
            username="tester",
            task_type="quick_image",
            inputs={"prompt": "hello"},
            prompt="hello",
            is_video=False,
            source_post_id=None,
            deduct_quota=True,
        ),
        presentation=SimpleNamespace(
            message_spec=BotTaskMessageSpec(initial_status_text="提交中"),
            submitted_status_builder=None,
            send_result=True,
            reply_markup=None,
            result_meta=None,
            delete_status=True,
            allow_contribute=True,
            prefer_edit_status=False,
        ),
        billing=SimpleNamespace(
            billing_resolution=None,
            requested_duration=None,
            missing_output_should_refund=True,
        ),
        failure_policy=SimpleNamespace(
            unexpected_error_log_message="err {error}",
            unexpected_error_prefix="出错了",
            refund_suffix_mode="if_refunded",
            unexpected_should_refund=None,
        ),
        cleanup_policy=SimpleNamespace(
            cleanup_paths=[],
            cleanup_enabled=False,
            cleanup_files_func=lambda *_args, **_kwargs: None,
        ),
    )

    await task_service_flow.run_bot_task_application(flow=flow)

    submission = submission_stage.await_args.kwargs["submission"]
    assert submission.client_type == "bot:qqcc"
