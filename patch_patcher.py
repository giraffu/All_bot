import os
import glob

search_str = """        elif task_type == "i2i_pro":
            filename = "i2i_pro.json"
"""
replace_str = """        elif task_type == "i2i_pro":
            filename = "i2i_pro.json"
        elif task_type == "img2img_lora":
            filename = "Qwen-Rapid-AIO.json"
"""

for fpath in glob.glob("/home/hfy/APP/All_bot/workers/comfy_agent*/workflow_patcher.py"):
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    
    if search_str in content:
        content = content.replace(search_str, replace_str)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Patched {fpath}")
    else:
        print(f"Skipped {fpath}")
