from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    TypeHandler,
)

from qqcc_bot import callback_handler, keyboards, main as qqcc_main, prompt_handlers
from qqcc_bot import commands as qqcc_commands
from qqcc_bot import regeneration_callback
from src.handlers.fsm import quick_image_fsm, quick_video_fsm
from src.constants import (
    MODE_CUSTOM_VIDEO,
    MODE_IMAGE_TO_VIDEO,
    MODE_PERFECT_VIDEO_INSERT,
    MODE_WAN22_VIDEO_V2,
)
from src.handlers.fsm.quick_draw_callback_data import (
    build_quick_filter_scene_callback_data,
    build_quick_draw_scene_callback_data,
)
from src.handlers.fsm.quick_video_callback_data import (
    build_quick_video_scene_callback_data,
)
from src.handlers import prompt_router
from src.i18n.translator import get_text
from src.services.qqcc_config_service import SCENE_PRESET_VERSION, normalize_qqcc_config
from src.services.qqcc_regeneration_service import QQCCRegenerationSubmission


def _keyboard_texts(reply_markup):
    return [
        [getattr(button, "text", button) for button in row]
        for row in reply_markup.keyboard
    ]


def _inline_keyboard_texts(reply_markup):
    return [[button.text for button in row] for row in reply_markup.inline_keyboard]


def _clear_main_bot_link_env(monkeypatch):
    for name in (
        "QQCC_MAIN_BOT_URL",
        "QQCC_MAIN_BOT_USERNAME",
    ):
        monkeypatch.delenv(name, raising=False)


def test_qqcc_main_menu_only_contains_lazy_generation_entries():
    keyboard = _keyboard_texts(keyboards.get_qqcc_main_menu_keyboard("zh"))

    assert keyboard == [
        ["快速换脸"],
        ["AI绘图", "AI动图"],
        ["修仙市集"],
        ["私有bot"],
        ["前往主bot"],
    ]
    assert get_text("menu.video_edit", "zh") == "🎬 视频创作"


def _config_with_all_main_menu_entries(*, buttons_per_row: int):
    return normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "main_menu_layout": {
                "buttons_per_row": buttons_per_row,
                "button_order": [
                    "market",
                    "private_bot",
                    "main_bot_link",
                    "quick_faceswap",
                    "ai_filter",
                    "ai_draw",
                    "ai_video",
                    "video_edit",
                ],
            },
            "draw_scenes": [{"id": "draw", "name": "绘图", "prompt": "draw prompt"}],
            "filter_scenes": [
                {"id": "filter", "name": "滤镜", "prompt": "filter prompt"}
            ],
            "video_scenes": [{"id": "video", "name": "动图", "prompt": "video prompt"}],
            "ai_video_scenes": [
                {
                    "id": "ai_video",
                    "name": "AI视频",
                    "prompt": "ai video prompt",
                    "duration": 5,
                }
            ],
        }
    )


@pytest.mark.parametrize("buttons_per_row", [1, 2, 3, 4])
def test_qqcc_main_menu_supports_one_to_four_buttons_per_row(buttons_per_row):
    config = _config_with_all_main_menu_entries(buttons_per_row=buttons_per_row)

    rows = _keyboard_texts(keyboards.get_qqcc_main_menu_keyboard("zh", config))
    flat = [button for row in rows for button in row]

    assert flat == [
        "修仙市集",
        "私有bot",
        "前往主bot",
        "快速换脸",
        "AI滤镜",
        "AI绘图",
        "AI视频",
        "AI动图",
    ]
    assert [len(row) for row in rows] == [
        min(buttons_per_row, len(flat) - offset)
        for offset in range(0, len(flat), buttons_per_row)
    ]


def test_qqcc_main_menu_filters_hidden_buttons_before_chunking():
    config = _config_with_all_main_menu_entries(buttons_per_row=3)
    config["main_buttons"]["market"] = False

    rows = _keyboard_texts(
        keyboards.get_qqcc_main_menu_keyboard(
            "zh",
            config,
            include_private_bot_entry=False,
        )
    )

    assert rows == [
        ["前往主bot", "快速换脸", "AI滤镜"],
        ["AI绘图", "AI视频", "AI动图"],
    ]


def test_qqcc_grid_menu_keeps_independent_entries_when_generation_is_disabled():
    config = normalize_qqcc_config(
        {
            "global_enabled": False,
            "main_menu_layout": {
                "buttons_per_row": 2,
                "button_order": ["main_bot_link", "private_bot"],
            },
        }
    )

    rows = _keyboard_texts(keyboards.get_qqcc_main_menu_keyboard("zh", config))

    assert rows == [["前往主bot", "私有bot"]]


def test_qqcc_grid_menu_falls_back_when_every_entry_is_hidden():
    config = normalize_qqcc_config(
        {
            "global_enabled": False,
            "main_buttons": {
                "private_bot": False,
                "main_bot_link": False,
            },
            "main_menu_layout": {"buttons_per_row": 4},
        }
    )

    rows = _keyboard_texts(keyboards.get_qqcc_main_menu_keyboard("zh", config))

    assert rows == [[get_text("menu.main_menu", "zh")]]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "loader", [qqcc_commands._load_menu_config, prompt_handlers._load_menu_config]
)
async def test_private_bot_menu_config_failure_does_not_fall_back_to_defaults(loader):
    context = SimpleNamespace(
        bot_data={
            "bot_client_type": "bot:qqcc-private:7",
            "private_qqcc_bot_id": 7,
            "qqcc_config_loader": AsyncMock(side_effect=RuntimeError("db down")),
        }
    )

    with pytest.raises(RuntimeError, match="db down"):
        await loader(context)


def test_qqcc_main_bot_link_keyboard_uses_url_button():
    keyboard = keyboards.get_qqcc_main_bot_link_keyboard("zh", "https://t.me/main_bot")

    button = keyboard.inline_keyboard[0][0]
    assert button.text == "前往主bot"
    assert button.url == "https://t.me/main_bot"


def test_resolve_main_bot_url_prefers_configured_url(monkeypatch):
    _clear_main_bot_link_env(monkeypatch)
    monkeypatch.setenv("QQCC_MAIN_BOT_URL", "https://t.me/main_bot?start=qqcc")
    monkeypatch.setenv("QQCC_MAIN_BOT_USERNAME", "@fallback_bot")

    assert qqcc_commands.resolve_main_bot_url() == "https://t.me/main_bot?start=qqcc"


def test_resolve_main_bot_url_can_build_from_username(monkeypatch):
    _clear_main_bot_link_env(monkeypatch)
    monkeypatch.setenv("QQCC_MAIN_BOT_USERNAME", "@main_bot")

    assert qqcc_commands.resolve_main_bot_url() == "https://t.me/main_bot"


@pytest.mark.asyncio
async def test_qqcc_photo_menu_is_blocked_for_stale_keyboard_compatibility(monkeypatch):
    monkeypatch.setattr(
        prompt_handlers,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=normalize_qqcc_config(None)),
    )
    reply_text = AsyncMock()
    message = SimpleNamespace(reply_text=reply_text)
    update = SimpleNamespace(
        effective_message=message,
        message=None,
        edited_message=None,
    )
    context = SimpleNamespace(
        lang="zh",
        t=lambda key: {"qqcc.feature_disabled": "功能暂未开放"}.get(key, key),
    )

    await prompt_handlers.handle_photo_edit_menu(update, context)

    reply_text.assert_awaited_once()
    assert reply_text.await_args.kwargs["text"] == "功能暂未开放"


def test_qqcc_config_hides_closed_main_and_submenu_buttons():
    config = normalize_qqcc_config(
        {
            "main_buttons": {
                "quick_undress": False,
                "quick_faceswap": False,
                "photo_edit": True,
                "video_edit": False,
                "market": False,
                "main_bot_link": True,
            },
            "photo_buttons": {
                "masturbation": False,
                "random_faceswap": True,
            },
        }
    )

    main_rows = _keyboard_texts(keyboards.get_qqcc_main_menu_keyboard("zh", config))

    assert main_rows == [["AI绘图"], ["私有bot"], ["前往主bot"]]


def test_qqcc_main_menu_shows_default_ai_draw_scenes():
    main_rows = _keyboard_texts(keyboards.get_qqcc_main_menu_keyboard("zh"))
    reply_markup = keyboards.get_qqcc_draw_edit_inline_keyboard("zh")

    assert main_rows == [
        ["快速换脸"],
        ["AI绘图", "AI动图"],
        ["修仙市集"],
        ["私有bot"],
        ["前往主bot"],
    ]
    assert _inline_keyboard_texts(reply_markup) == [["快速自慰", "快速脱衣"]]
    assert reply_markup.inline_keyboard[0][0].callback_data == (
        build_quick_draw_scene_callback_data("quick_masturbation")
    )


