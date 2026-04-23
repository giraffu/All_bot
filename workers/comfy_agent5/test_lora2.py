import json

with open('/home/hfy/APP/All_bot/Qwen-Rapid-AIO2.json', 'r') as f:
    data = json.load(f)

# Change to LoraLoaderBypassModelOnly ? Let's see what happens if we remove the LoRA node completely just to test.
# But we need the LoRA.

