import re
from typing import Dict, Optional
from src.i18n.translator import load_locales

# 定义装饰器与路由表
prompt_routes = {}
GLOBAL_REVERSE_MAP: Dict[str, str] = {}

def prompt_route(i18n_key: str):
    """
    Register a handler for a specific i18n menu key.
    Commands should be registered using CommandHandler in bot_test.py instead.
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
    
    # 提取已注册的菜单 key，以及一些可能未通过装饰器直接注册但在 FSM 中作为回退的 key
    registered_keys = set(prompt_routes.keys())
    
    additional_menu_keys = [
        "menu.cancel",        # 取消
        "menu.exit",          # 退出
        "menu.main_menu",     # 🏠 主菜单
        "menu.back_main"      # 🔙 返回主菜单
    ]
    all_keys = registered_keys.union(additional_menu_keys)
    
    # 遍历所有支持的语种，将翻译结果反向映射回 key
    for lang, translations in locales.items():
        for key in all_keys:
            # Simple nested value getter for the key
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

def is_global_menu_command(text: str) -> bool:
    """黑盒化拦截器：供各个 FSM 内部调用，O(1) 字典查询"""
    if not text:
        return False
        
    # 如果是已被剥离的全局命令，也允许 FSM 安全退出
    if text in ["/checkin", "/queue", "/start", "/cancel", "/maintenance"]:
        return True
        
    return text in GLOBAL_REVERSE_MAP
