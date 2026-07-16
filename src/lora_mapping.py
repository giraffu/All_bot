import re
from typing import Any

from src.lora_catalog import ALL_LORA_MODELS

REVERSE_LORA_MODELS = {
    display_name: model_name for model_name, display_name in ALL_LORA_MODELS.items()
}

MODEL_TAG_PATTERN = re.compile(r"^\[模型:\s*(.*?)\]")
STRENGTH_TAG_PATTERN = re.compile(r"^\[强度:\s*([0-9]*\.?[0-9]+)\]")

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


def translate_tags(tags_list: list[str]) -> list[str]:
    """Translate model IDs to human-readable tags based on the LoRA catalog."""
    translated_tags = []
    for tag in tags_list:
        raw_tag = tag.strip("#")
        if raw_tag in ALL_LORA_MODELS:
            translated_tags.append(f"#{ALL_LORA_MODELS[raw_tag]}")
        elif any(
            marker in raw_tag.lower()
            for marker in ("/", "\\", ".safetensors", ".ckpt", ".pt")
        ):
            translated_tags.append("#附加模型")
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


def _normalize_lora_strength(value: Any) -> float | None:
    if value is None:
        return None
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized >= 0 else None


def extract_prompt_lora_context(
    prompt: str | None,
) -> tuple[str, str | None, float | None]:
    raw_prompt = (prompt or "").strip()
    model_match = MODEL_TAG_PATTERN.match(raw_prompt)
    if not model_match:
        return raw_prompt, None, None

    lora_tag = model_match.group(1).strip()
    clean_prompt = raw_prompt[model_match.end() :].lstrip()
    strength_match = STRENGTH_TAG_PATTERN.match(clean_prompt)
    lora_strength = None
    if strength_match:
        lora_strength = _normalize_lora_strength(strength_match.group(1))
        clean_prompt = clean_prompt[strength_match.end() :].lstrip()

    return clean_prompt, resolve_lora_name_from_tag(lora_tag), lora_strength


def extract_prompt_lora_name(
    prompt: str | None,
) -> tuple[str, str | None]:
    clean_prompt, lora_name, _ = extract_prompt_lora_context(prompt)
    return clean_prompt, lora_name


def decorate_prompt_with_lora_context(
    prompt: str | None,
    *,
    lora_name: str | None,
    lora_strength: Any = None,
) -> str:
    raw_prompt = (prompt or "").strip()
    if not lora_name:
        return raw_prompt

    clean_prompt, _, _ = extract_prompt_lora_context(raw_prompt)
    parts = [f"[模型: {lora_name}]"]
    normalized_strength = _normalize_lora_strength(lora_strength)
    if normalized_strength is not None:
        parts.append(f"[强度: {normalized_strength:.2f}]")
    if clean_prompt:
        parts.append(clean_prompt)
    return " ".join(parts)
