from __future__ import annotations

import math


LTX25_VIDEO_UPSCALE_TASK_TYPE = "ltx25_video_upscale"
LTX25_VIDEO_UPSCALE_DURATION_SECONDS = 5
LTX25_VIDEO_UPSCALE_MAX_DURATION_SECONDS = 20
LTX25_VIDEO_UPSCALE_SOURCE_DURATION_TOLERANCE_SECONDS = 0.25
LTX25_VIDEO_UPSCALE_MAX_SOURCE_DURATION_SECONDS = (
    LTX25_VIDEO_UPSCALE_MAX_DURATION_SECONDS
    + LTX25_VIDEO_UPSCALE_SOURCE_DURATION_TOLERANCE_SECONDS
)
LTX25_VIDEO_UPSCALE_FPS = 24
LTX25_VIDEO_UPSCALE_DEFAULT_RESOLUTION = "1080p"
LTX25_VIDEO_UPSCALE_RESOLUTION_LONG_EDGES = {
    "720p": 1280,
    "1080p": 1920,
    "2k": 2560,
}
LTX25_VIDEO_UPSCALE_CREDITS_PER_SECOND = {
    "720p": 5,
    "1080p": 10,
    "2k": 18,
}
LTX25_VIDEO_UPSCALE_COST = (
    LTX25_VIDEO_UPSCALE_DURATION_SECONDS
    * LTX25_VIDEO_UPSCALE_CREDITS_PER_SECOND[
        LTX25_VIDEO_UPSCALE_DEFAULT_RESOLUTION
    ]
)
LTX25_VIDEO_UPSCALE_MAX_BYTES = 40 * 1024 * 1024
LTX25_VIDEO_UPSCALE_FACTOR = 2
LTX25_VIDEO_UPSCALE_DEFAULT_PROMPT = (
    "Preserve the exact same subject, identity, composition, camera motion, "
    "body proportions, clothing, background, timing, and action. Add coherent fine "
    "detail and natural texture without changing the scene."
)
LTX25_VIDEO_UPSCALE_NEGATIVE_PROMPT = (
    "worst quality, inconsistent motion, blurry, jittery, distorted, identity drift, "
    "changed composition, duplicated limbs, text artifacts"
)


def normalize_ltx25_video_upscale_prompt(value: object) -> str:
    prompt = str(value or "").strip()
    if len(prompt) > 2_000:
        raise ValueError("视频高清化提示词不能超过 2000 个字符。")
    return prompt or LTX25_VIDEO_UPSCALE_DEFAULT_PROMPT


def normalize_ltx25_video_upscale_duration(value: object) -> int:
    try:
        duration = int(str(value or LTX25_VIDEO_UPSCALE_DURATION_SECONDS).rstrip("s"))
    except (TypeError, ValueError) as exc:
        raise ValueError("视频高清化支持 1 至 20 秒视频。") from exc
    if not 1 <= duration <= LTX25_VIDEO_UPSCALE_MAX_DURATION_SECONDS:
        raise ValueError("视频高清化支持 1 至 20 秒视频。")
    return duration


def normalize_ltx25_video_upscale_source_duration(value: object) -> int:
    """Map a probed media duration to a whole-second model frame grid."""
    try:
        source_duration = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("无法读取视频时长。") from exc
    if not math.isfinite(source_duration) or source_duration <= 0:
        raise ValueError("无法读取视频时长。")
    if source_duration > LTX25_VIDEO_UPSCALE_MAX_SOURCE_DURATION_SECONDS:
        raise ValueError("视频高清化当前只支持最长 20 秒的视频。")
    duration = math.ceil(
        source_duration
        - LTX25_VIDEO_UPSCALE_SOURCE_DURATION_TOLERANCE_SECONDS
    )
    return min(
        LTX25_VIDEO_UPSCALE_MAX_DURATION_SECONDS,
        max(1, duration),
    )


def get_ltx25_video_upscale_frame_count(duration: object) -> int:
    normalized = normalize_ltx25_video_upscale_duration(duration)
    return normalized * LTX25_VIDEO_UPSCALE_FPS + 1


def normalize_ltx25_video_upscale_resolution(value: object) -> str:
    normalized = str(value or LTX25_VIDEO_UPSCALE_DEFAULT_RESOLUTION).strip().lower()
    aliases = {
        "720": "720p",
        "1080": "1080p",
        "1440p": "2k",
        "2560": "2k",
        "2560x1440": "2k",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in LTX25_VIDEO_UPSCALE_RESOLUTION_LONG_EDGES:
        raise ValueError("视频高清化清晰度只支持 720p、1080p 或 2K。")
    return normalized


def get_ltx25_video_upscale_cost(duration: object, resolution: object) -> int:
    normalized_duration = normalize_ltx25_video_upscale_duration(duration)
    normalized_resolution = normalize_ltx25_video_upscale_resolution(resolution)
    return (
        normalized_duration
        * LTX25_VIDEO_UPSCALE_CREDITS_PER_SECOND[normalized_resolution]
    )


def get_ltx25_video_upscale_available_resolutions(
    source_width: object,
    source_height: object,
) -> tuple[str, ...]:
    try:
        width = int(source_width)
        height = int(source_height)
    except (TypeError, ValueError) as exc:
        raise ValueError("无法读取视频分辨率。") from exc
    if width <= 0 or height <= 0:
        raise ValueError("无法读取视频分辨率。")
    source_long_edge = max(width, height)
    return tuple(
        resolution
        for resolution, long_edge in LTX25_VIDEO_UPSCALE_RESOLUTION_LONG_EDGES.items()
        if long_edge > source_long_edge
    )


def resolve_ltx25_video_upscale_resolution(
    source_width: object,
    source_height: object,
    requested_resolution: object = None,
) -> str:
    available = get_ltx25_video_upscale_available_resolutions(
        source_width, source_height
    )
    if not available:
        raise ValueError("原视频已经达到或超过 2K，暂无可用高清化档位。")
    if requested_resolution in (None, "", "auto"):
        return available[0]
    normalized = normalize_ltx25_video_upscale_resolution(requested_resolution)
    if normalized not in available:
        raise ValueError("目标清晰度必须高于原视频，且最高为 2K。")
    return normalized


def get_ltx25_video_upscale_model_input_dimensions(
    source_width: object,
    source_height: object,
    resolution: object,
) -> tuple[int, int]:
    width = int(source_width)
    height = int(source_height)
    if width <= 0 or height <= 0:
        raise ValueError("无法读取视频分辨率。")
    normalized = normalize_ltx25_video_upscale_resolution(resolution)
    model_long_edge = LTX25_VIDEO_UPSCALE_RESOLUTION_LONG_EDGES[normalized] // 2
    if width >= height:
        model_width = model_long_edge
        model_height = max(32, int(model_width * height / width / 32) * 32)
    else:
        model_height = model_long_edge
        model_width = max(32, int(model_height * width / height / 32) * 32)
    return model_width, model_height
