"""Compatibility facade for the shared smart image aspect adapter."""

from shared.image_aspect import (
    MIN_SAFE_RETAINED_AREA,
    AspectAdaptation,
    AspectAdaptationMode,
    AspectUnits,
    CropBox,
    FocusDetectionUnavailable,
    FocusDetector,
    FocusRegion,
    SaliencyCropper,
    adapt_image_to_aspect,
)

__all__ = [
    "MIN_SAFE_RETAINED_AREA",
    "AspectAdaptation",
    "AspectAdaptationMode",
    "AspectUnits",
    "CropBox",
    "FocusDetectionUnavailable",
    "FocusDetector",
    "FocusRegion",
    "SaliencyCropper",
    "adapt_image_to_aspect",
]
