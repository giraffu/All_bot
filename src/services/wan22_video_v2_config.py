WAN22_VIDEO_V2_RESOLUTION_PRESETS = {
    "preview": {
        "label_zh": "极速",
        "label_en": "Fast",
        "precision_preset": "0.26 MP - Preview",
        "approx_resolution": "512p",
        "cost": 6,
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
    "0.36 MP - Small": "preview",
    "512": "preview",
    "512p": "preview",
    "720": "standard",
    "720p": "standard",
    "1024": "hd",
    "1024p": "hd",
}

WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET = "preview"

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

WAN22_CHAIN_HISTORY_TASK_TYPES = frozenset(
    {"wan22_video_v2", "custom_video", "video_lora"}
)


def is_wan22_chain_history_task_type(task_type: str | None) -> bool:
    return bool(task_type and task_type in WAN22_CHAIN_HISTORY_TASK_TYPES)


def normalize_wan22_video_v2_resolution_preset(
    resolution_preset: str | None,
) -> str:
    normalized = (resolution_preset or "").strip()
    if normalized in WAN22_VIDEO_V2_RESOLUTION_PRESETS:
        return normalized
    if normalized in WAN22_VIDEO_V2_LEGACY_RESOLUTION_ALIASES:
        return WAN22_VIDEO_V2_LEGACY_RESOLUTION_ALIASES[normalized]

    for preset_key, preset in WAN22_VIDEO_V2_RESOLUTION_PRESETS.items():
        if normalized == preset["precision_preset"]:
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


def get_wan22_video_v2_cost(resolution_preset: str | None) -> int:
    preset_key = normalize_wan22_video_v2_resolution_preset(resolution_preset)
    preset = WAN22_VIDEO_V2_RESOLUTION_PRESETS[preset_key]
    return int(preset["cost"])


def resolve_wan22_model_profile(profile_name: str | None) -> dict[str, str]:
    normalized = str(profile_name or "").strip()
    return WAN22_MODEL_PROFILES.get(
        normalized,
        WAN22_MODEL_PROFILES[WAN22_VIDEO_V2_MODEL_PROFILE],
    )
