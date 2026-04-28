import os
import re
import json
import subprocess
from collections import defaultdict

ROOT_DIR = "/home/hfy/APP/All_bot"
OUTPUT_FILE = os.path.join(ROOT_DIR, "code_analysis.md")

EXCLUDE_DIRS = {".git", "venv", ".venv", "env", "node_modules", "__pycache__", "dashboard", "migrations"}

def get_python_files():
    py_files = []
    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]
        for file in files:
            if file.endswith(".py"):
                py_files.append(os.path.join(root, file))
    return py_files

def run_command(cmd, cwd=ROOT_DIR):
    try:
        result = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.stdout
    except Exception as e:
        return str(e)

issues_by_file = defaultdict(list)
metrics = {
    "total_files": 0,
    "total_lines": 0,
    "dead_code_lines": 0,
    "avg_complexity": 0.0,
    "duplicated_lines": 0,
}

def add_issue(filepath, line, issue_type, severity, description, suggestion=""):
    rel_path = os.path.relpath(filepath, ROOT_DIR)
    issues_by_file[rel_path].append({
        "line": line,
        "type": issue_type,
        "severity": severity,
        "description": description,
        "suggestion": suggestion
    })

def parse_vulture(py_files):
    # Vulture for dead code
    print("Running vulture...")
    cmd = ["vulture"] + py_files
    output = run_command(cmd)
    for line in output.splitlines():
        # Example format: src/utils.py:10: unused function 'foo' (60% confidence)
        match = re.match(r"^(.*?):(\d+):\s+(.*)$", line)
        if match:
            filepath, line_num, msg = match.groups()
            abs_path = os.path.abspath(os.path.join(ROOT_DIR, filepath))
            add_issue(abs_path, line_num, "死代码 (Dead Code)", "Medium", msg)
            metrics["dead_code_lines"] += 1

def parse_ruff(py_files):
    # Ruff for imports, scope, and general smells
    print("Running ruff...")
    cmd = ["ruff", "check", "--output-format=json"] + py_files
    output = run_command(cmd)
    try:
        data = json.loads(output)
        for item in data:
            filepath = item.get("location", {}).get("row", 1) # Fallback if missing
            row = item["location"]["row"]
            abs_path = item["filename"]
            code = item["code"]
            msg = item["message"]
            
            issue_type = "代码规范 (Linting)"
            severity = "Low"
            if code.startswith("F401"):
                issue_type = "导入问题 (Imports)"
                severity = "Low"
            elif code.startswith("F8"):
                issue_type = "作用域问题 (Scope)"
                severity = "High"
            elif code.startswith("C90"):
                issue_type = "代码坏味道 (Smells)"
                severity = "Medium"
            elif code.startswith("E501"):
                continue # ignore line length
            
            add_issue(abs_path, row, issue_type, severity, f"[{code}] {msg}")
    except Exception as e:
        print("Error parsing ruff:", e)

def parse_radon(py_files):
    print("Running radon...")
    cmd = ["radon", "cc", "-s", "-j"] + py_files
    output = run_command(cmd)
    total_cc = 0
    total_blocks = 0
    try:
        data = json.loads(output)
        for filepath, blocks in data.items():
            if isinstance(blocks, str): continue # Error message
            abs_path = os.path.abspath(os.path.join(ROOT_DIR, filepath))
            for block in blocks:
                cc = block["complexity"]
                total_cc += cc
                total_blocks += 1
                if cc > 10:
                    add_issue(abs_path, block["lineno"], "代码坏味道 (Smells)", "High" if cc > 20 else "Medium", f"圈复杂度过高 (CC={cc}): {block['name']}")
        if total_blocks > 0:
            metrics["avg_complexity"] = total_cc / total_blocks
    except Exception as e:
        print("Error parsing radon:", e)

def parse_bandit(py_files):
    print("Running bandit...")
    cmd = ["bandit", "-q", "-f", "json", "-r"] + py_files
    output = run_command(cmd)
    try:
        # Extract json part if there is any other output
        start = output.find('{')
        if start != -1:
            output = output[start:]
        data = json.loads(output)
        for result in data.get("results", []):
            abs_path = result["filename"]
            line = result["line_number"]
            sev = result["issue_severity"]
            if sev == "HIGH": severity = "Critical"
            elif sev == "MEDIUM": severity = "High"
            else: severity = "Medium"
            
            add_issue(abs_path, line, "安全/性能 (Security/Performance)", severity, result["issue_text"])
    except Exception as e:
        print("Error parsing bandit:", e)

def check_todos_and_comments(py_files):
    print("Checking comments...")
    todo_pattern = re.compile(r"#\s*(TODO|FIXME|XXX)(.*)", re.IGNORECASE)
    for py_file in py_files:
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                metrics["total_lines"] += len(lines)
                for i, line in enumerate(lines):
                    match = todo_pattern.search(line)
                    if match:
                        add_issue(py_file, i+1, "注释清理 (Comments)", "Low", f"发现遗留注释: {match.group(0).strip()}")
        except Exception:
            pass

