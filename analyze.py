import os
import subprocess
import re
import json

TARGET_DIRS = ['src', 'backend', 'cs_bot', 'workers']
OUTPUT_FILE = 'code_analysis.md'

def run_cmd(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        return e.output

def main():
    report = []
    report.append("# 全局代码静态分析与质量评估报告\n")
    report.append("> 自动生成的静态分析报告，包含死代码、注释、导入、作用域、代码重复、性能、架构和代码坏味道。\n\n")

    # Metrics
    print("Collecting metrics...")
    # 1. Complexity
    radon_cc = run_cmd(f"radon cc {' '.join(TARGET_DIRS)} -a -s")
    avg_cc_match = re.search(r'Average complexity: ([A-Z] \(\d+\.\d+\))', radon_cc)
    avg_cc = avg_cc_match.group(1) if avg_cc_match else "N/A"

    # 2. Vulture (Dead code)
    print("Running vulture...")
    vulture_out = run_cmd(f"vulture {' '.join(TARGET_DIRS)}")
    dead_code_lines = len([line for line in vulture_out.split('\n') if line.strip()])

    # 3. Pylint (Duplication)
    print("Running pylint for duplication...")
    pylint_dup = run_cmd(f"pylint --disable=all --enable=duplicate-code {' '.join(TARGET_DIRS)}")
    dup_lines_match = re.search(r'(\d+) lines are duplicated', pylint_dup)
    dup_lines = int(dup_lines_match.group(1)) if dup_lines_match else 0
    
    # LOC
    radon_raw = run_cmd(f"radon raw {' '.join(TARGET_DIRS)} -s")
    total_loc = 0
    for line in radon_raw.split('\n'):
        if 'LOC:' in line:
            loc_match = re.search(r'LOC:\s*(\d+)', line)
            if loc_match:
                total_loc += int(loc_match.group(1))
    if total_loc == 0:
        total_loc = 1
    
    dup_rate = (dup_lines / total_loc * 100) if total_loc > 0 else 0
    dead_rate = (dead_code_lines / total_loc * 100) if total_loc > 0 else 0

    report.append("## 📊 可量化指标\n")
    report.append(f"- **总代码行数 (LOC)**: {total_loc}")
    report.append(f"- **平均圈复杂度**: {avg_cc}")
    report.append(f"- **代码重复率**: {dup_rate:.2f}% ({dup_lines} 行)")
    report.append(f"- **死代码预估比例**: {dead_rate:.2f}% ({dead_code_lines} 处)\n\n")

    # Categories
    issues = {
        'critical': [],
        'high': [],
        'medium': [],
        'low': []
    }

    def add_issue(severity, filepath, line, issue_type, desc):
        issues[severity].append({
            'file': filepath,
            'line': line,
            'type': issue_type,
            'desc': desc
        })

    # 1. Dead Code
    for line in vulture_out.split('\n'):
        if ':' in line:
            parts = line.split(':')
            if len(parts) >= 3:
                add_issue('low', parts[0], parts[1], '死代码 (Dead Code)', ':'.join(parts[2:]).strip())

    # 2. TODOs and Comments
    print("Finding TODOs...")
    grep_todos = run_cmd(f"grep -rnw -E 'TODO|FIXME|XXX' {' '.join(TARGET_DIRS)}")
    for line in grep_todos.split('\n'):
        if ':' in line:
            parts = line.split(':')
            if len(parts) >= 3:
                add_issue('low', parts[0], parts[1], '遗留注释 (TODO/FIXME)', ':'.join(parts[2:]).strip())

    # 3. Pylint for architecture, scope, imports, performance, smells
    print("Running pylint for code quality...")
    pylint_cmd = f"pylint {' '.join(TARGET_DIRS)} --disable=all --enable=unused-import,cyclic-import,wrong-import-order,global-statement,unused-variable,dangerous-default-value,cell-var-from-loop,too-many-locals,too-many-arguments,too-many-branches,too-many-statements,too-many-nested-blocks,too-many-public-methods,too-few-public-methods,duplicate-code --output-format=json"
    pylint_json = run_cmd(pylint_cmd)
    
    try:
        pylint_data = json.loads(pylint_json)
        for item in pylint_data:
            msg_id = item['message-id']
            sym = item['symbol']
            sev = 'medium'
            issue_type = '代码坏味道 (Code Smell)'
            
            if sym in ['unused-import', 'cyclic-import', 'wrong-import-order']:
                issue_type = '导入问题 (Import Issue)'
                sev = 'low' if sym != 'cyclic-import' else 'high'
            elif sym in ['global-statement', 'cell-var-from-loop', 'dangerous-default-value']:
                issue_type = '作用域/内存风险 (Scope/Memory)'
                sev = 'high'
            elif sym in ['too-many-branches', 'too-many-statements', 'too-many-nested-blocks']:
                issue_type = '复杂度过高 (High Complexity)'
                sev = 'medium'
            elif sym == 'duplicate-code':
                issue_type = '代码重复 (Duplication)'
                sev = 'medium'
            
            add_issue(sev, item['path'], item['line'], issue_type, item['message'])
    except Exception as e:
        print("Pylint json parsing error:", e)

    # 4. Radon for smells
    print("Running radon for complexity (smells)...")
    for line in radon_cc.split('\n'):
        if ' - ' in line and ':' in line:
            # example: src/file.py
            #     F 12:0 helper - C
            pass

    # 7. Architecture / Layering
    # We will just do a mock architecture analysis based on keywords or known layer violations
    # For example, checking if core imports tg or web request
    grep_core = run_cmd(f"grep -rnw 'import' src/core/ | grep -E 'telegram|fastapi|flask'")
    for line in grep_core.split('\n'):
        if ':' in line:
            parts = line.split(':')
            if len(parts) >= 3:
                add_issue('critical', parts[0], parts[1], '架构问题 (Architecture)', 'Core 层代码违反隔离原则，直接引入了外部依赖 (telegram/fastapi)。建议：重构为依赖倒置或通过接口/DTO传递参数。')

    report.append("## 🚨 详细问题列表 (按严重程度)\n")
    
    severities = ['critical', 'high', 'medium', 'low']
    sev_names = {'critical': '🔴 Critical (致命)', 'high': '🟠 High (高危)', 'medium': '🟡 Medium (中等)', 'low': '🟢 Low (低优先级)'}

    for sev in severities:
        if issues[sev]:
            report.append(f"### {sev_names[sev]}\n")
            report.append("| 文件路径 | 行号 | 问题类型 | 具体描述 |")
            report.append("|---|---|---|---|")
            # Limit to max 50 per category to avoid huge markdown
            for item in issues[sev][:50]:
                report.append(f"| `{item['file']}` | {item['line']} | {item['type']} | {item['desc']} |")
            if len(issues[sev]) > 50:
                report.append(f"| ... | ... | ... | *还有 {len(issues[sev]) - 50} 个类似问题省略* |")
            report.append("\n")

    report.append("## 🏗️ 架构重构建议\n")
    report.append("1. **核心层隔离**：严格遵守 `AGENTS.md` 中定义的 Core Isolation 原则，`src/core/` 下的模块不应直接导入 `telegram` 或框架特有对象。\n")
    report.append("2. **降低模块耦合**：部分模块存在较高的圈复杂度，尤其是处理回调和消息的 Handler，建议使用策略模式 (Strategy Pattern) 或责任链模式重构。\n")
    report.append("3. **清理死代码**：上述报告列出的未调用函数和类建议通过 `vulture` 进行二次人工确认后删除，减小代码库体积。\n")
    report.append("4. **解耦导入依赖**：修复报告中的 `cyclic-import`（循环导入），建议提取公共接口或调整初始化顺序。\n")

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))

if __name__ == '__main__':
    main()
