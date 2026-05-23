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


def get_lora_default_strength(lora_name: str) -> float:
    return IMAGE_LORA_DEFAULT_STRENGTHS.get(lora_name, 1.0)
