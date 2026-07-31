from types import SimpleNamespace
from unittest.mock import AsyncMock
import warnings

import pytest
from telegram.ext import ConversationHandler
from telegram.warnings import PTBUserWarning

from src.handlers.conversation_states import AffiliateRedeemState
from src.handlers.fsm import affiliate_redeem_fsm


def _context():
    return SimpleNamespace(
        user_data={},
        t=lambda key: key,
    )


def _message_update(text: str):
    return SimpleNamespace(
        message=SimpleNamespace(text=text),
        effective_user=SimpleNamespace(
            id=5340735895,
            username="Hgirraffe",
            full_name="Hgirraffe",
            language_code="zh",
        ),
    )


def test_usdt_redeem_conversation_has_three_steps_and_five_minute_timeout():
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=PTBUserWarning)
        handler = affiliate_redeem_fsm.get_affiliate_redeem_fsm_handler()

    assert handler.conversation_timeout == 300
    assert AffiliateRedeemState.WAIT_USDT_AMOUNT in handler.states
    assert AffiliateRedeemState.WAIT_USDT_ADDRESS in handler.states
    assert AffiliateRedeemState.WAIT_USDT_CONFIRM in handler.states
    confirm = handler.states[AffiliateRedeemState.WAIT_USDT_CONFIRM][0]
    assert confirm.pattern.pattern == "^affiliate_redeem_usdt_(confirm|cancel)$"


@pytest.mark.asyncio
async def test_usdt_amount_and_address_are_normalized_before_confirmation(
    monkeypatch,
):
    reply = AsyncMock()
    monkeypatch.setattr(affiliate_redeem_fsm, "robust_reply_text", reply)
    context = _context()

    amount_state = await affiliate_redeem_fsm.receive_usdt_amount(
        _message_update("5"),
        context,
    )
    address_state = await affiliate_redeem_fsm.receive_usdt_address(
        _message_update("EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"),
        context,
    )

    assert amount_state == AffiliateRedeemState.WAIT_USDT_ADDRESS
    assert address_state == AffiliateRedeemState.WAIT_USDT_CONFIRM
    assert context.user_data[affiliate_redeem_fsm.AFFILIATE_REDEEM_FSM_KEY] == {
        "amount_usdt": affiliate_redeem_fsm.Decimal("5.0000"),
        "payout_address": (
            "UQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_p0p"
        ),
    }
    assert "TON" in reply.await_args_list[-1].args[1]


@pytest.mark.asyncio
async def test_global_menu_interrupt_clears_usdt_conversation(monkeypatch):
    reply = AsyncMock()
    monkeypatch.setattr(affiliate_redeem_fsm, "robust_reply_text", reply)
    monkeypatch.setattr(
        affiliate_redeem_fsm,
        "is_global_menu_command",
        lambda text: text == "个人中心",
    )
    context = _context()
    context.user_data.update(
        {
            "in_conversation": True,
            affiliate_redeem_fsm.AFFILIATE_REDEEM_FSM_KEY: {
                "amount_usdt": affiliate_redeem_fsm.Decimal("5")
            },
        }
    )

    state = await affiliate_redeem_fsm.receive_usdt_amount(
        _message_update("个人中心"),
        context,
    )

    assert state == ConversationHandler.END
    assert "in_conversation" not in context.user_data
    assert affiliate_redeem_fsm.AFFILIATE_REDEEM_FSM_KEY not in context.user_data
