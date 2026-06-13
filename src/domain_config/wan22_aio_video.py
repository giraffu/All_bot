from dataclasses import dataclass, field
from typing import Any, Mapping

from src.constants import (
    MODE_CUSTOM_VIDEO,
    MODE_IMAGE_TO_VIDEO,
    MODE_IMAGE_TO_VIDEO_LITERAL,
    MODE_WAN22_VIDEO_V2,
)

WAN22_AIO_EXECUTION_IMAGE_TO_VIDEO = "image_to_video"
WAN22_AIO_EXECUTION_WAN22_VIDEO_V2 = MODE_WAN22_VIDEO_V2

WAN22_VIDEO_V2_RESOLUTION_PRESETS = {
    "preview": {
        "label_zh": "极速",
        "label_en": "Fast",
        "precision_preset": "0.26 MP - Preview",
        "approx_resolution": "512p",
        "cost": 6,
    },
    "small": {
        "label_zh": "清晰",
        "label_en": "Small",
        "precision_preset": "0.36 MP - Small",
        "approx_resolution": "600p",
        "cost": 12,
    },
    "standard": {
        "label_zh": "标准",
        "label_en": "Standard",
        "precision_preset": "0.52 MP - SD",
        "approx_resolution": "720p",
        "cost": 20,
    },
    "hd": {
        "label_zh": "高清",
        "label_en": "HD",
        "precision_preset": "0.65 MP - Balanced",
        "approx_resolution": "810p",
        "cost": 30,
    },
}

WAN22_VIDEO_V2_LEGACY_RESOLUTION_ALIASES = {
    "fast": "preview",
    "512": "preview",
    "512p": "preview",
    "600": "small",
    "600p": "small",
    "720": "standard",
    "720p": "standard",
    "1024": "hd",
    "1024p": "hd",
}

WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET = "preview"
WAN22_VIDEO_V2_DEFAULT_DURATION_SECONDS = 5
WAN22_VIDEO_V2_DURATION_SECONDS = (5, 8, 10)
WAN22_VIDEO_V2_FRAME_COUNT_BY_DURATION = {
    5: 81,
    8: 129,
    10: 161,
}
WAN22_VIDEO_V2_DURATION_COST_MULTIPLIERS = {
    5: 1.0,
    8: 2.0,
    10: 3.0,
}

WAN22_VIDEO_V2_MODEL_PROFILE = "wan22_video_v2"
WAN22_LEGACY_IMAGE_TO_VIDEO_MODEL_PROFILE = "legacy_image_to_video"

WAN22_MODEL_PROFILES = {
    WAN22_VIDEO_V2_MODEL_PROFILE: {
        "high": "DasiwaWAN22I2V14BLightspeed_snatchkissHighV11.safetensors",
        "low": "DasiwaWAN22I2V14BLightspeed_snatchkissLowV11.safetensors",
    },
    WAN22_LEGACY_IMAGE_TO_VIDEO_MODEL_PROFILE: {
        "high": "wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8H.safetensors",
        "low": "wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8L.safetensors",
    },
}

DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT = (
    "censored, mosaic censoring, bar censor, pixelated, glowing, bloom, blurry, "
    "out of focus, low detail, bad anatomy, ugly, overexposed, underexposed, "
    "distorted face, extra limbs, cartoonish, 3d render artifacts, duplicate "
    "people, unnatural lighting, bad composition, missing shadows, low "
    "resolution, poorly textured, glitch, noise, grain, static, motionless, "
    "still frame, stylized, artwork, painting, illustration, many people in "
    "background, three legs, walking backward, unnatural skin tone, discolored "
    "eyelid, red eyelids, closed eyes, poorly drawn hands, extra fingers, fused "
    "fingers, poorly drawn face, deformed, disfigured, malformed limbs, fog, "
    "mist, voluminous eyelashes,"
)


@dataclass(frozen=True)
class Wan22AioVideoProfile:
    name: str
    public_task_types: tuple[str, ...]
    execution_task_type: str
    model_profile: str
    allow_lora: bool
    output_task_prefix: str
    default_duration_seconds: int = WAN22_VIDEO_V2_DEFAULT_DURATION_SECONDS
    resolution_presets: Mapping[str, Mapping[str, Any]] = field(
        default_factory=lambda: WAN22_VIDEO_V2_RESOLUTION_PRESETS
    )

    def owns_public_task_type(self, task_type: str | None) -> bool:
        return bool(task_type and task_type in self.public_task_types)


