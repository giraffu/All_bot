import re
from typing import List

from src.handlers.fsm.edit_image_fsm import LORA_MODELS as IMAGE_LORA_MODELS
from src.handlers.fsm.video_lora_fsm import LORA_MODELS as VIDEO_LORA_MODELS

ALL_LORA_MODELS = {**VIDEO_LORA_MODELS, **IMAGE_LORA_MODELS}
REVERSE_LORA_MODELS = {display_name: model_name for model_name, display_name in ALL_LORA_MODELS.items()}

# 历史 prompt 中可能残留手写/旧展示名，这里统一兜底到模型文件名。
REVERSE_LORA_MODELS.update(
    {
        "逼真": "qwen/YARN_1.0.safetensors",
        "菊花+内凹穴": "qwen/adjust_pussy_anus.safetensors",
        "真实质感": "qwen/realistic_texture.safetensors",
        "平胸/无毛穴": "qwen/flat_chest_hairless.safetensors",
        "扶他(阴茎)": "qwen/penis.safetensors",
    }
)


def translate_tags(tags_list: List[str]) -> List[str]:
    """Translate model IDs to human-readable tags based on ALL_LORA_MODELS mapping."""
    translated_tags = []
    for tag in tags_list:
        raw_tag = tag.strip("#")
        if raw_tag in ALL_LORA_MODELS:
            translated_tags.append(f"#{ALL_LORA_MODELS[raw_tag]}")
        else:
            translated_tags.append(tag)
    return translated_tags


def resolve_lora_name_from_tag(tag: str | None) -> str | None:
    if tag is None:
        return None
    normalized_tag = tag.strip()
    if not normalized_tag:
        return None
    return REVERSE_LORA_MODELS.get(normalized_tag, normalized_tag)


def extract_prompt_lora_name(
    prompt: str | None,
) -> tuple[str, str | None]:
    raw_prompt = (prompt or "").strip()
    match = re.search(r"\[模型:\s*(.*?)\]\s*(.*)", raw_prompt, re.DOTALL)
    if not match:
        return raw_prompt, None

    lora_tag = match.group(1).strip()
    clean_prompt = match.group(2).strip()
    return clean_prompt, resolve_lora_name_from_tag(lora_tag)
