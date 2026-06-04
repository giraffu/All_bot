from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.handlers.callbacks.gallery_callbacks_interactions import (
    _build_gallery_reaction_reply_markup,
    _extract_gallery_submit_media_metadata,
    handle_rate_action,
    handle_submit_gallery_callback,
)


def test_extract_gallery_submit_media_metadata_prefers_video_payload():
    query = SimpleNamespace(
        message=SimpleNamespace(
            video=SimpleNamespace(width=1280, height=720, duration=8),
            photo=[],
        )
    )

    assert _extract_gallery_submit_media_metadata(query) == ("video", 1280, 720, 8)


def test_extract_gallery_submit_media_metadata_uses_last_photo_size():
    query = SimpleNamespace(
        message=SimpleNamespace(
            video=None,
            photo=[
                SimpleNamespace(width=512, height=512),
                SimpleNamespace(width=1024, height=768),
            ],
        )
    )

    assert _extract_gallery_submit_media_metadata(query) == ("image", 1024, 768, None)


def test_build_gallery_reaction_reply_markup_updates_like_and_dislike_buttons():
    inline_keyboard = [
        [
            InlineKeyboardButton("👍 赞 (1)", callback_data="gallery_like_9_latest_all_1"),
            InlineKeyboardButton("👎 踩 (2)", callback_data="gallery_dislike_9_latest_all_1"),
        ],
        [InlineKeyboardButton("其他", callback_data="noop")],
    ]

    markup = _build_gallery_reaction_reply_markup(
        inline_keyboard=inline_keyboard,
        post_id=9,
        action="like",
        action_state="liked",
        likes_count=5,
        dislikes_count=2,
        sort_type="latest",
        category="all",
        page="1",
    )

    assert markup.inline_keyboard[0][0].text == "✅ 已赞 (5)"
    assert markup.inline_keyboard[0][0].callback_data == "gallery_like_9_latest_all_1"
    assert markup.inline_keyboard[0][1].text == "👎 踩 (2)"
    assert markup.inline_keyboard[1][0].text == "其他"


@pytest.mark.asyncio
async def test_handle_submit_gallery_callback_rejects_submission_banned_user(monkeypatch):
    query = SimpleNamespace(
        data="submit_gallery_task-1",
        from_user=SimpleNamespace(id=123),
        message=SimpleNamespace(video=None, photo=[SimpleNamespace(width=512, height=512)]),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace()
    safe_answer_query = AsyncMock()

    monkeypatch.setattr(
        "src.handlers.callbacks.gallery_callbacks_interactions.get_or_create_user_by_telegram",
        AsyncMock(
            return_value=(
                SimpleNamespace(
                    id=321,
                    is_submission_banned=True,
                    submission_ban_reason=None,
                ),
                False,
            )
        ),
    )
    monkeypatch.setattr(
        "src.handlers.callbacks.gallery_callbacks_interactions.safe_answer_query",
        safe_answer_query,
    )

    await handle_submit_gallery_callback(update, context)

    safe_answer_query.assert_awaited_once_with(
        query,
        text="⚠️ 违禁被封，请联系管理员解封",
        show_alert=True,
    )


@pytest.mark.asyncio
async def test_handle_rate_action_recovers_task_id_from_gallery_button(monkeypatch):
    query = SimpleNamespace(
        message=SimpleNamespace(
            message_id=77,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🚀 一键投稿至广场",
                            callback_data="submit_gallery_task-9",
                        )
                    ],
                    [
                        InlineKeyboardButton("👍", callback_data="rate_like"),
                        InlineKeyboardButton("👎", callback_data="rate_dislike"),
                    ],
                ]
            ),
        )
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(bot_data={})
    update_rating = AsyncMock()

    monkeypatch.setattr(
        "src.handlers.callbacks.gallery_callbacks_interactions.update_history_rating_by_task_id",
        update_rating,
    )
    monkeypatch.setattr(
        "src.handlers.callbacks.gallery_callbacks_interactions.robust_edit_reply_markup",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "src.handlers.callbacks.gallery_callbacks_interactions.safe_answer_query",
        AsyncMock(),
    )

    await handle_rate_action(update, context, 1)

    update_rating.assert_awaited_once_with("task-9", 1)
