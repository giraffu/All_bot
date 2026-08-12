from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.ext import ConversationHandler

from src.handlers.conversation_states import AdvancedVideoProState
from src.handlers.fsm import advanced_video_pro_fsm as fsm


@pytest.mark.asyncio
async def test_pro_entry_replaces_legacy_menu_with_mode_picker(monkeypatch):
    reply = AsyncMock()
    monkeypatch.setattr(fsm, "robust_reply_text", reply)
    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    context = SimpleNamespace(user_data={}, lang="zh")
    update = SimpleNamespace(effective_message=object())

    state = await fsm.start(update, context)

    assert state == AdvancedVideoProState.WAIT_SETTINGS
    assert context.user_data["in_conversation"] == fsm.TAG
    assert context.user_data[fsm.DATA_KEY]["mode"] is None
    assert "高级图生视频pro" in reply.await_args.args[1]
    mode_callbacks = [button.callback_data for row in reply.await_args.kwargs["reply_markup"].inline_keyboard for button in row]
    assert "avp_mode_ref2v" not in mode_callbacks


@pytest.mark.asyncio
async def test_pro_t2v_settings_route_directly_to_prompt(monkeypatch):
    edit = AsyncMock()
    monkeypatch.setattr(fsm, "robust_edit_text", edit)
    query = SimpleNamespace(data="avp_mode_t2v", answer=AsyncMock(), message=object())
    context = SimpleNamespace(
        user_data={fsm.DATA_KEY: {"mode": None, "duration": 5, "preset": "preview", "aspect": "16:9", "images": [], "reference_descriptions": []}},
        lang="zh",
    )
    update = SimpleNamespace(callback_query=query)

    assert await fsm.settings_callback(update, context) == AdvancedVideoProState.WAIT_SETTINGS
    query.data = "avp_settings_done"
    assert await fsm.settings_callback(update, context) == AdvancedVideoProState.WAIT_PROMPT


@pytest.mark.asyncio
async def test_pro_settings_accept_user_addon_but_do_not_expose_acceleration(monkeypatch):
    edit = AsyncMock()
    monkeypatch.setattr(fsm, "robust_edit_text", edit)
    query = SimpleNamespace(data="avp_addon_penis", answer=AsyncMock(), message=object())
    data = {"mode": "t2v", "duration": 5, "preset": "preview", "aspect": "16:9", "addon_model": None}
    context = SimpleNamespace(user_data={fsm.DATA_KEY: data}, lang="zh")

    await fsm.settings_callback(SimpleNamespace(callback_query=query), context)

    assert data["addon_model"] == "penis"
    callbacks = [button.callback_data for row in edit.await_args.kwargs["reply_markup"].inline_keyboard for button in row]
    assert "avp_addon_penis" in callbacks
    assert all("lightx" not in value.lower() for value in callbacks)


@pytest.mark.asyncio
async def test_legacy_ltx_settings_are_explicitly_expired():
    query = SimpleNamespace(answer=AsyncMock())
    context = SimpleNamespace(lang="zh")
    state = await fsm.legacy_callback(SimpleNamespace(callback_query=query), context)
    assert state == ConversationHandler.END
    assert "旧设置已失效" in query.answer.await_args.args[0]


def test_pro_handler_keeps_historical_menu_route():
    handler = fsm.get_advanced_video_pro_fsm_handler()
    assert handler.name == "advanced_video_pro_fsm"
    assert AdvancedVideoProState.WAIT_SETTINGS in handler.states
