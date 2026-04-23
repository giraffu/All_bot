import json

with open('/home/hfy/APP/All_bot/Qwen-Rapid-AIO2.json', 'r') as f:
    data = json.load(f)

# Revert to standard LoraLoader
data["100"]["class_type"] = "LoraLoader"
data["100"]["inputs"]["strength_clip"] = 0.6
data["100"]["inputs"]["clip"] = ["1", 1]
data["100"]["inputs"]["model"] = ["1", 0]

# BUT we only connect the CLIP to the downstream nodes.
# We connect the Model from the checkpoint DIRECTLY to KSampler.
data["2"]["inputs"]["model"] = ["1", 0]

# The downstream clip nodes (3 and 4) use the Lora's clip output
data["3"]["inputs"]["clip"] = ["100", 1]
data["4"]["inputs"]["clip"] = ["100", 1]

with open('/home/hfy/APP/All_bot/Qwen-Rapid-AIO2_clip_only.json', 'w') as f:
    json.dump(data, f, indent=2)
