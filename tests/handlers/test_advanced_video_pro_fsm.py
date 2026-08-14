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
async def test_pro_settings_expose_fixed_redmix_stack_without_addon_callbacks(monkeypatch):
    edit = AsyncMock()
    monkeypatch.setattr(fsm, "robust_edit_text", edit)
    query = SimpleNamespace(data="avp_mode_t2v", answer=AsyncMock(), message=object())
    data = {"mode": None, "duration": 5, "preset": "preview", "aspect": "16:9"}
    context = SimpleNamespace(user_data={fsm.DATA_KEY: data}, lang="zh")

    await fsm.settings_callback(SimpleNamespace(callback_query=query), context)

    assert data["mode"] == "t2v"
    assert "固定 RedMix 8-step 整合栈" in edit.await_args.args[1]
    callbacks = [button.callback_data for row in edit.await_args.kwargs["reply_markup"].inline_keyboard for button in row]
    assert not any(value.startswith("avp_addon_") for value in callbacks)


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


@pytest.mark.asyncio
async def test_pro_prompt_is_reviewed_before_generation_and_offers_optimizer(monkeypatch):
    reply = AsyncMock()
    monkeypatch.setattr(fsm, "robust_reply_text", reply)
    monkeypatch.setenv("MINIMAX_H3_PROMPT_OPTIMIZER_ENABLED", "true")
    data = {
        "mode": "t2v", "duration": 5, "preset": "preview", "aspect": "16:9",
        "images": [], "reference_descriptions": [],
    }
    context = SimpleNamespace(user_data={fsm.DATA_KEY: data}, lang="zh")
    update = SimpleNamespace(
        message=SimpleNamespace(text="原始提示词"),
        effective_message=object(),
    )

    state = await fsm.receive_prompt(update, context)

    assert state == AdvancedVideoProState.WAIT_CONFIRMATION
    assert data["original_prompt"] == "原始提示词"
    assert data["prompt"] == "原始提示词"
    callbacks = [
        button.callback_data
        for row in reply.await_args.kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert callbacks == ["avp_prompt_optimize", "avp_prompt_generate"]


@pytest.mark.asyncio
async def test_pro_direct_generate_uses_reviewed_prompt(monkeypatch):
    submit = AsyncMock(return_value=ConversationHandler.END)
    monkeypatch.setattr(fsm, "_submit_generation", submit)
    query = SimpleNamespace(data="avp_prompt_generate", answer=AsyncMock(), message=object())
    data = {"prompt": "reviewed", "optimizer_pending": False}
    context = SimpleNamespace(user_data={fsm.DATA_KEY: data}, lang="zh")
    update = SimpleNamespace(callback_query=query)

    state = await fsm.prompt_callback(update, context)

    assert state == ConversationHandler.END
    submit.assert_awaited_once_with(update, context, data)


@pytest.mark.asyncio
async def test_pro_optimizer_runs_in_background_and_replaces_prompt(monkeypatch):
    optimize = AsyncMock(return_value="optimized 200 word prompt")
    resolve_user = AsyncMock(
        return_value=(SimpleNamespace(id=7007, username="alice"), False)
    )
    edit = AsyncMock()
    captured = []
    monkeypatch.setattr(fsm, "optimize_advanced_video_prompt", optimize)
    monkeypatch.setattr(
        fsm,
        "get_or_create_user_by_telegram",
        resolve_user,
        raising=False,
    )
    monkeypatch.setattr(fsm, "robust_edit_text", edit)
    monkeypatch.setattr(fsm, "create_background_task", lambda _context, coro: captured.append(coro))
    monkeypatch.setenv("MINIMAX_H3_PROMPT_OPTIMIZER_ENABLED", "true")
    query = SimpleNamespace(data="avp_prompt_optimize", answer=AsyncMock(), message=object())
    data = {
        "mode": "i2v", "duration": 10,
        "images": ["/tmp/start.png"], "original_prompt": "original",
        "prompt": "original", "optimizer_pending": False,
    }
    context = SimpleNamespace(user_data={fsm.DATA_KEY: data}, lang="zh")
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=7, username="alice"),
        effective_chat=SimpleNamespace(id=99),
    )

    state = await fsm.prompt_callback(update, context)
    assert state == AdvancedVideoProState.WAIT_CONFIRMATION
    assert data["optimizer_pending"] is True
    assert len(captured) == 1

    await captured[0]

    assert data["prompt"] == "optimized 200 word prompt"
    assert data["optimizer_pending"] is False
    resolve_user.assert_awaited_once_with(7, username="alice")
    assert optimize.await_args.kwargs["internal_user_id"] == 7007
    assert optimize.await_args.kwargs["mode"] == "i2v"
    assert "addon_items" not in optimize.await_args.kwargs
    assert "优化完成" in edit.await_args.args[1]
