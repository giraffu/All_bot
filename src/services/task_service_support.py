from typing import Any

from src.constants import DEFAULT_DURATION, DEFAULT_RESOLUTION
from src.utils import robust_reply_text


def normalize_custom_video_resolution_value(resolution: Any) -> int:
    if isinstance(resolution, int):
        if resolution >= 1024:
            return 1024
        if resolution >= 720:
            return 720
        return 512
    if resolution == "1024p":
        return 1024
    if resolution == "720p":
        return 720
    return 512


def normalize_custom_video_duration_value(duration: Any) -> int:
    if isinstance(duration, int):
        if duration >= 10:
            return 10
        if duration >= 8:
            return 8
        return 5
    if duration == "10s":
        return 10
    if duration == "8s":
        return 8
    return 5


def _canonical_custom_video_resolution(resolution: Any) -> str:
    normalized = normalize_custom_video_resolution_value(resolution)
    if normalized == 1024:
        return "1024p"
    if normalized == 720:
        return "720p"
    return DEFAULT_RESOLUTION


def _canonical_custom_video_duration(duration: Any) -> str:
    normalized = normalize_custom_video_duration_value(duration)
    if normalized == 10:
        return "10s"
    if normalized == 8:
        return "8s"
    return DEFAULT_DURATION


async def resolve_custom_video_settings(
    context,
    *,
    update=None,
    warn_invalid_combo: bool = False,
    reply_text_func=robust_reply_text,
    resolution: Any = None,
    duration: Any = None,
) -> tuple[str, str, int, int]:
    resolution = (
        context.user_data.get("custom_video_resolution", DEFAULT_RESOLUTION)
        if resolution is None
        else resolution
    )
    duration = (
        context.user_data.get("custom_video_duration", DEFAULT_DURATION)
        if duration is None
        else duration
    )
    resolution = _canonical_custom_video_resolution(resolution)
    duration = _canonical_custom_video_duration(duration)

    if resolution == "1024p" and duration == "10s":
        resolution = "720p"
        context.user_data["custom_video_resolution"] = resolution
        if warn_invalid_combo and update is not None:
            await reply_text_func(
                update.effective_message,
                "⚠️ 检测到非法配置(1024p+10s)，已自动降级为720p+10s。",
            )

    return (
        resolution,
        duration,
        normalize_custom_video_resolution_value(resolution),
        normalize_custom_video_duration_value(duration),
    )


async def get_acceleration_notice(user_id: int, *, quota_manager) -> str:
    stats = await quota_manager.get_user_stats(user_id)
    if stats.get("generation_count", 0) < 2:
        return "\n✨ [新手特权] 前2次生成享受极速排队通道！"
    return ""
