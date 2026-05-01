import re

with open("src/services/task_service.py", "r") as f:
    content = f.read()

# Fix 1: mode_name display in _handle_task_completion
content = content.replace('mode_name = MODE_NAME_MAP.get(task_type, task_type)', 
                          'mode_name = MODE_NAME_MAP.get(task_type, task_type)\n                display_mode_name = context.t(mode_name) if hasattr(context, "t") else mode_name')
content = content.replace('caption=f"✅ {mode_name} 生成完成",', 'caption=f"✅ {display_mode_name} 生成完成",')

# Fix 2: mode_name display in process_image_task, process_video_task etc.
content = content.replace('mode_name = MODE_NAME_MAP.get(mode, mode)',
                          'mode_name = MODE_NAME_MAP.get(mode, mode)\n        display_mode_name = context.t(mode_name) if hasattr(context, "t") else mode_name')
content = content.replace('msg_text = f"🚀 正在处理{mode_name}生成任务', 'msg_text = f"🚀 正在处理{display_mode_name}生成任务')
# Notice there is another caption=f"✅ {mode_name} 生成完成", allow_contribute=allow_contribute
# which was already replaced by the first replace? No, the first replace is global. Let's check.

with open("src/services/task_service.py", "w") as f:
    f.write(content)
