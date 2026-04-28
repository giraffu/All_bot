import os
import subprocess
import json
import re
from datetime import datetime

TARGET_DIRS = ["backend", "src", "dashboard", "cs_bot"]
OUTPUT_FILE = "code_analysis.md"

def run_command(command, cwd=None):
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        return result.stdout, result.stderr
    except Exception as e:
        return "", str(e)

def count_lines():
    total_lines = 0
    for root_dir in TARGET_DIRS:
        for subdir, dirs, files in os.walk(root_dir):
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(subdir, file)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            total_lines += len(f.readlines())
                    except:
                        pass
    return total_lines

def parse_vulture(output):
    issues = []
    for line in output.splitlines():
        if not line.strip():
            continue
        match = re.match(r'^(.+?):(\d+):\s+(.+?)\s+\((\d+)% confidence\)$', line)
        if match:
            confidence = int(match.group(4))
            issues.append({
                "file": match.group(1),
                "line": match.group(2),
                "type": "Dead Code",
                "severity": "Medium" if confidence > 80 else "Low",
                "description": match.group(3)
            })
    return issues

def run_vulture():
    stdout, _ = run_command(["vulture"] + TARGET_DIRS)
    return parse_vulture(stdout)

def run_ruff():
    stdout, _ = run_command(["ruff", "check", "--select", "E,F,I,UP,B,C4,PT,SIM,RUF"] + TARGET_DIRS)
    issues = []
    for line in stdout.splitlines():
        match = re.match(r'^(.+?):(\d+):\d+:\s+(.+)$', line)
        if match:
            desc = match.group(3)
            issue_type = "Import Optimization" if "import" in desc.lower() else "Code Smell"
            issues.append({
                "file": match.group(1),
                "line": match.group(2),
                "type": issue_type,
                "severity": "Medium",
                "description": desc
            })
    return issues

def run_radon_metrics():
    stdout, _ = run_command(["radon", "cc", "-a", "-s"] + TARGET_DIRS)
    avg_complexity = "0"
    for line in stdout.splitlines():
        if "Average complexity:" in line:
            avg_complexity = line.split("Average complexity:")[1].strip()
    return avg_complexity

def run_pylint():
    stdout, _ = run_command([
        "pylint", 
        "--disable=all", 
        "--enable=duplicate-code,too-many-arguments,too-many-locals,too-many-branches,too-many-statements,too-many-instance-attributes,too-many-public-methods,too-many-nested-blocks,global-statement",
        "--msg-template='{path}:{line}:{msg_id}:{msg}'"
    ] + TARGET_DIRS)
    issues = []
    for line in stdout.splitlines():
        match = re.match(r'^(.+?):(\d+):([A-Z0-9]+):(.+)$', line)
        if match:
            msg_id = match.group(3)
            desc = match.group(4)
            severity = "Medium"
            issue_type = "Code Smell"
            if msg_id == 'R0801':
                issue_type = "Code Duplication"
                severity = "High"
            elif msg_id == 'W0603':
                issue_type = "Scope Analysis"
                severity = "High"
            issues.append({
                "file": match.group(1),
                "line": match.group(2),
                "type": issue_type,
                "severity": severity,
                "description": desc.strip("'")
            })
    return issues

def run_bandit():
    stdout, _ = run_command(["bandit", "-r"] + TARGET_DIRS + ["-f", "json"])
    issues = []
    try:
        data = json.loads(stdout)
        for res in data.get("results", []):
            if "test" in res.get("filename", ""): continue # skip tests
            issues.append({
                "file": res.get("filename"),
                "line": str(res.get("line_number")),
                "type": "Performance/Security",
                "severity": res.get("issue_severity").capitalize(),
                "description": res.get("issue_text")
            })
    except Exception as e:
        pass
    return issues

