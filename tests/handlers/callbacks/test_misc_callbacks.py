from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.handlers.callbacks import misc_callbacks


def _build_random_faceswap_update():
    user = SimpleNamespace(id=12345, username="tester", full_name="Test User")
    message = SimpleNamespace(chat_id=10001)
    query = SimpleNamespace(from_user=user, message=message)
    return SimpleNamespace(
        callback_query=query,
        effective_user=user,
        effective_chat=SimpleNamespace(id=10001),
    )


@pytest.mark.asyncio
async def test_random_faceswap_again_uses_quick_image_submission_plan(monkeypatch):
    update = _build_random_faceswap_update()
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={"last_face_image": "/tmp/face.png"},
    )
    scheduled = []
    process_calls = []

    async def fake_process_generation_task(**kwargs):
        process_calls.append(kwargs)
        return None

    def fake_create_background_task(_context, coroutine):
        scheduled.append(coroutine)

    monkeypatch.setattr(misc_callbacks, "safe_answer_query", AsyncMock())
    monkeypatch.setattr(misc_callbacks, "robust_send_message", AsyncMock())
    monkeypatch.setattr(misc_callbacks, "is_maintenance_mode", lambda: False)
    monkeypatch.setattr(
        misc_callbacks, "_load_qqcc_config_for_context", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        misc_callbacks,
        "get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=88), False)),
    )
    monkeypatch.setattr(
        misc_callbacks.permission_service,
        "calculate_user_priority",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        misc_callbacks.permission_service,
        "check_quota",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        misc_callbacks, "load_prompts", lambda: {"face_swap": "swap prompt"}
    )
    monkeypatch.setattr(
        misc_callbacks,
        "list_quick_faceswap_template_files",
        lambda: ["quick_face/body.png"],
    )
    monkeypatch.setattr(
        misc_callbacks,
        "process_generation_task",
        fake_process_generation_task,
    )
    monkeypatch.setattr(
        misc_callbacks,
        "create_background_task",
        fake_create_background_task,
    )

    await misc_callbacks.random_faceswap_again_callback(update, context)
    assert len(scheduled) == 1

    await scheduled[0]

    assert process_calls == [
        {
            "context": context,
            "chat_id": 10001,
            "user_id": 12345,
            "username": "tester",
            "prompt": "swap prompt",
            "images": ["template:quick_face/body.png", "/tmp/face.png"],
            "task_type": "face_swap",
            "cleanup": False,
            "reply_markup": process_calls[0]["reply_markup"],
        }
    ]
    assert (
        process_calls[0]["reply_markup"].inline_keyboard[0][0].callback_data
        == "random_faceswap_again"
    )


@pytest.mark.asyncio
async def test_random_faceswap_again_reports_missing_template(monkeypatch):
    update = _build_random_faceswap_update()
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={"last_face_image": "/tmp/face.png"},
    )

    monkeypatch.setattr(misc_callbacks, "safe_answer_query", AsyncMock())
    send_message = AsyncMock()
    monkeypatch.setattr(misc_callbacks, "robust_send_message", send_message)
    monkeypatch.setattr(misc_callbacks, "is_maintenance_mode", lambda: False)
    monkeypatch.setattr(
        misc_callbacks, "_load_qqcc_config_for_context", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        misc_callbacks,
        "get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=88), False)),
    )
    monkeypatch.setattr(
        misc_callbacks.permission_service,
        "calculate_user_priority",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        misc_callbacks.permission_service,
        "check_quota",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        misc_callbacks, "load_prompts", lambda: {"face_swap": "swap prompt"}
    )
    monkeypatch.setattr(
        misc_callbacks, "list_quick_faceswap_template_files", lambda: []
    )
    create_background_task = AsyncMock()
    monkeypatch.setattr(
        misc_callbacks, "create_background_task", create_background_task
    )

    await misc_callbacks.random_faceswap_again_callback(update, context)

    create_background_task.assert_not_called()
    send_message.assert_awaited_once()
    assert "未找到身体模板" in send_message.await_args.args[2]
