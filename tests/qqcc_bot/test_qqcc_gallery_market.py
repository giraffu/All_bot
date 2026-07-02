from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

from qqcc_bot import gallery_market
from src.constants import (
    MODE_I2I_DRAW,
    MODE_I2I_PRO,
    MODE_LTX_VIDEO,
    MODE_PORNMASTER_FLUX2_MULTI_EDIT,
    MODE_SCAIL2_ACTION_TRANSFER,
)


def _button_texts(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


def _button_callbacks(markup):
    return [[button.callback_data for button in row] for row in markup.inline_keyboard]


def test_market_tabs_align_with_web_visible_types_without_txt2img():
    task_types = [tab.task_type for tab in gallery_market.QQCC_MARKET_TABS]
    labels = _button_texts(
        gallery_market.build_qqcc_gallery_market_menu_markup(
            context=SimpleNamespace(t=lambda key, **_kwargs: key)
        )
    )

    assert "txt2img" not in task_types
    assert "edit_group" in task_types
    assert "free_edit_v2_group" in task_types
    assert "img2video_group" in task_types
    assert labels[0] == ["qqcc.market.tabs.all", "qqcc.market.tabs.i2i_pro"]


def test_market_post_markup_uses_native_web_and_disabled_apply_modes(monkeypatch):
    monkeypatch.setattr(
        gallery_market,
        "build_market_web_apply_url",
        lambda post_id: f"https://web.example/gallery?apply_id={post_id}",
    )

    native_post = SimpleNamespace(id=1, likes_count=0, dislikes_count=0)
    native_markup = gallery_market.build_qqcc_market_post_markup(
        post=native_post,
        history=SimpleNamespace(type=MODE_I2I_PRO, extra_outputs={}),
        type_code="i2ip",
        sort_code="new",
        page=0,
        has_next=False,
    )
    assert _button_callbacks(native_markup)[1] == [f"{gallery_market.QG_APPLY_PREFIX}1"]

    web_post = SimpleNamespace(id=2, likes_count=0, dislikes_count=0)
    web_markup = gallery_market.build_qqcc_market_post_markup(
        post=web_post,
        history=SimpleNamespace(
            type=MODE_SCAIL2_ACTION_TRANSFER,
            input_file="reference.png|motion.mp4",
            extra_outputs={},
        ),
        type_code="sca",
        sort_code="new",
        page=0,
        has_next=False,
    )
    assert web_markup.inline_keyboard[1][0].url == "https://web.example/gallery?apply_id=2"

    disabled_post = SimpleNamespace(id=3, likes_count=0, dislikes_count=0)
    disabled_markup = gallery_market.build_qqcc_market_post_markup(
        post=disabled_post,
        history=SimpleNamespace(type=MODE_I2I_DRAW, extra_outputs={}),
        type_code="i2id",
        sort_code="new",
        page=0,
        has_next=False,
    )
    assert _button_callbacks(disabled_markup)[1] == ["noop"]


@pytest.mark.asyncio
async def test_submit_native_gallery_apply_passes_source_post_and_blocks_recontribution(monkeypatch):
    captured = {}

    async def fake_i2i_pro_task(**kwargs):
        captured.update(kwargs)
        return None, None

    monkeypatch.setattr(gallery_market, "process_i2i_pro_task", fake_i2i_pro_task)

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=99, username="tester"),
        effective_chat=SimpleNamespace(id=123),
    )
    context = SimpleNamespace(user_data={}, bot_data={"bot_client_type": "bot:qqcc"})

    await gallery_market.submit_qqcc_gallery_apply_session(
        update=update,
        context=context,
        image_path="/tmp/ref.png",
        session={
            "task_type": MODE_I2I_PRO,
            "prompt": "same style",
            "source_post_id": 42,
        },
    )

    assert captured["images"] == ["/tmp/ref.png"]
    assert captured["source_post_id"] == 42
    assert captured["allow_contribute"] is False
    assert captured["prompt"] == "same style"


@pytest.mark.asyncio
async def test_submit_ltx_gallery_apply_restores_existing_user_data(monkeypatch):
    captured = {}

    async def fake_ltx_task(**kwargs):
        captured.update(
            {
                "kwargs": kwargs,
                "resolution": kwargs["context"].user_data["ltx_video_resolution"],
                "duration": kwargs["context"].user_data["ltx_video_duration"],
            }
        )
        return None, None

    monkeypatch.setattr(gallery_market, "process_ltx_video_task", fake_ltx_task)

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=99, username="tester"),
        effective_chat=SimpleNamespace(id=123),
    )
    context = SimpleNamespace(
        user_data={
            "ltx_video_resolution": "old-res",
            "ltx_video_duration": "old-duration",
        },
        bot_data={"bot_client_type": "bot:qqcc"},
    )

    await gallery_market.submit_qqcc_gallery_apply_session(
        update=update,
        context=context,
        image_path="/tmp/ref.png",
        session={
            "task_type": MODE_LTX_VIDEO,
            "prompt": "animate",
            "source_post_id": 43,
            "width": 1024,
            "height": 576,
            "duration": 5,
        },
    )

    assert captured["resolution"] == "1024x576"
    assert captured["duration"] == "5s"
    assert captured["kwargs"]["source_post_id"] == 43
    assert captured["kwargs"]["allow_contribute"] is False
    assert context.user_data["ltx_video_resolution"] == "old-res"
    assert context.user_data["ltx_video_duration"] == "old-duration"


def test_gallery_apply_mode_sends_complex_templates_to_web():
    assert gallery_market.resolve_qqcc_gallery_apply_mode(
        SimpleNamespace(type=MODE_PORNMASTER_FLUX2_MULTI_EDIT, extra_outputs={})
    ) == ("web", None)


@pytest.mark.asyncio
async def test_gallery_apply_media_without_session_is_silent(monkeypatch):
    reply_text = AsyncMock()
    monkeypatch.setattr(gallery_market, "robust_reply_text", reply_text)

    update = SimpleNamespace(effective_message=SimpleNamespace())
    context = SimpleNamespace(user_data={})

    await gallery_market.handle_qqcc_gallery_apply_media(update, context)

    reply_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_gallery_apply_media_expires_stale_session(monkeypatch):
    reply_text = AsyncMock()
    monkeypatch.setattr(gallery_market, "robust_reply_text", reply_text)

    update = SimpleNamespace(effective_message=SimpleNamespace())
    context = SimpleNamespace(
        user_data={
            gallery_market.QQCC_GALLERY_APPLY_SESSION_KEY: {"created_at": 1}
        },
        t=lambda key, **_kwargs: key,
    )

    await gallery_market.handle_qqcc_gallery_apply_media(update, context)

    assert gallery_market.QQCC_GALLERY_APPLY_SESSION_KEY not in context.user_data
    reply_text.assert_awaited_once()
    assert reply_text.await_args.args[1] == "qqcc.market.apply_expired"
