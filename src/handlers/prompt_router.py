import re

# 定义装饰器与路由表
prompt_routes = {}
GLOBAL_MENU_FILTER = None

def prompt_route(pattern: str, is_regex: bool = False):
    def decorator(func):
        prompt_routes[(pattern, is_regex)] = func
        return func
    return decorator

def build_global_menu_filter():
    """在路由注册完成后的系统启动阶段，统一预编译一次正则对象"""
    global GLOBAL_MENU_FILTER
    # 提取所有精准匹配的菜单文本并转义
    menu_texts = [re.escape(k[0]) for k, v in prompt_routes.items() if not k[1]]
    
    # 补充一些在其他地方可能会作为回退的硬编码菜单项（以防万一）
    additional_menus = ["取消", "退出", "🏠 主菜单", "🔙 返回主菜单", "/checkin", "/queue"]
    for m in additional_menus:
        if re.escape(m) not in menu_texts:
            menu_texts.append(re.escape(m))
            
    exact_pattern = f"^({'|'.join(menu_texts)})$"
    
    # 提取已有的正则表达式
    regex_patterns = [k[0] for k, v in prompt_routes.items() if k[1]]
    
    # 合并为一个大的匹配组
    all_patterns = [exact_pattern] + regex_patterns
    pattern = f"({'|'.join(all_patterns)})"
    
    GLOBAL_MENU_FILTER = re.compile(pattern)

def is_global_menu_command(text: str) -> bool:
    """黑盒化拦截器：供各个 FSM 内部调用，无需暴露底层的正则细节"""
    if not GLOBAL_MENU_FILTER:
        return False
    return bool(GLOBAL_MENU_FILTER.match(text))
