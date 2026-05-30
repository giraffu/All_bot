WAN22_VIDEO_V2_RESOLUTION_PRESETS = {
    "fast": {
        "label_zh": "极速",
        "label_en": "Fast",
        "precision_preset": "0.36 MP - Small",
        "cost": 10,
    },
    "standard": {
        "label_zh": "标准",
        "label_en": "Standard",
        "precision_preset": "0.52 MP - SD",
        "cost": 20,
    },
    "hd": {
        "label_zh": "高清",
        "label_en": "HD",
        "precision_preset": "0.65 MP - Balanced",
        "cost": 30,
    },
}

WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET = "standard"


def normalize_wan22_video_v2_resolution_preset(
    resolution_preset: str | None,
) -> str:
    normalized = (resolution_preset or "").strip()
    if normalized in WAN22_VIDEO_V2_RESOLUTION_PRESETS:
        return normalized

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


def get_wan22_video_v2_cost(resolution_preset: str | None) -> int:
    preset_key = normalize_wan22_video_v2_resolution_preset(resolution_preset)
    preset = WAN22_VIDEO_V2_RESOLUTION_PRESETS[preset_key]
    return int(preset["cost"])