def test_qqcc_main_menu_keeps_ai_draw_when_draw_scenes_are_empty():
    config = normalize_qqcc_config(
        {"main_buttons": {"quick_faceswap": True}, "draw_scenes": []}
    )

    main_rows = _keyboard_texts(keyboards.get_qqcc_main_menu_keyboard("zh", config))

    assert main_rows == [
        ["快速换脸"],
        ["AI绘图", "AI动图"],
        ["修仙市集"],
        ["私有bot"],
        ["前往主bot"],
    ]


def test_qqcc_main_menu_shows_ai_filter_when_filter_scenes_are_configured():
    config = normalize_qqcc_config(
        {
            "filter_scenes": [
                {
                    "id": "real_skin",
                    "name": "真实质感",
                    "prompt": "real skin prompt",
                }
            ],
        }
    )

    main_rows = _keyboard_texts(keyboards.get_qqcc_main_menu_keyboard("zh", config))
    reply_markup = keyboards.get_qqcc_filter_edit_inline_keyboard("zh", config)

    assert main_rows == [
        ["快速换脸"],
        ["AI绘图", "AI滤镜", "AI动图"],
        ["修仙市集"],
        ["私有bot"],
        ["前往主bot"],
    ]
    assert _inline_keyboard_texts(reply_markup) == [["真实质感"]]
    assert reply_markup.inline_keyboard[0][0].callback_data == (
        build_quick_filter_scene_callback_data("real_skin")
    )


def test_qqcc_main_menu_shows_ai_video_after_ai_animation_only_with_valid_scene():
    config = normalize_qqcc_config(
        {
            "main_buttons": {"ai_video": True},
            "ai_video_scenes": [
                {
                    "id": "cinema",
                    "name": "电影运镜",
                    "prompt": "camera orbit",
                    "duration": 10,
                }
            ],
        }
    )

    rows = _keyboard_texts(keyboards.get_qqcc_main_menu_keyboard("zh", config))

    assert rows[1] == ["AI绘图", "AI动图", "AI视频"]
    ai_video_keyboard = keyboards.get_qqcc_ai_video_inline_keyboard("zh", config)
    assert ai_video_keyboard.inline_keyboard[0][0].text == "电影运镜"
    assert (
        ai_video_keyboard.inline_keyboard[0][0].callback_data == "qaivid_scene:cinema"
    )


def test_qqcc_video_menu_contains_lazy_video_scenes():
    reply_markup = keyboards.get_qqcc_video_edit_inline_keyboard("zh")
    rows = _inline_keyboard_texts(reply_markup)
    flat = [text for row in rows for text in row]

    assert [len(row) for row in rows] == [3, 2]
    assert "🛌 动图传教士" in flat
    assert "🎬 动图后入" in flat
    assert "🎬 口交黑人" in flat
    assert "🎬 脱衣吐舌" in flat
    assert "🎬 特写口交" in flat
    assert reply_markup.inline_keyboard[0][0].callback_data == (
        build_quick_video_scene_callback_data("missionary")
    )


@pytest.mark.asyncio
async def test_qqcc_video_menu_route_replies_with_inline_scene_buttons(monkeypatch):
    monkeypatch.setattr(
        prompt_handlers,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=normalize_qqcc_config(None)),
    )
    reply_text = AsyncMock()
    message = SimpleNamespace(reply_text=reply_text)
    update = SimpleNamespace(
        effective_message=message,
        message=None,
        edited_message=None,
    )
    context = SimpleNamespace(
        lang="zh",
        t=lambda key: f"translated:{key}",
    )

    await prompt_handlers.handle_video_edit_menu(update, context)

    reply_text.assert_awaited_once()
    kwargs = reply_text.await_args.kwargs
    assert kwargs["text"] == "translated:system.video_edit_hint"
    assert _inline_keyboard_texts(kwargs["reply_markup"]) == [
        ["🛌 动图传教士", "🎬 动图后入", "🎬 口交黑人"],
        ["🎬 脱衣吐舌", "🎬 特写口交"],
    ]


def test_qqcc_video_menu_uses_dynamic_scene_config():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "video_scenes": [
                {
                    "id": "kiss",
                    "name": "亲吻",
                    "prompt": "kissing prompt",
                    "duration": "8s",
                },
                {
                    "id": "dance",
                    "name": "跳舞",
                    "prompt": "dance prompt",
                    "duration": "10s",
                },
                {
                    "id": "turn",
                    "name": "转身",
                    "prompt": "turn prompt",
                    "duration": "5s",
                },
                {
                    "id": "smile",
                    "name": "微笑",
                    "prompt": "smile prompt",
                    "duration": "5s",
                },
            ],
        }
    )

    reply_markup = keyboards.get_qqcc_video_edit_inline_keyboard("zh", config)

    assert _inline_keyboard_texts(reply_markup) == [
        ["亲吻", "跳舞", "转身"],
        ["微笑"],
    ]
    assert reply_markup.inline_keyboard[0][1].callback_data == (
        build_quick_video_scene_callback_data("dance")
    )


def test_qqcc_draw_menu_uses_dynamic_scene_config():
    config = normalize_qqcc_config(
        {
            "draw_scenes": [
                {
                    "id": "soft_light",
                    "name": "柔光写真",
                    "prompt": "soft light prompt",
                },
                {
                    "id": "anime",
                    "name": "动漫风",
                    "prompt": "anime style prompt",
                },
                {
                    "id": "oil",
                    "name": "油画",
                    "prompt": "oil painting prompt",
                },
                {
                    "id": "cyber",
                    "name": "赛博",
                    "prompt": "cyber prompt",
                },
            ]
        }
    )

    reply_markup = keyboards.get_qqcc_draw_edit_inline_keyboard("zh", config)

    assert _inline_keyboard_texts(reply_markup) == [
        ["快速自慰", "快速脱衣", "柔光写真"],
        ["动漫风", "油画", "赛博"],
    ]
    assert reply_markup.inline_keyboard[1][0].callback_data == (
        build_quick_draw_scene_callback_data("anime")
    )


@pytest.mark.asyncio
async def test_qqcc_ai_draw_menu_route_replies_with_inline_scene_buttons(monkeypatch):
    config = normalize_qqcc_config(
        {
            "copywriting": {
                "ai_draw_menu": "请选择你要使用的绘图场景。",
            },
            "draw_scenes": [
                {
                    "id": "soft_light",
                    "name": "柔光写真",
                    "prompt": "soft light prompt",
                },
                {
                    "id": "anime",
                    "name": "动漫风",
                    "prompt": "anime style prompt",
                },
            ],
        }
    )
    monkeypatch.setattr(
        prompt_handlers,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=config),
    )
    reply_text = AsyncMock()
    message = SimpleNamespace(reply_text=reply_text)
    update = SimpleNamespace(
        effective_message=message,
        message=None,
        edited_message=None,
    )
    context = SimpleNamespace(
        lang="zh",
        t=lambda key: f"translated:{key}",
    )

    await prompt_handlers.handle_ai_draw_menu(update, context)

    reply_text.assert_awaited_once()
    kwargs = reply_text.await_args.kwargs
    assert kwargs["text"] == "请选择你要使用的绘图场景。"
    assert _inline_keyboard_texts(kwargs["reply_markup"]) == [
        ["快速自慰", "快速脱衣", "柔光写真"],
        ["动漫风"],
    ]


@pytest.mark.asyncio
async def test_qqcc_ai_filter_menu_route_replies_with_inline_scene_buttons(monkeypatch):
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "filter_scenes": [
                {
                    "id": "real_skin",
                    "name": "真实质感",
                    "prompt": "real skin prompt",
                },
                {
                    "id": "clear_detail",
                    "name": "清晰增强",
                    "prompt": "clear detail prompt",
                },
            ],
        }
    )
    monkeypatch.setattr(
        prompt_handlers,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=config),
    )
    reply_text = AsyncMock()
    message = SimpleNamespace(reply_text=reply_text)
    update = SimpleNamespace(
        effective_message=message,
        message=None,
        edited_message=None,
    )
    context = SimpleNamespace(
        lang="zh",
        t=lambda key: f"translated:{key}",
    )

    await prompt_handlers.handle_ai_filter_menu(update, context)

    reply_text.assert_awaited_once()
    kwargs = reply_text.await_args.kwargs
    assert kwargs["text"] == "translated:system.ai_filter_hint"
    assert _inline_keyboard_texts(kwargs["reply_markup"]) == [
        ["真实质感", "清晰增强"],
    ]


