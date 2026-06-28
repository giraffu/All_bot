from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.ext import ConversationHandler

from src.constants import MODE_TXT2IMG
from src.handlers import prompt_router
from src.handlers.fsm import txt2img_fsm
from src.i18n.keyboards import get_main_menu_keyboard
from src.i18n.translator import get_text


def test_main_menu_places_txt2img_left_of_i2i_pro():
    keyboard = get_main_menu_keyboard("zh")
    target_row = keyboard.keyboard[3]

    assert [button.text for button in target_row] == [
        get_text("menu.txt2img", "zh"),
        get_text("menu.i2i_pro", "zh"),
        get_text("menu.free_edit", "zh"),
    ]


def test_main_menu_does_not_show_free_edit_v2_as_top_level_button():
    get_main_menu_keyboard.cache_clear()
    keyboard = get_main_menu_keyboard("zh")
    button_texts = [
        button.text
        for row in keyboard.keyboard
        for button in row
    ]

    assert get_text("menu.free_edit_v2", "zh") not in button_texts


def test_build_global_menu_filter_includes_txt2img_label():
    prompt_router.GLOBAL_REVERSE_MAP.clear()

    prompt_router.build_global_menu_filter()

    assert prompt_router.GLOBAL_REVERSE_MAP[get_text("menu.txt2img", "zh")] == "menu.txt2img"
    assert prompt_router.GLOBAL_REVERSE_MAP[get_text("menu.txt2img", "en")] == "menu.txt2img"


def test_txt2img_fsm_exposes_handler():
    handler = txt2img_fsm.get_txt2img_fsm_handler()

    assert handler.name == "txt2img_fsm"
    assert len(handler.entry_points) == 1


@pytest.mark.asyncio
async def test_start_txt2img_uses_english_locale(monkeypatch):
    reply_mock = AsyncMock()

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(txt2img_fsm, "robust_reply_text", reply_mock)

    update = SimpleNamespace(
        message=SimpleNamespace(text="✨ Text2Img"),
    )
    context = SimpleNamespace(user_data={}, lang="en")

    result = await txt2img_fsm.start_txt2img(update, context)

    assert result == txt2img_fsm.Txt2ImgState.WAIT_PROMPT
    assert context.user_data["txt2img_data"]["cost"] > 0
    assert "Entered Text2Img mode" in reply_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_receive_prompt_submits_txt2img_task(monkeypatch):
    reply_mock = AsyncMock()
    quota_mock = AsyncMock()
    create_task_mock = Mock()
    captured = {}

    monkeypatch.setattr(txt2img_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(txt2img_fsm, "is_global_menu_command", lambda _text: False)
    monkeypatch.setattr(txt2img_fsm.permission_service, "check_quota", quota_mock)

    def fake_process_generation_task(
        context,
        chat_id,
        user_id,
        username,
        prompt,
        images,
        **kwargs,
    ):
        captured.update(
            {
                "context": context,
                "chat_id": chat_id,
                "user_id": user_id,
                "username": username,
                "prompt": prompt,
                "images": images,
                **kwargs,
            }
        )
        return "submitted-coro"

    def fake_create_background_task(context, coro):
        create_task_mock(context, coro)

    monkeypatch.setattr(txt2img_fsm, "process_generation_task", fake_process_generation_task)
    monkeypatch.setattr(txt2img_fsm, "create_background_task", fake_create_background_task)

    update = SimpleNamespace(
        effective_user=SimpleNamespace(
            id=123,
            username="tester",
            full_name="Test User",
        ),
        effective_chat=SimpleNamespace(id=456),
        message=SimpleNamespace(chat_id=456, text="a fox immortal, moonlight, cinematic"),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={
            "in_conversation": "TXT2IMG",
            "txt2img_data": {"cost": 2},
        },
    )

    result = await txt2img_fsm.receive_prompt(update, context)

    assert result == ConversationHandler.END
    quota_mock.assert_awaited_once()
    assert captured["task_type"] == MODE_TXT2IMG
    assert captured["images"] == []
    assert captured["prompt"] == "a fox immortal, moonlight, cinematic"
    create_task_mock.assert_called_once_with(context, "submitted-coro")
    assert "in_conversation" not in context.user_data
    assert "txt2img_data" not in context.user_data
