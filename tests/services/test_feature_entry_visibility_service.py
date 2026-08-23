from copy import deepcopy

from src.services.feature_entry_visibility_service import (
    DEFAULT_FEATURE_ENTRY_VISIBILITY_CONFIG,
    FEATURE_ENTRY_VISIBILITY_CONFIG_KEY,
    build_public_entry_visibility_flags,
    normalize_feature_entry_visibility_config,
)


def test_feature_entry_visibility_defaults_keep_pro_and_character_entries_hidden():
    config = normalize_feature_entry_visibility_config(None)

    assert config == DEFAULT_FEATURE_ENTRY_VISIBILITY_CONFIG
    assert config == {
        "web": {
            "ltx_video": True,
            "minimax_h3": False,
            "character_assets": False,
        },
        "gallery": {"minimax_h3": False},
    }
    assert FEATURE_ENTRY_VISIBILITY_CONFIG_KEY == "feature_entry_visibility_config:v1"


def test_feature_entry_visibility_normalizes_unknown_and_invalid_values_safely():
    config = normalize_feature_entry_visibility_config(
        {
            "web": {
                "ltx_video": False,
                "minimax_h3": True,
                "character_assets": "true",
                "unknown": True,
            },
            "gallery": {"minimax_h3": True, "unknown": True},
        }
    )

    assert config == {
        "web": {
            "ltx_video": False,
            "minimax_h3": True,
            "character_assets": False,
        },
        "gallery": {"minimax_h3": True},
    }


def test_public_flags_keep_web_and_gallery_pro_visibility_independent():
    config = deepcopy(DEFAULT_FEATURE_ENTRY_VISIBILITY_CONFIG)
    config["web"]["minimax_h3"] = True
    config["gallery"]["minimax_h3"] = False

    assert build_public_entry_visibility_flags(config) == {
        "enable_ltx_video_entry": True,
        "enable_minimax_h3_entry": True,
        "enable_character_assets_entry": False,
        "enable_gallery_minimax_h3_entry": False,
    }
