from types import SimpleNamespace
from unittest.mock import AsyncMock
from decimal import Decimal

import pytest

from src.handlers.callbacks import billing_callbacks


@pytest.mark.asyncio
async def test_recharge_back_preserves_buttons_and_uses_unified_ton_webapp(
    monkeypatch,
):
    message = SimpleNamespace(edit_reply_markup=AsyncMock())
    query = SimpleNamespace(message=message)
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(lang="zh", user_data={})

    monkeypatch.setattr(billing_callbacks, "safe_answer_query", AsyncMock())
    monkeypatch.setattr(
        billing_callbacks,
        "build_ton_payment_mini_app_url",
        lambda: "https://web.example/billing?method=ton&kind=membership",
    )
    monkeypatch.setattr(
        billing_callbacks,
        "build_usdt_ton_payment_mini_app_url",
        lambda *, kind: f"https://web.example/billing?method=usdt-ton&kind={kind}",
    )

    await billing_callbacks.recharge_back_callback(update, context)

    reply_markup = message.edit_reply_markup.await_args.kwargs["reply_markup"]
    buttons = [row[0] for row in reply_markup.inline_keyboard]
    assert len(buttons) == 7
    assert buttons[0].web_app.url.endswith(
        "/billing?method=usdt-ton&kind=membership"
    )
    assert buttons[1].web_app.url.endswith(
        "/billing?method=usdt-ton&kind=credits"
    )
    assert buttons[2].web_app.url.endswith(
        "/billing?method=ton&kind=membership"
    )
    assert [button.callback_data for button in buttons[3:]] == [
        "recharge_stars_menu",
        "recharge_stars_credit_menu",
        "recharge_rmb_menu",
        "recharge_rmb_credit_menu",
    ]


@pytest.mark.asyncio
async def test_recharge_rmb_menu_callback_translates_membership_option_labels(
    monkeypatch,
):
    plans = [
        SimpleNamespace(
            id=1,
            name="基础月卡",
            identity_name="内门弟子",
            price_rmb="30.00",
        )
    ]
    message = SimpleNamespace(edit_reply_markup=AsyncMock())
    query = SimpleNamespace(message=message)
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(lang="en")

    monkeypatch.setattr(
        billing_callbacks,
        "list_visible_membership_plans",
        AsyncMock(return_value=plans),
    )
    monkeypatch.setattr(billing_callbacks, "safe_answer_query", AsyncMock())

    await billing_callbacks.recharge_rmb_menu_callback(update, context)

    reply_markup = message.edit_reply_markup.await_args.kwargs["reply_markup"]
    assert (
        reply_markup.inline_keyboard[0][0].text
        == "¥ 30.00 - Basic Monthly Plan (Inner Disciple)"
    )
    assert reply_markup.inline_keyboard[1][0].text == "🔙 Back to payment methods"


@pytest.mark.asyncio
async def test_buy_star_plan_callback_creates_pending_order_with_order_v2_payload(
    monkeypatch,
):
    plan = SimpleNamespace(
        id=1,
        name="Stars Plan",
        identity_name="内门弟子",
        duration_days=30,
        reward_credits=100,
        price_stars=100,
    )
    query = SimpleNamespace(
        data="buy_star_plan_1",
        from_user=SimpleNamespace(id=12345),
        message=SimpleNamespace(chat_id=12345),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(bot=SimpleNamespace(send_invoice=AsyncMock()))

    monkeypatch.setattr(
        billing_callbacks, "get_visible_membership_plan", AsyncMock(return_value=plan)
    )
    monkeypatch.setattr(
        billing_callbacks, "safe_answer_query", AsyncMock()
    )
    monkeypatch.setattr(
        billing_callbacks, "get_or_create_user_by_telegram", AsyncMock(return_value=(SimpleNamespace(id=2002), False))
    )
    monkeypatch.setattr(
        billing_callbacks, "is_order_v2_enabled", lambda: True
    )
    monkeypatch.setattr(
        billing_callbacks,
        "create_stars_pending_order",
        AsyncMock(return_value="bo_stars_1"),
    )

    context.lang = "en"
    await billing_callbacks.buy_star_plan_callback(update, context)

    context.bot.send_invoice.assert_awaited_once()
    assert (
        context.bot.send_invoice.await_args.kwargs["payload"] == "ORDER_V2:bo_stars_1"
    )
    assert (
        context.bot.send_invoice.await_args.kwargs["title"]
        == "💎 Sect Treasury - Stars Plan (Inner Disciple)"
    )


@pytest.mark.asyncio
async def test_buy_rmb_plan_failure_replaces_connecting_message(monkeypatch):
    plan = SimpleNamespace(
        id=1,
        name="RMB Plan",
        identity_name="内门弟子",
        duration_days=30,
        reward_credits=100,
        price_rmb=Decimal("30.00"),
    )
    message = SimpleNamespace(edit_text=AsyncMock())
    query = SimpleNamespace(
        data="buy_rmb_plan_1_alipay",
        from_user=SimpleNamespace(id=12345),
        message=message,
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(lang="zh", user_data={})

    safe_answer = AsyncMock()
    monkeypatch.setattr(billing_callbacks, "safe_answer_query", safe_answer)
    monkeypatch.setattr(
        billing_callbacks,
        "get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=2002), False)),
    )
    monkeypatch.setattr(
        billing_callbacks,
        "get_visible_membership_plan",
        AsyncMock(return_value=plan),
    )
    monkeypatch.setattr(
        billing_callbacks,
        "create_rmb_pending_order",
        AsyncMock(return_value=(SimpleNamespace(id=1), "public-order-1")),
    )
    monkeypatch.setattr(
        billing_callbacks,
        "create_rmb_payment_url",
        AsyncMock(return_value={"code": 0, "msg": "Invalid response format"}),
    )
    monkeypatch.setattr(
        billing_callbacks,
        "fail_rmb_payment_creation",
        AsyncMock(),
    )

    await billing_callbacks.buy_rmb_plan_callback(update, context)

    assert message.edit_text.await_count == 2
    failure_call = message.edit_text.await_args_list[-1]
    assert failure_call.kwargs["text"] == "❌ 获取支付链接失败：Invalid response format"
    reply_markup = failure_call.kwargs["reply_markup"]
    assert reply_markup.inline_keyboard[0][0].callback_data == "recharge_back"
    safe_answer.assert_awaited_once()
