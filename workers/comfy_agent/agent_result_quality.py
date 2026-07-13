import io
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageChops, ImageStat, UnidentifiedImageError


I2I_PRO_TASK_TYPE = "i2i_pro"
I2I_PRO_BLACK_MEAN_THRESHOLD = 5.0
I2I_PRO_BLACK_STDDEV_THRESHOLD = 5.0
I2I_PRO_DARK_PIXEL_THRESHOLD = 8
I2I_PRO_DARK_PIXEL_RATIO_THRESHOLD = 0.98
I2I_PRO_REFERENCE_DIFF_THRESHOLD = 25.0


@dataclass(frozen=True)
class OutputQualityIssue:
    reason: str
    metric: float
    threshold: float


def _open_rgb_image(image_bytes: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise RuntimeError("result is not a readable image") from exc
    return image.convert("RGB")


def _dark_pixel_ratio(gray_image: Image.Image) -> float:
    sample = gray_image.resize(
        (
            max(1, gray_image.width // 8),
            max(1, gray_image.height // 8),
        )
    )
    pixel_count = sample.width * sample.height
    if pixel_count <= 0:
        return 0.0
    histogram = sample.histogram()
    dark_pixels = sum(histogram[:I2I_PRO_DARK_PIXEL_THRESHOLD])
    return dark_pixels / pixel_count


def assess_i2i_pro_output_quality(
    *,
    primary_bytes: bytes,
    reference_bytes: bytes | None = None,
) -> OutputQualityIssue | None:
    output = _open_rgb_image(primary_bytes)
    gray_output = output.convert("L")
    output_stats = ImageStat.Stat(gray_output)
    output_mean = float(output_stats.mean[0])
    output_stddev = float(output_stats.stddev[0])
    dark_ratio = _dark_pixel_ratio(gray_output)

    if (
        output_mean <= I2I_PRO_BLACK_MEAN_THRESHOLD
        and output_stddev <= I2I_PRO_BLACK_STDDEV_THRESHOLD
    ) or dark_ratio >= I2I_PRO_DARK_PIXEL_RATIO_THRESHOLD:
        return OutputQualityIssue(
            reason="black_image",
            metric=output_mean,
            threshold=I2I_PRO_BLACK_MEAN_THRESHOLD,
        )

    if reference_bytes:
        reference = _open_rgb_image(reference_bytes).resize(output.size)
        diff = ImageChops.difference(reference, output).convert("L")
        diff_mean = float(ImageStat.Stat(diff).mean[0])
        if diff_mean <= I2I_PRO_REFERENCE_DIFF_THRESHOLD:
            return OutputQualityIssue(
                reason="too_similar_to_input",
                metric=diff_mean,
                threshold=I2I_PRO_REFERENCE_DIFF_THRESHOLD,
            )

    return None


async def assess_materialized_output_quality(
    *,
    task_type: str,
    params: dict[str, Any],
    outputs,
    comfy_client,
    logger,
) -> OutputQualityIssue | None:
    if task_type != I2I_PRO_TASK_TYPE:
        return None

    primary = getattr(outputs, "primary", None)
    content_type = str(getattr(primary, "content_type", "") or "")
    if not content_type.startswith("image/"):
        return None

    reference_bytes = None
    reference_image = str(params.get("image") or "").strip()
    if reference_image:
        try:
            reference_bytes = await comfy_client.get_view(
                reference_image,
                "",
                type="input",
            )
        except Exception as exc:
            logger.warning(
                "Failed to fetch i2i_pro reference input for quality check: %s",
                exc,
            )

    return assess_i2i_pro_output_quality(
        primary_bytes=primary.file_data,
        reference_bytes=reference_bytes,
    )
