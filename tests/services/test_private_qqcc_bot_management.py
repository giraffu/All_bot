from types import SimpleNamespace

import pytest

from src.services.qqcc_config_service import QqccSceneCreditCostError

from src.services.private_qqcc_bot_management import (
    PRIVATE_BOT_CONFIG_MAX_DRAW_CHAIN_DEPTH,
    PrivateBotConfigLimitError,
    PrivateBotConfigVersionConflict,
    build_private_bot_config_payload,
    update_private_bot_config_record,
)


def _bot(**overrides):
    values = {
        "id": 7,
        "telegram_bot_id": 123,
        "telegram_username": "tenant_bot",
        "telegram_display_name": "Tenant",
        "owner_enabled": True,
        "admin_enabled": True,
        "runtime_status": "active",
        "last_error_code": None,
        "last_error_message": None,
        "last_webhook_at": None,
        "last_update_at": None,
        "updated_at": None,
        "config": {"global_enabled": True},
        "config_version": 3,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_owner_config_update_is_optimistic_and_normalizes_unknown_fields():
    bot = _bot()

    update_private_bot_config_record(
        bot,
        expected_version=3,
        raw_config={
            "global_enabled": False,
            "main_buttons": {"ai_draw": False, "unknown": True},
            "main_menu_layout": {
                "buttons_per_row": 4,
                "button_order": ["main_bot_link", "ai_draw"],
            },
            "unknown_section": {"secret": True},
        },
    )

    assert bot.config_version == 4
    assert bot.config["global_enabled"] is False
    assert bot.config["main_buttons"]["ai_draw"] is False
    assert bot.config["main_menu_layout"]["buttons_per_row"] == 4
    assert bot.config["main_menu_layout"]["button_order"][:2] == [
        "main_bot_link",
        "ai_draw",
    ]
    assert "unknown" not in bot.config["main_buttons"]
    assert "unknown_section" not in bot.config


def test_owner_config_update_rejects_stale_version_without_mutating_record():
    bot = _bot()
    original = dict(bot.config)

    with pytest.raises(PrivateBotConfigVersionConflict):
        update_private_bot_config_record(
            bot,
            expected_version=2,
            raw_config={"global_enabled": False},
        )

    assert bot.config == original
    assert bot.config_version == 3


def test_owner_config_update_rejects_non_positive_scene_credit_cost():
    bot = _bot()

    with pytest.raises(QqccSceneCreditCostError):
        update_private_bot_config_record(
            bot,
            expected_version=3,
            raw_config={
                "draw_scenes": [
                    {
                        "id": "draw",
                        "name": "Draw",
                        "prompt": "draw",
                        "credit_cost": 0,
                    }
                ]
            },
        )

    assert bot.config_version == 3


def test_owner_payload_never_contains_encrypted_or_fingerprint_credentials():
    bot = _bot(
        token_ciphertext="encrypted-secret",
        token_fingerprint="fingerprint-secret",
        webhook_secret_hash="webhook-secret",
    )

    payload = build_private_bot_config_payload(bot)

    assert payload["bot"]["id"] == 7
    assert payload["config_version"] == 3
    serialized = str(payload)
    assert "encrypted-secret" not in serialized
    assert "fingerprint-secret" not in serialized
    assert "webhook-secret" not in serialized


def test_private_demo_media_must_belong_to_current_tenant():
    own_media = {
        "object_key": "qqcc/private/7/demo/draw/scene_a/input",
        "media_type": "image",
        "mime_type": "image/png",
        "file_name": "demo.png",
        "content_sha256": "a" * 64,
        "telegram_file_ids": {},
    }
    bot = _bot()

    update_private_bot_config_record(
        bot,
        expected_version=3,
        raw_config={
            "scene_preset_version": 1,
            "draw_scenes": [
                {
                    "id": "scene_a",
                    "name": "Scene A",
                    "prompt": "prompt",
                    "demo_input_media": own_media,
                }
            ],
        },
    )
    assert (
        bot.config["draw_scenes"][0]["demo_input_media"]["object_key"]
        == own_media["object_key"]
    )

    with pytest.raises(ValueError, match="another tenant"):
        update_private_bot_config_record(
            bot,
            expected_version=4,
            raw_config={
                "scene_preset_version": 1,
                "draw_scenes": [
                    {
                        "id": "scene_a",
                        "name": "Scene A",
                        "prompt": "prompt",
                        "demo_input_media": {
                            **own_media,
                            "object_key": "qqcc/private/8/demo/draw/scene_a/input",
                        },
                    }
                ],
            },
        )

    with pytest.raises(ValueError, match="another tenant"):
        update_private_bot_config_record(
            bot,
            expected_version=4,
            raw_config={
                "scene_preset_version": 1,
                "draw_scenes": [
                    {
                        "id": "scene_a",
                        "name": "Scene A",
                        "prompt": "prompt",
                        "demo_input_media": {
                            **own_media,
                            "object_key": "qqcc/demo/draw/scene_a/input",
                        },
                    }
                ],
            },
        )


def test_owner_config_rejects_oversized_prompt_before_normalization():
    bot = _bot()

    with pytest.raises(PrivateBotConfigLimitError, match="prompt is too long"):
        update_private_bot_config_record(
            bot,
            expected_version=3,
            raw_config={
                "draw_scenes": [
                    {
                        "id": "scene_a",
                        "name": "Scene A",
                        "prompt": "x" * 12_001,
                    }
                ]
            },
        )

    assert bot.config_version == 3


def test_owner_config_rejects_deep_draw_postprocess_chain():
    bot = _bot()
    scenes = [
        {
            "id": f"scene_{index}",
            "name": f"Scene {index}",
            "prompt": "safe",
            "postprocess_draw_scene_id": f"scene_{index + 1}",
        }
        for index in range(PRIVATE_BOT_CONFIG_MAX_DRAW_CHAIN_DEPTH + 1)
    ]
    scenes[-1]["postprocess_draw_scene_id"] = ""

    with pytest.raises(PrivateBotConfigLimitError, match="too deep"):
        update_private_bot_config_record(
            bot,
            expected_version=3,
            raw_config={"draw_scenes": scenes},
        )
