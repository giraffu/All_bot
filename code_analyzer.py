import os
import ast
import json

def analyze_python_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines_of_code = len(content.splitlines())
        
        try:
            tree = ast.parse(content)
        except Exception:
            return {"lines": lines_of_code, "error": "SyntaxError"}
            
        classes = []
        functions = []
        imports = []
        
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                methods = [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
                classes.append({"name": node.name, "methods": methods})
            elif isinstance(node, ast.FunctionDef):
                functions.append(node.name)
            elif isinstance(node, ast.Import):
                for n in node.names:
                    imports.append(n.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
                    
        return {
            "lines": lines_of_code,
            "classes": classes,
            "functions": functions,
            "imports": list(set(imports))
        }
    except Exception as e:
        return {"error": str(e)}

def scan_directory(dir_path, exclude_dirs=('.git', '__pycache__', 'node_modules', 'venv', '.venv', '.idea', '.vscode', 'output', 'images')):
    result = {}
    items = sorted(os.listdir(dir_path))
    for item in items:
        if item in exclude_dirs or item.endswith('.png') or item.endswith('.jpg'):
            continue
            
        path = os.path.join(dir_path, item)
        if os.path.isdir(path):
            sub_result = scan_directory(path, exclude_dirs)
            if sub_result:  # Only add non-empty directories
                result[item] = sub_result
        elif path.endswith('.py'):
            result[item] = analyze_python_file(path)
        else:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    result[item] = {"lines": len(f.readlines()), "type": "other"}
            except Exception:
                result[item] = {"type": "binary/unreadable"}
                
    return result

project_data = scan_directory('.')
with open('project_analysis.json', 'w', encoding='utf-8') as f:
    json.dump(project_data, f, indent=2, ensure_ascii=False)