@pytest.mark.asyncio
async def test_qqcc_stale_photo_menu_button_is_blocked(monkeypatch):
    config = normalize_qqcc_config({"main_buttons": {"photo_edit": False}})
    monkeypatch.setattr(
        prompt_handlers,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=config),
    )

    reply_text = AsyncMock()
    message = SimpleNamespace(reply_text=reply_text)
    update = SimpleNamespace(
        effective_message=message,
        message=None,
        edited_message=None,
    )
    context = SimpleNamespace(
        lang="zh",
        t=lambda key: {"qqcc.feature_disabled": "功能暂未开放"}.get(key, key),
    )

    await prompt_handlers.handle_photo_edit_menu(update, context)

    kwargs = reply_text.await_args.kwargs
    assert kwargs["text"] == "功能暂未开放"
    assert "🖼️ 懒人P图" not in [
        text for row in _keyboard_texts(kwargs["reply_markup"]) for text in row
    ]


def test_qqcc_prompt_routes_are_limited_to_lazy_menus():
    assert set(prompt_handlers.QQCC_PROMPT_ROUTES) == {
        "menu.photo_edit",
        "qqcc.menu.ai_draw",
        "qqcc.menu.ai_filter",
        "qqcc.menu.ai_video",
        "menu.video_edit",
        "menu.main_menu",
        "menu.back_main",
        "menu.open_main_bot",
        "qqcc.menu.market",
    }


def test_qqcc_lazy_main_buttons_are_routable_without_main_bot_prompt_routes(
    monkeypatch,
):
    monkeypatch.setattr(prompt_router, "prompt_routes", {}, raising=False)

    prompt_router.build_global_menu_filter()

    assert prompt_router.GLOBAL_REVERSE_MAP["💃 快速脱衣"] == "menu.photo_edit_undress"
    assert prompt_router.GLOBAL_REVERSE_MAP["快速换脸"] == "qqcc.menu.quick_faceswap"
    assert prompt_router.GLOBAL_REVERSE_MAP["🖼️ 懒人P图"] == "menu.photo_edit"
    assert prompt_router.GLOBAL_REVERSE_MAP["AI绘图"] == "qqcc.menu.ai_draw"
    assert prompt_router.GLOBAL_REVERSE_MAP["AI滤镜"] == "qqcc.menu.ai_filter"
    assert prompt_router.GLOBAL_REVERSE_MAP["AI动图"] == "menu.video_edit"
    assert prompt_router.GLOBAL_REVERSE_MAP["🎬 视频创作"] == "menu.video_edit"
    assert prompt_router.GLOBAL_REVERSE_MAP["修仙市集"] == "qqcc.menu.market"
    assert prompt_router.GLOBAL_REVERSE_MAP["前往主bot"] == "menu.open_main_bot"


def test_register_handlers_only_registers_qqcc_surface(monkeypatch):
    added_handlers = []
    error_handlers = []

    class FakeApp:
        def add_handler(self, handler, *args, **kwargs):
            added_handlers.append((handler, args, kwargs))

        def add_error_handler(self, handler):
            error_handlers.append(handler)

    monkeypatch.setattr(qqcc_main, "get_quick_image_fsm_handler", lambda: "quick-image")
    monkeypatch.setattr(qqcc_main, "get_quick_video_fsm_handler", lambda: "quick-video")

    qqcc_main.register_handlers(FakeApp())

    handlers = [item[0] for item in added_handlers]
    assert handlers[0].__class__ is TypeHandler
    assert any(
        handler.__class__ is TypeHandler
        and args == ()
        and kwargs == {"group": 1000}
        for handler, args, kwargs in added_handlers
    )
    assert "quick-image" in handlers
    assert "quick-video" in handlers
    assert sum(isinstance(handler, CommandHandler) for handler in handlers) == 2
    assert sum(isinstance(handler, CallbackQueryHandler) for handler in handlers) == 1
    assert sum(isinstance(handler, MessageHandler) for handler in handlers) == 2
    assert len(error_handlers) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("callback_data", ["submit_gallery_task-1", "public_share"])
async def test_qqcc_publish_callbacks_are_blocked_before_shared_handlers(
    monkeypatch,
    callback_data,
):
    safe_answer = AsyncMock()
    ensure_user = AsyncMock()
    monkeypatch.setattr(callback_handler, "safe_answer_query", safe_answer)
    monkeypatch.setattr(
        callback_handler.permission_service,
        "ensure_user",
        ensure_user,
    )

    query = SimpleNamespace(
        data=callback_data,
        from_user=SimpleNamespace(id=123),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(
            id=123,
            username="tester",
            full_name="Tester",
            language_code="zh",
        ),
    )
    context = SimpleNamespace()

    await callback_handler.handle_callback_query(update, context)

    safe_answer.assert_awaited_once_with(
        query,
        text="功能暂未开放",
        show_alert=True,
    )
    ensure_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_qqcc_regenerate_callback_routes_and_starts_background_task(monkeypatch):
    ensure_user = AsyncMock()
    check_quota = AsyncMock()
    answer = AsyncMock()
    send_message = AsyncMock(return_value=SimpleNamespace(message_id=55))
    scheduled = []

    def fake_create_background_task(context, coroutine):
        scheduled.append((context, coroutine))
        coroutine.close()

    submission = QQCCRegenerationSubmission(
        kind="quick_image",
        display_mode_name="柔光写真",
        image_path="/tmp/input.png",
        plan=SimpleNamespace(total_cost=2),
    )
    prepare = AsyncMock(return_value=submission)

    monkeypatch.setattr(callback_handler.permission_service, "ensure_user", ensure_user)
    monkeypatch.setattr(
        regeneration_callback.permission_service, "check_quota", check_quota
    )
    monkeypatch.setattr(regeneration_callback, "safe_answer_query", answer)
    monkeypatch.setattr(regeneration_callback, "robust_send_message", send_message)
    monkeypatch.setattr(
        regeneration_callback, "create_background_task", fake_create_background_task
    )
    monkeypatch.setattr(
        regeneration_callback,
        "prepare_qqcc_regeneration_submission",
        prepare,
    )

    query = SimpleNamespace(
        data="qqcc_regenerate:task-1",
        from_user=SimpleNamespace(id=123),
        message=SimpleNamespace(message_id=99),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(
            id=123,
            username="tester",
            full_name="Tester",
            language_code="zh",
        ),
        effective_chat=SimpleNamespace(id=456),
    )
    tenant_config = {"global_enabled": False, "draw_scenes": []}
    config_loader = AsyncMock(return_value=tenant_config)
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        bot_data={
            "bot_client_type": "bot:qqcc-private:7",
            "private_qqcc_bot_id": 7,
            "qqcc_config_loader": config_loader,
            "msg_meta_99": {
                "_qqcc_regenerate": {
                    "kind": "quick_image",
                    "mode": "pornmaster_flux2_single_edit",
                    "scene_id": "soft_light",
                    "display_mode_name": "柔光写真",
                }
            },
        },
    )

    await callback_handler.handle_callback_query(update, context)

    ensure_user.assert_awaited_once()
    answer.assert_awaited_once_with(query, text="🔁 正在重新生成...", cache_time=1)
    prepare.assert_awaited_once()
    assert prepare.await_args.kwargs["task_id"] == "task-1"
    assert prepare.await_args.kwargs["message_meta"] == context.bot_data["msg_meta_99"]
    assert await prepare.await_args.kwargs["load_config_func"]() == tenant_config
    config_loader.assert_awaited_once()
    check_quota.assert_awaited_once_with(123, "tester", "Tester", cost=2)
    send_message.assert_awaited_once_with(
        context.bot,
        456,
        "🔁 正在重新生成柔光写真，请耐心等待...",
    )
    assert scheduled and scheduled[0][0] is context


@pytest.mark.asyncio
async def test_qqcc_start_returns_simplified_menu(monkeypatch):
    _clear_main_bot_link_env(monkeypatch)
    monkeypatch.setattr(
        "qqcc_bot.commands.get_user_channel_status",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "qqcc_bot.commands.notify_inviter_reward",
        lambda *_args, **_kwargs: AsyncMock()(),
    )
    monkeypatch.setattr(
        "qqcc_bot.commands.load_runtime_qqcc_config",
        AsyncMock(return_value=normalize_qqcc_config(None)),
    )
    permission = SimpleNamespace(
        check_access=AsyncMock(return_value=None),
        ensure_user=AsyncMock(return_value=False),
    )
    monkeypatch.setattr("qqcc_bot.commands.permission_service", permission)

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(
            id=123,
            username="tester",
            full_name="Tester",
            language_code="zh",
        ),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(
        args=[],
        lang="zh",
        t=lambda key: f"translated:{key}",
        bot=object(),
        user_data={},
    )

    await qqcc_main.start(update, context)

    reply_text.assert_awaited_once()
    kwargs = reply_text.await_args.kwargs
    assert _keyboard_texts(kwargs["reply_markup"]) == [
        ["快速换脸"],
        ["AI绘图", "AI动图"],
        ["修仙市集"],
        ["私有bot"],
        ["前往主bot"],
    ]


