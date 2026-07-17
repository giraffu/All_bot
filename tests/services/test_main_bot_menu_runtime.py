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
