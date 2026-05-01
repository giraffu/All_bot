import os
import glob

fsm_files = glob.glob("src/handlers/fsm/*.py")

for f in fsm_files:
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    content = content.replace(
        '"🔄 已为您退出当前输入步骤（后台正在生成的任务不受影响）。\\n👉 **请再次点击刚才的按钮**，即可开始新任务！"',
        'context.t("system.fsm_exit_hint")'
    )
    
    content = content.replace(
        '"⚠️ 当前处于交互流程中。请按提示操作，或发送 /cancel 取消本次操作。"',
        'context.t("system.fsm_in_progress_hint")'
    )
    
    with open(f, 'w', encoding='utf-8') as file:
        file.write(content)

print("Done")
