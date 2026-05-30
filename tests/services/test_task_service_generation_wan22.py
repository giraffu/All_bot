from src.services.task_service_generation_wan22 import (
    DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT,
    WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET,
    get_wan22_video_v2_cost,
    get_wan22_video_v2_resolution_label,
    normalize_wan22_video_v2_negative_prompt,
    normalize_wan22_video_v2_resolution_preset,
)


def test_normalize_wan22_video_v2_negative_prompt_falls_back_to_default():
    assert (
        normalize_wan22_video_v2_negative_prompt("   ")
        == DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT
    )


def test_normalize_wan22_video_v2_negative_prompt_keeps_custom_value():
    assert (
        normalize_wan22_video_v2_negative_prompt(" custom negative ")
        == "custom negative"
    )


def test_normalize_wan22_video_v2_resolution_preset_falls_back_to_default():
    assert (
        normalize_wan22_video_v2_resolution_preset("not-valid")
        == WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET
    )


def test_normalize_wan22_video_v2_resolution_preset_accepts_precision_value():
    assert (
        normalize_wan22_video_v2_resolution_preset("0.65 MP - Balanced") == "hd"
    )


def test_get_wan22_video_v2_resolution_label_uses_language():
    assert get_wan22_video_v2_resolution_label("fast", lang="zh") == "极速"
    assert get_wan22_video_v2_resolution_label("fast", lang="en") == "Fast"


def test_get_wan22_video_v2_cost_uses_resolution_preset():
    assert get_wan22_video_v2_cost("fast") == 10
    assert get_wan22_video_v2_cost("standard") == 20
    assert get_wan22_video_v2_cost("hd") == 30
    assert get_wan22_video_v2_cost("not-valid") == 20
