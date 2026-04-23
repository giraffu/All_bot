import json

with open('/home/hfy/APP/All_bot/Qwen-Rapid-AIO2.json', 'r') as f:
    data = json.load(f)

# Connect CheckpointLoaderSimple (node 1) directly to KSampler (node 2)
if "100" in data:
    data["2"]["inputs"]["model"] = ["1", 0]
    # Delete the incompatible LoRA node
    del data["100"]

with open('/home/hfy/APP/All_bot/Qwen-Rapid-AIO2.json', 'w') as f:
    json.dump(data, f, indent=2)
