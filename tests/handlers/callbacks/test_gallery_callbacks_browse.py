from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.handlers.callbacks.gallery_callbacks_browse import (
    _build_gallery_reply_markup,
    build_gallery_category_menu,
    gallery_catmenu_callback,
    parse_gallery_browse_callback_data,
)


def test_parse_gallery_browse_callback_data_supports_category_and_page():
    assert parse_gallery_browse_callback_data("gallery_sort_latest_vidlora_3") == (
        "latest",
        "vidlora",
        3,
    )


def test_parse_gallery_browse_callback_data_defaults_to_all_category():
    assert parse_gallery_browse_callback_data("gallery_page_hot_2") == (
        "hot",
        "all",
        2,
    )


def test_build_gallery_reply_markup_preserves_page_navigation_and_counts():
    markup = _build_gallery_reply_markup(
        post_id=9,
        sort_type="latest",
        category="all",
        page=1,
        has_next=True,
        likes_count=5,
        dislikes_count=2,
    )

    first_row = markup.inline_keyboard[0]
    second_row = markup.inline_keyboard[1]

    assert first_row[0].callback_data == "gallery_like_9_latest_all_1"
    assert first_row[1].callback_data == "gallery_dislike_9_latest_all_1"
    assert second_row[0].callback_data == "gallery_page_latest_all_0"
    assert second_row[1].callback_data == "gallery_page_latest_all_2"


def test_build_gallery_category_menu_uses_stable_category_callbacks():
    markup = build_gallery_category_menu("latest")

    rows = markup.inline_keyboard
    assert rows[0][0].callback_data == "gallery_sort_latest_all"
    assert rows[-1][0].callback_data == "gallery_sort_latest_vidlora"


@pytest.mark.asyncio
async def test_gallery_catmenu_callback_edits_reply_markup(monkeypatch):
    edit_mock = AsyncMock()
    answer_mock = AsyncMock()
    query = SimpleNamespace(
        data="gallery_catmenu_latest",
        message=SimpleNamespace(),
    )
    update = SimpleNamespace(callback_query=query)

    monkeypatch.setattr(
        "src.handlers.callbacks.gallery_callbacks_browse.robust_edit_reply_markup",
        edit_mock,
    )
    monkeypatch.setattr(
        "src.handlers.callbacks.gallery_callbacks_browse.safe_answer_query",
        answer_mock,
    )

    await gallery_catmenu_callback(update, None)

    edit_mock.assert_awaited_once()
    assert edit_mock.await_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == (
        "gallery_sort_latest_all"
    )
    answer_mock.assert_awaited_once_with(query)
