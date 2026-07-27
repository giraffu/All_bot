from __future__ import annotations

from io import BytesIO
import os
import tempfile
from typing import Final

from PIL import Image, ImageOps

from src.services.fsm_temp_file_service import FSM_TEMP_DIR
from src.services.smart_image_aspect_service import (
    FocusDetector,
    SaliencyCropper,
    adapt_image_to_aspect,
)
from src.services.smartcrop_saliency_adapter import smartcrop_saliency_crop
from src.services.yunet_face_detector import detect_yunet_focus_regions

QQCC_VIDEO_ASPECT_SOURCE: Final = "source"
QQCC_VIDEO_ASPECT_RATIOS: Final = ("source", "9:16", "16:9", "1:1")
_ASPECT_UNITS: Final = {
    "9:16": (9, 16),
    "16:9": (16, 9),
    "1:1": (1, 1),
}
_SUPPORTED_IMAGE_FORMATS: Final = frozenset({"JPEG", "PNG"})


class QqccVideoFrameAdaptationError(ValueError):
    pass


def normalize_qqcc_video_aspect_ratio(value: object) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    return (
        normalized
        if normalized in QQCC_VIDEO_ASPECT_RATIOS
        else QQCC_VIDEO_ASPECT_SOURCE
    )


def _load_supported_image(content: bytes) -> Image.Image:
    try:
        image = Image.open(BytesIO(content))
        if image.format not in _SUPPORTED_IMAGE_FORMATS:
            raise QqccVideoFrameAdaptationError(
                "QQCC video frames must be JPEG or PNG"
            )
        image.load()
        return image
    except QqccVideoFrameAdaptationError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise QqccVideoFrameAdaptationError(
            "QQCC video frame could not be decoded"
        ) from exc


def adapt_qqcc_video_frame_bytes(
    content: bytes,
    *,
    aspect_ratio: str,
    focus_detector: FocusDetector = detect_yunet_focus_regions,
    saliency_cropper: SaliencyCropper = smartcrop_saliency_crop,
) -> bytes:
    normalized_aspect = normalize_qqcc_video_aspect_ratio(aspect_ratio)
    image = _load_supported_image(content)
    if normalized_aspect == QQCC_VIDEO_ASPECT_SOURCE:
        image.close()
        return content

    try:
        normalized_image = ImageOps.exif_transpose(image).convert("RGB")
        adaptation = adapt_image_to_aspect(
            normalized_image,
            aspect=_ASPECT_UNITS[normalized_aspect],
            focus_detector=focus_detector,
            saliency_cropper=saliency_cropper,
        )
        output = BytesIO()
        adaptation.image.save(output, format="PNG")
        return output.getvalue()
    except QqccVideoFrameAdaptationError:
        raise
    except (OSError, ValueError) as exc:
        raise QqccVideoFrameAdaptationError(
            "QQCC video frame could not be adapted"
        ) from exc
    finally:
        image.close()


def adapt_qqcc_video_frame_file(
    path: str,
    *,
    aspect_ratio: str,
    output_dir: str = FSM_TEMP_DIR,
    focus_detector: FocusDetector = detect_yunet_focus_regions,
    saliency_cropper: SaliencyCropper = smartcrop_saliency_crop,
) -> str:
    try:
        with open(path, "rb") as source_file:
            content = source_file.read()
    except OSError as exc:
        raise QqccVideoFrameAdaptationError(
            "QQCC video frame could not be read"
        ) from exc

    normalized_aspect = normalize_qqcc_video_aspect_ratio(aspect_ratio)
    adapted = adapt_qqcc_video_frame_bytes(
        content,
        aspect_ratio=normalized_aspect,
        focus_detector=focus_detector,
        saliency_cropper=saliency_cropper,
    )
    if normalized_aspect == QQCC_VIDEO_ASPECT_SOURCE:
        return path

    os.makedirs(output_dir, exist_ok=True)
    file_descriptor, output_path = tempfile.mkstemp(
        prefix="qqcc_video_frame_",
        suffix=".png",
        dir=output_dir,
    )
    try:
        with os.fdopen(file_descriptor, "wb") as output_file:
            output_file.write(adapted)
    except BaseException:
        try:
            os.close(file_descriptor)
        except OSError:
            pass
        try:
            os.unlink(output_path)
        except OSError:
            pass
        raise
    return output_path