WAN22_AIO_VIDEO_PROFILES = {
    WAN22_LEGACY_IMAGE_TO_VIDEO_MODEL_PROFILE: Wan22AioVideoProfile(
        name=WAN22_LEGACY_IMAGE_TO_VIDEO_MODEL_PROFILE,
        public_task_types=(
            MODE_CUSTOM_VIDEO,
            MODE_IMAGE_TO_VIDEO,
            MODE_IMAGE_TO_VIDEO_LITERAL,
        ),
        execution_task_type=WAN22_AIO_EXECUTION_IMAGE_TO_VIDEO,
        model_profile=WAN22_LEGACY_IMAGE_TO_VIDEO_MODEL_PROFILE,
        allow_lora=True,
        output_task_prefix=WAN22_AIO_EXECUTION_IMAGE_TO_VIDEO,
    ),
    WAN22_VIDEO_V2_MODEL_PROFILE: Wan22AioVideoProfile(
        name=WAN22_VIDEO_V2_MODEL_PROFILE,
        public_task_types=(MODE_WAN22_VIDEO_V2,),
        execution_task_type=WAN22_AIO_EXECUTION_WAN22_VIDEO_V2,
        model_profile=WAN22_VIDEO_V2_MODEL_PROFILE,
        allow_lora=False,
        output_task_prefix=MODE_WAN22_VIDEO_V2,
    ),
}

WAN22_CHAIN_HISTORY_TASK_TYPES = frozenset(
    task_type
    for profile in WAN22_AIO_VIDEO_PROFILES.values()
    for task_type in profile.public_task_types
)


def is_wan22_chain_history_task_type(task_type: str | None) -> bool:
    return bool(task_type and task_type in WAN22_CHAIN_HISTORY_TASK_TYPES)


def normalize_wan22_video_v2_resolution_preset(
    resolution_preset: str | None,
) -> str:
    normalized = (resolution_preset or "").strip()
    normalized_lower = normalized.lower()
    if normalized in WAN22_VIDEO_V2_RESOLUTION_PRESETS:
        return normalized
    for preset_key in WAN22_VIDEO_V2_RESOLUTION_PRESETS:
        if normalized_lower == preset_key.lower():
            return preset_key
    for alias, preset_key in WAN22_VIDEO_V2_LEGACY_RESOLUTION_ALIASES.items():
        if normalized_lower == alias.lower():
            return preset_key

    for preset_key, preset in WAN22_VIDEO_V2_RESOLUTION_PRESETS.items():
        if normalized_lower == str(preset["precision_preset"]).lower():
            return preset_key

    return WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET


def get_wan22_video_v2_resolution_label(
    resolution_preset: str | None,
    *,
    lang: str = "zh",
) -> str:
    preset_key = normalize_wan22_video_v2_resolution_preset(resolution_preset)
    preset = WAN22_VIDEO_V2_RESOLUTION_PRESETS[preset_key]
    return preset["label_en"] if lang == "en" else preset["label_zh"]


def get_wan22_video_v2_resolution_display(
    resolution_preset: str | None,
    *,
    lang: str = "zh",
) -> str:
    preset_key = normalize_wan22_video_v2_resolution_preset(resolution_preset)
    preset = WAN22_VIDEO_V2_RESOLUTION_PRESETS[preset_key]
    label = preset["label_en"] if lang == "en" else preset["label_zh"]
    approx_resolution = preset["approx_resolution"]
    if lang == "en":
        return f"{label} (approx. {approx_resolution})"
    return f"{label}（约 {approx_resolution}）"


def normalize_wan22_video_v2_duration_seconds(duration: Any) -> int:
    text = str(duration or "").strip().lower()
    if text.endswith("s"):
        text = text[:-1]
    try:
        seconds = int(text)
    except (TypeError, ValueError):
        return WAN22_VIDEO_V2_DEFAULT_DURATION_SECONDS
    if seconds in WAN22_VIDEO_V2_DURATION_SECONDS:
        return seconds
    return WAN22_VIDEO_V2_DEFAULT_DURATION_SECONDS


