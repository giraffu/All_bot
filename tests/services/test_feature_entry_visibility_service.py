from copy import deepcopy

from src.services.feature_entry_visibility_service import (
    ADVANCED_VIDEO_PRO_MODES,
    DEFAULT_FEATURE_ENTRY_VISIBILITY_CONFIG,
    FEATURE_ENTRY_VISIBILITY_CONFIG_KEY,
    build_public_entry_visibility_flags,
    get_advanced_video_pro_profile,
    normalize_feature_entry_visibility_config,
)


def test_feature_entry_visibility_defaults_keep_pro_and_character_entries_hidden():
    config = normalize_feature_entry_visibility_config(None)

    assert config == DEFAULT_FEATURE_ENTRY_VISIBILITY_CONFIG
    assert config == {
        "web": {
            "edit": True,
            "edit_v2_5": True,
            "edit_v3": True,
            "txt2img": True,
            "i2i_pro": True,
            "custom_video": True,
            "face_swap": True,
            "random_faceswap": True,
            "ltx_video": True,
            "ltx_video_v2": True,
            "ltx_t2v": True,
            "minimax_h3": False,
            "wan22_video_v2": True,
            "scail2_action_transfer": True,
            "scail2_video_replacement": True,
            "scail2_face_swap_v2": True,
            "character_assets": False,
        },
        "gallery": {
            "txt2img": True,
            "i2i_pro": True,
            "edit": True,
            "free_edit_v2_5": True,
            "free_edit_v3": True,
            "custom_video": True,
            "ltx_video": True,
            "minimax_h3": False,
            "wan22_video_v2": True,
            "scail2_action_transfer": True,
            "scail2_video_replacement": True,
            "scail2_face_swap_v2": True,
        },
        "advanced_video_pro": {
            mode: {"main_model": "10eros", "addon_models": []}
            for mode in ADVANCED_VIDEO_PRO_MODES
        },
    }
    assert FEATURE_ENTRY_VISIBILITY_CONFIG_KEY == "feature_entry_visibility_config:v1"


def test_feature_entry_visibility_normalizes_unknown_and_invalid_values_safely():
    config = normalize_feature_entry_visibility_config(
        {
            "web": {
                "edit": False,
                "custom_video": False,
                "ltx_video": False,
                "minimax_h3": True,
                "character_assets": "true",
                "unknown": True,
            },
            "gallery": {
                "minimax_h3": True,
                "txt2img": False,
                "unknown": True,
            },
            "advanced_video_pro": {
                "i2v": {
                    "main_model": "official",
                    "addon_models": ["motion_booster", "unknown", "motion_booster"],
                },
                "ref2v": {
                    "main_model": "official_ref2v_turbo",
                    "addon_models": ["motion_booster_ref2va"],
                },
            },
        }
    )

    assert config == {
        "web": {
            "edit": False,
            "edit_v2_5": True,
            "edit_v3": True,
            "txt2img": True,
            "i2i_pro": True,
            "custom_video": False,
            "face_swap": True,
            "random_faceswap": True,
            "ltx_video": False,
            "ltx_video_v2": True,
            "ltx_t2v": True,
            "minimax_h3": True,
            "wan22_video_v2": True,
            "scail2_action_transfer": True,
            "scail2_video_replacement": True,
            "scail2_face_swap_v2": True,
            "character_assets": False,
        },
        "gallery": {
            "txt2img": False,
            "i2i_pro": True,
            "edit": True,
            "free_edit_v2_5": True,
            "free_edit_v3": True,
            "custom_video": True,
            "ltx_video": True,
            "minimax_h3": True,
            "wan22_video_v2": True,
            "scail2_action_transfer": True,
            "scail2_video_replacement": True,
            "scail2_face_swap_v2": True,
        },
        "advanced_video_pro": {
            "t2v": {"main_model": "10eros", "addon_models": []},
            "i2v": {
                "main_model": "official",
                "addon_models": ["motion_booster"],
            },
            "flf2v": {"main_model": "10eros", "addon_models": []},
            "ref2v": {
                "main_model": "official_ref2v_turbo",
                "addon_models": ["motion_booster_ref2va"],
            },
        },
    }

    profile = get_advanced_video_pro_profile(config, "i2v")
    assert profile == {
        "main_model": "official",
        "addon_items": [{"name": "motion_booster", "strength": 0.7}],
    }


def test_public_flags_keep_web_and_gallery_pro_visibility_independent():
    config = deepcopy(DEFAULT_FEATURE_ENTRY_VISIBILITY_CONFIG)
    config["web"]["minimax_h3"] = True
    config["gallery"]["minimax_h3"] = False

    assert build_public_entry_visibility_flags(config) == {
        "enable_edit_entry": True,
        "enable_edit_v2_5_entry": True,
        "enable_edit_v3_entry": True,
        "enable_txt2img_entry": True,
        "enable_i2i_pro_entry": True,
        "enable_custom_video_entry": True,
        "enable_face_swap_entry": True,
        "enable_random_faceswap_entry": True,
        "enable_ltx_video_entry": True,
        "enable_ltx_video_v2_entry": True,
        "enable_ltx_t2v_entry": True,
        "enable_minimax_h3_entry": True,
        "enable_wan22_video_v2_entry": True,
        "enable_scail2_action_transfer_entry": True,
        "enable_scail2_video_replacement_entry": True,
        "enable_scail2_face_swap_v2_entry": True,
        "enable_character_assets_entry": False,
        "enable_gallery_txt2img_entry": True,
        "enable_gallery_i2i_pro_entry": True,
        "enable_gallery_edit_entry": True,
        "enable_gallery_free_edit_v2_5_entry": True,
        "enable_gallery_free_edit_v3_entry": True,
        "enable_gallery_custom_video_entry": True,
        "enable_gallery_ltx_video_entry": True,
        "enable_gallery_minimax_h3_entry": False,
        "enable_gallery_wan22_video_v2_entry": True,
        "enable_gallery_scail2_action_transfer_entry": True,
        "enable_gallery_scail2_video_replacement_entry": True,
        "enable_gallery_scail2_face_swap_v2_entry": True,
    }
