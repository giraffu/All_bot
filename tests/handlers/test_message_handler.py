from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.handlers import message_handler


def _build_private_update_with_edited_message(text: str = "unknown text"):
    chat = SimpleNamespace(type="private", id=10001)
    edited_message = SimpleNamespace(
        text=text,
        chat=chat,
        chat_id=chat.id,
    )
    user = SimpleNamespace(
        id=20001,
        username="tester",
        full_name="Test User",
    )
    return SimpleNamespace(
        message=None,
        edited_message=edited_message,
        effective_user=user,
        effective_chat=chat,
    )


def _build_context():
    return SimpleNamespace(
        bot=SimpleNamespace(),
        lang="zh",
        user_data={},
        t=lambda key: key,
    )


def _build_profile_update():
    chat = SimpleNamespace(type="private", id=10001)
    message = SimpleNamespace(text="个人中心", chat=chat, chat_id=chat.id)
    user = SimpleNamespace(
        id=20001,
        username="tester",
        full_name="Test User",
        first_name="Tester",
        language_code="zh",
    )
    return SimpleNamespace(
        message=message,
        edited_message=None,
        effective_user=user,
        effective_chat=chat,
    )


@pytest.mark.asyncio
async def test_handle_prompt_uses_edited_message_for_private_fallback(monkeypatch):
    reply_mock = AsyncMock()

    monkeypatch.setattr(message_handler, "ensure_user_access_reward", AsyncMock())
    monkeypatch.setattr(message_handler, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        "src.handlers.prompt_router.GLOBAL_REVERSE_MAP",
        {},
        raising=False,
    )
    monkeypatch.setattr(
        "src.i18n.keyboards.get_main_menu_keyboard",
        lambda _lang: "fake-keyboard",
    )

    update = _build_private_update_with_edited_message()
    context = _build_context()

    result = await message_handler.handle_prompt(update, context)

    assert result is None
    reply_mock.assert_awaited_once()
    call_args = reply_mock.await_args
    assert call_args.args[0] is update.edited_message
    assert "不认识的指令" in call_args.args[1]
    assert call_args.kwargs["reply_markup"] == "fake-keyboard"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "route_key", "keyboard_attr", "expected_text"),
    [
        ("主菜单", "menu.main_menu", "get_main_menu_keyboard", "已返回主菜单"),
        ("懒人P图", "menu.photo_edit", "get_photo_edit_keyboard", "system.photo_edit_hint"),
    ],
)
async def test_handle_prompt_route_uses_edited_message_reply_target(
    monkeypatch, text, route_key, keyboard_attr, expected_text
):
    reply_mock = AsyncMock()

    monkeypatch.setattr(message_handler, "ensure_user_access_reward", AsyncMock())
    monkeypatch.setattr(message_handler, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        "src.handlers.prompt_router.GLOBAL_REVERSE_MAP",
        {text: route_key},
        raising=False,
    )
    monkeypatch.setattr(
        f"src.i18n.keyboards.{keyboard_attr}",
        lambda _lang: "fake-keyboard",
    )

    update = _build_private_update_with_edited_message(text=text)
    context = _build_context()

    result = await message_handler.handle_prompt(update, context)

    assert result is None
    reply_mock.assert_awaited_once()
    call_args = reply_mock.await_args
    assert call_args.args[0] is update.edited_message
    assert expected_text in call_args.args[1]


@pytest.mark.asyncio
async def test_handle_share_displays_affiliate_balance_semantics(monkeypatch):
    reply_mock = AsyncMock()

    monkeypatch.setattr(message_handler, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        message_handler,
        "build_share_reply",
        AsyncMock(
            return_value=(
                "历史累计返佣：*$ 9.99 USDT*\n已兑换返佣：*$ 1.11 USDT*\n当前可兑换余额：*$ 8.88 USDT*\n返佣说明：历史累计返佣用于展示成绩；当前可兑换余额才会随兑换减少",
                "share-keyboard",
            )
        ),
    )

    update = _build_profile_update()
    context = _build_context()
    context.bot.username = "aivision666_bot"

    await message_handler.handle_share(update, context, text="分享赚灵石")

    reply_mock.assert_awaited_once()
    message_handler.build_share_reply.assert_awaited_once_with(
        context=context,
        user=update.effective_user,
    )
    sent_text = reply_mock.await_args.args[1]
    assert "历史累计返佣：*$ 9.99 USDT*" in sent_text
    assert "已兑换返佣：*$ 1.11 USDT*" in sent_text
    assert "当前可兑换余额：*$ 8.88 USDT*" in sent_text
    assert "返佣说明：历史累计返佣用于展示成绩；当前可兑换余额才会随兑换减少" in sent_text
    assert reply_mock.await_args.kwargs["reply_markup"] == "share-keyboard"


