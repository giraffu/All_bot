import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram import Update
from telegram.ext import ConversationHandler

from src.handlers.conversation_states import AdvancedVideoProState
from src.handlers.fsm import advanced_video_pro_fsm as fsm


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "images", "allow_contribute"),
    [
        ("t2v", [], False),
        ("i2v", ["start.png"], True),
        ("flf2v", ["start.png", "end.png"], True),
    ],
)
async def test_pro_main_bot_only_allows_image_modes_to_contribute(
    monkeypatch, mode, images, allow_contribute
):
    submit = Mock(return_value=object())
    monkeypatch.setattr(fsm, "submit_advanced_video_pro_plan", submit)
    monkeypatch.setattr(fsm, "create_background_task", Mock())
    monkeypatch.setattr(fsm, "robust_reply_text", AsyncMock())
    monkeypatch.setattr(fsm.permission_service, "check_quota", AsyncMock())
    context = SimpleNamespace(user_data={fsm.DATA_KEY: {}}, lang="zh")
    update = SimpleNamespace(
        effective_message=object(),
        effective_user=SimpleNamespace(id=7, username="alice", full_name="Alice"),
        effective_chat=SimpleNamespace(id=99),
    )
    data = {
        "mode": mode, "prompt": "move", "images": images,
        "reference_descriptions": [], "duration": 5, "preset": "preview",
        "aspect": "16:9", "addon_models": [],
    }

    assert await fsm._submit_generation(update, context, data) == ConversationHandler.END
    assert submit.call_args.kwargs["allow_contribute"] is allow_contribute


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
    assert context.user_data[fsm.DATA_KEY]["addon_models"] == []
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
async def test_pro_settings_hide_model_internals_but_keep_six_effect_choices(monkeypatch):
    edit = AsyncMock()
    monkeypatch.setattr(fsm, "robust_edit_text", edit)
    query = SimpleNamespace(data="avp_mode_t2v", answer=AsyncMock(), message=object())
    data = {
        "mode": None,
        "duration": 5,
        "preset": "preview",
        "aspect": "16:9",
        "addon_models": [],
    }
    context = SimpleNamespace(user_data={fsm.DATA_KEY: data}, lang="zh")

    await fsm.settings_callback(SimpleNamespace(callback_query=query), context)

    assert data["mode"] == "t2v"
    settings_text = edit.await_args.args[1]
    keyboard = edit.await_args.kwargs["reply_markup"].inline_keyboard
    button_text = " ".join(button.text for row in keyboard for button in row)
    public_copy = f"{settings_text} {button_text}"
    for private_term in (
        "基础链路",
        "10Eros",
        "LightX2V",
        "LoRA",
        "NaughtyTimes",
        "HMNSFW",
        "HMBreasts",
        "VagAssist",
        "HMPussy",
        "HMPenis",
    ):
        assert private_term not in public_copy
    assert "效果增强：未启用" in settings_text
    assert "成人动作测试一" in button_text
    assert "成人动作测试二" in button_text
    assert "全选效果" in button_text
    assert "清空效果" in button_text
    callbacks = [button.callback_data for row in keyboard for button in row]
    assert "avp_addon_naughty_times" in callbacks
    assert "avp_addon_sex_pose" in callbacks
    assert "avp_addon_breasts" in callbacks
    assert "avp_addon_vagassist" in callbacks
    assert "avp_addon_pussy" in callbacks
    assert "avp_addon_penis" in callbacks
    assert "avp_addon_all" in callbacks
    assert "avp_addon_none" in callbacks


@pytest.mark.asyncio
async def test_pro_settings_toggle_addon_and_select_all(monkeypatch):
    monkeypatch.setattr(fsm, "robust_edit_text", AsyncMock())
    data = {
        "mode": "t2v", "duration": 5, "preset": "preview", "aspect": "16:9",
        "images": [], "reference_descriptions": [], "addon_models": [],
    }
    query = SimpleNamespace(
        data="avp_addon_naughty_times", answer=AsyncMock(), message=object()
    )
    context = SimpleNamespace(user_data={fsm.DATA_KEY: data}, lang="zh")
    update = SimpleNamespace(callback_query=query)

    await fsm.settings_callback(update, context)
    assert data["addon_models"] == ["naughty_times"]
    query.data = "avp_addon_all"
    await fsm.settings_callback(update, context)
    assert data["addon_models"] == list(fsm.MINIMAX_H3_ADDON_MODELS)
    query.data = "avp_addon_none"
    await fsm.settings_callback(update, context)
    assert data["addon_models"] == []


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


def test_pro_timeout_cleanup_matches_callback_updates():
    handler = fsm.get_advanced_video_pro_fsm_handler()
    callback_update = Update(update_id=1, callback_query=object())

    assert any(
        timeout_handler.check_update(callback_update)
        for timeout_handler in handler.states[ConversationHandler.TIMEOUT]
    )


