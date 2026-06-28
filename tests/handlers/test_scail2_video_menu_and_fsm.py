from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram import Update
from telegram.ext import ConversationHandler

from src.constants import (
    MODE_SCAIL2_ACTION_TRANSFER,
    MODE_SCAIL2_FACE_SWAP_V2,
    MODE_SCAIL2_VIDEO_REPLACEMENT,
)
from src.handlers import prompt_router
from src.handlers.fsm import scail2_video_fsm
from src.i18n.keyboards import get_main_menu_keyboard, get_video_to_video_keyboard
from src.i18n.translator import get_text


def _button_texts(row):
    return [button.text for button in row]


def _build_message(**kwargs):
    defaults = {"chat_id": 456, "text": None, "document": None, "photo": None, "video": None}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _build_context(**user_data):
    return SimpleNamespace(
        user_data=user_data or {},
        lang="zh",
        bot=SimpleNamespace(get_file=AsyncMock()),
    )


def _build_query(data: str):
    return SimpleNamespace(
        data=data,
        from_user=SimpleNamespace(id=123, username="tester", full_name="Tester"),
        message=SimpleNamespace(chat_id=456, message_id=789),
        answer=AsyncMock(),
    )


def _build_cancel_update():
    return Update.de_json(
        {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "date": 0,
                "chat": {"id": 456, "type": "private"},
                "from": {"id": 123, "is_bot": False, "first_name": "Aaron"},
                "text": "/cancel",
                "entities": [{"type": "bot_command", "offset": 0, "length": 7}],
            },
        },
        bot=SimpleNamespace(username="allbot"),
    )


def test_main_menu_uses_video_to_video_in_old_face_video_position():
    keyboard = get_main_menu_keyboard("zh")
    target_row = keyboard.keyboard[2]

    assert _button_texts(target_row) == [
        get_text("menu.photo_edit", "zh"),
        get_text("menu.video_edit", "zh"),
        get_text("menu.video_to_video", "zh"),
    ]


def test_video_to_video_keyboard_order():
    get_video_to_video_keyboard.cache_clear()
    keyboard = get_video_to_video_keyboard("zh")

    assert [_button_texts(row) for row in keyboard.keyboard] == [
        [
            get_text("menu.video_to_video_replacement", "zh"),
            get_text("menu.video_to_video_action_transfer", "zh"),
        ],
        [get_text("menu.face_video", "zh")],
        [get_text("menu.back_main", "zh")],
    ]


def test_global_menu_filter_includes_video_to_video_and_keeps_face_video_compat():
    prompt_router.GLOBAL_REVERSE_MAP.clear()

    prompt_router.build_global_menu_filter()

    assert (
        prompt_router.GLOBAL_REVERSE_MAP[get_text("menu.video_to_video", "zh")]
        == "menu.video_to_video"
    )
    assert (
        prompt_router.GLOBAL_REVERSE_MAP[
            get_text("menu.video_to_video_replacement", "zh")
        ]
        == "menu.video_to_video_replacement"
    )
    assert (
        prompt_router.GLOBAL_REVERSE_MAP[
            get_text("menu.video_to_video_action_transfer", "zh")
        ]
        == "menu.video_to_video_action_transfer"
    )
    assert (
        prompt_router.GLOBAL_REVERSE_MAP[
            get_text("menu.video_to_video_action_transfer_long", "zh")
        ]
        == "menu.video_to_video_action_transfer"
    )
    assert (
        prompt_router.GLOBAL_REVERSE_MAP[get_text("menu.face_video", "zh")]
        == "menu.face_video"
    )


def test_scail2_video_fsm_exposes_video_to_video_and_face_swap_entrypoints():
    handler = scail2_video_fsm.get_scail2_video_fsm_handler()

    assert handler.name == "scail2_video_fsm"
    assert len(handler.entry_points) == 4


def test_scail2_video_cancel_is_routed_to_fallback_not_state_catchalls():
    handler = scail2_video_fsm.get_scail2_video_fsm_handler()
    update = _build_cancel_update()

    for state in (
        scail2_video_fsm.Scail2VideoState.WAIT_REFERENCE_IMAGE,
        scail2_video_fsm.Scail2VideoState.WAIT_MOTION_VIDEO,
        scail2_video_fsm.Scail2VideoState.WAIT_PROMPT,
        ConversationHandler.TIMEOUT,
    ):
        assert not any(
            state_handler.check_update(update)
            for state_handler in handler.states[state]
        )

    assert handler.fallbacks[0].callback is scail2_video_fsm.cancel_conversation
    assert handler.fallbacks[0].check_update(update)


@pytest.mark.asyncio
async def test_start_action_transfer_initializes_mode(monkeypatch):
    reply_mock = AsyncMock()
    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(scail2_video_fsm, "robust_reply_text", reply_mock)

    update = SimpleNamespace(message=_build_message())
    context = _build_context()

    result = await scail2_video_fsm.start_action_transfer(update, context)

    assert result == scail2_video_fsm.Scail2VideoState.WAIT_REFERENCE_IMAGE
    assert context.user_data["in_conversation"] == "SCAIL2_VIDEO"
    assert (
        context.user_data["scail2_video_data"]["task_type"]
        == MODE_SCAIL2_ACTION_TRANSFER
    )
    reply_mock.assert_awaited_once()


def test_action_transfer_duration_keyboard_uses_merged_options():
    context = _build_context(
        scail2_video_data={"task_type": MODE_SCAIL2_ACTION_TRANSFER}
    )

    keyboard = scail2_video_fsm._build_duration_keyboard(context)

    assert [
        button.callback_data
        for row in keyboard.inline_keyboard[:-1]
        for button in row
    ] == [
        "fsm_scail2_duration_5",
        "fsm_scail2_duration_8",
        "fsm_scail2_duration_10",
        "fsm_scail2_duration_15",
        "fsm_scail2_duration_20",
    ]


