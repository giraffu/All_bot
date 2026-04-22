import json
from workflow_patcher import WorkflowPatcher

patcher = WorkflowPatcher("/home/hfy/APP/All_bot/workers/comfy_agent1/workflows")
wf = patcher.load_workflow("ltx_video")
params = {
    "image": "test_data/C577ECBD-6492-4D9C-9BE5-5F5679DC5112.jpeg",
    "prompt": "Selfie-style closeup video of a young chinese woman",
    "length": 10,
    "width": 704,
    "height": 1280,
    "priority": 10
}
patched_wf = patcher.patch_workflow("ltx_video", wf, params)
print("Node 61 in patched_wf:", "61" in patched_wf)

import requests
resp = requests.post('http://192.168.1.226:8188/prompt', json={"prompt": patched_wf}).json()
print("Prompt ID:", resp["prompt_id"])
import time
time.sleep(2)
hist = requests.get(f'http://192.168.1.226:8188/history/{resp["prompt_id"]}').json()
if resp["prompt_id"] in hist:
    print("Executed outputs:", hist[resp["prompt_id"]]["prompt"][4])
else:
    queue = requests.get('http://192.168.1.226:8188/queue').json()
    for q in queue["queue_running"] + queue["queue_pending"]:
        if q[1] == resp["prompt_id"]:
            print("Outputs to execute:", q[4])
