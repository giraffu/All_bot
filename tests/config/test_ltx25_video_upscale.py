import pytest

from src.domain_config.ltx25_video_upscale import (
    LTX25_VIDEO_UPSCALE_IC_GUIDE_TEMPORAL_MULTIPLIER,
    LTX25_VIDEO_UPSCALE_MODEL_SPATIOTEMPORAL_BUDGET,
    LTX25_VIDEO_UPSCALE_TEMPORAL_COMPRESSION,
    build_ltx25_video_upscale_plan,
    get_ltx25_video_upscale_frame_count,
    get_ltx25_video_upscale_available_resolutions,
    get_ltx25_video_upscale_target_dimensions,
    normalize_ltx25_video_upscale_duration,
    normalize_ltx25_video_upscale_source_duration,
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ((1920, 1080), (2560, 1440)),
        ((1080, 1920), (1440, 2560)),
        ((576, 864), (1440, 2160)),
        ((1080, 1080), (1440, 1440)),
    ],
)
def test_2k_target_preserves_source_aspect_inside_qhd_envelope(source, expected):
    assert get_ltx25_video_upscale_target_dimensions(*source, "2k") == expected


def test_available_resolutions_are_based_on_real_scale_not_a_fixed_long_edge():
    assert get_ltx25_video_upscale_available_resolutions(1920, 1080) == ("2k",)
    assert get_ltx25_video_upscale_available_resolutions(576, 864) == (
        "720p",
        "1080p",
        "2k",
    )
    assert get_ltx25_video_upscale_available_resolutions(2560, 1440) == ()


def test_near_target_sources_use_vsr_without_diffusion_regeneration():
    plan = build_ltx25_video_upscale_plan(1920, 1080, "2k")

    assert plan.mode == "vsr_only"
    assert (plan.target_width, plan.target_height) == (2560, 1440)
    assert plan.model_width is None
    assert plan.model_height is None


@pytest.mark.parametrize(
    ("source", "resolution", "duration", "target", "model_canvas"),
    [
        ((854, 480), "1080p", 5, (1920, 1080), (640, 352)),
        ((910, 512), "2k", 5, (2560, 1440), (640, 352)),
        ((576, 864), "2k", 5, (1440, 2160), (384, 576)),
        ((768, 448), "2k", 10, (2468, 1440), (448, 256)),
        ((768, 448), "2k", 15, (2468, 1440), (384, 224)),
    ],
)
def test_low_resolution_sources_use_duration_bounded_hybrid_canvas(
    source, resolution, duration, target, model_canvas
):
    plan = build_ltx25_video_upscale_plan(*source, resolution, duration=duration)

    assert plan.mode == "ltx_hybrid"
    assert (plan.target_width, plan.target_height) == target
    assert (plan.model_width, plan.model_height) == model_canvas
    assert plan.latent_width == plan.model_width * 2
    assert plan.latent_height == plan.model_height * 2
    assert plan.content_width <= plan.model_width
    assert plan.content_height <= plan.model_height
    assert plan.content_width + plan.pad_x * 2 <= plan.model_width
    assert plan.content_height + plan.pad_y * 2 <= plan.model_height
    assert 1 <= plan.vsr_scale <= 4


def test_duration_limit_matches_h3_and_accepts_the_encoding_tail():
    assert normalize_ltx25_video_upscale_duration(15) == 15
    assert normalize_ltx25_video_upscale_source_duration(15.166667) == 15

    with pytest.raises(ValueError, match="1 至 15 秒"):
        normalize_ltx25_video_upscale_duration(16)
    with pytest.raises(ValueError, match="最长 15 秒"):
        normalize_ltx25_video_upscale_source_duration(15.251)


def test_every_supported_duration_stays_inside_the_single_window_token_budget():
    previous_area = None
    for duration in range(1, 16):
        plan = build_ltx25_video_upscale_plan(
            768,
            448,
            "2k",
            duration=duration,
        )
        frame_count = get_ltx25_video_upscale_frame_count(duration)
        latent_frames = (
            (frame_count - 1) // LTX25_VIDEO_UPSCALE_TEMPORAL_COMPRESSION
        ) + 1
        combined_latent_frames = (
            latent_frames * LTX25_VIDEO_UPSCALE_IC_GUIDE_TEMPORAL_MULTIPLIER
        )
        area = plan.model_width * plan.model_height

        assert area * combined_latent_frames <= (
            LTX25_VIDEO_UPSCALE_MODEL_SPATIOTEMPORAL_BUDGET
        )
        assert plan.vsr_scale <= 4
        if previous_area is not None:
            assert area <= previous_area
        previous_area = area
