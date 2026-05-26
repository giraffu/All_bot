IMAGE_LORA_MODELS = {
    "": "无",
    "qwen/YARN_1.0.safetensors": "逼真",
    "qwen/adjust_pussy_anus.safetensors": "菊花+内凹穴",
    "qwen/realistic_texture.safetensors": "真实质感",
    "qwen/flat_chest_hairless.safetensors": "平胸/无毛穴",
    "qwen/penis.safetensors": "扶他(阴茎)",
}

VIDEO_LORA_MODELS = {
    "": "无",
    "BreastGrow": "巨乳膨胀",
    "BreastInsertion": "乳交",
    "Cum": "颜射",
    "Cunilingus": "舔阴",
    "Flatchested": "平胸",
    "Footjob": "足交",
    "Insertion": "插入优化",
}

IMAGE_LORA_DEFAULT_STRENGTHS = {
    "qwen/YARN_1.0.safetensors": 0.3,
    "qwen/flat_chest_hairless.safetensors": 0.8,
    "qwen/penis.safetensors": 0.7,
    "qwen/realistic_texture.safetensors": 0.8,
}

ALL_LORA_MODELS = {**VIDEO_LORA_MODELS, **IMAGE_LORA_MODELS}

IMAGE_LORA_LABELS_EN = {
    "": "None",
    "qwen/YARN_1.0.safetensors": "Realistic",
    "qwen/adjust_pussy_anus.safetensors": "Pussy + Inner Anus",
    "qwen/realistic_texture.safetensors": "Realistic Texture",
    "qwen/flat_chest_hairless.safetensors": "Flat Chest / Hairless",
    "qwen/penis.safetensors": "Futanari (Penis)",
}

VIDEO_LORA_LABELS_EN = {
    "": "None",
    "BreastGrow": "Breast Growth",
    "BreastInsertion": "Breast Insertion",
    "Cum": "Cumshot",
    "Cunilingus": "Cunnilingus",
    "Flatchested": "Flat Chest",
    "Footjob": "Footjob",
    "Insertion": "Insertion Boost",
}


def get_image_lora_display_name(lora_name: str, lang: str = "zh") -> str:
    normalized_name = lora_name or ""
    if lang == "en":
        return IMAGE_LORA_LABELS_EN.get(normalized_name, normalized_name or "None")
    return IMAGE_LORA_MODELS.get(normalized_name, normalized_name or "无")


def get_video_lora_display_name(lora_name: str, lang: str = "zh") -> str:
    normalized_name = lora_name or ""
    if lang == "en":
        return VIDEO_LORA_LABELS_EN.get(normalized_name, normalized_name or "None")
    return VIDEO_LORA_MODELS.get(normalized_name, normalized_name or "无")


def get_lora_default_strength(lora_name: str) -> float:
    return IMAGE_LORA_DEFAULT_STRENGTHS.get(lora_name, 1.0)