@pytest.mark.asyncio
async def test_qqcc_cancel_clears_gallery_apply_session(monkeypatch):
    temp_file = "/tmp/a.png"
    monkeypatch.setattr(
        "qqcc_bot.commands.load_runtime_qqcc_config",
        AsyncMock(return_value=normalize_qqcc_config(None)),
    )
    cleanup = MagicMock()
    monkeypatch.setattr("qqcc_bot.commands.cleanup_fsm_user_data", cleanup)
    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(
        lang="zh",
        t=lambda key: f"translated:{key}",
        user_data={
            "in_conversation": True,
            "qqcc_gallery_apply": {"source_post_id": 42},
            "quick_image_data": {"image_path": temp_file},
        },
    )

    await qqcc_commands.cancel(update, context)

    assert "qqcc_gallery_apply" not in context.user_data
    cleanup.assert_called_once_with(context.user_data)
    reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_qqcc_start_keeps_main_bot_jump_in_menu_when_configured(monkeypatch):
    _clear_main_bot_link_env(monkeypatch)
    monkeypatch.setenv("QQCC_MAIN_BOT_URL", "https://t.me/main_bot")
    monkeypatch.setattr(
        "qqcc_bot.commands.get_user_channel_status",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "qqcc_bot.commands.notify_inviter_reward",
        lambda *_args, **_kwargs: AsyncMock()(),
    )
    monkeypatch.setattr(
        "qqcc_bot.commands.load_runtime_qqcc_config",
        AsyncMock(return_value=normalize_qqcc_config(None)),
    )
    permission = SimpleNamespace(
        check_access=AsyncMock(return_value=None),
        ensure_user=AsyncMock(return_value=False),
    )
    monkeypatch.setattr("qqcc_bot.commands.permission_service", permission)

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(
            id=123,
            username="tester",
            full_name="Tester",
            language_code="zh",
        ),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(
        args=[],
        lang="zh",
        t=lambda key: f"translated:{key}",
        bot=object(),
        user_data={},
    )

    await qqcc_main.start(update, context)

    reply_text.assert_awaited_once()
    kwargs = reply_text.await_args.kwargs
    assert getattr(kwargs["reply_markup"], "inline_keyboard", None) is None
    assert _keyboard_texts(kwargs["reply_markup"]) == [
        ["快速换脸"],
        ["AI绘图", "AI动图"],
        ["修仙市集"],
        ["私有bot"],
        ["前往主bot"],
    ]


@pytest.mark.asyncio
async def test_qqcc_quick_image_old_button_is_blocked(monkeypatch):
    reply_text = AsyncMock()
    monkeypatch.setattr(quick_image_fsm, "robust_reply_text", reply_text)
    monkeypatch.setattr(
        quick_image_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(
            return_value=normalize_qqcc_config(
                {"photo_buttons": {"random_faceswap": False}}
            )
        ),
    )

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        callback_query=None,
        message=SimpleNamespace(text="🎭 随机换脸"),
        edited_message=None,
    )
    context = SimpleNamespace(
        bot_data={"bot_client_type": "bot:qqcc"},
        user_data={},
        lang="zh",
        t=lambda key, **_kwargs: {"qqcc.feature_disabled": "功能暂未开放"}.get(
            key, key
        ),
    )

    result = await quick_image_fsm.start_quick_image(update, context)

    assert result == -1
    reply_text.assert_awaited_once()
    assert reply_text.await_args.args[1] == "功能暂未开放"


@pytest.mark.asyncio
async def test_qqcc_draw_scene_sends_demo_album_before_upload_hint(monkeypatch):
    events = []
    demo_sender = AsyncMock(side_effect=lambda **_kwargs: events.append("demo"))
    reply_text = AsyncMock(side_effect=lambda *_args, **_kwargs: events.append("text"))
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "copywriting": {
                "ai_draw_scene_start": "已选择【{butten}】，请发送原图。",
            },
            "draw_scenes": [
                {
                    "id": "portrait",
                    "name": "人像",
                    "prompt": "portrait prompt",
                    "demo_input_media": {
                        "object_key": "qqcc/demo/draw/portrait/input",
                        "media_type": "image",
                        "mime_type": "image/png",
                        "file_name": "before.png",
                    },
                    "demo_output_media": {
                        "object_key": "qqcc/demo/draw/portrait/output",
                        "media_type": "image",
                        "mime_type": "image/png",
                        "file_name": "after.png",
                    },
                }
            ],
        }
    )
    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(quick_image_fsm, "robust_reply_text", reply_text)
    monkeypatch.setattr(quick_image_fsm, "send_qqcc_scene_demo_media", demo_sender)
    monkeypatch.setattr(
        quick_image_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=config),
    )
    callback_message = SimpleNamespace(chat_id=456)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        callback_query=SimpleNamespace(
            data=build_quick_draw_scene_callback_data("portrait"),
            message=callback_message,
            answer=AsyncMock(),
        ),
        message=None,
        edited_message=None,
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(id=999),
        bot_data={"bot_client_type": "bot:qqcc"},
        user_data={},
        lang="zh",
        t=lambda key, **_kwargs: key,
    )

    result = await quick_image_fsm.start_quick_image(update, context)

    assert result == quick_image_fsm.QuickImageState.WAIT_IMAGE
    assert events == ["demo", "text"]
    demo_sender.assert_awaited_once_with(
        message=callback_message,
        bot=context.bot,
        scene_kind="draw",
        scene=config["draw_scenes"][0],
    )
    assert reply_text.await_args.args[1] == "已选择【人像】，请发送原图。"


@pytest.mark.asyncio
async def test_qqcc_draw_scene_callback_replaces_pending_video_flow(monkeypatch):
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "make_input",
                    "name": "生成输入图",
                    "prompt": "draw prompt",
                }
            ],
        }
    )
    reply_text = AsyncMock()
    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(quick_image_fsm, "robust_reply_text", reply_text)
    monkeypatch.setattr(quick_image_fsm, "send_qqcc_scene_demo_media", AsyncMock())
    monkeypatch.setattr(
        quick_image_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=config),
    )

    callback_message = SimpleNamespace(chat_id=456)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        callback_query=SimpleNamespace(
            data=build_quick_draw_scene_callback_data("make_input"),
            message=callback_message,
            answer=AsyncMock(),
        ),
        message=None,
        edited_message=None,
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(id=999),
        bot_data={"bot_client_type": "bot:qqcc"},
        user_data={
            "in_conversation": "QUICK_VIDEO_custom_video",
            "quick_video_data": {"mode": "custom_video", "image_path": None},
        },
        lang="zh",
        t=lambda key, **_kwargs: key,
    )

    result = await quick_image_fsm.start_quick_image(update, context)

    assert result == quick_image_fsm.QuickImageState.WAIT_IMAGE
    assert "quick_video_data" not in context.user_data
    assert context.user_data["in_conversation"].startswith("QUICK_IMAGE_")
    assert context.user_data["quick_image_data"]["scene_id"] == "make_input"
    reply_text.assert_awaited_once_with(
        callback_message,
        "fsm.quick_image.ai_draw_start",
        parse_mode="Markdown",
    )


@pytest.mark.asyncio
async def test_qqcc_draw_scene_callback_keeps_non_video_conflict_protection(monkeypatch):
    edit_text = AsyncMock()
    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(quick_image_fsm, "robust_edit_text", edit_text)
    callback_message = SimpleNamespace(chat_id=456)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        callback_query=SimpleNamespace(
            data=build_quick_draw_scene_callback_data("make_input"),
            message=callback_message,
            answer=AsyncMock(),
        ),
        message=None,
        edited_message=None,
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(id=999),
        bot_data={"bot_client_type": "bot:qqcc"},
        user_data={
            "in_conversation": "QUICK_IMAGE_edit",
            "quick_image_data": {"mode": "edit", "image_path": None},
        },
        lang="zh",
        t=lambda key, **_kwargs: key,
    )

    result = await quick_image_fsm.start_quick_image(update, context)

    assert result == quick_image_fsm.ConversationHandler.END
    assert context.user_data["in_conversation"] == "QUICK_IMAGE_edit"
    assert context.user_data["quick_image_data"]["mode"] == "edit"
    edit_text.assert_awaited_once_with(
        callback_message,
        "fsm.common.conflict",
        parse_mode="Markdown",
    )


