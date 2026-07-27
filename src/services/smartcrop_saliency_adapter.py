from __future__ import annotations

from typing import Callable

from PIL import Image

from src.services.smart_image_aspect_service import CropBox

SMARTCROP_ANALYSIS_LONG_EDGE = 256


def smartcrop_saliency_crop(
    image: Image.Image,
    crop_size: tuple[int, int],
    *,
    smartcrop_factory: Callable[[], object] | None = None,
) -> CropBox:
    if smartcrop_factory is None:
        from smartcrop import SmartCrop

        smartcrop_factory = SmartCrop

    crop_width, crop_height = crop_size
    analysis_scale = min(
        1.0,
        SMARTCROP_ANALYSIS_LONG_EDGE / max(image.size),
    )
    analysis_image = image
    if analysis_scale < 1:
        analysis_image = image.resize(
            (
                max(1, round(image.width * analysis_scale)),
                max(1, round(image.height * analysis_scale)),
            ),
            Image.Resampling.LANCZOS,
        )
    analysis_width = max(1, round(crop_width * analysis_scale))
    analysis_height = max(1, round(crop_height * analysis_scale))
    cropper = smartcrop_factory()
    result = cropper.crop(
        analysis_image,
        analysis_width,
        analysis_height,
        max_scale=1,
        min_scale=1,
        num_scale_steps=1,
    )
    crop = result["top_crop"]
    focus_x = (
        float(crop["x"]) + float(crop["width"]) / 2
    ) / analysis_scale
    focus_y = (
        float(crop["y"]) + float(crop["height"]) / 2
    ) / analysis_scale
    left = max(0, min(image.width - crop_width, round(focus_x - crop_width / 2)))
    top = max(0, min(image.height - crop_height, round(focus_y - crop_height / 2)))
    return (
        left,
        top,
        left + crop_width,
        top + crop_height,
    )
