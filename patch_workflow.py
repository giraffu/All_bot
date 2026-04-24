import os
import glob

patch_str = """        # Dynamic JSON pruning for img2img task to avoid empty nodes and blank inputs
        if task_type == "img2img":
            # Handle LoRA dynamically (default to no LoRA)
            lora_name = params.get("lora_name", "")
            if lora_name and str(lora_name).strip() != "":
                if "32" in wf and "inputs" in wf["32"]:
                    wf["32"]["inputs"]["lora_name"] = lora_name
                    if params.get("lora_strength") is not None:
                        wf["32"]["inputs"]["strength_model"] = float(params["lora_strength"])
            else:
                # Strip LoRA node and connect KSampler (2) directly to Checkpoint (1)
                if "2" in wf and "inputs" in wf["2"]:
                    wf["2"]["inputs"]["model"] = ["1", 0]
                if "32" in wf:
                    wf.pop("32", None)

            # 3 is the TextEncodeQwenImageEditPlus node
            text_encode_node_id = str(mapping.get("prompt", "3"))"""

old_str = """        # Dynamic JSON pruning for img2img task to avoid empty nodes and blank inputs
        if task_type == "img2img":
            # 3 is the TextEncodeQwenImageEditPlus node
            text_encode_node_id = str(mapping.get("prompt", "3"))"""

for file_path in glob.glob("/home/hfy/APP/All_bot/workers/*/workflow_patcher.py"):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    if old_str in content:
        new_content = content.replace(old_str, patch_str)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Patched {file_path}")
    else:
        print(f"Skipped {file_path} (already patched or string not found)")
