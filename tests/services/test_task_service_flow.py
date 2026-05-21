from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from asgi_correlation_id import correlation_id

from src.services import task_service_flow
from src.services.task_service_types import BotTaskMessageSpec


@pytest.mark.asyncio
async def test_submit_bot_task_sets_runtime_state_and_returns_saved_inputs(monkeypatch):
    process_submit = AsyncMock(
        return_value={
            "cost": 18,
            "registry_task_id": "registry-1",
            "saved_inputs": ["input-a.png"],
        }
    )
    monkeypatch.setattr(task_service_flow, "process_and_submit_task", process_submit)
    runtime_state = SimpleNamespace(
        task_submitted=False,
        actual_cost=0,
        registry_task_id=None,
    )

    token = correlation_id.set(None)
    try:
        task_id, saved_inputs = await task_service_flow.submit_bot_task(
            runtime_state=runtime_state,
            internal_user_id=456,
            username="tester",
            task_type="ltx_video",
            inputs={"prompt": "hello"},
            source_post_id=9,
            deduct_quota=False,
        )
        assert correlation_id.get() == task_id
    finally:
        correlation_id.reset(token)

    assert isinstance(task_id, str)
    assert saved_inputs == ["input-a.png"]
    assert runtime_state.task_submitted is True
    assert runtime_state.actual_cost == 18
    assert runtime_state.registry_task_id == "registry-1"
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
        get_or_send_status_msg_func=AsyncMock(),
    )

    assert result == "sent"
    reply_text.assert_awaited_once_with(update.effective_message, "正在提交")


@pytest.mark.asyncio
async def test_send_initial_task_status_uses_injected_reply_text_func():
    injected_reply = AsyncMock(return_value="compat-sent")
    update = SimpleNamespace(effective_message=object())
    spec = BotTaskMessageSpec(initial_status_text="正在提交")

    result = await task_service_flow.send_initial_task_status(
        context=object(),
        update=update,
        chat_id=123,
        status_msg_id=None,
        message_spec=spec,
        get_or_send_status_msg_func=AsyncMock(),
        reply_text_func=injected_reply,
    )

    assert result == "compat-sent"
    injected_reply.assert_awaited_once_with(update.effective_message, "正在提交")


@pytest.mark.asyncio
async def test_update_submitted_task_status_prefers_submitted_text(monkeypatch):
    edit_text = AsyncMock()
    monkeypatch.setattr(task_service_flow, "robust_edit_text", edit_text)

    status_msg = object()
    spec = BotTaskMessageSpec(
        initial_status_text="正在提交",
        submitted_status_text="已提交",
        progress_wait_text="请稍候",
    )

    await task_service_flow.update_submitted_task_status(
        status_msg=status_msg,
        message_spec=spec,
    )

    edit_text.assert_awaited_once_with(status_msg, "已提交")


@pytest.mark.asyncio
async def test_update_submitted_task_status_uses_injected_edit_text_func():
    injected_edit = AsyncMock()
    status_msg = object()
    spec = BotTaskMessageSpec(
        initial_status_text="正在提交",
        submitted_status_text=None,
        progress_wait_text="请稍候",
    )

    await task_service_flow.update_submitted_task_status(
        status_msg=status_msg,
        message_spec=spec,
        edit_text_func=injected_edit,
    )

    injected_edit.assert_awaited_once_with(status_msg, "请稍候")
