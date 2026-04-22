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
    "priority": 10,
    "seed": 123456789
}
patched_wf = patcher.patch_workflow("ltx_video", wf, params)
task_id = "0ec28f84-4ac2-4d4b-ae42-530d86cfc55e"
for node_id, node in patched_wf.items():
    if isinstance(node, dict) and "class_type" in node:
        if node["class_type"] in ["SaveImage", "VHS_VideoCombine", "SaveAnimatedWEBP"]:
            if "inputs" in node:
                node["inputs"]["filename_prefix"] = f"{task_id}"

import requests
resp = requests.post('http://192.168.1.226:8188/prompt', json={"prompt": patched_wf}).json()
print("Outputs to execute with task_id patch:", requests.get('http://192.168.1.226:8188/queue').json()["queue_pending"][-1][4])
open("test_prompt.json", "w").write(json.dumps(patched_wf, indent=2))
