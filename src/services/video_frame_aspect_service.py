from __future__ import annotations

from PIL import Image, ImageOps


class VideoFrameAspectError(ValueError):
    pass


def validate_video_frame_aspects(
    image_paths: list[str] | tuple[str, ...],
    *,
    relative_tolerance: float = 0.01,
) -> tuple[tuple[int, int], ...]:
    dimensions: list[tuple[int, int]] = []
    for raw_path in image_paths:
        try:
            with Image.open(raw_path) as image:
                normalized = ImageOps.exif_transpose(image)
                dimensions.append((int(normalized.width), int(normalized.height)))
        except (OSError, ValueError) as exc:
            raise VideoFrameAspectError("无法读取输入图片尺寸，请重新上传。") from exc
    if len(dimensions) >= 2:
        first_width, first_height = dimensions[0]
        last_width, last_height = dimensions[1]
        first_ratio = first_width / first_height
        last_ratio = last_width / last_height
        if abs(first_ratio - last_ratio) / first_ratio > relative_tolerance:
            raise VideoFrameAspectError("尾帧比例需与首帧一致，请重新上传尾帧。")
    return tuple(dimensions)
