import json
import sys
sys.path.append('.')
from workflow_patcher import WorkflowPatcher

patcher = WorkflowPatcher('workflows')
wf = patcher.load_workflow('img2img')
patched = patcher.patch_workflow('img2img', wf, {'seed': None})

for k, v in patched.items():
    if isinstance(v, dict) and 'inputs' in v:
        if 'noise_seed' in v['inputs']:
            print(f"Node {k} noise_seed: {v['inputs']['noise_seed']}")
        if 'seed' in v['inputs']:
            print(f"Node {k} seed: {v['inputs']['seed']}")