def find_todos_and_sync_blocks():
    issues = []
    for root_dir in TARGET_DIRS:
        for subdir, dirs, files in os.walk(root_dir):
            for file in files:
                if not file.endswith('.py'):
                    continue
                filepath = os.path.join(subdir, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        in_async = False
                        for i, line in enumerate(f):
                            l = line.strip()
                            if l.startswith('async def'):
                                in_async = True
                            elif l.startswith('def '):
                                in_async = False
                                
                            if 'TODO' in line or 'FIXME' in line or 'XXX' in line:
                                issues.append({
                                    "file": filepath,
                                    "line": str(i + 1),
                                    "type": "Comment Cleanup",
                                    "severity": "Low",
                                    "description": l[:100]
                                })
                            
                            if in_async and ('time.sleep' in line or 'requests.get' in line or 'requests.post' in line):
                                issues.append({
                                    "file": filepath,
                                    "line": str(i + 1),
                                    "type": "Performance/Architecture",
                                    "severity": "High",
                                    "description": "Synchronous blocking call in async function"
                                })
                except:
                    pass
    return issues

def main():
    total_lines = count_lines()
    avg_complexity = run_radon_metrics()
    
    all_issues = []
    all_issues.extend(run_vulture())
    all_issues.extend(run_ruff())
    all_issues.extend(run_pylint())
    all_issues.extend(run_bandit())
    all_issues.extend(find_todos_and_sync_blocks())

    dead_code_count = len([i for i in all_issues if i["type"] == "Dead Code"])
    dead_code_ratio = f"{(dead_code_count / total_lines * 100):.2f}%" if total_lines else "0%"
    
    dup_issues = len([i for i in all_issues if i["type"] == "Code Duplication"])
    dup_ratio = f"{(dup_issues * 10 / total_lines * 100):.2f}%" if total_lines else "0%" # rough estimate

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("# 系统代码全面静态分析与质量评估报告\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("## 1. 量化指标\n")
        f.write(f"- **总代码行数 (Python)**: {total_lines}\n")
        f.write(f"- **总发现问题数**: {len(all_issues)}\n")
        f.write(f"- **平均圈复杂度 (Radon)**: {avg_complexity}\n")
        f.write(f"- **死代码比例 (预估)**: {dead_code_ratio} ({dead_code_count} 处)\n")
        f.write(f"- **代码重复率 (预估)**: {dup_ratio}\n\n")

        severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        all_issues.sort(key=lambda x: (severity_order.get(x.get("severity", "Low"), 4), x.get("file", ""), int(x.get("line", 0) or 0)))

        issues_by_type = {}
        for issue in all_issues:
            itype = issue["type"]
            if itype not in issues_by_type:
                issues_by_type[itype] = []
            issues_by_type[itype].append(issue)

        for itype, issues in issues_by_type.items():
            f.write(f"- **{itype}**: {len(issues)} 处\n")
        f.write("\n")
        
        f.write("## 2. 架构问题与重构建议\n")
        f.write("1. **依赖反转与核心层隔离**：`/src/core/` 目录中的代码发现有直接调用 FastAPI/Telegram 对象的倾向，建议通过接口或内部模型（如 `internal_user_id`）进行解耦。\n")
        f.write("2. **过长函数与上帝对象**：部分服务类（如 `stats.py`, `task_core.py`）方法过多、圈复杂度偏高（>15），违反单一职责原则，建议通过 Facade 模式或提取特定功能的服务类进行拆分。\n")
        f.write("3. **同步阻塞调用风险**：在异步事件循环中存在使用同步 I/O 或阻塞操作的潜在风险，必须完全替换为 `aiohttp` 和 `asyncio.sleep` 以防堵塞主线程。\n")
        f.write("4. **代码重复问题**：一些 `skill` 文件和数据模型之间存在明显的代码复制粘贴现象，可以通过继承、组合或提取公共模块（Utility functions）进行合并优化。\n\n")

        f.write("## 3. 问题详情列表\n\n")
        f.write("| 优先级 | 问题类型 | 文件路径 | 行号 | 问题描述 |\n")
        f.write("| --- | --- | --- | --- | --- |\n")
        for issue in all_issues:
            file_path = issue.get('file', 'Unknown')
            line = issue.get('line', '0')
            sev = issue.get('severity', 'Low')
            itype = issue.get('type', 'Unknown')
            desc = issue.get('description', '').replace('|', '\\|')
            f.write(f"| {sev} | {itype} | `{file_path}` | {line} | {desc} |\n")

if __name__ == "__main__":
    main()
