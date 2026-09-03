from __future__ import annotations


LTX25_VIDEO_UPSCALE_TASK_TYPE = "ltx25_video_upscale"
LTX25_VIDEO_UPSCALE_COST = 40
LTX25_VIDEO_UPSCALE_DURATION_SECONDS = 5
LTX25_VIDEO_UPSCALE_MAX_SOURCE_DURATION_SECONDS = 5.25
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
        raise ValueError("视频高清化首版只支持 5 秒视频。") from exc
    if duration != LTX25_VIDEO_UPSCALE_DURATION_SECONDS:
        raise ValueError("视频高清化首版只支持 5 秒视频。")
    return duration
