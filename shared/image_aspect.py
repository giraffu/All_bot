from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Sequence

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

CropBox = tuple[int, int, int, int]
AspectUnits = tuple[int, int]

MIN_SAFE_RETAINED_AREA = 0.55
FOREGROUND_CANVAS_FRACTION = 0.94


class FocusDetectionUnavailable(RuntimeError):
    """Raised when the configured focus detector cannot make a safe decision."""


@dataclass(frozen=True, slots=True)
class FocusRegion:
    left: int
    top: int
    right: int
    bottom: int
    confidence: float = 1.0


class FocusDetector(Protocol):
    def __call__(self, image: Image.Image) -> Sequence[FocusRegion]: ...


class SaliencyCropper(Protocol):
    def __call__(self, image: Image.Image, crop_size: tuple[int, int]) -> CropBox: ...


class AspectAdaptationMode(str, Enum):
    UNCHANGED = "unchanged"
    FOCUS_CROP = "focus_crop"
    SALIENCY_CROP = "saliency_crop"
    CENTER_CROP = "center_crop"
    BLURRED_PADDING = "blurred_padding"


@dataclass(frozen=True, slots=True)
class AspectAdaptation:
    image: Image.Image
    mode: AspectAdaptationMode
    retained_area: float
    crop_box: CropBox | None = None
    focus_count: int = 0


def _validate_aspect(aspect: AspectUnits) -> AspectUnits:
    width, height = aspect
    if width <= 0 or height <= 0:
        raise ValueError("aspect units must be positive")
    return width, height


