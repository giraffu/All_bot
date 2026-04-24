import os
import glob
import json

for file_path in glob.glob("/home/hfy/APP/All_bot/workers/*/workflows/mappings.json"):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if "img2img" in data and "img2img_lora" not in data:
        data["img2img_lora"] = data["img2img"].copy()
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Patched {file_path}")
    else:
        print(f"Skipped {file_path} (already patched or img2img not found)")
