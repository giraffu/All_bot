import json
import sys
sys.path.append('.')
from workflow_patcher import WorkflowPatcher

patcher = WorkflowPatcher('workflows')
wf = patcher.load_workflow('video_edit')
patched = patcher.patch_workflow('video_edit', wf, {'seed': 123456789})

for k, v in patched.items():
    if isinstance(v, dict) and 'inputs' in v:
        if 'noise_seed' in v['inputs']:
            print(f"Node {k} noise_seed: {v['inputs']['noise_seed']}")
