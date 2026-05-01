with open("src/services/task_service.py", "r") as f:
    content = f.read()

content = content.replace('mode_name = MODE_NAME_MAP.get(mode, mode)',
                          'mode_name = MODE_NAME_MAP.get(mode, mode)\n        display_mode_name = context.t(mode_name) if hasattr(context, "t") else mode_name')
content = content.replace('msg_text = f"🚀 正在处理{mode_name}生成任务', 'msg_text = f"🚀 正在处理{display_mode_name}生成任务')
content = content.replace('caption=f"✅ {mode_name} 生成完成", allow_contribute=allow_contribute', 'caption=f"✅ {display_mode_name} 生成完成", allow_contribute=allow_contribute')

with open("src/services/task_service.py", "w") as f:
    f.write(content)
