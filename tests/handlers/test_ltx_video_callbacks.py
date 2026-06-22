from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.constants import MODE_LTX_VIDEO
from src.handlers.callbacks import ltx_video_callbacks


def _build_update(query):
    return SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=12345, username="tester"),
        effective_chat=SimpleNamespace(id=10001),
    )


@pytest.mark.asyncio
async def test_stitch_ltx_video_callback_uses_full_chain(monkeypatch):
    safe_answer = AsyncMock()
    send_message = AsyncMock()
    send_video = AsyncMock(return_value=SimpleNamespace(message_id=99))
    edit_reply_markup = AsyncMock()
    current_history = SimpleNamespace(user_id=321, task_id="ltx-task-3")
    previous_histories = [
        SimpleNamespace(user_id=321, task_id="ltx-task-1"),
        SimpleNamespace(user_id=321, task_id="ltx-task-2"),
    ]

    monkeypatch.setattr(ltx_video_callbacks, "safe_answer_query", safe_answer)
    monkeypatch.setattr(ltx_video_callbacks, "robust_send_message", send_message)
    monkeypatch.setattr(ltx_video_callbacks, "robust_send_video", send_video)
    monkeypatch.setattr(
        ltx_video_callbacks, "robust_edit_reply_markup", edit_reply_markup
    )
    monkeypatch.setattr(
        ltx_video_callbacks,
        "load_owned_ltx_history",
        AsyncMock(side_effect=[current_history, *previous_histories]),
    )
    stitch_mock = AsyncMock(
        return_value=SimpleNamespace(
            video_bytes=b"stitched-video",
            task_id="ltx-stitched-task",
            task_type=MODE_LTX_VIDEO,
            prompt="stitched prompt",
            extra_outputs={"ltx_chain_stitch": {"segment_count": 3}},
            allow_contribute=True,
            segment_count=3,
        )
    )
    monkeypatch.setattr(
        ltx_video_callbacks, "stitch_ltx_histories_and_create_history", stitch_mock
    )

    message = SimpleNamespace(
        message_id=77,
        reply_markup=InlineKeyboardMarkup(
            [[
                InlineKeyboardButton(
                    "🔗 完成拼接",
                    callback_data="ltx_stitch_chain:ltx-task-3",
                )
            ]]
        ),
    )
    query = SimpleNamespace(data="ltx_stitch_chain:ltx-task-3", message=message)
    update = _build_update(query)
    context = SimpleNamespace(
        bot=MagicMock(),
        bot_data={
            "msg_meta_77": {
                "task_id": "ltx-task-3",
                "ltx_chain_task_ids": ["ltx-task-1", "ltx-task-2"],
            }
        },
    )

    await ltx_video_callbacks.stitch_ltx_video_callback(update, context)

    stitch_mock.assert_awaited_once()
    stitched_histories = stitch_mock.await_args.kwargs["histories"]
    assert [history.task_id for history in stitched_histories] == [
        "ltx-task-1",
        "ltx-task-2",
        "ltx-task-3",
    ]
    assert stitch_mock.await_args.kwargs["user_id"] == 321
    assert stitch_mock.await_args.kwargs["source_task_id"] == "ltx-task-3"
    assert stitch_mock.await_args.kwargs["source"] == "bot"
    send_video.assert_awaited_once()
    assert send_video.await_args.kwargs["caption"] == "✅ 3 段 LTX 视频已拼接完成"
    reply_markup = send_video.await_args.kwargs["reply_markup"]
    first_row = reply_markup.inline_keyboard[0]
    assert [btn.callback_data for btn in first_row] == [
        "submit_gallery_ltx-stitched-task"
    ]
    assert context.bot_data["msg_meta_99"]["task_id"] == "ltx-stitched-task"
    assert context.bot_data["msg_meta_99"]["prompt"] == "stitched prompt"
    edit_reply_markup.assert_awaited_once()
