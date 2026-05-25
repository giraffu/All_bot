from src.lora_mapping import (
    decorate_prompt_with_lora_context,
    extract_prompt_lora_context,
    extract_prompt_lora_name,
    resolve_lora_name_from_tag,
)


def test_extract_prompt_lora_name_maps_display_name_to_model_name():
    prompt, lora_name = extract_prompt_lora_name("[模型: BreastGrow] glowing neon city")

    assert prompt == "glowing neon city"
    assert lora_name == "BreastGrow"


def test_extract_prompt_lora_name_maps_legacy_alias_to_model_name():
    prompt, lora_name = extract_prompt_lora_name("[模型: 真实质感] cinematic portrait")

    assert prompt == "cinematic portrait"
    assert lora_name == "qwen/realistic_texture.safetensors"


def test_resolve_lora_name_from_tag_returns_raw_tag_for_unknown_values():
    assert resolve_lora_name_from_tag("custom/community-lora.safetensors") == "custom/community-lora.safetensors"


def test_extract_prompt_lora_context_reads_strength_when_present():
    prompt, lora_name, lora_strength = extract_prompt_lora_context(
        "[模型: qwen/YARN_1.0.safetensors] [强度: 0.35] cinematic portrait"
    )

    assert prompt == "cinematic portrait"
    assert lora_name == "qwen/YARN_1.0.safetensors"
    assert lora_strength == 0.35


def test_decorate_prompt_with_lora_context_writes_strength_and_replaces_existing_tags():
    prompt = decorate_prompt_with_lora_context(
        "[模型: old-model] [强度: 1.00] cinematic portrait",
        lora_name="qwen/YARN_1.0.safetensors",
        lora_strength=0.3,
    )

    assert prompt == "[模型: qwen/YARN_1.0.safetensors] [强度: 0.30] cinematic portrait"
