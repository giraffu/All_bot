from typing import List

from src.handlers.fsm.edit_image_fsm import LORA_MODELS as IMAGE_LORA_MODELS
from src.handlers.fsm.video_lora_fsm import LORA_MODELS as VIDEO_LORA_MODELS

ALL_LORA_MODELS = {**VIDEO_LORA_MODELS, **IMAGE_LORA_MODELS}

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
