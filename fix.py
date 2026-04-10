import os

fsm_dir = "src/handlers/fsm"
for filename in os.listdir(fsm_dir):
    if filename.endswith("_fsm.py"):
        filepath = os.path.join(fsm_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        content = content.replace('"🔄 已为您自动取消未完成的流程。\n👉 **请再次点击刚才的按钮**，即可开始新任务！"', '"🔄 已为您自动取消未完成的流程。\\n👉 **请再次点击刚才的按钮**，即可开始新任务！"')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Fixed {filepath}")
