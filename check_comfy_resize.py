import json
import urllib.request
import urllib.parse
import time

def queue_prompt():
    with open('/home/hfy/APP/All_bot/workers/comfy_agent1/workflows/face_video.json', 'r') as f:
        prompt = json.load(f)
    
    # We want to test what Node 361 (ImageResizeKJv2) outputs.
    # We can add a SaveImage node to it.
    prompt["999"] = {
        "class_type": "SaveImage",
        "inputs": {
            "filename_prefix": "test_resize",
            "images": ["361", 0]
        }
    }
    
    data = json.dumps({"prompt": prompt}).encode('utf-8')
    req = urllib.request.Request("http://127.0.0.1:8188/prompt", data=data)
    try:
        urllib.request.urlopen(req)
        print("Prompt queued")
    except Exception as e:
        print(f"Error: {e}")

queue_prompt()
