#!/usr/bin/env python3
"""
文档质量检查机制 (Document Quality Checker)
该脚本用于扫描 docs/ 目录下的所有子模块文档，确保其满足标准化技术规范要求。
检查项：
1. 包含必须的 H2 章节标题（目标与范围、架构图、核心代码、接口定义、测试要求、部署回滚、监控规则）。
2. 包含至少一个 Mermaid 图表 (```mermaid)。
3. 包含代码片段的 Markdown 行号链接。
"""

import os
import re
import sys

DOCS_DIR = os.path.join(os.path.dirname(__file__), '..', 'docs')

REQUIRED_SECTIONS = [
    r"## 1\. 目标与范围",
    r"## 2\. 架构图.*",
    r"## 3\. 核心代码片段",
    r"## 4\. 接口定义",
    r"## 5\. 单元与集成测试要求",
    r"## 6\. 部署与回滚步骤",
    r"## 7\. 监控告警规则.*"
]

def check_file(filepath: str) -> list[str]:
    errors = []
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Check sections
    for section_regex in REQUIRED_SECTIONS:
        if not re.search(section_regex, content):
            errors.append(f"Missing required section matching: '{section_regex}'")

    # 2. Check for Mermaid diagrams
    if "```mermaid" not in content:
        errors.append("Missing at least one Mermaid diagram block (```mermaid).")

    # 3. Check for Code Reference link
    if not re.search(r"\[.+\]\(file://.*#L\d+", content):
        errors.append("Missing code reference link with line numbers (e.g. [file.py](file:///path#L123)).")

    return errors

def main():
    if not os.path.exists(DOCS_DIR):
        print(f"Error: Docs directory {DOCS_DIR} not found.")
        sys.exit(1)

    files_checked = 0
    files_with_errors = 0

    for filename in os.listdir(DOCS_DIR):
        if filename.startswith("子模块_") and filename.endswith(".md"):
            filepath = os.path.join(DOCS_DIR, filename)
            files_checked += 1
            errors = check_file(filepath)
            
            if errors:
                files_with_errors += 1
                print(f"\n[FAIL] {filename}")
                for err in errors:
                    print(f"  - {err}")
            else:
                print(f"[PASS] {filename}")

    print("\n" + "="*40)
    print(f"Quality Check Summary: Checked {files_checked} files.")
    if files_with_errors > 0:
        print(f"Result: {files_with_errors} files failed the quality check.")
        sys.exit(1)
    else:
        print("Result: All sub-module documents passed the quality check! 🎉")
        sys.exit(0)

if __name__ == "__main__":
    main()