@pytest.mark.asyncio
async def test_pro_callback_timeout_clears_conversation_guard():
    context = SimpleNamespace(
        user_data={
            "in_conversation": fsm.TAG,
            fsm.DATA_KEY: {"mode": "t2v", "images": []},
        },
        lang="zh",
    )
    callback_update = Update(update_id=1, callback_query=object())

    state = await fsm.timeout(callback_update, context)

    assert state == ConversationHandler.END
    assert "in_conversation" not in context.user_data
    assert fsm.DATA_KEY not in context.user_data


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
async def test_pro_optimizer_detaches_from_fsm_after_persistent_submission(monkeypatch):
    start_task = AsyncMock(return_value=SimpleNamespace(optimizer_task_id="optimizer-1"))
    monkeypatch.setattr(fsm, "start_advanced_video_prompt_task", start_task)
    monkeypatch.setattr(
        fsm,
        "get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=7007, username="alice"), False)),
    )
    edit = AsyncMock()
    monkeypatch.setattr(fsm, "robust_edit_text", edit)
    monkeypatch.setenv("MINIMAX_H3_PROMPT_OPTIMIZER_ENABLED", "true")
    data = {
        "mode": "t2v",
        "duration": 5,
        "preset": "preview",
        "aspect": "16:9",
        "images": [],
        "reference_descriptions": [],
        "addon_models": [],
        "original_prompt": "original",
        "prompt": "original",
        "optimizer_pending": False,
    }
    context = SimpleNamespace(
        user_data={fsm.DATA_KEY: data, "in_conversation": fsm.TAG},
        lang="zh",
    )
    update = SimpleNamespace(
        callback_query=SimpleNamespace(
            data="avp_prompt_optimize", answer=AsyncMock(), message=object()
        ),
        effective_user=SimpleNamespace(id=7, username="alice"),
        effective_chat=SimpleNamespace(id=99),
    )

    state = await fsm.prompt_callback(update, context)

    assert state == ConversationHandler.END
    assert fsm.DATA_KEY not in context.user_data
    assert "in_conversation" not in context.user_data
    assert start_task.await_args.kwargs["internal_user_id"] == 7007
    assert start_task.await_args.kwargs["generation_cost"] == 10
    assert "可以继续使用其他功能" in edit.await_args.args[1]


@pytest.mark.asyncio
async def test_pro_optimizer_retry_uses_a_new_client_request_id(monkeypatch):
    start_task = AsyncMock(
        side_effect=[
            RuntimeError("first attempt failed"),
            SimpleNamespace(optimizer_task_id="optimizer-2"),
        ]
    )
    resolve_user = AsyncMock(
        return_value=(SimpleNamespace(id=7007, username="alice"), False)
    )
    monkeypatch.setattr(fsm, "start_advanced_video_prompt_task", start_task)
    monkeypatch.setattr(fsm, "get_or_create_user_by_telegram", resolve_user)
    monkeypatch.setattr(fsm, "robust_edit_text", AsyncMock())
    monkeypatch.setenv("MINIMAX_H3_PROMPT_OPTIMIZER_ENABLED", "true")
    query = SimpleNamespace(
        data="avp_prompt_optimize", answer=AsyncMock(), message=object()
    )
    data = {
        "mode": "i2v",
        "duration": 10,
        "preset": "preview",
        "aspect": "16:9",
        "images": ["/tmp/start.png"],
        "reference_descriptions": [],
        "addon_models": [],
        "original_prompt": "original",
        "prompt": "original",
        "optimizer_pending": False,
    }
    context = SimpleNamespace(user_data={fsm.DATA_KEY: data}, lang="zh")
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=7, username="alice"),
        effective_chat=SimpleNamespace(id=99),
    )

    await fsm.prompt_callback(update, context)
    assert data["optimizer_pending"] is False

    await fsm.prompt_callback(update, context)

    first_request_id = start_task.await_args_list[0].kwargs["client_request_id"]
    retry_request_id = start_task.await_args_list[1].kwargs["client_request_id"]
    assert first_request_id != retry_request_id
    assert str(uuid.UUID(first_request_id)) == first_request_id
    assert str(uuid.UUID(retry_request_id)) == retry_request_id


@pytest.mark.asyncio
async def test_pro_optimizer_error_does_not_expose_internal_http_details(monkeypatch):
    start_task = AsyncMock(
        side_effect=RuntimeError(
            "System error: Client error '409 Conflict' for url "
            "'http://central-api:8003/api/v1/prompt_optimize'"
        )
    )
    edit = AsyncMock()
    monkeypatch.setattr(fsm, "start_advanced_video_prompt_task", start_task)
    monkeypatch.setattr(
        fsm,
        "get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=7007), False)),
    )
    monkeypatch.setattr(fsm, "robust_edit_text", edit)
    monkeypatch.setenv("MINIMAX_H3_PROMPT_OPTIMIZER_ENABLED", "true")
    data = {
        "mode": "t2v",
        "duration": 5,
        "preset": "preview",
        "aspect": "16:9",
        "images": [],
        "reference_descriptions": [],
        "addon_models": [],
        "original_prompt": "original",
        "prompt": "original",
        "optimizer_pending": False,
    }
    context = SimpleNamespace(user_data={fsm.DATA_KEY: data}, lang="zh")
    update = SimpleNamespace(
        callback_query=SimpleNamespace(
            data="avp_prompt_optimize", answer=AsyncMock(), message=object()
        ),
        effective_user=SimpleNamespace(id=7, username="alice"),
        effective_chat=SimpleNamespace(id=99),
    )

    await fsm.prompt_callback(update, context)

    public_error = edit.await_args.args[1]
    assert "提示词优化提交失败" in public_error
    assert "原提示词已保留" in public_error
    assert "central-api" not in public_error
    assert "409 Conflict" not in public_error
    assert "http://" not in public_error
