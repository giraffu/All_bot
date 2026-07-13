from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.handlers import prompt_router
from src.handlers import menu_route_registry
from src.handlers.message_handler_prompt import handle_prompt_impl


@pytest.mark.asyncio
async def test_handle_prompt_impl_delegates_to_route_dispatch(monkeypatch):
    ensure_access = AsyncMock()
    extract_message = MagicMock(return_value=("msg", "主菜单"))
    dispatch_route = AsyncMock(return_value=(True, "routed"))
    reply_fallback = AsyncMock()
    logger = SimpleNamespace(info=MagicMock())
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1))
    context = SimpleNamespace(lang="zh")

    monkeypatch.setattr(
        "src.handlers.prompt_router.GLOBAL_REVERSE_MAP",
        {"主菜单": "menu.main_menu"},
        raising=False,
    )

    result = await handle_prompt_impl(
        update,
        context,
        prompt_routes={"menu.main_menu": object()},
        ensure_user_access_reward=ensure_access,
        extract_prompt_message_text=extract_message,
        dispatch_prompt_route=dispatch_route,
        reply_private_prompt_fallback=reply_fallback,
        reply_text="reply-text",
        logger=logger,
    )

    assert result == "routed"
    ensure_access.assert_awaited_once_with(context, update.effective_user)
    dispatch_route.assert_awaited_once()
    reply_fallback.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_prompt_impl_falls_back_for_unmatched_private_prompt(monkeypatch):
    ensure_access = AsyncMock()
    extract_message = MagicMock(return_value=("msg", "unknown"))
    dispatch_route = AsyncMock(return_value=(False, None))
    reply_fallback = AsyncMock(return_value=None)
    logger = SimpleNamespace(info=MagicMock())
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1))
    context = SimpleNamespace(lang="zh")

    monkeypatch.setattr(
        "src.handlers.prompt_router.GLOBAL_REVERSE_MAP",
        {},
        raising=False,
    )

    result = await handle_prompt_impl(
        update,
        context,
        prompt_routes={},
        ensure_user_access_reward=ensure_access,
        extract_prompt_message_text=extract_message,
        dispatch_prompt_route=dispatch_route,
        reply_private_prompt_fallback=reply_fallback,
        reply_text="reply-text",
        logger=logger,
    )

    assert result is None
    reply_fallback.assert_awaited_once_with(
        "msg",
        lang="zh",
        reply_text="reply-text",
    )


def test_build_global_menu_filter_prefers_video_lora_for_shared_image_to_video_label(
    monkeypatch,
):
    monkeypatch.setattr(
        prompt_router,
        "load_locales",
        lambda: {
            "zh": {
                "menu": {
                    "video_lora": "🎬 图生视频",
                    "custom_video": "🎬 图生视频",
                }
            }
        },
    )
    monkeypatch.setattr(prompt_router, "prompt_routes", {}, raising=False)

    prompt_router.build_global_menu_filter()

    assert prompt_router.GLOBAL_REVERSE_MAP["🎬 图生视频"] == "menu.video_lora"


def test_build_global_menu_filter_keeps_legacy_custom_video_text():
    prompt_router.GLOBAL_REVERSE_MAP.clear()

    prompt_router.build_global_menu_filter()

    assert prompt_router.GLOBAL_REVERSE_MAP["🎬 自定义图生视频"] == "menu.custom_video"


def test_menu_route_registry_partitions_route_sources():
    assert "menu.video_lora" in menu_route_registry.FSM_MENU_KEYS
    assert "qqcc.menu.quick_faceswap" in menu_route_registry.FSM_MENU_KEYS
    assert "qqcc.menu.ai_filter" in menu_route_registry.FSM_MENU_KEYS
    assert "menu.video_lora" in menu_route_registry.SPECIAL_TRANSLATION_ROUTE_KEYS
    assert "qqcc.menu.ai_filter" in menu_route_registry.SPECIAL_TRANSLATION_ROUTE_KEYS
    assert (
        menu_route_registry.LEGACY_TEXT_ALIASES["🎬 自定义图生视频"]
        == "menu.custom_video"
    )
    assert menu_route_registry.LEGACY_TEXT_ALIASES["AI动图"] == "menu.video_edit"
    assert menu_route_registry.LEGACY_TEXT_ALIASES["AI滤镜"] == "qqcc.menu.ai_filter"


def test_menu_route_registry_builds_all_reverse_route_keys():
    route_keys = menu_route_registry.build_global_reverse_route_keys(
        registered_route_keys={"menu.profile"}
    )

    assert "menu.profile" in route_keys
    assert "menu.video_to_video_replacement" in route_keys
    assert "qqcc.menu.market" in route_keys
    assert "qqcc.menu.ai_filter" in route_keys
