import json

file_path = '/home/hfy/APP/All_bot/workers/comfy_agent4/workflows/Qwen-Rapid-AIO.json'

with open(file_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 1. 添加 LoraLoader 节点
data["100"] = {
    "inputs": {
        "lora_name": "lightning_lora.safetensors", # 这里可以替换为实际的 LoRA 文件名
        "strength_model": 0.6,
        "strength_clip": 0.6,
        "model": ["1", 0],
        "clip": ["1", 1]
    },
    "class_type": "LoraLoader",
    "_meta": {
        "title": "Load LoRA"
    }
}

# 2. 修改 KSampler (节点 2)
data["2"]["inputs"]["model"] = ["100", 0]
data["2"]["inputs"]["sampler_name"] = "res_5s"
data["2"]["inputs"]["cfg"] = 0.8
# steps 已经是 4，scheduler 已经是 beta，但以防万一还是显式设置
data["2"]["inputs"]["steps"] = 4
data["2"]["inputs"]["scheduler"] = "beta"

# 3. 修改 TextEncode 节点 (节点 3 和 4)
data["3"]["inputs"]["clip"] = ["100", 1]
data["4"]["inputs"]["clip"] = ["100", 1]

with open(file_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("Modification complete.")