@pytest.mark.asyncio
async def test_private_qqcc_scene_passes_trusted_tenant_id_to_demo_cache(monkeypatch):
    demo_sender = AsyncMock()
    monkeypatch.setattr(quick_image_fsm, "send_qqcc_scene_demo_media", demo_sender)
    monkeypatch.setattr(quick_image_fsm, "robust_reply_text", AsyncMock())
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "portrait",
                    "name": "人像",
                    "prompt": "portrait prompt",
                    "demo_input_media": {
                        "object_key": "qqcc/private/7/demo/draw/portrait/input",
                        "media_type": "image",
                        "mime_type": "image/png",
                        "file_name": "before.png",
                    },
                }
            ],
        }
    )
    callback_message = SimpleNamespace(chat_id=456)
    update = SimpleNamespace(
        callback_query=SimpleNamespace(
            data=build_quick_draw_scene_callback_data("portrait"),
            message=callback_message,
            answer=AsyncMock(),
        ),
        message=None,
        edited_message=None,
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(id=999),
        bot_data={
            "bot_client_type": "bot:qqcc-private:7",
            "private_qqcc_bot_id": 7,
        },
        user_data={},
        lang="zh",
        t=lambda key, **_kwargs: key,
    )

    result = await quick_image_fsm._start_qqcc_image_scene(
        update,
        context,
        qqcc_config=config,
        scene_id="portrait",
        scene_kind="draw",
    )

    assert result == quick_image_fsm.QuickImageState.WAIT_IMAGE
    demo_sender.assert_awaited_once_with(
        message=callback_message,
        bot=context.bot,
        scene_kind="draw",
        scene=config["draw_scenes"][0],
        private_bot_id=7,
    )


@pytest.mark.asyncio
async def test_qqcc_filter_scene_sends_input_output_demo_images(monkeypatch):
    demo_sender = AsyncMock()
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "filter_scenes": [
                {
                    "id": "cinema",
                    "name": "电影感",
                    "prompt": "cinema prompt",
                    "demo_input_media": {
                        "object_key": "qqcc/demo/filter/cinema/input",
                        "media_type": "image",
                        "mime_type": "image/jpeg",
                        "file_name": "before.jpg",
                    },
                    "demo_output_media": {
                        "object_key": "qqcc/demo/filter/cinema/output",
                        "media_type": "image",
                        "mime_type": "image/jpeg",
                        "file_name": "after.jpg",
                    },
                }
            ],
        }
    )
    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(quick_image_fsm, "robust_reply_text", AsyncMock())
    monkeypatch.setattr(quick_image_fsm, "send_qqcc_scene_demo_media", demo_sender)
    monkeypatch.setattr(
        quick_image_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=config),
    )
    callback_message = SimpleNamespace(chat_id=456)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        callback_query=SimpleNamespace(
            data=build_quick_filter_scene_callback_data("cinema"),
            message=callback_message,
            answer=AsyncMock(),
        ),
        message=None,
        edited_message=None,
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(id=999),
        bot_data={"bot_client_type": "bot:qqcc"},
        user_data={},
        lang="zh",
        t=lambda key, **_kwargs: key,
    )

    result = await quick_image_fsm.start_quick_image(update, context)

    assert result == quick_image_fsm.QuickImageState.WAIT_IMAGE
    demo_sender.assert_awaited_once_with(
        message=callback_message,
        bot=context.bot,
        scene_kind="filter",
        scene=config["filter_scenes"][0],
    )


@pytest.mark.asyncio
async def test_qqcc_video_settings_only_keeps_start_button(monkeypatch):
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=7), False)),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_group",
        AsyncMock(return_value="金丹期"),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_identity",
        AsyncMock(return_value="核心弟子"),
    )
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "video_scenes": [
                {
                    "id": "long",
                    "name": "长动图",
                    "prompt": "long prompt",
                    "duration": "10s",
                }
            ],
            "video_settings": {
                "resolutions": {"512p": False, "720p": False, "1024p": False},
                "durations": {"5s": False, "8s": False, "10s": False},
            },
        }
    )
    context = SimpleNamespace(
        lang="zh",
        t=lambda key, **_kwargs: "灵石" if key == "app.credits" else key,
    )

    markup = await quick_video_fsm._build_quick_video_settings_markup(
        context=context,
        user_id=123,
        resolution="512p",
        duration="10s",
        qqcc_config=config,
    )
    callbacks = [
        button.callback_data for row in markup.inline_keyboard for button in row
    ]

    assert callbacks == ["qvid_start_generation"]
    assert not any(callback.startswith("set_dur_") for callback in callbacks)


@pytest.mark.asyncio
async def test_qqcc_fixed_price_video_settings_have_no_resolution_buttons(monkeypatch):
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=7), False)),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_group",
        AsyncMock(return_value="金丹期"),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_identity",
        AsyncMock(return_value="核心弟子"),
    )
    config = normalize_qqcc_config(
        {
            "video_scenes": [
                {
                    "id": "fixed",
                    "name": "固定价",
                    "prompt": "move",
                    "duration": "5s",
                    "credit_cost": 9,
                }
            ]
        }
    )
    context = SimpleNamespace(
        lang="zh",
        user_data={"quick_video_data": {"credit_cost": 9}},
        t=lambda key, **_kwargs: "灵石" if key == "app.credits" else key,
    )

    markup = await quick_video_fsm._build_quick_video_settings_markup(
        context=context,
        user_id=123,
        resolution="512p",
        duration="5s",
        qqcc_config=config,
    )
    resolution_callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if str(button.callback_data).startswith("set_res_")
    ]

    assert resolution_callbacks == []


@pytest.mark.asyncio
async def test_qqcc_video_prompt_override_does_not_affect_main_bot(monkeypatch):
    captured = []

    monkeypatch.setattr(
        quick_video_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(
            return_value=normalize_qqcc_config(
                {
                    "video_scenes": [
                        {
                            "id": "missionary",
                            "name": "自定义动图",
                            "prompt": "qqcc scene prompt",
                            "duration": "8s",
                        }
                    ],
                    "prompts": {"perfect_video_insert": "legacy override"},
                }
            )
        ),
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=7), False)),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_group",
        AsyncMock(return_value="金丹期"),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_identity",
        AsyncMock(return_value="核心弟子"),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "check_quota",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(quick_video_fsm, "robust_edit_text", AsyncMock())
    background_tasks = []

    def fake_process_video_task_template(**kwargs):
        captured.append(kwargs)
        return "queued"

    async def fake_process_generation_task(**kwargs):
        captured.append(kwargs)
        return None, None

    monkeypatch.setattr(
        quick_video_fsm,
        "process_video_task_template",
        fake_process_video_task_template,
    )
    monkeypatch.setattr(
        quick_video_fsm,
        "process_generation_task",
        fake_process_generation_task,
    )
    monkeypatch.setattr(
        quick_video_fsm,
        "create_background_task",
        lambda _context, task: background_tasks.append(task),
    )

    def make_update_and_context(bot_data):
        query = SimpleNamespace(
            from_user=SimpleNamespace(id=123, username="tester"),
            data="qvid_start_generation",
            answer=AsyncMock(),
            message=SimpleNamespace(chat_id=456, message_id=77),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(
                id=123,
                username="tester",
                full_name="Tester",
            ),
            effective_chat=SimpleNamespace(id=456),
        )
        context = SimpleNamespace(
            bot_data=bot_data,
            user_data={
                "quick_video_data": {
                    "mode": MODE_CUSTOM_VIDEO
                    if bot_data
                    else MODE_PERFECT_VIDEO_INSERT,
                    "scene_id": "missionary" if bot_data else None,
                    "mode_name": "自定义动图" if bot_data else None,
                    "prompt_override": "qqcc scene prompt" if bot_data else None,
                    "resolution": "512p",
                    "duration": "8s" if bot_data else "5s",
                    "image_path": "/tmp/input.png",
                }
            },
            lang="zh",
            t=lambda key, **_kwargs: key,
        )
        return update, context

    update, context = make_update_and_context({"bot_client_type": "bot:qqcc"})
    await quick_video_fsm.start_generation(update, context)
    await background_tasks.pop(0)

    update, context = make_update_and_context({})
    await quick_video_fsm.start_generation(update, context)
    await background_tasks.pop(0)

    assert captured[0]["mode"] == MODE_CUSTOM_VIDEO
    assert captured[0]["default_prompt_key"] == MODE_CUSTOM_VIDEO
    assert captured[0]["default_prompt_text"] == "qqcc scene prompt"
    assert captured[0]["prompt_override"] == "qqcc scene prompt"
    assert captured[0]["display_mode_name_override"] == "自定义动图"
    assert captured[1]["prompt_override"] is None


