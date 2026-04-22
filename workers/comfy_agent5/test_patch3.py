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
print("Node 61 inputs:", patched_wf.get("61"))
print("Node 18 inputs:", patched_wf.get("18"))
print("Node 19 inputs:", patched_wf.get("19"))
print("Node 181 inputs:", patched_wf.get("181"))
import requests
resp = requests.post('http://192.168.1.226:8188/prompt', json={"prompt": patched_wf}).json()
print("Outputs to execute with full patch:", requests.get('http://192.168.1.226:8188/queue').json()["queue_pending"][-1][4])
