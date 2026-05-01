with open("src/handlers/fsm/gallery_apply_fsm.py", "r") as f:
    content = f.read()

content = content.replace('mode_name = MODE_NAME_MAP.get(task_type, task_type)\n    msg = (',
                          'mode_name = MODE_NAME_MAP.get(task_type, task_type)\n    display_mode_name = context.t(mode_name) if hasattr(context, "t") else mode_name\n    msg = (')
content = content.replace('【{html.escape(mode_name)}】', '【{html.escape(display_mode_name)}】')

with open("src/handlers/fsm/gallery_apply_fsm.py", "w") as f:
    f.write(content)
