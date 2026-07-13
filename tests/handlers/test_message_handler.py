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
        ("主菜单", "menu.main_menu", "get_main_menu_keyboard", "system.back_to_main"),
        ("图片换脸", "menu.photo_edit", "get_photo_edit_keyboard", "system.photo_edit_hint"),
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
    monkeypatch.setattr(
        message_handler,
        "build_versioned_mini_app_url",
        lambda: "https://web.aivison.it.com/?v=test-build",
    )

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
        web_url="https://web.aivison.it.com/?v=test-build",
    )


@pytest.mark.asyncio
async def test_handle_checkin_replies_gate_payload_before_building_checkin(monkeypatch):
    reply_mock = AsyncMock()
    update = _build_profile_update()
    context = _build_context()

    monkeypatch.setattr(message_handler, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        message_handler,
        "get_checkin_gate_reply",
        AsyncMock(return_value=("gate-text", "gate-keyboard")),
    )
    build_checkin_reply = AsyncMock(return_value="should-not-run")
    monkeypatch.setattr(message_handler, "build_checkin_reply", build_checkin_reply)

    await message_handler.handle_checkin(update, context, text="签到")

    reply_mock.assert_awaited_once_with(
        update.message,
        "gate-text",
        parse_mode="Markdown",
        reply_markup="gate-keyboard",
    )
    build_checkin_reply.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler_name", "build_payload_name", "text"),
    [
        ("handle_photo_edit_menu", "build_photo_edit_payload", "图片换脸"),
        ("handle_lazy_bot_menu", "build_lazy_bot_payload", "懒人bot"),
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
    if handler_name == "handle_photo_edit_menu":
        monkeypatch.setattr(message_handler, "ensure_user_access_reward", AsyncMock())

    await getattr(message_handler, handler_name)(update, context, text=text)

    reply_with_payload.assert_awaited_once_with(
        update,
        reply_text=message_handler.robust_reply_text,
        build_payload=getattr(message_handler, build_payload_name),
        **(
            {"context": context}
            if build_payload_name in {
                "build_photo_edit_payload",
                "build_back_to_main_payload",
                "build_lazy_bot_payload",
                "build_recharge_payload",
            }
            else {}
        ),
    )


@pytest.mark.asyncio
async def test_old_gallery_text_routes_to_lazy_bot_payload_in_main_bot(monkeypatch):
    reply_with_payload = AsyncMock(return_value=None)
    update = _build_private_update_with_edited_message(text="修仙市集")
    context = _build_context()

    monkeypatch.setattr(message_handler, "reply_with_built_payload", reply_with_payload)

    await message_handler.handle_lazy_bot_menu(update, context, text="修仙市集")

    reply_with_payload.assert_awaited_once_with(
        update,
        reply_text=message_handler.robust_reply_text,
        build_payload=message_handler.build_lazy_bot_payload,
        context=context,
    )


def test_migrated_lazy_text_routes_point_to_lazy_bot_handler():
    for route_key in (
        "menu.gallery",
        "qqcc.menu.market",
        "menu.video_edit",
        "qqcc.menu.ai_draw",
        "qqcc.menu.ai_filter",
        "qqcc.menu.quick_faceswap",
    ):
        assert message_handler.prompt_routes[route_key] is message_handler.handle_lazy_bot_menu


@pytest.mark.asyncio
async def test_dispatch_built_menu_handler_rewards_user_before_reply(monkeypatch):
    reply_with_payload = AsyncMock(return_value=None)
    ensure_reward = AsyncMock(return_value=None)
    update = _build_profile_update()
    context = _build_context()

    monkeypatch.setattr(message_handler, "reply_with_built_payload", reply_with_payload)
    monkeypatch.setattr(message_handler, "ensure_user_access_reward", ensure_reward)

    result = await message_handler._dispatch_built_menu_handler(
        update,
        context,
        build_payload=message_handler.build_photo_edit_payload,
        include_context=True,
        ensure_reward=True,
    )

    assert result is None
    ensure_reward.assert_awaited_once_with(context, update.effective_user)
    reply_with_payload.assert_awaited_once_with(
        update,
        reply_text=message_handler.robust_reply_text,
        build_payload=message_handler.build_photo_edit_payload,
        context=context,
    )


@pytest.mark.asyncio
async def test_dispatch_built_menu_handler_short_circuits_when_reward_user_missing(monkeypatch):
    reply_with_payload = AsyncMock(return_value=None)
    ensure_reward = AsyncMock(return_value=None)
    update = _build_private_update_with_edited_message(text="图片换脸")
    update.effective_user = None
    context = _build_context()

    monkeypatch.setattr(message_handler, "reply_with_built_payload", reply_with_payload)
    monkeypatch.setattr(message_handler, "ensure_user_access_reward", ensure_reward)

    result = await message_handler._dispatch_built_menu_handler(
        update,
        context,
        build_payload=message_handler.build_photo_edit_payload,
        include_context=True,
        ensure_reward=True,
    )

    assert result is None
    ensure_reward.assert_not_awaited()
    reply_with_payload.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_async_menu_handler_passes_common_reply_dependencies():
    impl = AsyncMock(return_value=None)
    update = _build_private_update_with_edited_message(text="noop")
    context = _build_context()

    result = await message_handler._dispatch_async_menu_handler(
        update,
        context,
        impl=impl,
        build_payload=message_handler.build_share_reply,
        user="USER",
    )

    assert result is None
    impl.assert_awaited_once_with(
        update,
        context=context,
        build_payload=message_handler.build_share_reply,
        reply_with_async_payload=message_handler.reply_with_async_payload,
        reply_text=message_handler.robust_reply_text,
        user="USER",
    )


@pytest.mark.asyncio
async def test_async_menu_builder_keeps_queue_extra_kwargs():
    impl = AsyncMock(return_value=None)
    update = _build_private_update_with_edited_message(text="排队")
    context = _build_context()
    handler = message_handler._build_async_menu_handler(
        handler_name="handle_queue_status",
        route_keys=("menu.queue",),
        impl_ref=lambda: message_handler.handle_queue_status_impl,
        build_payload_ref=lambda: message_handler.get_queue_status_reply,
        task_type_display_names=message_handler.TASK_TYPE_DISPLAY_NAMES,
    )

    original_impl = message_handler.handle_queue_status_impl
    try:
        message_handler.handle_queue_status_impl = impl
        result = await handler(update, context, text="排队")
    finally:
        message_handler.handle_queue_status_impl = original_impl

    assert result is None
    impl.assert_awaited_once_with(
        update,
        context=context,
        build_payload=message_handler.get_queue_status_reply,
        reply_with_async_payload=message_handler.reply_with_async_payload,
        reply_text=message_handler.robust_reply_text,
        task_type_display_names=message_handler.TASK_TYPE_DISPLAY_NAMES,
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
                "user": "USER",
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
        update.effective_user = "USER"
        context = "CTX"

    await getattr(message_handler, handler_name)(update, context, text="noop")

    reply_with_payload.assert_awaited_once_with(
        update,
        reply_text=message_handler.robust_reply_text,
        build_payload=getattr(message_handler, build_payload_name),
        **extra_kwargs,
    )


def _build_media_update():
    chat = SimpleNamespace(type="private", id=10001)
    message = SimpleNamespace(
        chat=chat,
        chat_id=chat.id,
        photo=["photo"],
        video="video",
        document="document",
    )
    user = SimpleNamespace(id=20001, username="tester", full_name="Test User")
    return SimpleNamespace(
        message=message,
        edited_message=None,
        effective_user=user,
        effective_chat=chat,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler_name", "unsupported_message"),
    [
        ("handle_photo", None),
        ("handle_video", message_handler.UNSUPPORTED_VIDEO_MESSAGE),
        ("handle_document", message_handler.UNSUPPORTED_DOCUMENT_MESSAGE),
    ],
)
async def test_media_handlers_delegate_with_expected_unsupported_message(
    monkeypatch, handler_name, unsupported_message
):
    handle_media_update_impl = AsyncMock(return_value="handled")
    update = _build_media_update()
    context = _build_context()

    monkeypatch.setattr(
        "src.handlers.message_handler_media_entry.handle_media_update_impl",
        handle_media_update_impl,
    )

    result = await getattr(message_handler, handler_name)(update, context)

    assert result == "handled"
    handle_media_update_impl.assert_awaited_once_with(
        update,
        context,
        handle_media_entry=message_handler.handle_media_entry,
        unsupported_message=unsupported_message,
        is_mentioned=message_handler._is_mentioned,
        ensure_access_and_reward=message_handler.ensure_access_and_reward,
        on_template_contribution=message_handler._handle_template_contribution,
        on_photo_idle=message_handler._handle_photo_idle,
        handle_media_message_fn=message_handler.handle_media_message,
    )
