from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest

from qqcc_bot import gallery_market
from src.constants import (
    MODE_I2I_DRAW,
    MODE_I2I_PRO,
    MODE_LTX_VIDEO,
    MODE_PORNMASTER_FLUX2_MULTI_EDIT,
    MODE_SCAIL2_ACTION_TRANSFER,
    MODE_SCAIL2_FACE_SWAP_V2,
    MODE_WAN22_VIDEO_V2,
)
from src.services.ltx_video_extension_service import build_ltx_stitched_extra_outputs
from src.services.wan22_video_v2_extension_service import build_wan22_stitched_extra_outputs


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


def test_market_post_markup_shows_one_click_and_web_for_applyable_posts(monkeypatch):
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
    assert _button_texts(native_markup)[1] == ["一键应用", "Web应用"]
    assert _button_callbacks(native_markup)[1] == [f"{gallery_market.QG_APPLY_PREFIX}1", None]
    assert native_markup.inline_keyboard[1][1].url == "https://web.example/gallery?apply_id=1"

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
    assert _button_texts(web_markup)[1] == ["一键应用", "Web应用"]
    assert _button_callbacks(web_markup)[1] == [f"{gallery_market.QG_APPLY_PREFIX}2", None]
    assert web_markup.inline_keyboard[1][1].url == "https://web.example/gallery?apply_id=2"

    face_swap_post = SimpleNamespace(id=4, likes_count=0, dislikes_count=0)
    face_swap_markup = gallery_market.build_qqcc_market_post_markup(
        post=face_swap_post,
        history=SimpleNamespace(
            type=MODE_SCAIL2_FACE_SWAP_V2,
            input_file="reference.png|motion.mp4",
            extra_outputs={},
        ),
        type_code="scf",
        sort_code="new",
        page=0,
        has_next=False,
    )
    assert _button_texts(face_swap_markup)[1] == ["Web应用"]
    assert _button_callbacks(face_swap_markup)[1] == [None]
    assert face_swap_markup.inline_keyboard[1][0].url == "https://web.example/gallery?apply_id=4"

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


def test_market_post_markup_hides_apply_buttons_for_stitched_videos():
    for history in (
        SimpleNamespace(
            type=MODE_WAN22_VIDEO_V2,
            extra_outputs=build_wan22_stitched_extra_outputs(
                chain_task_ids=["wan-a", "wan-b"],
                source_task_id="wan-a",
            ),
        ),
        SimpleNamespace(
            type=MODE_LTX_VIDEO,
            extra_outputs=build_ltx_stitched_extra_outputs(
                chain_task_ids=["ltx-a", "ltx-b"],
                source_task_id="ltx-a",
            ),
        ),
    ):
        markup = gallery_market.build_qqcc_market_post_markup(
            post=SimpleNamespace(id=5, likes_count=0, dislikes_count=0),
            history=history,
            type_code="all",
            sort_code="new",
            page=0,
            has_next=False,
        )
        flat_texts = [button.text for row in markup.inline_keyboard for button in row]

        assert "一键应用" not in flat_texts
        assert "Web应用" not in flat_texts
        assert "不可应用" not in flat_texts
        assert _button_texts(markup)[1] == ["最新", "热门", "常用"]


