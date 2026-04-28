from langchain_core.tools import tool


@tool
def get_system_time() -> str:
    """获取当前的系统时间"""
    from datetime import datetime
    return f"当前时间是: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

def get_tools():
    """返回此技能提供的所有工具"""
    return [get_system_time]
