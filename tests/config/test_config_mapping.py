from src.lora_mapping import extract_prompt_lora_name, resolve_lora_name_from_tag


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
