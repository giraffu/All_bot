import pytest

from src.core.video_billing import (
    infer_billing_resolution_from_dimensions,
    infer_legacy_ltx_requested_duration,
    infer_legacy_tier_video_requested_duration,
    resolve_apply_prompt_and_requested_duration,
    resolve_legacy_requested_duration,
)


@pytest.mark.parametrize(
    ("media_duration", "expected_requested_duration"),
    [
        (6, 5),
        (7, 5),
        (8, 10),
        (9, 10),
        (11, 10),
        (13, 15),
        (16, 15),
        (17, 15),
        (18, 20),
        (19, 20),
        (21, 20),
        (1, None),
        (23, None),
    ],
)
def test_infer_legacy_ltx_requested_duration(media_duration, expected_requested_duration):
    assert (
        infer_legacy_ltx_requested_duration(media_duration)
        == expected_requested_duration
    )


@pytest.mark.parametrize(
    ("media_duration", "expected_requested_duration"),
    [
        (5, 5),
        (6, 5),
        (7, 8),
        (8, 8),
        (9, 8),
        (10, 10),
        (11, 10),
        (12, 10),
        (1, None),
        (13, None),
    ],
)
def test_infer_legacy_tier_video_requested_duration(
    media_duration, expected_requested_duration
):
    assert (
        infer_legacy_tier_video_requested_duration(media_duration)
        == expected_requested_duration
    )


@pytest.mark.parametrize(
    ("width", "height", "task_type", "expected_billing_resolution"),
    [
        (720, 1280, "custom_video", "standard"),
        (512, 768, "custom_video", "preview"),
        (1024, 1536, "video_lora", "hd"),
    ],
)
def test_infer_billing_resolution_from_dimensions_uses_short_side_for_tier_video(
    width, height, task_type, expected_billing_resolution
):
    assert (
        infer_billing_resolution_from_dimensions(width, height, task_type)
        == expected_billing_resolution
    )


@pytest.mark.parametrize(
    ("task_type", "requested_duration", "media_duration", "expected_requested_duration"),
    [
        ("ltx_video", 20, 18, 20),
        ("ltx_video", None, 18, 20),
        ("custom_video", None, 9, 5),
        ("wan22_video_v2", 10, 9, 10),
        ("video_lora", None, 11, 5),
        ("image", None, 9, None),
    ],
)
def test_resolve_legacy_requested_duration(
    task_type,
    requested_duration,
    media_duration,
    expected_requested_duration,
):
    assert (
        resolve_legacy_requested_duration(
            task_type=task_type,
            requested_duration=requested_duration,
            duration=media_duration,
        )
        == expected_requested_duration
    )


@pytest.mark.parametrize(
    ("task_type", "prompt", "requested_duration", "expected_prompt", "expected_requested_duration"),
    [
        ("ltx_video", "[1344x768|20s] wide cinematic dolly shot", 20, "wide cinematic dolly shot", 20),
        ("ltx_video", "[1344x768|20s] wide cinematic dolly shot", None, "wide cinematic dolly shot", None),
        ("custom_video", "cinematic action shot", 8, "cinematic action shot", 8),
    ],
)
def test_resolve_apply_prompt_and_requested_duration(
    task_type,
    prompt,
    requested_duration,
    expected_prompt,
    expected_requested_duration,
):
    assert resolve_apply_prompt_and_requested_duration(
        task_type,
        prompt,
        requested_duration,
    ) == (expected_prompt, expected_requested_duration)