def get_wan22_video_v2_duration_label(
    duration: Any,
    *,
    lang: str = "zh",
) -> str:
    seconds = normalize_wan22_video_v2_duration_seconds(duration)
    return f"{seconds}s" if lang == "en" else f"{seconds} 秒"


def get_wan22_video_v2_duration_multiplier_label(duration: Any) -> str:
    seconds = normalize_wan22_video_v2_duration_seconds(duration)
    multiplier = WAN22_VIDEO_V2_DURATION_COST_MULTIPLIERS[seconds]
    return f"*{float(multiplier):g}"


def get_wan22_video_v2_frame_count(duration: Any) -> int:
    seconds = normalize_wan22_video_v2_duration_seconds(duration)
    return WAN22_VIDEO_V2_FRAME_COUNT_BY_DURATION[seconds]


def get_wan22_video_v2_cost(
    resolution_preset: str | None,
    duration: Any = None,
) -> int:
    preset_key = normalize_wan22_video_v2_resolution_preset(resolution_preset)
    preset = WAN22_VIDEO_V2_RESOLUTION_PRESETS[preset_key]
    duration_seconds = normalize_wan22_video_v2_duration_seconds(duration)
    multiplier = WAN22_VIDEO_V2_DURATION_COST_MULTIPLIERS[duration_seconds]
    return int(round(float(preset["cost"]) * multiplier))


def resolve_wan22_model_profile(profile_name: str | None) -> dict[str, str]:
    normalized = str(profile_name or "").strip()
    return WAN22_MODEL_PROFILES.get(
        normalized,
        WAN22_MODEL_PROFILES[WAN22_VIDEO_V2_MODEL_PROFILE],
    )


def resolve_wan22_aio_video_profile(
    profile_or_task_type: str | None,
) -> Wan22AioVideoProfile:
    normalized = str(profile_or_task_type or "").strip()
    if normalized in WAN22_AIO_VIDEO_PROFILES:
        return WAN22_AIO_VIDEO_PROFILES[normalized]
    for profile in WAN22_AIO_VIDEO_PROFILES.values():
        if profile.owns_public_task_type(normalized):
            return profile
    return WAN22_AIO_VIDEO_PROFILES[WAN22_VIDEO_V2_MODEL_PROFILE]


def normalize_wan22_video_v2_negative_prompt(negative_prompt: str | None) -> str:
    normalized = (negative_prompt or "").strip()
    return normalized or DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT


def normalize_wan22_video_v2_chain_task_ids(chain_task_ids: Any) -> list[str]:
    if not isinstance(chain_task_ids, (list, tuple)):
        return []
    normalized: list[str] = []
    for value in chain_task_ids:
        task_id = str(value or "").strip()
        if task_id:
            normalized.append(task_id)
    return normalized


def build_wan22_aio_video_result_meta(
    *,
    profile: Wan22AioVideoProfile | str | None,
    resolution_preset: str | None,
    negative_prompt: str | None,
    use_end_frame: bool,
    duration_seconds: Any = None,
    prev_task_id: str | None = None,
    chain_task_ids: Any = None,
    lora_name: str | None = None,
    lora_strength: float | None = None,
) -> dict[str, Any]:
    resolved_profile = (
        resolve_wan22_aio_video_profile(profile)
        if not isinstance(profile, Wan22AioVideoProfile)
        else profile
    )
    meta: dict[str, Any] = {
        "wan22_resolution_preset": normalize_wan22_video_v2_resolution_preset(
            resolution_preset
        ),
        "wan22_duration_seconds": normalize_wan22_video_v2_duration_seconds(
            duration_seconds
        ),
        "wan22_negative_prompt": normalize_wan22_video_v2_negative_prompt(
            negative_prompt
        ),
        "wan22_use_end_frame": bool(use_end_frame),
        "wan22_model_profile": resolved_profile.model_profile,
        "wan22_chain_task_ids": normalize_wan22_video_v2_chain_task_ids(
            chain_task_ids
        ),
    }
    prev_task_id = str(prev_task_id or "").strip()
    if prev_task_id:
        meta["wan22_prev_task_id"] = prev_task_id

    if resolved_profile.allow_lora:
        normalized_lora_name = str(lora_name or "").strip()
        if normalized_lora_name:
            meta["lora_name"] = normalized_lora_name
            meta["lora_strength"] = lora_strength

    return meta
