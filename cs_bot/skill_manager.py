import os
import glob
import importlib.util
import inspect
from typing import List, Callable
from langchain_core.tools import tool

class SkillManager:
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = skills_dir
        self.prompts: List[str] = []
        self.tools: List[Callable] = []

    def load_skills(self):
        """
        动态加载所有 skill。
        每个 skill 可以是一个包含 prompt.md 和 tools 的独立模块，
        或者简单点：读取 skills/ 目录下的所有 .md 文件作为 prompt 知识库，
        并加载 skills/ 目录下的 python 文件中的 tools。
        """
        self.prompts = []
        self.tools = []

        # 1. 动态加载所有的 .md 文件作为知识库 (Prompts)
        md_files = glob.glob(os.path.join(self.skills_dir, "*.md"))
        for md_file in md_files:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    # 获取文件名作为知识模块的标题
                    base_name = os.path.basename(md_file).replace(".md", "")
                    self.prompts.append(f"--- [知识库: {base_name}] ---\n{content}\n")
                    
        # 2. 动态加载所有的 python tool
        # 为了方便扩展，我们约定所有的 tool 都写在 skills/ 目录下的 .py 文件里，
        # 并且可以通过一个约定的函数 get_tools() 导出，或者直接扫描带有 @tool 装饰器的函数
        
        py_files = glob.glob(os.path.join(self.skills_dir, "*.py"))
        for py_file in py_files:
            if os.path.basename(py_file).startswith("__"):
                continue
            
            module_name = os.path.basename(py_file).replace(".py", "")
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # 如果模块定义了 get_tools() 函数，则调用它获取 tools
                if hasattr(module, "get_tools") and callable(module.get_tools):
                    module_tools = module.get_tools()
                    if isinstance(module_tools, list):
                        self.tools.extend(module_tools)

    def get_combined_prompt(self) -> str:
        """
        将所有动态加载的知识库合并成一个完整的 System Prompt
        """
        return "\n\n".join(self.prompts)

    def get_all_tools(self) -> List[Callable]:
        """
        返回所有动态加载的工具列表
        """
        return self.tools

# 单例模式，供全局使用
skill_manager = SkillManager()