@pytest.mark.asyncio
async def test_qqcc_video_scene_lora_submits_legacy_video_lora(monkeypatch):
    captured = []

    monkeypatch.setattr(
        quick_video_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(
            return_value=normalize_qqcc_config(
                {
                    "video_scenes": [
                        {
                            "id": "lora_scene",
                            "name": "模型动图",
                            "prompt": "lora scene prompt",
                            "duration": "5s",
                            "engine": "image_to_video",
                            "lora_name": "BreastGrow",
                        }
                    ]
                }
            )
        ),
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=7), False)),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_group",
        AsyncMock(return_value="金丹期"),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_identity",
        AsyncMock(return_value="核心弟子"),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "check_quota",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(quick_video_fsm, "robust_edit_text", AsyncMock())
    background_tasks = []
    monkeypatch.setattr(
        quick_video_fsm,
        "process_video_task_template",
        lambda **kwargs: captured.append(kwargs) or "queued",
    )
    monkeypatch.setattr(
        quick_video_fsm,
        "create_background_task",
        lambda _context, task: background_tasks.append(task),
    )

    query = SimpleNamespace(
        from_user=SimpleNamespace(id=123, username="tester"),
        data="qvid_start_generation",
        answer=AsyncMock(),
        message=SimpleNamespace(chat_id=456, message_id=77),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(
            id=123,
            username="tester",
            full_name="Tester",
        ),
        effective_chat=SimpleNamespace(id=456),
    )
    context = SimpleNamespace(
        bot_data={"bot_client_type": "bot:qqcc"},
        user_data={
            "quick_video_data": {
                "mode": MODE_CUSTOM_VIDEO,
                "scene_id": "lora_scene",
                "mode_name": "模型动图",
                "resolution": "720p",
                "duration": "5s",
                "image_path": "/tmp/input.png",
            }
        },
        lang="zh",
        t=lambda key, **_kwargs: key,
    )

    await quick_video_fsm.start_generation(update, context)
    await background_tasks.pop(0)

    assert captured[0]["mode"] == MODE_IMAGE_TO_VIDEO
    assert captured[0]["lora_name"] == "wan22_explicit_077"
    assert captured[0]["prompt_override"] == "lora scene prompt"
    assert captured[0]["display_mode_name_override"] == "模型动图"


@pytest.mark.asyncio
async def test_qqcc_video_scene_v2_submits_wan22_v2(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        quick_video_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(
            return_value=normalize_qqcc_config(
                {
                    "video_scenes": [
                        {
                            "id": "v2_scene",
                            "name": "新版动图",
                            "prompt": "v2 scene prompt",
                            "duration": "10s",
                            "engine": "wan22_video_v2",
                            "lora_name": "BreastGrow",
                        }
                    ]
                }
            )
        ),
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=7), False)),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_group",
        AsyncMock(return_value="金丹期"),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_identity",
        AsyncMock(return_value="核心弟子"),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "check_quota",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(quick_video_fsm, "robust_edit_text", AsyncMock())
    background_tasks = []

    monkeypatch.setattr(
        quick_video_fsm,
        "process_generation_task",
        lambda **kwargs: captured.update(kwargs) or "queued",
    )
    monkeypatch.setattr(
        quick_video_fsm,
        "create_background_task",
        lambda _context, task: background_tasks.append(task),
    )

    query = SimpleNamespace(
        from_user=SimpleNamespace(id=123, username="tester"),
        data="qvid_start_generation",
        answer=AsyncMock(),
        message=SimpleNamespace(chat_id=456, message_id=77),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(
            id=123,
            username="tester",
            full_name="Tester",
        ),
        effective_chat=SimpleNamespace(id=456),
    )
    context = SimpleNamespace(
        bot_data={"bot_client_type": "bot:qqcc"},
        user_data={
            "quick_video_data": {
                "mode": MODE_CUSTOM_VIDEO,
                "scene_id": "v2_scene",
                "mode_name": "新版动图",
                "resolution": "1024p",
                "duration": "10s",
                "image_path": "/tmp/input.png",
            }
        },
        lang="zh",
        t=lambda key, **_kwargs: key,
    )

    await quick_video_fsm.start_generation(update, context)
    await background_tasks.pop(0)

    assert captured["task_type"] == MODE_WAN22_VIDEO_V2
    assert captured["prompt"] == "v2 scene prompt"
    assert captured["images"] == ["/tmp/input.png"]
    assert captured["resolution"] == "720p"
    assert captured["duration"] == "10s"
    assert "lora_name" not in captured


@pytest.mark.asyncio
async def test_qqcc_video_scene_generates_tail_frame_before_legacy_video(monkeypatch):
    tail_calls = []
    video_calls = []
    background_tasks = []

    monkeypatch.setattr(
        quick_video_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(
            return_value=normalize_qqcc_config(
                {
                    "draw_scenes": [
                        {
                            "id": "tail_pose",
                            "name": "尾帧姿势",
                            "prompt": "tail prompt",
                        }
                    ],
                    "video_scenes": [
                        {
                            "id": "tail_video",
                            "name": "首尾动图",
                            "prompt": "video prompt",
                            "duration": "5s",
                            "engine": "image_to_video",
                            "lora_name": "BreastGrow",
                            "end_frame_draw_scene_id": "tail_pose",
                        }
                    ],
                }
            )
        ),
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=7), False)),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_group",
        AsyncMock(return_value="金丹期"),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_identity",
        AsyncMock(return_value="核心弟子"),
    )
    check_quota = AsyncMock(return_value=None)
    monkeypatch.setattr(quick_video_fsm.permission_service, "check_quota", check_quota)
    monkeypatch.setattr(quick_video_fsm, "robust_edit_text", AsyncMock())

    async def fake_process_generation_task(**kwargs):
        tail_calls.append(kwargs)
        return b"tail-bytes", "tail-output.png"

    async def fake_process_video_task_template(**kwargs):
        video_calls.append(kwargs)
        return b"video-bytes", "video-output.mp4"

    monkeypatch.setattr(
        quick_video_fsm,
        "process_generation_task",
        fake_process_generation_task,
    )
    monkeypatch.setattr(
        quick_video_fsm,
        "process_video_task_template",
        fake_process_video_task_template,
    )
    monkeypatch.setattr(
        quick_video_fsm,
        "download_output_file_to_fsm_temp",
        AsyncMock(return_value="/tmp/generated-tail.png"),
    )
    monkeypatch.setattr(
        quick_video_fsm,
        "create_background_task",
        lambda _context, task: background_tasks.append(task),
    )

    query = SimpleNamespace(
        from_user=SimpleNamespace(id=123, username="tester"),
        data="qvid_start_generation",
        answer=AsyncMock(),
        message=SimpleNamespace(chat_id=456, message_id=77),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(
            id=123,
            username="tester",
            full_name="Tester",
        ),
        effective_chat=SimpleNamespace(id=456),
    )
    context = SimpleNamespace(
        bot_data={"bot_client_type": "bot:qqcc"},
        user_data={
            "quick_video_data": {
                "mode": MODE_CUSTOM_VIDEO,
                "scene_id": "tail_video",
                "mode_name": "首尾动图",
                "resolution": "512p",
                "duration": "5s",
                "image_path": "/tmp/input.png",
            }
        },
        lang="zh",
        t=lambda key, **_kwargs: key,
    )

    await quick_video_fsm.start_generation(update, context)
    await background_tasks[0]

    assert check_quota.await_args.kwargs["cost"] == 22
    assert tail_calls[0]["task_type"] == "pornmaster_flux2_single_edit"
    assert tail_calls[0]["prompt"] == "tail prompt"
    assert tail_calls[0]["images"] == ["/tmp/input.png"]
    assert tail_calls[0]["send_result"] is False
    assert tail_calls[0]["allow_contribute"] is False
    assert video_calls[0]["mode"] == MODE_IMAGE_TO_VIDEO
    assert video_calls[0]["image_path"] == "/tmp/input.png"
    assert video_calls[0]["end_image_path"] == "/tmp/generated-tail.png"
    assert video_calls[0]["use_end_frame"] is True
    assert video_calls[0]["lora_name"] == "wan22_explicit_077"
    assert video_calls[0]["allow_contribute"] is False


