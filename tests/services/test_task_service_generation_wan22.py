from src.services.task_service_generation_wan22 import (
    DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT,
    WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET,
    get_wan22_video_v2_cost,
    get_wan22_video_v2_resolution_display,
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
        normalize_wan22_video_v2_resolution_preset("0.26 MP - Preview")
        == "preview"
    )
    assert (
        normalize_wan22_video_v2_resolution_preset("0.65 MP - Balanced") == "hd"
    )


def test_normalize_wan22_video_v2_resolution_preset_maps_legacy_fast_to_preview():
    assert normalize_wan22_video_v2_resolution_preset("fast") == "preview"
    assert (
        normalize_wan22_video_v2_resolution_preset("0.36 MP - Small")
        == "preview"
    )


def test_get_wan22_video_v2_resolution_label_uses_language():
    assert get_wan22_video_v2_resolution_label("preview", lang="zh") == "极速"
    assert get_wan22_video_v2_resolution_label("preview", lang="en") == "Fast"
    assert get_wan22_video_v2_resolution_label("fast", lang="zh") == "极速"
    assert get_wan22_video_v2_resolution_label("fast", lang="en") == "Fast"


def test_get_wan22_video_v2_resolution_display_includes_approx_resolution():
    assert (
        get_wan22_video_v2_resolution_display("preview", lang="zh")
        == "极速（约 512p）"
    )
    assert (
        get_wan22_video_v2_resolution_display("standard", lang="zh")
        == "标准（约 720p）"
    )
    assert (
        get_wan22_video_v2_resolution_display("hd", lang="zh")
        == "高清（约 810p）"
    )
    assert (
        get_wan22_video_v2_resolution_display("preview", lang="en")
        == "Fast (approx. 512p)"
    )


def test_get_wan22_video_v2_cost_uses_resolution_preset():
    assert get_wan22_video_v2_cost("preview") == 6
    assert get_wan22_video_v2_cost("fast") == 6
    assert get_wan22_video_v2_cost("standard") == 20
    assert get_wan22_video_v2_cost("hd") == 30
    assert get_wan22_video_v2_cost("not-valid") == 6
