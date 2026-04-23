import json

with open('/home/hfy/APP/All_bot/Qwen-Rapid-AIO2.json', 'r') as f:
    data = json.load(f)

# Change LoraLoader to LoraLoaderModelOnly
data["100"]["class_type"] = "LoraLoaderModelOnly"
# Remove strength_clip and clip from inputs
if "strength_clip" in data["100"]["inputs"]:
    del data["100"]["inputs"]["strength_clip"]
if "clip" in data["100"]["inputs"]:
    del data["100"]["inputs"]["clip"]

# Redirect clip for node 3 and 4
for node_id in ["3", "4"]:
    if "clip" in data[node_id]["inputs"]:
        data[node_id]["inputs"]["clip"] = ["1", 1]

with open('/home/hfy/APP/All_bot/Qwen-Rapid-AIO2_fixed.json', 'w') as f:
    json.dump(data, f, indent=2)
