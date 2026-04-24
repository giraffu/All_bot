import os
import glob

patch_str_1 = """        # Map task types to filenames (matching backend worker.py logic)
        if task_type in ["img2img", "img2img_lora"]:
            filename = "Qwen-Rapid-AIO.json" """

old_str_1 = """        # Map task types to filenames (matching backend worker.py logic)
        if task_type == "img2img":
            filename = "Qwen-Rapid-AIO.json" """


patch_str_2 = """        # Dynamic JSON pruning for img2img task to avoid empty nodes and blank inputs
        if task_type in ["img2img", "img2img_lora"]:"""

old_str_2 = """        # Dynamic JSON pruning for img2img task to avoid empty nodes and blank inputs
        if task_type == "img2img":"""


for file_path in glob.glob("/home/hfy/APP/All_bot/workers/*/workflow_patcher.py"):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    changed = False
    if old_str_1 in content:
        content = content.replace(old_str_1, patch_str_1)
        changed = True
        
    if old_str_2 in content:
        content = content.replace(old_str_2, patch_str_2)
        changed = True
        
    if changed:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Patched {file_path}")
    else:
        print(f"Skipped {file_path} (already patched or string not found)")