@pytest.mark.asyncio
async def test_handle_share_delegates_to_reply_with_async_payload(monkeypatch):
    reply_with_payload = AsyncMock(return_value=None)
    update = _build_profile_update()
    context = _build_context()

    monkeypatch.setattr(message_handler, "reply_with_async_payload", reply_with_payload)

    await message_handler.handle_share(update, context, text="分享赚灵石")

    reply_with_payload.assert_awaited_once_with(
        update,
        reply_text=message_handler.robust_reply_text,
        build_payload=message_handler.build_share_reply,
        context=context,
        user=update.effective_user,
    )


@pytest.mark.asyncio
async def test_handle_personal_center_uses_runtime_reply_builder(monkeypatch):
    reply_with_payload = AsyncMock(return_value=None)

    monkeypatch.setattr(message_handler, "reply_with_async_payload", reply_with_payload)

    update = _build_profile_update()
    context = _build_context()

    await message_handler.handle_personal_center(update, context, text="个人中心")

    reply_with_payload.assert_awaited_once_with(
        update,
        reply_text=message_handler.robust_reply_text,
        build_payload=message_handler.build_personal_center_reply,
        context=context,
        user=update.effective_user,
        invite_link="https://t.me/AiVisionAV",
        web_url="https://web.aivison.it.com/",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler_name", "build_payload_name", "text"),
    [
        ("handle_video_edit_menu", "build_video_edit_payload", "视频编辑"),
        ("handle_gallery_menu", "build_gallery_payload", "画廊"),
        ("handle_back_to_main_menu", "build_back_to_main_payload", "主菜单"),
        ("handle_recharge_menu", "build_recharge_payload", "充值"),
    ],
)
async def test_menu_handlers_delegate_to_reply_with_built_payload(
    monkeypatch, handler_name, build_payload_name, text
):
    reply_with_payload = AsyncMock(return_value=None)
    update = _build_private_update_with_edited_message(text=text)
    context = _build_context()

    monkeypatch.setattr(message_handler, "reply_with_built_payload", reply_with_payload)

    await getattr(message_handler, handler_name)(update, context, text=text)

    reply_with_payload.assert_awaited_once_with(
        update,
        reply_text=message_handler.robust_reply_text,
        build_payload=getattr(message_handler, build_payload_name),
        **({"context": context} if build_payload_name in {"build_video_edit_payload", "build_back_to_main_payload"} else {}),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler_name", "build_payload_name", "extra_kwargs"),
    [
        (
            "handle_switch_lang",
            "toggle_user_language",
            {"parse_mode": None, "context": "CTX", "user": "USER"},
        ),
        (
            "handle_queue_status",
            "get_queue_status_reply",
            {
                "context": "CTX",
                "task_type_display_names": message_handler.TASK_TYPE_DISPLAY_NAMES,
            },
        ),
    ],
)
async def test_async_menu_like_handlers_delegate_to_reply_with_async_payload(
    monkeypatch, handler_name, build_payload_name, extra_kwargs
):
    reply_with_payload = AsyncMock(return_value=None)
    update = _build_private_update_with_edited_message(text="noop")
    context = _build_context()

    monkeypatch.setattr(message_handler, "reply_with_async_payload", reply_with_payload)
    if handler_name == "handle_switch_lang":
        update.effective_user = "USER"
        context = "CTX"
    elif handler_name == "handle_queue_status":
        context = "CTX"

    await getattr(message_handler, handler_name)(update, context, text="noop")

    reply_with_payload.assert_awaited_once_with(
        update,
        reply_text=message_handler.robust_reply_text,
        build_payload=getattr(message_handler, build_payload_name),
        **extra_kwargs,
    )
