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
# Manual patch without custom ltx_video logic
patched_wf = json.loads(json.dumps(wf))
for key, value in params.items():
    patcher.heuristic_patch(patched_wf, key, value)

import requests
resp = requests.post('http://192.168.1.226:8188/prompt', json={"prompt": patched_wf}).json()
print("Outputs to execute without custom patch:", requests.get('http://192.168.1.226:8188/queue').json()["queue_pending"][-1][4])