@pytest.mark.asyncio
async def test_qqcc_video_scene_uses_postprocessed_tail_frame(monkeypatch):
    generation_calls = []
    video_calls = []
    background_tasks = []

    monkeypatch.setattr(
        quick_video_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(
            return_value=normalize_qqcc_config(
                {
                    "draw_scenes": [
                        {
                            "id": "tail_pose",
                            "name": "尾帧姿势",
                            "prompt": "tail prompt",
                            "postprocess_draw_scene_id": "tail_polish",
                        },
                        {
                            "id": "tail_polish",
                            "name": "尾帧精修",
                            "prompt": "tail polish prompt",
                        },
                    ],
                    "video_scenes": [
                        {
                            "id": "tail_video",
                            "name": "首尾动图",
                            "prompt": "video prompt",
                            "duration": "5s",
                            "engine": "image_to_video",
                            "lora_name": "BreastGrow",
                            "end_frame_draw_scene_id": "tail_pose",
                        }
                    ],
                }
            )
        ),
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=7), False)),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_group",
        AsyncMock(return_value="金丹期"),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_identity",
        AsyncMock(return_value="核心弟子"),
    )
    check_quota = AsyncMock(return_value=None)
    monkeypatch.setattr(quick_video_fsm.permission_service, "check_quota", check_quota)
    monkeypatch.setattr(quick_video_fsm, "robust_edit_text", AsyncMock())

    async def fake_process_generation_task(**kwargs):
        generation_calls.append(kwargs)
        return b"tail-bytes", f"tail-output-{len(generation_calls)}.png"

    async def fake_process_video_task_template(**kwargs):
        video_calls.append(kwargs)
        return b"video-bytes", "video-output.mp4"

    monkeypatch.setattr(
        quick_video_fsm,
        "process_generation_task",
        fake_process_generation_task,
    )
    monkeypatch.setattr(
        quick_video_fsm,
        "process_video_task_template",
        fake_process_video_task_template,
    )
    monkeypatch.setattr(
        quick_video_fsm,
        "download_output_file_to_fsm_temp",
        AsyncMock(side_effect=["/tmp/tail-pose.png", "/tmp/tail-polish.png"]),
    )
    monkeypatch.setattr(
        quick_video_fsm,
        "create_background_task",
        lambda _context, task: background_tasks.append(task),
    )

    query = SimpleNamespace(
        from_user=SimpleNamespace(id=123, username="tester"),
        data="qvid_start_generation",
        answer=AsyncMock(),
        message=SimpleNamespace(chat_id=456, message_id=77),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(
            id=123,
            username="tester",
            full_name="Tester",
        ),
        effective_chat=SimpleNamespace(id=456),
    )
    context = SimpleNamespace(
        bot_data={"bot_client_type": "bot:qqcc"},
        user_data={
            "quick_video_data": {
                "mode": MODE_CUSTOM_VIDEO,
                "scene_id": "tail_video",
                "mode_name": "首尾动图",
                "resolution": "512p",
                "duration": "5s",
                "image_path": "/tmp/input.png",
            }
        },
        lang="zh",
        t=lambda key, **_kwargs: key,
    )

    await quick_video_fsm.start_generation(update, context)
    await background_tasks[0]

    assert check_quota.await_args.kwargs["cost"] == 24
    assert generation_calls[0]["prompt"] == "tail prompt"
    assert generation_calls[0]["images"] == ["/tmp/input.png"]
    assert generation_calls[0]["send_result"] is False
    assert generation_calls[0]["allow_contribute"] is False
    assert generation_calls[1]["prompt"] == "tail polish prompt"
    assert generation_calls[1]["images"] == ["/tmp/tail-pose.png"]
    assert generation_calls[1]["send_result"] is False
    assert generation_calls[1]["allow_contribute"] is False
    assert video_calls[0]["end_image_path"] == "/tmp/tail-polish.png"
    assert video_calls[0]["allow_contribute"] is False


@pytest.mark.asyncio
async def test_qqcc_video_scene_generates_tail_frame_before_wan22_v2(monkeypatch):
    generation_calls = []
    background_tasks = []

    monkeypatch.setattr(
        quick_video_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(
            return_value=normalize_qqcc_config(
                {
                    "draw_scenes": [
                        {
                            "id": "tail_pose",
                            "name": "尾帧姿势",
                            "prompt": "tail prompt",
                        }
                    ],
                    "video_scenes": [
                        {
                            "id": "v2_tail_video",
                            "name": "新版首尾动图",
                            "prompt": "v2 video prompt",
                            "duration": "8s",
                            "engine": "wan22_video_v2",
                            "end_frame_draw_scene_id": "tail_pose",
                        }
                    ],
                }
            )
        ),
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=7), False)),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_group",
        AsyncMock(return_value="金丹期"),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_identity",
        AsyncMock(return_value="核心弟子"),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "check_quota",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(quick_video_fsm, "robust_edit_text", AsyncMock())

    async def fake_process_generation_task(**kwargs):
        generation_calls.append(kwargs)
        if kwargs.get("is_video"):
            return b"video-bytes", "video-output.mp4"
        return b"tail-bytes", "tail-output.png"

    monkeypatch.setattr(
        quick_video_fsm,
        "process_generation_task",
        fake_process_generation_task,
    )
    monkeypatch.setattr(
        quick_video_fsm,
        "download_output_file_to_fsm_temp",
        AsyncMock(return_value="/tmp/generated-tail.png"),
    )
    monkeypatch.setattr(
        quick_video_fsm,
        "create_background_task",
        lambda _context, task: background_tasks.append(task),
    )

    query = SimpleNamespace(
        from_user=SimpleNamespace(id=123, username="tester"),
        data="qvid_start_generation",
        answer=AsyncMock(),
        message=SimpleNamespace(chat_id=456, message_id=77),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(
            id=123,
            username="tester",
            full_name="Tester",
        ),
        effective_chat=SimpleNamespace(id=456),
    )
    context = SimpleNamespace(
        bot_data={"bot_client_type": "bot:qqcc"},
        user_data={
            "quick_video_data": {
                "mode": MODE_CUSTOM_VIDEO,
                "scene_id": "v2_tail_video",
                "mode_name": "新版首尾动图",
                "resolution": "512p",
                "duration": "8s",
                "image_path": "/tmp/input.png",
            }
        },
        lang="zh",
        t=lambda key, **_kwargs: key,
    )

    await quick_video_fsm.start_generation(update, context)
    await background_tasks[0]

    assert generation_calls[0]["task_type"] == "pornmaster_flux2_single_edit"
    assert generation_calls[0]["send_result"] is False
    assert generation_calls[1]["task_type"] == MODE_WAN22_VIDEO_V2
    assert generation_calls[1]["prompt"] == "v2 video prompt"
    assert generation_calls[1]["images"] == [
        "/tmp/input.png",
        "/tmp/generated-tail.png",
    ]
    assert generation_calls[1]["resolution"] == "720p"
    assert generation_calls[1]["duration"] == "8s"


@pytest.mark.asyncio
async def test_qqcc_video_scene_skips_video_when_tail_frame_generation_fails(
    monkeypatch,
):
    background_tasks = []
    cleaned_paths = []
    video_task = AsyncMock()

    monkeypatch.setattr(
        quick_video_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(
            return_value=normalize_qqcc_config(
                {
                    "draw_scenes": [
                        {
                            "id": "tail_pose",
                            "name": "尾帧姿势",
                            "prompt": "tail prompt",
                        }
                    ],
                    "video_scenes": [
                        {
                            "id": "tail_video",
                            "name": "首尾动图",
                            "prompt": "video prompt",
                            "duration": "5s",
                            "end_frame_draw_scene_id": "tail_pose",
                        }
                    ],
                }
            )
        ),
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=7), False)),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_group",
        AsyncMock(return_value="金丹期"),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_identity",
        AsyncMock(return_value="核心弟子"),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "check_quota",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(quick_video_fsm, "robust_edit_text", AsyncMock())
    monkeypatch.setattr(
        quick_video_fsm,
        "process_generation_task",
        AsyncMock(return_value=(None, None)),
    )
    monkeypatch.setattr(quick_video_fsm, "process_video_task_template", video_task)
    monkeypatch.setattr(
        quick_video_fsm,
        "cleanup_fsm_temp_files",
        lambda paths: cleaned_paths.extend(path for path in paths if path),
    )
    monkeypatch.setattr(
        quick_video_fsm,
        "create_background_task",
        lambda _context, task: background_tasks.append(task),
    )

    query = SimpleNamespace(
        from_user=SimpleNamespace(id=123, username="tester"),
        data="qvid_start_generation",
        answer=AsyncMock(),
        message=SimpleNamespace(chat_id=456, message_id=77),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(
            id=123,
            username="tester",
            full_name="Tester",
        ),
        effective_chat=SimpleNamespace(id=456),
    )
    context = SimpleNamespace(
        bot_data={"bot_client_type": "bot:qqcc"},
        user_data={
            "quick_video_data": {
                "mode": MODE_CUSTOM_VIDEO,
                "scene_id": "tail_video",
                "mode_name": "首尾动图",
                "resolution": "512p",
                "duration": "5s",
                "image_path": "/tmp/input.png",
            }
        },
        lang="zh",
        t=lambda key, **_kwargs: key,
    )

    await quick_video_fsm.start_generation(update, context)
    await background_tasks[0]

    video_task.assert_not_awaited()
    assert cleaned_paths == ["/tmp/input.png"]


