from __future__ import annotations

from dataclasses import dataclass
import math


LTX25_VIDEO_UPSCALE_TASK_TYPE = "ltx25_video_upscale"
LTX25_VIDEO_UPSCALE_DURATION_SECONDS = 5
LTX25_VIDEO_UPSCALE_MAX_DURATION_SECONDS = 15
LTX25_VIDEO_UPSCALE_SOURCE_DURATION_TOLERANCE_SECONDS = 0.25
LTX25_VIDEO_UPSCALE_MAX_SOURCE_DURATION_SECONDS = (
    LTX25_VIDEO_UPSCALE_MAX_DURATION_SECONDS
    + LTX25_VIDEO_UPSCALE_SOURCE_DURATION_TOLERANCE_SECONDS
)
LTX25_VIDEO_UPSCALE_FPS = 24
LTX25_VIDEO_UPSCALE_DEFAULT_RESOLUTION = "1080p"
LTX25_VIDEO_UPSCALE_RESOLUTION_SHORT_EDGES = {
    "720p": 720,
    "1080p": 1080,
    "2k": 1440,
}
LTX25_VIDEO_UPSCALE_MAX_LONG_EDGE = 2560
LTX25_VIDEO_UPSCALE_HYBRID_SCALE_THRESHOLD = 2.0
LTX25_VIDEO_UPSCALE_MODEL_MAX_LONG_EDGE = 864
LTX25_VIDEO_UPSCALE_VSR_MAX_SCALE = 4.0
LTX25_VIDEO_UPSCALE_TEMPORAL_COMPRESSION = 8
LTX25_VIDEO_UPSCALE_IC_GUIDE_TEMPORAL_MULTIPLIER = 2
# Keep one IC-LoRA sampling window within the 32 GB canary envelope. The
# budget is expressed as combined latent frames * model-input pixels and is
# calibrated to 15 seconds at a 384x224 model canvas.
LTX25_VIDEO_UPSCALE_MODEL_SPATIOTEMPORAL_BUDGET = 92 * 384 * 224
LTX25_VIDEO_UPSCALE_CREDITS_PER_SECOND = {
    "720p": 5,
    "1080p": 10,
    "2k": 36,
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


@dataclass(frozen=True)
class Ltx25VideoUpscalePlan:
    resolution: str
    mode: str
    source_width: int
    source_height: int
    target_width: int
    target_height: int
    scale: float
    model_width: int | None = None
    model_height: int | None = None
    latent_width: int | None = None
    latent_height: int | None = None
    content_width: int | None = None
    content_height: int | None = None
    pad_x: int = 0
    pad_y: int = 0
    vsr_scale: float = 1.0


def normalize_ltx25_video_upscale_prompt(value: object) -> str:
    prompt = str(value or "").strip()
    if len(prompt) > 2_000:
        raise ValueError("视频高清化提示词不能超过 2000 个字符。")
    return prompt or LTX25_VIDEO_UPSCALE_DEFAULT_PROMPT


def normalize_ltx25_video_upscale_duration(value: object) -> int:
    try:
        duration = int(str(value or LTX25_VIDEO_UPSCALE_DURATION_SECONDS).rstrip("s"))
    except (TypeError, ValueError) as exc:
        raise ValueError("视频高清化支持 1 至 15 秒视频。") from exc
    if not 1 <= duration <= LTX25_VIDEO_UPSCALE_MAX_DURATION_SECONDS:
        raise ValueError("视频高清化支持 1 至 15 秒视频。")
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
        raise ValueError("视频高清化当前只支持最长 15 秒的视频。")
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
    if normalized not in LTX25_VIDEO_UPSCALE_RESOLUTION_SHORT_EDGES:
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
    return tuple(
        resolution
        for resolution in LTX25_VIDEO_UPSCALE_RESOLUTION_SHORT_EDGES
        if _target_scale(width, height, resolution) > 1.0
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
    duration: object = LTX25_VIDEO_UPSCALE_DURATION_SECONDS,
) -> tuple[int, int]:
    plan = build_ltx25_video_upscale_plan(
        source_width,
        source_height,
        resolution,
        duration=duration,
    )
    if plan.model_width is None or plan.model_height is None:
        return plan.target_width, plan.target_height
    return plan.model_width, plan.model_height


def _positive_dimensions(source_width: object, source_height: object) -> tuple[int, int]:
    try:
        width = int(source_width)
        height = int(source_height)
    except (TypeError, ValueError) as exc:
        raise ValueError("无法读取视频分辨率。") from exc
    if width <= 0 or height <= 0:
        raise ValueError("无法读取视频分辨率。")
    return width, height


def _round_even(value: float) -> int:
    return max(2, int(round(value / 2.0)) * 2)


def _target_scale(width: int, height: int, resolution: object) -> float:
    normalized = normalize_ltx25_video_upscale_resolution(resolution)
    short_edge = min(width, height)
    long_edge = max(width, height)
    return min(
        LTX25_VIDEO_UPSCALE_RESOLUTION_SHORT_EDGES[normalized] / short_edge,
        LTX25_VIDEO_UPSCALE_MAX_LONG_EDGE / long_edge,
    )


def get_ltx25_video_upscale_target_dimensions(
    source_width: object,
    source_height: object,
    resolution: object,
) -> tuple[int, int]:
    """Fit the source ratio into the selected short-edge/QHD envelope."""
    width, height = _positive_dimensions(source_width, source_height)
    normalized = normalize_ltx25_video_upscale_resolution(resolution)
    source_ratio = width / height
    for common_ratio in (16 / 9, 9 / 16, 3 / 2, 2 / 3, 1.0):
        if abs(source_ratio - common_ratio) / common_ratio <= 0.01:
            source_ratio = common_ratio
            break
    target_short = LTX25_VIDEO_UPSCALE_RESOLUTION_SHORT_EDGES[normalized]
    if source_ratio >= 1:
        target_width = target_short * source_ratio
        target_height = float(target_short)
    else:
        target_width = float(target_short)
        target_height = target_short / source_ratio
    envelope_scale = min(1.0, LTX25_VIDEO_UPSCALE_MAX_LONG_EDGE / max(
        target_width, target_height
    ))
    return (
        _round_even(target_width * envelope_scale),
        _round_even(target_height * envelope_scale),
    )


def _hybrid_model_canvas(
    width: int,
    height: int,
    target_width: int,
    target_height: int,
    duration: int,
) -> tuple[int, int]:
    source_long = max(width, height)
    source_short = min(width, height)
    target_long = max(target_width, target_height)
    lower_long = math.ceil(
        target_long / (2 * LTX25_VIDEO_UPSCALE_VSR_MAX_SCALE) / 32
    ) * 32
    upper_long = int(min(
        LTX25_VIDEO_UPSCALE_MODEL_MAX_LONG_EDGE,
        target_long / 2,
    ) / 32) * 32
    desired_long = min(upper_long, max(lower_long, source_long))
    start_long = min(
        upper_long,
        max(lower_long, int(round(desired_long / 32)) * 32),
    )
    frame_count = get_ltx25_video_upscale_frame_count(duration)
    latent_frames = (
        (frame_count - 1) // LTX25_VIDEO_UPSCALE_TEMPORAL_COMPRESSION
    ) + 1
    combined_latent_frames = (
        latent_frames * LTX25_VIDEO_UPSCALE_IC_GUIDE_TEMPORAL_MULTIPLIER
    )
    max_canvas_area = (
        LTX25_VIDEO_UPSCALE_MODEL_SPATIOTEMPORAL_BUDGET
        // combined_latent_frames
    )

    for canvas_long in range(start_long, lower_long - 1, -32):
        desired_short = canvas_long * source_short / source_long
        canvas_short = max(32, int(round(desired_short / 32)) * 32)
        if canvas_long * canvas_short > max_canvas_area:
            continue
        if width >= height:
            model_width, model_height = canvas_long, canvas_short
        else:
            model_width, model_height = canvas_short, canvas_long
        vsr_scale = max(
            target_width / (model_width * 2),
            target_height / (model_height * 2),
        )
        if vsr_scale <= LTX25_VIDEO_UPSCALE_VSR_MAX_SCALE:
            return model_width, model_height

    raise ValueError("该视频宽高比无法在当前 15 秒显存预算内安全高清化。")


def build_ltx25_video_upscale_plan(
    source_width: object,
    source_height: object,
    resolution: object,
    *,
    duration: object = LTX25_VIDEO_UPSCALE_DURATION_SECONDS,
) -> Ltx25VideoUpscalePlan:
    width, height = _positive_dimensions(source_width, source_height)
    normalized = normalize_ltx25_video_upscale_resolution(resolution)
    normalized_duration = normalize_ltx25_video_upscale_duration(duration)
    target_width, target_height = get_ltx25_video_upscale_target_dimensions(
        width, height, normalized
    )
    scale = _target_scale(width, height, normalized)
    if scale <= 1.0:
        raise ValueError("目标清晰度必须高于原视频，且最高为 2K。")
    if scale <= LTX25_VIDEO_UPSCALE_HYBRID_SCALE_THRESHOLD:
        return Ltx25VideoUpscalePlan(
            resolution=normalized,
            mode="vsr_only",
            source_width=width,
            source_height=height,
            target_width=target_width,
            target_height=target_height,
            scale=scale,
            vsr_scale=scale,
        )

    model_width, model_height = _hybrid_model_canvas(
        width,
        height,
        target_width,
        target_height,
        normalized_duration,
    )
    latent_width = model_width * 2
    latent_height = model_height * 2
    fit_scale = min(model_width / width, model_height / height)
    content_width = min(model_width, _round_even(width * fit_scale))
    content_height = min(model_height, _round_even(height * fit_scale))
    pad_x = (model_width - content_width) // 2
    pad_y = (model_height - content_height) // 2
    return Ltx25VideoUpscalePlan(
        resolution=normalized,
        mode="ltx_hybrid",
        source_width=width,
        source_height=height,
        target_width=target_width,
        target_height=target_height,
        scale=scale,
        model_width=model_width,
        model_height=model_height,
        latent_width=latent_width,
        latent_height=latent_height,
        content_width=content_width,
        content_height=content_height,
        pad_x=pad_x,
        pad_y=pad_y,
        vsr_scale=max(target_width / latent_width, target_height / latent_height),
    )
