import json
import os
from typing import Any, Dict
from functools import lru_cache

class SafeDict(dict):
    """
    A dictionary that safely falls back to the placeholder if a key is missing.
    Used for safe string formatting.
    """
    def __missing__(self, key: str) -> str:
        return '{' + key + '}'

@lru_cache(maxsize=1)
def load_locales() -> Dict[str, Dict[str, Any]]:
    """Load JSON locales into memory."""
    locales = {}
    base_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'shared', 'locales')
    
    for lang in ['zh', 'en']:
        file_path = os.path.join(base_dir, f"{lang}.json")
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                locales[lang] = json.load(f)
        else:
            locales[lang] = {}
            
    return locales

def _get_nested_value(d: dict, key_path: str) -> Any:
    keys = key_path.split('.')
    current = d
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current

def get_text(key: str, lang: str = 'zh', **kwargs) -> str:
    """
    Get translated text by key and language, with safe formatting.
    
    Args:
        key: The key in the JSON file (e.g., 'system.error_insufficient_credits')
        lang: The language code ('zh', 'en', etc.)
        kwargs: The parameters to format the string
    """
    locales = load_locales()
    
    # Fallback to zh if language not found
    if lang not in locales:
        lang = 'zh'
        
    text = _get_nested_value(locales[lang], key)
    
    # Fallback to zh translation if key is missing in target language
    if text is None and lang != 'zh':
        text = _get_nested_value(locales['zh'], key)
        
    # Fallback to key itself if absolutely not found
    if text is None:
        text = key
        
    # Format the text safely
    if kwargs and isinstance(text, str):
        try:
            return text.format_map(SafeDict(**kwargs))
        except Exception:
            return text
            
    return str(text)

class I18nTranslator:
    def __init__(self, lang: str = 'zh'):
        self.lang = lang
        
    def __call__(self, key: str, **kwargs) -> str:
        return get_text(key, self.lang, **kwargs)
