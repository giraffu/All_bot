from types import SimpleNamespace

from src.handlers.callbacks.gallery_callbacks_browse import (
    _build_gallery_reply_markup,
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
