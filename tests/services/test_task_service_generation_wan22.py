from src.services.task_service_generation_wan22 import (
    DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT,
    normalize_wan22_video_v2_negative_prompt,
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
