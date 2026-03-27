import os
import re

def is_commented_code(line):
    # Regex to match common Python keywords/structures in comments
    code_patterns = [
        r'#\s*def\s+\w+',
        r'#\s*class\s+\w+',
        r'#\s*import\s+',
        r'#\s*from\s+[\w\.]+\s+import\s+',
        r'#\s*if\s+.+:',
        r'#\s*elif\s+.+:',
        r'#\s*else:',
        r'#\s*for\s+.+\s+in\s+:',
        r'#\s*while\s+.+:',
        r'#\s*return\s+',
        r'#\s*yield\s+',
        r'#\s*print\(',
        r'#\s*logger\.',
        r'#\s*await\s+',
        r'#\s*[\w\.]+\s*=\s*.+',
    ]
    for pattern in code_patterns:
        if re.search(pattern, line):
            return True
    return False

def scan_directory(directory):
    results = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py') and not root.startswith('./venv') and '__pycache__' not in root:
                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    
                for i, line in enumerate(lines):
                    if is_commented_code(line.strip()):
                        results.append((file_path, i+1, line.strip()))
    return results

if __name__ == '__main__':
    commented_code = scan_directory('src')
    for file_path, line_num, line in commented_code:
        print(f"{file_path}:{line_num}: {line}")
