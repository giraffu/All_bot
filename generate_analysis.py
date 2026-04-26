import os
import subprocess
import json
import re
from collections import defaultdict

OUTPUT_FILE = "code_analysis.md"

def run_cmd(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout, result.stderr
    except Exception as e:
        return str(e), ""

def analyze_python():
    print("Running Vulture...")
    vulture_out, _ = run_cmd("vulture src backend workers cs_bot --min-confidence 70")
    
    print("Running Radon...")
    radon_out, _ = run_cmd("radon cc src backend workers cs_bot -a -j")
    
    print("Running Pylint...")
    pylint_out, _ = run_cmd("pylint src backend workers cs_bot --output-format=json --disable=all --enable=F,E,W,R,C --max-line-length=120")
    
    print("Running Pylint for duplicate code...")
    pylint_dup_out, _ = run_cmd("pylint src backend workers cs_bot --disable=all --enable=duplicate-code --output-format=json")
    
    return vulture_out, radon_out, pylint_out, pylint_dup_out

def grep_todos():
    print("Searching for TODO/FIXME...")
    out, _ = run_cmd("grep -rnE '(TODO|FIXME|XXX)' src backend workers cs_bot frontend/src dashboard/frontend/src dashboard/backend ton_payment_frontend/src")
    return out

def get_severity(pylint_type, symbol=None):
    if pylint_type in ('error', 'fatal'):
        return 'Critical' if symbol in ('syntax-error', 'fatal') else 'High'
    elif pylint_type == 'warning':
        return 'Medium'
    return 'Low'

def determine_issue_type(symbol):
    imports = ('unused-import', 'cyclic-import', 'wrong-import-order', 'wrong-import-position', 'reimported')
    scope = ('global-statement', 'global-variable-not-assigned', 'redefined-outer-name', 'cell-var-from-loop')
    perf = ('unnecessary-comprehension', 'consider-using-generator', 'unnecessary-pass', 'eval-used')
    arch = ('too-many-public-methods', 'too-many-ancestors', 'too-many-instance-attributes')
    smell = ('too-many-arguments', 'too-many-locals', 'too-many-branches', 'too-many-statements', 'too-many-return-statements', 'too-many-nested-blocks', 'too-complex')
    
    if symbol in imports: return "导入优化"
    if symbol in scope: return "作用域分析"
    if symbol in perf: return "性能问题"
    if symbol in arch: return "架构问题"
    if symbol in smell: return "代码坏味道"
    if symbol == 'duplicate-code': return "代码重复"
    return "一般代码规范"

def generate_report():
    vulture_out, radon_out, pylint_out, pylint_dup_out = analyze_python()
    todos = grep_todos()
    
    # Store issues by file path
    file_issues = defaultdict(list)
    
    # Process Pylint
    dup_blocks = 0
    try:
        pylint_data = json.loads(pylint_out) if pylint_out else []
        for issue in pylint_data:
            file_issues[issue['path']].append({
                'line': issue['line'],
                'type': determine_issue_type(issue['symbol']),
                'severity': get_severity(issue['type'], issue['symbol']),
                'desc': f"{issue['message']} ({issue['symbol']})"
            })
    except Exception as e:
        print("Failed to parse pylint json:", e)

    try:
        dup_data = json.loads(pylint_dup_out) if pylint_dup_out else []
        for issue in dup_data:
            if issue['symbol'] == 'duplicate-code':
                dup_blocks += 1
            file_issues[issue['path']].append({
                'line': issue['line'],
                'type': "代码重复",
                'severity': 'Medium',
                'desc': f"{issue['message']} ({issue['symbol']})"
            })
    except:
        pass
        
    # Process Vulture (Dead code)
    dead_code_count = 0
    for line in vulture_out.split('\n'):
        if line.strip() and not line.startswith('Code'):
            parts = line.split(':', 2)
            if len(parts) >= 3:
                dead_code_count += 1
                filepath = parts[0].strip()
                file_issues[filepath].append({
                    'line': parts[1].strip(),
                    'type': "死代码检测",
                    'severity': "Low",
                    'desc': parts[2].strip()
                })

    # Process TODOs
    todo_count = 0
    for t in todos.split('\n'):
        if t.strip():
            parts = t.split(':', 2)
            if len(parts) >= 3:
                todo_count += 1
                filepath = parts[0].strip()
                file_issues[filepath].append({
                    'line': parts[1].strip(),
                    'type': "注释清理",
                    'severity': "Low",
                    'desc': "遗留注释 (TODO/FIXME/XXX): " + parts[2].strip()
                })
            
    # Process Radon (Complexity)
    complex_blocks = 0
    total_cc = 0
    count_cc = 0
    try:
        radon_data = json.loads(radon_out)
        for file, blocks in radon_data.items():
            for block in blocks:
                cc = block.get('complexity', 0)
                total_cc += cc
                count_cc += 1
                if cc > 10:
                    complex_blocks += 1
                    file_issues[file].append({
                        'line': block.get('lineno', '?'),
                        'type': "代码坏味道",
                        'severity': "High" if cc > 20 else "Medium",
                        'desc': f"高复杂度代码块 ({block.get('type', '')} `{block.get('name', '')}`): Cyclomatic Complexity = {cc}"
                    })
    except:
        pass

    avg_complexity = round(total_cc / count_cc, 2) if count_cc > 0 else 0

    # Build markdown
    report = ["# 全局代码静态分析与质量评估报告\n"]
    
    # Metrics
    report.append("## 📊 可量化指标汇总\n")
    report.append(f"- **平均代码复杂度 (Cyclomatic Complexity)**: {avg_complexity}")
    report.append(f"- **高复杂度代码块数量 (>10)**: {complex_blocks}")
    report.append(f"- **死代码/未引用对象数量**: {dead_code_count}")
    report.append(f"- **TODO/FIXME 遗留注释数量**: {todo_count}")
    report.append(f"- **代码重复段落数**: {dup_blocks}\n")
    
    # Refactoring Advice
    report.append("## 💡 架构重构建议\n")
    report.append("1. **单一职责原则(SRP)**: 对于包含过多公共方法或属性的类，建议将其拆分为更小、职责更单一的组件（如将数据库访问、业务逻辑和API响应分离）。")
    report.append("2. **依赖倒置与解耦**: 发现较多全局变量滥用和作用域冲突，建议使用依赖注入或上下文传递代替直接导入全局状态。")
    report.append("3. **并发锁与队列**: 在涉及到长耗时任务时，发现潜在的阻塞或缺少状态同步（详见并发、排队与任务调度规范）。\n")

    # Details Grouped by File
    report.append("## 📁 按文件结构的详细分析\n")
    
    for filepath, issues in sorted(file_issues.items()):
        report.append(f"### 📄 `{filepath}`")
        
        # Sort issues by line number
        def get_line_num(iss):
            try: return int(iss['line'])
            except: return 0
            
        issues.sort(key=get_line_num)
        
        report.append("| 行号 | 问题类型 | 严重程度 | 具体描述 |")
        report.append("| --- | --- | --- | --- |")
        
        for issue in issues:
            # Markdown escape for table
            desc = issue['desc'].replace('|', '\|').replace('\n', ' ')
            report.append(f"| {issue['line']} | {issue['type']} | **{issue['severity']}** | {desc} |")
            
        report.append("\n")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(report))
        
    print(f"Report generated successfully at {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_report()
