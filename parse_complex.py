import re

with open('code_analysis.md') as f:
    lines = f.readlines()

current_file = ""
for line in lines:
    if line.startswith("### 📄"):
        current_file = line.strip().split("`")[1]
    
    if "高复杂度代码块" in line:
        if "backend/app/main.py" in current_file or "routers/" in current_file:
            match = re.search(r'function `([^`]+)`', line)
            cc_match = re.search(r'Cyclomatic Complexity = (\d+)', line)
            if match and cc_match:
                print(f"- **{current_file}**: `{match.group(1)}` (复杂度: {cc_match.group(1)})")
