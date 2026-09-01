import pytest

from app.pricing import public_catalog, quote_points


def test_public_catalog_exposes_video_upscale_only() -> None:
    assert set(public_catalog()["services"]) == {"video_upscale"}


def test_image_pricing_is_fixed_by_multiplier() -> None:
    assert quote_points("image_upscale", 2) == 2
    assert quote_points("image_upscale", 4) == 4


def test_video_pricing_rounds_up_each_started_ten_seconds() -> None:
    assert quote_points("video_upscale", 2, 10) == 5
    assert quote_points("video_upscale", 2, 10.01) == 10
    assert quote_points("frame_interpolation", 4, 21) == 15


def test_invalid_presets_fail_closed() -> None:
    with pytest.raises(ValueError):
        quote_points("video_upscale", 4, 10)
    with pytest.raises(ValueError):
        quote_points("frame_interpolation", 2, None)
