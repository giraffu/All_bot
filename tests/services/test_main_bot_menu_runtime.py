from unittest.mock import AsyncMock

import pytest

from src.i18n.translator import get_text
from src.services.main_bot_menu_config_service import (
    DEFAULT_MAIN_BOT_MENU_CONFIG,
    normalize_main_bot_menu_config,
)
from src.services.main_bot_menu_runtime import (
    get_runtime_main_menu_keyboard,
    get_runtime_photo_edit_keyboard,
)


def _texts(keyboard):
    return [[button.text for button in row] for row in keyboard.keyboard]


@pytest.mark.asyncio
async def test_runtime_keyboard_loads_latest_config_for_each_render():
    config = normalize_main_bot_menu_config(DEFAULT_MAIN_BOT_MENU_CONFIG)
    config["main_menu"]["buttons_per_row"] = 1
    config["main_menu"]["items"][1]["visible"] = False
    loader = AsyncMock(return_value=config)

    keyboard = await get_runtime_main_menu_keyboard("zh", load_config_func=loader)

    loader.assert_awaited_once_with()
    assert all(len(row) == 1 for row in keyboard.keyboard)
    assert get_text("menu.recharge", "zh") not in sum(_texts(keyboard), [])


@pytest.mark.asyncio
async def test_runtime_keyboard_falls_back_to_defaults_when_config_load_fails():
    loader = AsyncMock(side_effect=RuntimeError("database unavailable"))

    keyboard = await get_runtime_photo_edit_keyboard(
        "zh",
        load_config_func=loader,
    )

    assert _texts(keyboard) == [
        [
            get_text("menu.photo_edit_faceswap", "zh"),
            get_text("menu.photo_edit_random_faceswap", "zh"),
        ],
        [get_text("menu.back_main", "zh")],
    ]


@pytest.mark.asyncio
async def test_runtime_keyboard_uses_ltx_label_in_prod_and_h3_label_in_test(monkeypatch):
    config = normalize_main_bot_menu_config(DEFAULT_MAIN_BOT_MENU_CONFIG)

    monkeypatch.setenv("ALLBOT_ENV", "prod")
    monkeypatch.delenv("MINIMAX_H3_BACKEND_ENABLED", raising=False)
    prod_keyboard = await get_runtime_main_menu_keyboard(
        "zh", load_config_func=AsyncMock(return_value=config)
    )

    monkeypatch.setenv("ALLBOT_ENV", "test")
    test_keyboard = await get_runtime_main_menu_keyboard(
        "zh", load_config_func=AsyncMock(return_value=config)
    )

    prod_labels = sum(_texts(prod_keyboard), [])
    test_labels = sum(_texts(test_keyboard), [])
    assert get_text("menu.ltx_video", "zh") in prod_labels
    assert get_text("menu.advanced_video_pro", "zh") not in prod_labels
    assert get_text("menu.advanced_video_pro", "zh") not in test_labels
    assert get_text("menu.ltx_video", "zh") in test_labels