def test_market_caption_translates_task_type_and_task_tags():
    context = SimpleNamespace(
        t=lambda key, **_kwargs: {
            "qqcc.market.title": "修仙市集",
            "qqcc.market.tabs.scail2_video_replacement": "视频换人",
            "task.mode_scail2_video_replacement": "视频换人",
        }.get(key, key)
    )
    post = SimpleNamespace(
        id=10,
        user=None,
        user_id=None,
        media_type="video",
        duration=6,
        width=512,
        height=896,
        likes_count=0,
        dislikes_count=0,
        applied_count=0,
        task_type="scail2_video_replacement",
    )
    history = SimpleNamespace(type="scail2_video_replacement")

    caption = gallery_market._build_post_caption(
        post=post,
        history=history,
        translated_tags=gallery_market.translate_market_tags(
            ["#task.mode_scail2_video_replacement"],
            context=context,
        ),
        context=context,
    )

    assert "<b>类型</b>：视频换人" in caption
    assert "<b>标签</b>：#视频换人" in caption
    assert "scail2_video_replacement" not in caption


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
        captured.update({"kwargs": kwargs})
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

    assert captured["kwargs"]["resolution"] == "1024x576"
    assert captured["kwargs"]["duration"] == "5s"
    assert captured["kwargs"]["source_post_id"] == 43
    assert captured["kwargs"]["allow_contribute"] is False
    assert context.user_data["ltx_video_resolution"] == "old-res"
    assert context.user_data["ltx_video_duration"] == "old-duration"


def test_gallery_apply_mode_sends_complex_templates_to_web():
    assert gallery_market.resolve_qqcc_gallery_apply_mode(
        SimpleNamespace(type=MODE_PORNMASTER_FLUX2_MULTI_EDIT, extra_outputs={})
    ) == ("web", None)


@pytest.mark.asyncio
async def test_load_apply_context_reuses_preloaded_entities(monkeypatch):
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, _tb):
            return None

    session = FakeSession()
    post = SimpleNamespace(id=43, is_active=True)
    history = SimpleNamespace(type=MODE_I2I_PRO, extra_outputs={})
    payload = SimpleNamespace(task_type=MODE_I2I_PRO, input_files=[])
    fetch_calls = 0
    build_calls = 0

    async def fake_fetch_gallery_apply_context_entities(*, db, post_id):
        nonlocal fetch_calls
        fetch_calls += 1
        assert db is session
        assert post_id == 43
        return post, history

    async def fake_build_gallery_apply_context_payload(**kwargs):
        nonlocal build_calls
        build_calls += 1
        assert kwargs["db"] is session
        assert kwargs["post"] is post
        assert kwargs["history"] is history
        return payload

    monkeypatch.setattr(gallery_market, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(
        gallery_market,
        "fetch_gallery_apply_context_entities",
        fake_fetch_gallery_apply_context_entities,
    )
    monkeypatch.setattr(
        gallery_market,
        "build_gallery_apply_context_payload",
        fake_build_gallery_apply_context_payload,
    )

    apply_context, mode = await gallery_market._load_apply_context_or_mode(43)

    assert apply_context is payload
    assert mode == "native"
    assert fetch_calls == 1
    assert build_calls == 1


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


@pytest.mark.asyncio
async def test_gallery_apply_media_cleans_downloaded_image_when_submission_fails(
    monkeypatch,
):
    reply_text = AsyncMock()
    cleanup = MagicMock()
    monkeypatch.setattr(gallery_market, "robust_reply_text", reply_text)
    monkeypatch.setattr(
        gallery_market,
        "_download_market_apply_image",
        AsyncMock(return_value="/tmp/qqcc-apply.png"),
    )
    monkeypatch.setattr(
        gallery_market,
        "submit_qqcc_gallery_apply_session",
        AsyncMock(side_effect=RuntimeError("submit failed")),
    )
    monkeypatch.setattr(gallery_market, "cleanup_fsm_temp_files", cleanup)

    update = SimpleNamespace(
        effective_message=SimpleNamespace(),
        effective_user=SimpleNamespace(id=99, username="tester"),
        effective_chat=SimpleNamespace(id=123),
    )
    context = SimpleNamespace(
        user_data={
            gallery_market.QQCC_GALLERY_APPLY_SESSION_KEY: {
                "created_at": 9999999999,
                "task_type": MODE_I2I_PRO,
            }
        },
        t=lambda key, **_kwargs: key,
    )

    await gallery_market.handle_qqcc_gallery_apply_media(update, context)

    cleanup.assert_called_once_with(["/tmp/qqcc-apply.png"])
    reply_text.assert_awaited_once()
    assert reply_text.await_args.args[1] == "qqcc.market.apply_submit_failed"