@pytest.mark.asyncio
async def test_start_face_swap_v2_initializes_new_task_type(monkeypatch):
    reply_mock = AsyncMock()
    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(scail2_video_fsm, "robust_reply_text", reply_mock)

    update = SimpleNamespace(message=_build_message())
    context = _build_context()

    result = await scail2_video_fsm.start_face_swap_v2(update, context)

    assert result == scail2_video_fsm.Scail2VideoState.WAIT_REFERENCE_IMAGE
    assert (
        context.user_data["scail2_video_data"]["task_type"]
        == MODE_SCAIL2_FACE_SWAP_V2
    )
    reply_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_duration_selection_schedules_video_replacement_task(monkeypatch):
    edit_mock = AsyncMock()
    create_background_task_mock = Mock()
    context = _build_context(
        in_conversation="SCAIL2_VIDEO",
        scail2_video_data={
            "task_type": MODE_SCAIL2_VIDEO_REPLACEMENT,
            "reference_image_path": "/tmp/ref.png",
            "motion_video_path": "/tmp/motion.mp4",
            "prompt": "cinematic dance, detailed character",
        },
    )
    query = _build_query("fsm_scail2_duration_8")
    update = SimpleNamespace(callback_query=query)

    monkeypatch.setattr(scail2_video_fsm, "robust_edit_text", edit_mock)
    monkeypatch.setattr(
        scail2_video_fsm.permission_service,
        "check_quota",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        scail2_video_fsm,
        "process_scail2_video_task",
        lambda *args, **kwargs: ("bg-task", args, kwargs),
    )
    monkeypatch.setattr(
        scail2_video_fsm,
        "create_background_task",
        create_background_task_mock,
    )

    result = await scail2_video_fsm.process_duration_selection(update, context)

    assert result == ConversationHandler.END
    create_background_task_mock.assert_called_once()
    scheduled = create_background_task_mock.call_args.args[1]
    assert scheduled[0] == "bg-task"
    assert scheduled[2]["task_type"] == MODE_SCAIL2_VIDEO_REPLACEMENT
    assert scheduled[2]["reference_image_path"] == "/tmp/ref.png"
    assert scheduled[2]["motion_video_path"] == "/tmp/motion.mp4"
    assert scheduled[2]["prompt"] == "cinematic dance, detailed character"
    assert scheduled[2]["duration"] == 8
    assert "in_conversation" not in context.user_data
    assert "scail2_video_data" not in context.user_data


@pytest.mark.asyncio
async def test_skip_prompt_moves_to_duration_with_empty_prompt(monkeypatch):
    edit_mock = AsyncMock()
    context = _build_context(
        in_conversation="SCAIL2_VIDEO",
        scail2_video_data={
            "task_type": MODE_SCAIL2_FACE_SWAP_V2,
            "reference_image_path": "/tmp/ref.png",
            "motion_video_path": "/tmp/motion.mp4",
        },
    )
    query = _build_query("fsm_scail2_skip_prompt")
    update = SimpleNamespace(callback_query=query)

    monkeypatch.setattr(scail2_video_fsm, "robust_edit_text", edit_mock)

    result = await scail2_video_fsm.skip_prompt(update, context)

    assert result == scail2_video_fsm.Scail2VideoState.WAIT_DURATION
    assert context.user_data["scail2_video_data"]["prompt"] == ""
    query.answer.assert_awaited_once()
    edit_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_duration_selection_allows_skipped_prompt(monkeypatch):
    edit_mock = AsyncMock()
    create_background_task_mock = Mock()
    context = _build_context(
        in_conversation="SCAIL2_VIDEO",
        scail2_video_data={
            "task_type": MODE_SCAIL2_FACE_SWAP_V2,
            "reference_image_path": "/tmp/ref.png",
            "motion_video_path": "/tmp/motion.mp4",
            "prompt": "",
        },
    )
    query = _build_query("fsm_scail2_duration_5")
    update = SimpleNamespace(callback_query=query)

    monkeypatch.setattr(scail2_video_fsm, "robust_edit_text", edit_mock)
    monkeypatch.setattr(
        scail2_video_fsm.permission_service,
        "check_quota",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        scail2_video_fsm,
        "process_scail2_video_task",
        lambda *args, **kwargs: ("bg-task", args, kwargs),
    )
    monkeypatch.setattr(
        scail2_video_fsm,
        "create_background_task",
        create_background_task_mock,
    )

    result = await scail2_video_fsm.process_duration_selection(update, context)

    assert result == ConversationHandler.END
    scheduled = create_background_task_mock.call_args.args[1]
    assert scheduled[2]["task_type"] == MODE_SCAIL2_FACE_SWAP_V2
    assert scheduled[2]["prompt"] == ""
    assert scheduled[2]["duration"] == 5


@pytest.mark.asyncio
async def test_motion_video_rejects_files_over_40mb_before_download(monkeypatch):
    reply_mock = AsyncMock()
    context = _build_context(scail2_video_data={})
    message = _build_message(
        video=SimpleNamespace(
            file_id="video-file",
            file_size=scail2_video_fsm.SCAIL2_MAX_MOTION_VIDEO_BYTES + 1,
        )
    )
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=123))

    monkeypatch.setattr(scail2_video_fsm, "robust_reply_text", reply_mock)

    result = await scail2_video_fsm.receive_motion_video(update, context)

    assert result == scail2_video_fsm.Scail2VideoState.WAIT_MOTION_VIDEO
    context.bot.get_file.assert_not_awaited()
    reply_mock.assert_awaited_once()
    assert "40" in reply_mock.await_args.args[1]
