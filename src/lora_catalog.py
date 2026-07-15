import math


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

LTX_VIDEO_LORA_OPTIONS = {
    "none": {
        "path": "",
        "label_zh": "无",
        "label_en": "None",
        "default_strength": None,
    },
    "reasoning": {
        "path": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
        "label_zh": "运动逻辑优化",
        "label_en": "Reasoning Motion",
        "default_strength": 0.8,
    },
    "dr34ml4y": {
        "path": "ltx2.3/DR34ML4Y_LTXXX_PREVIEW_RC1.safetensors",
        "label_zh": "全能姿势",
        "label_en": "All-round Poses",
        "default_strength": 0.6,
    },
    "synth_pussy": {
        "path": "ltx2.3/SynthPussy_01_rank32.safetensors",
        "label_zh": "私处细节",
        "label_en": "Pussy Details",
        "default_strength": 0.8,
    },
    "titfuck": {
        "path": "ltx2.3/LTX2.3TITFUCKE2000.safetensors",
        "label_zh": "乳交",
        "label_en": "Titfuck",
        "default_strength": 1.0,
    },
    "deepthroat": {
        "path": "ltx2.3/ltxdeepthroat_v01.safetensors",
        "label_zh": "深喉/口交",
        "label_en": "Deepthroat",
        "default_strength": 1.0,
    },
    "penile_praxis": {
        "path": "ltx2.3/penile-praxis-general-nsfw-ltx-2-t2v-i2v.safetensors",
        "label_zh": "男根/多姿势",
        "label_en": "Penile Praxis",
        "default_strength": 1.0,
    },
    "pussyjob": {
        "path": "ltx2.3/pussyjob_v1.1_merged_ltx23.safetensors",
        "label_zh": "外阴摩擦",
        "label_en": "Pussyjob",
        "default_strength": 0.8,
    },
    "stomach_bulge": {
        "path": "ltx2.3/st0mach_bulge_ltx23_v1.1.safetensors",
        "label_zh": "腹部鼓起",
        "label_en": "Stomach Bulge",
        "default_strength": 0.8,
    },
    "sfbehind": {
        "path": "ltx2.3/sfbehind_LTX2_3_v0_1.safetensors",
        "label_zh": "后入",
        "label_en": "Rear View",
        "default_strength": 1.0,
    },
    "anal_insertion": {
        "path": "ltx2.3/nsfw_anal_insertion_ltx23_v1.0.safetensors",
        "label_zh": "肛交插入",
        "label_en": "Anal Insertion",
        "default_strength": 0.8,
    },
}

LTX_VIDEO_LORA_MODELS = {
    option["path"]: option["label_zh"]
    for option in LTX_VIDEO_LORA_OPTIONS.values()
}

LTX_VIDEO_LORA_LABELS_EN = {
    option["path"]: option["label_en"]
    for option in LTX_VIDEO_LORA_OPTIONS.values()
}

LTX_VIDEO_LORA_DEFAULT_STRENGTHS = {
    option["path"]: option["default_strength"]
    for option in LTX_VIDEO_LORA_OPTIONS.values()
    if option["path"] and option["default_strength"] is not None
}

LTX_VIDEO_LORA_CALLBACK_CHOICES = {
    option_id: option["path"] for option_id, option in LTX_VIDEO_LORA_OPTIONS.items()
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


def get_ltx_video_lora_display_name(lora_name: str, lang: str = "zh") -> str:
    normalized_name = resolve_ltx_video_lora_name(lora_name)
    if lang == "en":
        return LTX_VIDEO_LORA_LABELS_EN.get(normalized_name, normalized_name or "None")
    return LTX_VIDEO_LORA_MODELS.get(normalized_name, normalized_name or "无")


def get_lora_default_strength(lora_name: str) -> float:
    return IMAGE_LORA_DEFAULT_STRENGTHS.get(lora_name, 1.0)


def get_ltx_video_lora_default_strength(lora_name: str) -> float:
    normalized_name = resolve_ltx_video_lora_name(lora_name)
    return LTX_VIDEO_LORA_DEFAULT_STRENGTHS.get(normalized_name, 1.0)


def build_ltx_video_lora_item(
    lora_name: str | None,
    *,
    strength: float | None = None,
) -> dict[str, float | str] | None:
    normalized_name = resolve_ltx_video_lora_name(lora_name)
    if not normalized_name:
        return None
    default_strength = get_ltx_video_lora_default_strength(normalized_name)
    try:
        resolved_strength = default_strength if strength is None else float(strength)
    except (TypeError, ValueError):
        resolved_strength = default_strength
    if not math.isfinite(resolved_strength):
        resolved_strength = default_strength
    resolved_strength = round(round(min(2.0, max(0.1, resolved_strength)) * 20) / 20, 2)
    return {
        "name": normalized_name,
        "strength": float(resolved_strength),
    }


def normalize_ltx_video_lora_items(
    lora_items: list[dict[str, object]] | None,
    *,
    max_items: int | None = None,
) -> list[dict[str, float | str]]:
    normalized_items: list[dict[str, float | str]] = []
    seen_names: set[str] = set()
    for raw_item in lora_items or []:
        if not isinstance(raw_item, dict):
            continue
        item = build_ltx_video_lora_item(
            raw_item.get("name"),
            strength=raw_item.get("strength"),  # type: ignore[arg-type]
        )
        if not item:
            continue
        item_name = str(item["name"])
        if item_name in seen_names:
            continue
        seen_names.add(item_name)
        normalized_items.append(item)
        if max_items is not None and len(normalized_items) >= max_items:
            break
    return normalized_items


def resolve_ltx_video_lora_name(alias_or_name: str | None) -> str:
    normalized_name = (alias_or_name or "").strip()
    if not normalized_name:
        return ""
    return LTX_VIDEO_LORA_CALLBACK_CHOICES.get(normalized_name, normalized_name)
