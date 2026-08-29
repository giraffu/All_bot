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
        ("ref2v", ["person.png", "reference.png"], True),
    ],
)
async def test_pro_main_bot_allows_gallery_image_modes_to_contribute(
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
        "mode": mode,
        "prompt": "move",
        "images": images,
        "reference_descriptions": [],
        "duration": 5,
        "preset": "preview",
        "aspect": "16:9",
        "addon_models": [],
    }

    assert (
        await fsm._submit_generation(update, context, data) == ConversationHandler.END
    )
    assert submit.call_args.kwargs["allow_contribute"] is allow_contribute


@pytest.mark.asyncio
async def test_pro_entry_replaces_legacy_menu_with_mode_picker(monkeypatch):
    reply = AsyncMock()
    monkeypatch.setattr(fsm, "robust_reply_text", reply)
    monkeypatch.setattr(
        fsm,
        "load_advanced_video_pro_profiles",
        AsyncMock(
            return_value={
                mode: {"main_model": "10eros", "addon_items": []} for mode in fsm.MODES
            }
        ),
    )
    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    context = SimpleNamespace(user_data={}, lang="zh")
    update = SimpleNamespace(effective_message=object())

    state = await fsm.start(update, context)

    assert state == AdvancedVideoProState.WAIT_SETTINGS
    assert context.user_data["in_conversation"] == fsm.TAG
    assert context.user_data[fsm.DATA_KEY]["mode"] is None
    assert context.user_data[fsm.DATA_KEY]["runtime_profiles"]["i2v"] == {
        "main_model": "10eros",
        "addon_items": [],
    }
    assert "高级图生视频pro" in reply.await_args.args[1]
    assert "如果要切换功能，请发送 /cancel。" in reply.await_args.args[1]
    mode_callbacks = [
        button.callback_data
        for row in reply.await_args.kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert "avp_mode_ref2v" in mode_callbacks


@pytest.mark.asyncio
async def test_pro_t2v_settings_route_directly_to_prompt(monkeypatch):
    edit = AsyncMock()
    monkeypatch.setattr(fsm, "robust_edit_text", edit)
    query = SimpleNamespace(data="avp_mode_t2v", answer=AsyncMock(), message=object())
    context = SimpleNamespace(
        user_data={
            fsm.DATA_KEY: {
                "mode": None,
                "duration": 5,
                "preset": "preview",
                "aspect": "16:9",
                "images": [],
                "reference_descriptions": [],
            }
        },
        lang="zh",
    )
    update = SimpleNamespace(callback_query=query)

    assert (
        await fsm.settings_callback(update, context)
        == AdvancedVideoProState.WAIT_SETTINGS
    )
    query.data = "avp_settings_done"
    assert (
        await fsm.settings_callback(update, context)
        == AdvancedVideoProState.WAIT_PROMPT
    )


@pytest.mark.asyncio
async def test_pro_settings_hide_model_internals_and_scope_ref2va_effect_to_ref_mode(
    monkeypatch,
):
    edit = AsyncMock()
    monkeypatch.setattr(fsm, "robust_edit_text", edit)
    query = SimpleNamespace(data="avp_mode_t2v", answer=AsyncMock(), message=object())
    data = {
        "mode": None,
        "duration": 5,
        "preset": "preview",
        "aspect": "16:9",
        "runtime_profiles": {
            "t2v": {
                "main_model": "official",
                "addon_items": [{"name": "motion_booster", "strength": 0.7}],
            },
            "ref2v": {
                "main_model": "official_ref2v_turbo",
                "addon_items": [
                    {"name": "motion_booster_ref2va", "strength": 0.7},
                ],
            },
        },
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
        "Motion Booster",
        "REF2VA",
        "Mystic XXX",
        "HMBreasts",
        "VagAssist",
        "HMPussy",
        "HMPenis",
        "HMPussy V1 Stills",
        "Better Titfuck",
    ):
        assert private_term not in public_copy
    assert "直接发送提示词" in settings_text
    assert "如果要切换功能，请发送 /cancel。" in settings_text
    assert "成人动作测试一" not in button_text
    assert "成人动作测试二" not in button_text
    assert "成人动作强化" not in button_text
    assert "选满效果" not in button_text
    assert "清空效果" not in button_text
    callbacks = [button.callback_data for row in keyboard for button in row]
    assert not any(callback.startswith("avp_addon_") for callback in callbacks)
    assert "avp_settings_done" not in callbacks
    assert data["main_model"] == "official"
    assert data["addon_items"] == [
        {"name": "motion_booster", "strength": 0.7},
    ]

    query.data = "avp_mode_ref2v"
    await fsm.settings_callback(SimpleNamespace(callback_query=query), context)
    assert data["main_model"] == "official_ref2v_turbo"
    assert data["addon_items"] == [
        {"name": "motion_booster_ref2va", "strength": 0.7},
    ]


@pytest.mark.asyncio
async def test_pro_switching_mode_applies_that_modes_admin_profile(monkeypatch):
    monkeypatch.setattr(fsm, "robust_edit_text", AsyncMock())
    data = {
        "mode": "ref2v",
        "duration": 5,
        "preset": "preview",
        "aspect": "16:9",
        "images": [],
        "reference_descriptions": [],
        "runtime_profiles": {
            "i2v": {
                "main_model": "official",
                "addon_items": [{"name": "motion_booster", "strength": 0.7}],
            }
        },
    }
    query = SimpleNamespace(data="avp_mode_i2v", answer=AsyncMock(), message=object())

    await fsm.settings_callback(
        SimpleNamespace(callback_query=query),
        SimpleNamespace(user_data={fsm.DATA_KEY: data}, lang="zh"),
    )

    assert data["main_model"] == "official"
    assert data["addon_items"] == [
        {"name": "motion_booster", "strength": 0.7},
    ]


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
async def test_pro_prompt_submits_immediately_without_confirmation(monkeypatch):
    submit = AsyncMock(return_value=ConversationHandler.END)
    monkeypatch.setattr(fsm, "_submit_generation", submit)
    data = {
        "mode": "t2v",
        "duration": 5,
        "preset": "preview",
        "aspect": "16:9",
        "images": [],
        "reference_descriptions": [],
    }
    context = SimpleNamespace(user_data={fsm.DATA_KEY: data}, lang="zh")
    update = SimpleNamespace(
        message=SimpleNamespace(text="原始提示词"),
        effective_message=object(),
    )

    state = await fsm.receive_prompt(update, context)

    assert state == ConversationHandler.END
    assert data["prompt"] == "原始提示词"
    assert "original_prompt" not in data
    assert "optimizer_pending" not in data
    submit.assert_awaited_once_with(update, context, data)


@pytest.mark.parametrize(
    ("mode", "duration", "preset", "expected_cost"),
    [
        ("t2v", 10, "hd", 33),
        ("i2v", 15, "standard", 42),
        ("ref2v", 5, "preview", 11),
    ],
)
def test_pro_settings_show_current_credit_cost_and_option_prices(
    mode, duration, preset, expected_cost
):
    data = {
        "mode": mode,
        "duration": duration,
        "preset": preset,
        "aspect": "16:9",
    }
    context = SimpleNamespace(lang="zh")

    text = fsm._settings_text(context, data)
    button_text = [
        button.text
        for row in fsm._settings_keyboard(context, data).inline_keyboard
        for button in row
    ]

    assert f"预计消耗：{expected_cost} 灵石" in text
    assert any(
        str(expected_cost) in label and label.startswith("✅") for label in button_text
    )


@pytest.mark.parametrize(
    ("media_received", "expected_action"),
    [
        (False, "请输入视频提示词。"),
        (True, "图片已收到，请输入视频提示词。"),
    ],
)
def test_pro_prompt_request_explains_how_to_switch_features(
    media_received, expected_action
):
    text = fsm._prompt_request_text(
        SimpleNamespace(lang="zh"), {}, media_received=media_received
    )

    assert expected_action in text
    assert "如果要切换功能，请发送 /cancel。" in text


@pytest.mark.asyncio
async def test_pro_non_t2v_settings_prompt_explains_image_and_cancel_commands(
    monkeypatch,
):
    reply = AsyncMock()
    monkeypatch.setattr(fsm, "robust_reply_text", reply)
    context = SimpleNamespace(
        user_data={fsm.DATA_KEY: {"mode": "i2v"}},
        lang="zh",
    )
    update = SimpleNamespace(effective_message=object())

    state = await fsm.receive_settings_prompt(update, context)

    assert state == AdvancedVideoProState.WAIT_SETTINGS
    assert "请直接发送图片。" in reply.await_args.args[1]
    assert "如果要切换功能，请发送 /cancel。" in reply.await_args.args[1]


def test_pro_handler_has_no_prompt_confirmation_state():
    handler = fsm.get_advanced_video_pro_fsm_handler()

    assert AdvancedVideoProState.WAIT_CONFIRMATION not in handler.states


@pytest.mark.asyncio
async def test_ref2v_finish_references_offers_optional_main_character_voice(
    monkeypatch,
):
    edit = AsyncMock()
    monkeypatch.setattr(fsm, "robust_edit_text", edit)
    query = SimpleNamespace(data="avp_refs_done", answer=AsyncMock(), message=object())
    context = SimpleNamespace(
        user_data={
            fsm.DATA_KEY: {
                "mode": "ref2v",
                "images": ["subject.png"],
                "reference_audio": None,
            }
        },
        lang="zh",
    )

    state = await fsm.reference_callback(SimpleNamespace(callback_query=query), context)

    assert state == AdvancedVideoProState.WAIT_REFERENCE_AUDIO
    assert "主角参考语音" in edit.await_args.args[1]
    callbacks = [
        button.callback_data
        for row in edit.await_args.kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert callbacks == ["avp_audio_skip"]


@pytest.mark.asyncio
async def test_ref2v_audio_upload_shows_nonblocking_audio_1_reminder(monkeypatch):
    reply = AsyncMock()
    monkeypatch.setattr(fsm, "robust_reply_text", reply)
    monkeypatch.setattr(
        fsm,
        "download_telegram_file_to_fsm_temp",
        AsyncMock(return_value="/tmp/voice.ogg"),
    )
    telegram_file = object()
    context = SimpleNamespace(
        user_data={
            fsm.DATA_KEY: {
                "mode": "ref2v",
                "images": ["subject.png"],
                "reference_audio": None,
            }
        },
        bot=SimpleNamespace(get_file=AsyncMock(return_value=telegram_file)),
        lang="zh",
    )
    update = SimpleNamespace(
        message=SimpleNamespace(
            voice=SimpleNamespace(file_id="voice-id"),
            audio=None,
            document=None,
        )
    )

    state = await fsm.receive_reference_audio(update, context)

    assert state == AdvancedVideoProState.WAIT_PROMPT
    assert context.user_data[fsm.DATA_KEY]["reference_audio"] == "/tmp/voice.ogg"
    assert "<Audio 1>" in reply.await_args.args[1]
    assert "建议" in reply.await_args.args[1]


@pytest.mark.asyncio
async def test_ref2v_audio_skip_does_not_require_audio_tag(monkeypatch):
    edit = AsyncMock()
    monkeypatch.setattr(fsm, "robust_edit_text", edit)
    query = SimpleNamespace(data="avp_audio_skip", answer=AsyncMock(), message=object())
    context = SimpleNamespace(
        user_data={fsm.DATA_KEY: {"mode": "ref2v", "reference_audio": None}},
        lang="zh",
    )

    state = await fsm.reference_audio_callback(
        SimpleNamespace(callback_query=query), context
    )

    assert state == AdvancedVideoProState.WAIT_PROMPT
    assert "<Audio 1>" not in edit.await_args.args[1]