@pytest.mark.asyncio
async def test_qqcc_video_scene_tail_frame_precheck_uses_combined_cost(monkeypatch):
    from src.core.exceptions import InsufficientCreditsError

    background_tasks = []

    monkeypatch.setattr(
        quick_video_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(
            return_value=normalize_qqcc_config(
                {
                    "draw_scenes": [
                        {
                            "id": "tail_pose",
                            "name": "尾帧姿势",
                            "prompt": "tail prompt",
                        }
                    ],
                    "video_scenes": [
                        {
                            "id": "tail_video",
                            "name": "首尾动图",
                            "prompt": "video prompt",
                            "duration": "5s",
                            "end_frame_draw_scene_id": "tail_pose",
                        }
                    ],
                }
            )
        ),
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=7), False)),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_group",
        AsyncMock(return_value="金丹期"),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_identity",
        AsyncMock(return_value="核心弟子"),
    )
    check_quota = AsyncMock(side_effect=InsufficientCreditsError(current=7, cost=8))
    monkeypatch.setattr(quick_video_fsm.permission_service, "check_quota", check_quota)
    monkeypatch.setattr("src.utils.robust_send_message", AsyncMock())
    cleanup_mock = MagicMock()
    monkeypatch.setattr(quick_video_fsm, "cleanup_fsm_temp_files", cleanup_mock)
    monkeypatch.setattr(
        quick_video_fsm,
        "create_background_task",
        lambda _context, task: background_tasks.append(task),
    )

    query = SimpleNamespace(
        from_user=SimpleNamespace(id=123, username="tester"),
        data="qvid_start_generation",
        answer=AsyncMock(),
        message=SimpleNamespace(chat_id=456, message_id=77),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(
            id=123,
            username="tester",
            full_name="Tester",
        ),
        effective_chat=SimpleNamespace(id=456),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        bot_data={"bot_client_type": "bot:qqcc"},
        user_data={
            "quick_video_data": {
                "mode": MODE_CUSTOM_VIDEO,
                "scene_id": "tail_video",
                "mode_name": "首尾动图",
                "resolution": "512p",
                "duration": "5s",
                "image_path": "/tmp/input.png",
            }
        },
        lang="zh",
        t=lambda key, **_kwargs: key,
    )

    await quick_video_fsm.start_generation(update, context)

    assert check_quota.await_args.kwargs["cost"] == 22
    assert background_tasks == []
    cleanup_mock.assert_any_call(["/tmp/input.png"])


@pytest.mark.asyncio
async def test_qqcc_quick_video_scene_callback_selects_dynamic_scene(monkeypatch):
    events = []
    reply_mock = AsyncMock(side_effect=lambda *_args, **_kwargs: events.append("text"))
    demo_sender = AsyncMock(side_effect=lambda **_kwargs: events.append("demo"))
    answer_mock = AsyncMock()
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "copywriting": {
                "video_scene_start": "已选择【{butten}】，请发送原图。",
            },
            "draw_scenes": [
                {"id": "make_input", "name": "生成输入图", "prompt": "draw prompt"}
            ],
            "video_scenes": [
                {
                    "id": "kiss",
                    "name": "亲吻",
                    "prompt": "kissing prompt",
                    "duration": "8s",
                    "jump_draw_scene_id": "make_input",
                    "demo_input_media": {
                        "object_key": "qqcc/demo/video/kiss/input",
                        "media_type": "image",
                        "mime_type": "image/png",
                        "file_name": "before.png",
                    },
                    "demo_output_media": {
                        "object_key": "qqcc/demo/video/kiss/output",
                        "media_type": "video",
                        "mime_type": "video/mp4",
                        "file_name": "after.mp4",
                    },
                }
            ],
        }
    )

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(quick_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(quick_video_fsm, "send_qqcc_scene_demo_media", demo_sender)
    monkeypatch.setattr(
        quick_video_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=config),
    )

    user = SimpleNamespace(id=123, username="tester")
    callback_message = SimpleNamespace(chat_id=456)
    update = SimpleNamespace(
        effective_user=user,
        effective_chat=SimpleNamespace(id=456),
        message=None,
        edited_message=None,
        callback_query=SimpleNamespace(
            data=build_quick_video_scene_callback_data("kiss"),
            message=callback_message,
            answer=answer_mock,
            from_user=user,
        ),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(id=999),
        bot_data={"bot_client_type": "bot:qqcc"},
        user_data={},
        lang="zh",
        t=lambda key, **kwargs: f"{key}:{kwargs}" if kwargs else key,
    )

    result = await quick_video_fsm.start_quick_video(update, context)

    assert result == quick_video_fsm.QuickVideoState.WAIT_IMAGE
    assert context.user_data["quick_video_data"] == {
        "mode": MODE_CUSTOM_VIDEO,
        "scene_id": "kiss",
        "mode_name": "亲吻",
        "prompt_override": "kissing prompt",
        "default_prompt_key": MODE_CUSTOM_VIDEO,
        "default_prompt_text": "kissing prompt",
        "engine": "image_to_video",
        "lora_name": "",
        "end_frame_draw_scene_id": "",
            "resolution": "720p",
        "duration": "8s",
        "image_path": None,
    }
    answer_mock.assert_awaited_once()
    assert events == ["demo", "text"]
    demo_sender.assert_awaited_once_with(
        message=callback_message,
        bot=context.bot,
        scene_kind="video",
        scene=config["video_scenes"][0],
    )
    reply_mock.assert_awaited_once()
    assert reply_mock.await_args.args[1] == "已选择【亲吻】，请发送原图。"
    jump_button = reply_mock.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
    assert jump_button.text == "先去 AI绘图生成「生成输入图」"
    assert jump_button.callback_data == "qdraw_scene:make_input"


@pytest.mark.asyncio
async def test_qqcc_legacy_quick_video_callback_is_blocked_after_scene_removed(
    monkeypatch,
):
    edit_mock = AsyncMock()
    answer_mock = AsyncMock()
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "video_scenes": [
                {
                    "id": "kiss",
                    "name": "亲吻",
                    "prompt": "kissing prompt",
                    "duration": "8s",
                }
            ],
        }
    )

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(quick_video_fsm, "robust_edit_text", edit_mock)
    monkeypatch.setattr(
        quick_video_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=config),
    )

    user = SimpleNamespace(id=123, username="tester")
    callback_message = SimpleNamespace(chat_id=456)
    update = SimpleNamespace(
        effective_user=user,
        effective_chat=SimpleNamespace(id=456),
        message=None,
        edited_message=None,
        callback_query=SimpleNamespace(
            data="qvid_mode:menu.video_edit_doggy",
            message=callback_message,
            answer=answer_mock,
            from_user=user,
        ),
    )
    context = SimpleNamespace(
        bot_data={"bot_client_type": "bot:qqcc"},
        user_data={},
        lang="zh",
        t=lambda key, **_kwargs: {"qqcc.feature_disabled": "功能暂未开放"}.get(
            key, key
        ),
    )

    result = await quick_video_fsm.start_quick_video(update, context)

    assert result == -1
    answer_mock.assert_awaited_once()
    edit_mock.assert_awaited_once_with(
        callback_message, "功能暂未开放", parse_mode="Markdown"
    )


@pytest.mark.asyncio
async def test_qqcc_main_bot_menu_route_replies_with_url_button(monkeypatch):
    _clear_main_bot_link_env(monkeypatch)
    monkeypatch.setenv("QQCC_MAIN_BOT_URL", "https://t.me/main_bot")

    reply_text = AsyncMock()
    message = SimpleNamespace(reply_text=reply_text)
    update = SimpleNamespace(
        effective_message=message,
        message=None,
        edited_message=None,
    )
    context = SimpleNamespace(
        lang="zh",
        t=lambda key: f"translated:{key}",
    )

    await prompt_handlers.handle_open_main_bot(update, context)

    reply_text.assert_awaited_once()
    kwargs = reply_text.await_args.kwargs
    assert kwargs["text"] == "translated:system.open_main_bot_hint"
    button = kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.text == "前往主bot"
    assert button.url == "https://t.me/main_bot"
