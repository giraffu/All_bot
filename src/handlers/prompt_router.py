from typing import Dict
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
        "menu.cancel",  # 取消
        "menu.exit",  # 退出
        "menu.main_menu",  # 🏠 主菜单
        "menu.back_main",  # 🔙 返回主菜单
        "menu.face_video",  # 🎬 视频换脸
        "menu.i2i_pro",  # 🌟 幻想换脸
        "menu.free_edit",  # 🎨 自由P图
        "menu.video_lora",  # 🎬 图生视频
        "menu.custom_video",  # 🎬 图生视频(兼容入口)
        "menu.ltx_video",  # 🎬 高级图生视频
        # 图片编辑子菜单 FSM 入口
        "menu.photo_edit_undress",
        "menu.photo_edit_faceswap",
        "menu.photo_edit_masturbation",
        "menu.photo_edit_random_faceswap",
        # 视频编辑子菜单 FSM 入口
        "menu.video_edit_missionary",
        "menu.video_edit_doggy",
        "menu.video_edit_blowjob",
        "menu.video_edit_undress_tongue",
        "menu.video_edit_closeup_blowjob",
    ]
    all_keys = registered_keys.union(additional_menu_keys)

    # 遍历所有支持的语种，将翻译结果反向映射回 key
    for lang, translations in locales.items():
        for key in all_keys:
            # Simple nested value getter for the key
            parts = key.split(".")
            curr = translations
            for p in parts:
                if isinstance(curr, dict) and p in curr:
                    curr = curr[p]
                else:
                    curr = None
                    break

            if curr and isinstance(curr, str):
                GLOBAL_REVERSE_MAP[curr] = key

    # 增加硬编码向后兼容映射：支持老用户点击旧键盘的按钮
    hardcoded_backward_map = {
        "🏆 发现/排行榜": "menu.gallery",
        "💰 个人中心": "menu.profile",
        "👤 个人中心": "menu.profile",
        "🎬 懒人动图": "menu.video_edit",
    }
    for old_text, key in hardcoded_backward_map.items():
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