def check_duplication(py_files):
    print("Checking duplication...")
    cmd = ["pylint", "--disable=all", "--enable=duplicate-code", "--output-format=json"] + py_files
    output = run_command(cmd)
    try:
        if output.strip():
            # pylint might output something before json
            start = output.find('[')
            if start != -1:
                output = output[start:]
            data = json.loads(output)
            for item in data:
                if item.get("symbol") == "duplicate-code":
                    abs_path = item.get("path") or item.get("absolute_path", "unknown")
                    line = item.get("line", 1)
                    msg = item.get("message", "")
                    
                    if abs_path != "unknown":
                        abs_path = os.path.abspath(os.path.join(ROOT_DIR, abs_path))
                    
                    add_issue(abs_path, line, "代码重复 (Duplication)", "Medium", msg)
                    
                    # Extract duplicated lines count
                    m = re.search(r"Similar lines in \d+ files\s*==\n(.*)", msg, re.DOTALL)
                    if m:
                        # just an estimation
                        metrics["duplicated_lines"] += 10
    except Exception as e:
        print("Error parsing pylint:", e)

def analyze_architecture(py_files):
    print("Analyzing architecture...")
    # Basic heuristic check for architecture issues
    for py_file in py_files:
        rel_path = os.path.relpath(py_file, ROOT_DIR)
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Check Core Isolation violation
                if "src/core/" in rel_path:
                    if re.search(r"from telegram import Update|from fastapi import Request", content):
                        suggestion = "重构建议: 将平台相关的对象（如 Update/Request）解析前置到 Handler/Router 层，Core 层应只接收基础数据类型或内部模型（如 internal_user_id）。"
                        add_issue(py_file, 1, "架构问题 (Architecture)", "Critical", "核心层 (Core) 引入了平台相关对象 (Update/Request)，违反依赖倒置和核心隔离原则。", suggestion)
                
                # Check DB transactions in Routers
                if "routers/" in rel_path or "handlers/" in rel_path:
                    if "refund_credits" in content and "rollback" in content:
                        suggestion = "重构建议: 避免在使用依赖注入的 Session 时手动进行退款和回滚，推荐使用 Unit of Work 模式，由外层统一管理事务。"
                        add_issue(py_file, 1, "架构问题 (Architecture)", "High", "Router/Handler 层存在手动事务控制和退款逻辑，可能导致重复退款漏洞。", suggestion)
        except Exception:
            pass

def generate_report():
    print("Generating report...")
    py_files = get_python_files()
    metrics["total_files"] = len(py_files)
    
    parse_vulture(py_files)
    parse_ruff(py_files)
    parse_radon(py_files)
    parse_bandit(py_files)
    check_todos_and_comments(py_files)
    check_duplication(py_files)
    analyze_architecture(py_files)
    
    total_lines = metrics["total_lines"] or 1
    dup_rate = (metrics["duplicated_lines"] / total_lines) * 100
    dead_rate = (metrics["dead_code_lines"] / total_lines) * 100
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("# 代码全面静态分析与质量评估报告\n\n")
        f.write("## 1. 总体可量化指标\n\n")
        f.write(f"- **总分析文件数**: {metrics['total_files']}\n")
        f.write(f"- **总代码行数 (预估)**: {total_lines}\n")
        f.write(f"- **死代码比例**: {dead_rate:.2f}% ({metrics['dead_code_lines']} 个潜在问题点)\n")
        f.write(f"- **代码重复率 (预估)**: {dup_rate:.2f}%\n")
        f.write(f"- **平均圈复杂度 (CC)**: {metrics['avg_complexity']:.2f}\n\n")
        
        f.write("## 2. 详细文件分析\n\n")
        
        # Sort files by path
        sorted_files = sorted(issues_by_file.keys())
        for rel_path in sorted_files:
            issues = issues_by_file[rel_path]
            # Sort issues by severity priority
            severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
            issues.sort(key=lambda x: (severity_order.get(x["severity"], 4), int(x["line"])))
            
            f.write(f"### 文件: `{rel_path}`\n\n")
            f.write("| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |\n")
            f.write("|---|---|---|---|---|\n")
            for issue in issues:
                sugg = issue["suggestion"] or "-"
                f.write(f"| {issue['line']} | {issue['severity']} | {issue['type']} | {issue['description']} | {sugg} |\n")
            f.write("\n")
            
        f.write("## 3. 架构优化与重构总结\n\n")
        f.write("基于核心层的架构规则，以下是针对系统中常见架构问题的通用重构建议：\n\n")
        f.write("- **核心层隔离 (Core Isolation)**: 绝对禁止在 `src/core/` 目录中引入特定平台的上下文对象（如 Telegram 的 `Update` 或 FastAPI 的 `Request`）。应使用 `internal_user_id` 等内部模型进行流转。\n")
        f.write("- **事务管理与退款逻辑 (Transaction & Refund)**: 在外层路由和 Handler 中，避免在捕获异常后手动调用 `refund_credits` 等补偿机制。应统一依赖 Unit of Work (UoW) 进行 `rollback` 和数据状态的一致性保障，防止重复退款。\n")
        f.write("- **任务与并发控制 (Task Engine & Pub/Sub)**: 后端接口应避免循环轮询任务状态，建议使用 Redis Pub/Sub (`comfy:task_events:{task_id}`) 实现状态的实时触达；任务分发时，必须确保客户端提前生成 `task_id`，防止并发导致的时序问题。\n")
        f.write("- **避免过度耦合**: 识别模块之间互相引用的部分（循环依赖），通过提取公共接口（Interface）或引入事件总线（Event Bus）来解耦。\n")

if __name__ == "__main__":
    generate_report()
    print(f"Report generated at {OUTPUT_FILE}")
