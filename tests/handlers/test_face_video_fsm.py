from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.ext import ConversationHandler

from src.handlers.fsm import face_video_fsm


def _build_query(data: str):
    return SimpleNamespace(
        data=data,
        from_user=SimpleNamespace(id=12345, username="tester"),
        message=SimpleNamespace(chat_id=10001, message_id=777),
        answer=AsyncMock(),
    )


def _build_context(face_image_path=None, video_path=None):
    return SimpleNamespace(
        user_data={
            "in_conversation": "FACE_VIDEO",
            "face_video_data": {
                "face_image_path": face_image_path,
                "video_path": video_path,
            },
        }
    )


@pytest.mark.asyncio
async def test_face_video_resolution_selection_handles_expired_state_before_quota(monkeypatch):
    query = _build_query("fsm_fv_res_720")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={"in_conversation": "FACE_VIDEO"})
    priority_mock = AsyncMock()

    monkeypatch.setattr(
        face_video_fsm.permission_service,
        "calculate_user_priority",
        priority_mock,
    )

    result = await face_video_fsm.process_resolution_selection(update, context)

    assert result == ConversationHandler.END
    priority_mock.assert_not_awaited()
    query.answer.assert_awaited_once()
    assert query.answer.await_args.kwargs["show_alert"] is True
    assert "交互已失效" in query.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_face_video_resolution_selection_rejects_when_priority_exhausted(monkeypatch):
    edit_mock = AsyncMock()
    query = _build_query("fsm_fv_res_720")
    update = SimpleNamespace(callback_query=query)
    context = _build_context(face_image_path="/tmp/face.png", video_path="/tmp/video.mp4")

    monkeypatch.setattr(face_video_fsm, "robust_edit_text", edit_mock)
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=999), False)),
    )
    monkeypatch.setattr(
        face_video_fsm.permission_service,
        "calculate_user_priority",
        AsyncMock(return_value=0),
    )

    result = await face_video_fsm.process_resolution_selection(update, context)

    assert result == ConversationHandler.END
    edit_mock.assert_awaited_once()
    assert "额度" in edit_mock.await_args.args[1] or "优先" in edit_mock.await_args.args[1]
    assert "in_conversation" not in context.user_data
    assert "face_video_data" not in context.user_data


@pytest.mark.asyncio
async def test_face_video_resolution_selection_consumes_input_once(monkeypatch):
    query = _build_query("fsm_fv_res_720")
    update = SimpleNamespace(callback_query=query)
    context = _build_context(face_image_path=None, video_path="/tmp/video.mp4")

    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=999), False)),
    )
    monkeypatch.setattr(
        face_video_fsm.permission_service,
        "calculate_user_priority",
        AsyncMock(return_value=1),
    )

    result = await face_video_fsm.process_resolution_selection(update, context)

    assert result == ConversationHandler.END
    assert context.user_data["face_video_data"] == {}


@pytest.mark.asyncio
async def test_face_video_resolution_selection_schedules_background_task(monkeypatch):
    query = _build_query("fsm_fv_res_1024")
    update = SimpleNamespace(callback_query=query)
    context = _build_context(face_image_path="/tmp/face.png", video_path="/tmp/video.mp4")
    edit_mock = AsyncMock()
    create_background_task_mock = Mock()

    monkeypatch.setattr(face_video_fsm, "robust_edit_text", edit_mock)
    monkeypatch.setattr(face_video_fsm, "create_background_task", create_background_task_mock)
    monkeypatch.setattr(
        face_video_fsm,
        "process_face_video_task",
        lambda *args, **kwargs: ("bg-task", args, kwargs),
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=999), False)),
    )
    monkeypatch.setattr(
        face_video_fsm.permission_service,
        "calculate_user_priority",
        AsyncMock(return_value=1),
    )

    result = await face_video_fsm.process_resolution_selection(update, context)

    assert result == ConversationHandler.END
    edit_mock.assert_awaited_once()
    create_background_task_mock.assert_called_once()
    scheduled = create_background_task_mock.call_args.args[1]
    assert scheduled[0] == "bg-task"
    assert scheduled[1] == ()
    assert scheduled[2]["context"] is context
    assert scheduled[2]["chat_id"] == 10001
    assert scheduled[2]["user_id"] == 12345
    assert scheduled[2]["username"] == "tester"
    assert scheduled[2]["face_image_path"] == "/tmp/face.png"
    assert scheduled[2]["video_path"] == "/tmp/video.mp4"
    assert scheduled[2]["resolution"] == 1024
    assert scheduled[2]["cost"] == 36
    assert "in_conversation" not in context.user_data
    assert "face_video_data" not in context.user_data
