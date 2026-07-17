from copy import deepcopy

import pytest

from src.services.main_bot_menu_config_service import (
    DEFAULT_MAIN_BOT_MENU_CONFIG,
    MAIN_BOT_MENU_CONFIG_KEY,
    MainBotMenuConfigValidationError,
    normalize_main_bot_menu_config,
    validate_main_bot_menu_config,
)


def test_default_main_bot_menu_config_matches_current_menu_catalog():
    config = normalize_main_bot_menu_config(None)

    assert config == DEFAULT_MAIN_BOT_MENU_CONFIG
    assert config["main_menu"]["buttons_per_row"] == 3
    assert [item["key"] for item in config["main_menu"]["items"]] == [
        "menu.lazy_bot",
        "menu.recharge",
        "menu.checkin",
        "menu.profile",
        "menu.share",
        "menu.queue",
        "menu.switch_lang",
        "menu.photo_edit",
        "menu.video_to_video",
        "menu.txt2img",
        "menu.i2i_pro",
        "menu.free_edit",
        "menu.video_lora",
        "menu.ltx_video",
        "menu.wan22_video_v2",
    ]
    assert config["submenus"] == {
        "menu.photo_edit": [
            {"key": "menu.photo_edit_faceswap", "visible": True},
            {"key": "menu.photo_edit_random_faceswap", "visible": True},
        ],
        "menu.video_to_video": [
            {"key": "menu.video_to_video_replacement", "visible": True},
            {"key": "menu.video_to_video_action_transfer", "visible": True},
            {"key": "menu.face_video", "visible": True},
        ],
    }
    assert MAIN_BOT_MENU_CONFIG_KEY == "main_bot_menu_config:v1"


def test_normalize_main_bot_menu_config_drops_unknowns_and_appends_missing_items():
    config = normalize_main_bot_menu_config(
        {
            "main_menu": {
                "buttons_per_row": 4,
                "items": [
                    {"key": "menu.profile", "visible": False},
                    {"key": "unknown", "visible": True},
                    {"key": "menu.profile", "visible": True},
                    {"key": "menu.recharge", "visible": True},
                ],
            },
            "submenus": {
                "menu.photo_edit": [
                    {"key": "menu.photo_edit_random_faceswap", "visible": False},
                    {"key": "unknown", "visible": True},
                ],
                "unknown": [{"key": "menu.face_video", "visible": False}],
            },
        }
    )

    assert config["main_menu"]["buttons_per_row"] == 4
    assert config["main_menu"]["items"][:2] == [
        {"key": "menu.profile", "visible": False},
        {"key": "menu.recharge", "visible": True},
    ]
    assert len(config["main_menu"]["items"]) == 15
    assert config["submenus"]["menu.photo_edit"] == [
        {"key": "menu.photo_edit_random_faceswap", "visible": False},
        {"key": "menu.photo_edit_faceswap", "visible": True},
    ]
    assert "unknown" not in config["submenus"]


@pytest.mark.parametrize("buttons_per_row", [0, 5, "3", None])
def test_validate_main_bot_menu_config_rejects_invalid_row_size(buttons_per_row):
    payload = deepcopy(DEFAULT_MAIN_BOT_MENU_CONFIG)
    payload["main_menu"]["buttons_per_row"] = buttons_per_row

    with pytest.raises(MainBotMenuConfigValidationError):
        validate_main_bot_menu_config(payload)


def test_validate_main_bot_menu_config_rejects_all_hidden_main_items():
    payload = deepcopy(DEFAULT_MAIN_BOT_MENU_CONFIG)
    for item in payload["main_menu"]["items"]:
        item["visible"] = False

    with pytest.raises(MainBotMenuConfigValidationError):
        validate_main_bot_menu_config(payload)


def test_validate_main_bot_menu_config_returns_normalized_safe_payload():
    payload = deepcopy(DEFAULT_MAIN_BOT_MENU_CONFIG)
    payload["main_menu"]["items"].reverse()
    payload["submenus"]["menu.video_to_video"][0]["visible"] = False

    assert validate_main_bot_menu_config(payload) == payload