def _maximum_exact_crop_size(
    image_size: tuple[int, int],
    aspect: AspectUnits,
) -> tuple[int, int]:
    width, height = image_size
    ratio_width, ratio_height = _validate_aspect(aspect)
    scale = min(width // ratio_width, height // ratio_height)
    if scale < 1:
        raise ValueError("image is too small for the requested exact aspect ratio")
    return scale * ratio_width, scale * ratio_height


def _retained_area(
    image_size: tuple[int, int],
    crop_size: tuple[int, int],
) -> float:
    width, height = image_size
    crop_width, crop_height = crop_size
    return (crop_width * crop_height) / (width * height)


def _center_crop_box(
    image_size: tuple[int, int],
    crop_size: tuple[int, int],
) -> CropBox:
    width, height = image_size
    crop_width, crop_height = crop_size
    left = (width - crop_width) // 2
    top = (height - crop_height) // 2
    return left, top, left + crop_width, top + crop_height


def _normalized_region(
    region: FocusRegion,
    image_size: tuple[int, int],
) -> FocusRegion | None:
    width, height = image_size
    left = max(0, min(width, int(region.left)))
    top = max(0, min(height, int(region.top)))
    right = max(left, min(width, int(region.right)))
    bottom = max(top, min(height, int(region.bottom)))
    if right <= left or bottom <= top:
        return None
    return FocusRegion(left, top, right, bottom, float(region.confidence))


def _focus_safe_bounds(
    regions: Sequence[FocusRegion],
    image_size: tuple[int, int],
) -> CropBox | None:
    normalized = [
        item
        for region in regions
        if (item := _normalized_region(region, image_size)) is not None
    ]
    if not normalized:
        return None

    expanded: list[CropBox] = []
    width, height = image_size
    for region in normalized:
        face_width = region.right - region.left
        face_height = region.bottom - region.top
        expanded.append(
            (
                max(0, round(region.left - face_width * 0.35)),
                max(0, round(region.top - face_height * 0.65)),
                min(width, round(region.right + face_width * 0.35)),
                min(height, round(region.bottom + face_height * 1.25)),
            )
        )
    return (
        min(box[0] for box in expanded),
        min(box[1] for box in expanded),
        max(box[2] for box in expanded),
        max(box[3] for box in expanded),
    )


def _clamp(value: float, lower: int, upper: int) -> int:
    return max(lower, min(upper, round(value)))


def _focus_crop_box(
    image_size: tuple[int, int],
    crop_size: tuple[int, int],
    safe_bounds: CropBox,
) -> CropBox | None:
    width, height = image_size
    crop_width, crop_height = crop_size
    safe_left, safe_top, safe_right, safe_bottom = safe_bounds
    if safe_right - safe_left > crop_width or safe_bottom - safe_top > crop_height:
        return None

    if crop_width < width:
        lower = max(0, safe_right - crop_width)
        upper = min(safe_left, width - crop_width)
        if lower > upper:
            return None
        focus_center = (safe_left + safe_right) / 2
        left = _clamp(focus_center - crop_width / 2, lower, upper)
    else:
        left = 0

    if crop_height < height:
        lower = max(0, safe_bottom - crop_height)
        upper = min(safe_top, height - crop_height)
        if lower > upper:
            return None
        face_center = (safe_top + safe_bottom) / 2
        top = _clamp(face_center - crop_height * 0.30, lower, upper)
    else:
        top = 0
    return left, top, left + crop_width, top + crop_height


def _exact_canvas_size(
    image_size: tuple[int, int],
    aspect: AspectUnits,
) -> tuple[int, int]:
    ratio_width, ratio_height = _validate_aspect(aspect)
    longest_source_edge = max(image_size)
    scale = max(1, longest_source_edge // max(ratio_width, ratio_height))
    return ratio_width * scale, ratio_height * scale


def _blurred_padding(
    image: Image.Image,
    aspect: AspectUnits,
) -> Image.Image:
    canvas_size = _exact_canvas_size(image.size, aspect)
    source = image.convert("RGB")
    background = ImageOps.fit(
        source,
        canvas_size,
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    blur_radius = max(8, round(min(canvas_size) * 0.06))
    background = background.filter(ImageFilter.GaussianBlur(blur_radius))
    background = ImageEnhance.Color(background).enhance(0.65)
    background = ImageEnhance.Brightness(background).enhance(0.62)

    foreground = source.copy()
    max_size = (
        max(1, round(canvas_size[0] * FOREGROUND_CANVAS_FRACTION)),
        max(1, round(canvas_size[1] * FOREGROUND_CANVAS_FRACTION)),
    )
    foreground.thumbnail(max_size, Image.Resampling.LANCZOS)
    offset = (
        (canvas_size[0] - foreground.width) // 2,
        (canvas_size[1] - foreground.height) // 2,
    )
    background.paste(foreground, offset)
    return background


def _valid_crop_box(
    box: CropBox,
    *,
    image_size: tuple[int, int],
    crop_size: tuple[int, int],
) -> bool:
    left, top, right, bottom = box
    return (
        left >= 0
        and top >= 0
        and right <= image_size[0]
        and bottom <= image_size[1]
        and right - left == crop_size[0]
        and bottom - top == crop_size[1]
    )


def adapt_image_to_aspect(
    image: Image.Image,
    *,
    aspect: AspectUnits,
    focus_detector: FocusDetector | None = None,
    saliency_cropper: SaliencyCropper | None = None,
    min_safe_retained_area: float = MIN_SAFE_RETAINED_AREA,
) -> AspectAdaptation:
    """Adapt an image without allowing uncertain detection to crop a subject.

    This platform-neutral implementation is shared by control-plane and GPU
    runtime callers so their crop-versus-padding safety policy cannot drift.
    """

    source = image.convert("RGB")
    crop_size = _maximum_exact_crop_size(source.size, aspect)
    retained_area = _retained_area(source.size, crop_size)
    if crop_size == source.size:
        return AspectAdaptation(
            image=source.copy(),
            mode=AspectAdaptationMode.UNCHANGED,
            retained_area=1.0,
        )

    if retained_area < min_safe_retained_area:
        return AspectAdaptation(
            image=_blurred_padding(source, aspect),
            mode=AspectAdaptationMode.BLURRED_PADDING,
            retained_area=retained_area,
        )

    if focus_detector is None:
        return AspectAdaptation(
            image=_blurred_padding(source, aspect),
            mode=AspectAdaptationMode.BLURRED_PADDING,
            retained_area=retained_area,
        )
    try:
        focus_regions = list(focus_detector(source))
    except FocusDetectionUnavailable:
        return AspectAdaptation(
            image=_blurred_padding(source, aspect),
            mode=AspectAdaptationMode.BLURRED_PADDING,
            retained_area=retained_area,
        )

    safe_bounds = _focus_safe_bounds(focus_regions, source.size)
    if safe_bounds is not None:
        crop_box = _focus_crop_box(source.size, crop_size, safe_bounds)
        if crop_box is None:
            return AspectAdaptation(
                image=_blurred_padding(source, aspect),
                mode=AspectAdaptationMode.BLURRED_PADDING,
                retained_area=retained_area,
                focus_count=len(focus_regions),
            )
        return AspectAdaptation(
            image=source.crop(crop_box),
            mode=AspectAdaptationMode.FOCUS_CROP,
            retained_area=retained_area,
            crop_box=crop_box,
            focus_count=len(focus_regions),
        )

    if saliency_cropper is not None:
        try:
            crop_box = saliency_cropper(source, crop_size)
        except (ImportError, RuntimeError, ValueError):
            crop_box = _center_crop_box(source.size, crop_size)
            mode = AspectAdaptationMode.CENTER_CROP
        else:
            if _valid_crop_box(
                crop_box,
                image_size=source.size,
                crop_size=crop_size,
            ):
                mode = AspectAdaptationMode.SALIENCY_CROP
            else:
                crop_box = _center_crop_box(source.size, crop_size)
                mode = AspectAdaptationMode.CENTER_CROP
    else:
        crop_box = _center_crop_box(source.size, crop_size)
        mode = AspectAdaptationMode.CENTER_CROP
    return AspectAdaptation(
        image=source.crop(crop_box),
        mode=mode,
        retained_area=retained_area,
        crop_box=crop_box,
    )
