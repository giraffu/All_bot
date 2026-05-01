import json
from typing import Dict, Any

def load_locales() -> Dict[str, Dict[str, Any]]:
    return {
        "zh": {"menu": {"gallery": "🏆 发现/排行榜"}},
        "en": {"menu": {"gallery": "🏆 Gallery"}}
    }

GLOBAL_REVERSE_MAP = {}
locales = load_locales()
all_keys = ["menu.gallery", "menu.missing"]

for lang, translations in locales.items():
    for key in all_keys:
        parts = key.split('.')
        curr = translations
        for p in parts:
            if isinstance(curr, dict) and p in curr:
                curr = curr[p]
            else:
                curr = None
                break
        
        if curr and isinstance(curr, str):
            GLOBAL_REVERSE_MAP[curr] = key

print(GLOBAL_REVERSE_MAP)
