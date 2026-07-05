from typing import Dict

from src.handlers import menu_route_registry
from src.i18n.translator import load_locales

# 定义装饰器与路由表
prompt_routes = {}
GLOBAL_REVERSE_MAP: Dict[str, str] = {}


def _get_nested_translation_value(translations: dict, key: str):
    parts = key.split(".")
    curr = translations
    for p in parts:
        if isinstance(curr, dict) and p in curr:
            curr = curr[p]
        else:
            return None
    return curr


def prompt_route(i18n_key: str):
    """
    Register a handler for a specific i18n menu key.
    Commands should be registered using CommandHandler in bot_main.py instead.
    """

    def decorator(func):
        prompt_routes[i18n_key] = func
        return func

    return decorator


def build_global_menu_filter():
    """在系统启动阶段构建 O(1) 的多语言反向路由字典"""
    global GLOBAL_REVERSE_MAP
    GLOBAL_REVERSE_MAP.clear()

    locales = load_locales()
    all_keys = menu_route_registry.build_global_reverse_route_keys(
        prompt_routes.keys()
    )

    # 遍历所有支持的语种，将翻译结果反向映射回 key
    for lang, translations in locales.items():
        for key in all_keys:
            curr = _get_nested_translation_value(translations, key)
            if curr and isinstance(curr, str):
                GLOBAL_REVERSE_MAP[curr] = key

    for translations in locales.values():
        for translation_key, route_key in menu_route_registry.SPECIAL_TRANSLATION_ROUTES:
            text = _get_nested_translation_value(translations, translation_key)
            if text and isinstance(text, str):
                GLOBAL_REVERSE_MAP[text] = route_key

    for old_text, key in menu_route_registry.LEGACY_TEXT_ALIASES.items():
        if old_text not in GLOBAL_REVERSE_MAP:
            GLOBAL_REVERSE_MAP[old_text] = key


def is_global_menu_command(text: str) -> bool:
    """黑盒化拦截器：供各个 FSM 内部调用，O(1) 字典查询"""
    if not text:
        return False

    # 如果是已被剥离的全局命令，也允许 FSM 安全退出
    if text.split(" ")[0] in [
        "/checkin",
        "/queue",
        "/start",
        "/cancel",
        "/maintenance",
    ]:
        return True

    return text in GLOBAL_REVERSE_MAP
