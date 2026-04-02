import os

def generate_tree(dir_path, prefix="", exclude_dirs=('.git', '__pycache__', 'node_modules', 'venv', '.venv', '.idea', '.vscode')):
    tree_str = ""
    items = sorted(os.listdir(dir_path))
    items = [item for item in items if item not in exclude_dirs]
    for i, item in enumerate(items):
        path = os.path.join(dir_path, item)
        is_last = (i == len(items) - 1)
        connector = "└── " if is_last else "├── "
        tree_str += f"{prefix}{connector}{item}\n"
        if os.path.isdir(path):
            extension = "    " if is_last else "│   "
            tree_str += generate_tree(path, prefix + extension, exclude_dirs)
    return tree_str

with open('project_tree.txt', 'w', encoding='utf-8') as f:
    f.write(generate_tree('.'))

