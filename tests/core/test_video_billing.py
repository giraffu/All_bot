import pytest

from src.core.video_billing import (
    infer_legacy_ltx_requested_duration,
    infer_legacy_tier_video_requested_duration,
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
