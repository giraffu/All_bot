import json
import logging
import os
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class WorkflowPatcher:
    def __init__(self, workflows_dir: str):
        self.workflows_dir = workflows_dir
        self.mappings = self.load_mappings()

    def load_mappings(self) -> Dict[str, Any]:
        mapping_path = os.path.join(self.workflows_dir, "mappings.json")
        if os.path.exists(mapping_path):
            with open(mapping_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def strip_meta(self, data: Any) -> Any:
        if isinstance(data, dict):
            data.pop("_meta", None)
            for key, value in data.items():
                data[key] = self.strip_meta(value)
        elif isinstance(data, list):
            for i in range(len(data)):
                data[i] = self.strip_meta(data[i])
        return data

    def load_workflow(self, task_type: str) -> Optional[Dict[str, Any]]:
        filename = f"{task_type}.json"
        # Map task types to filenames (matching backend worker.py logic)
        if task_type == "img2img":
            filename = "Qwen-Rapid-AIO.json"
        elif task_type == "face_swap":
            filename = "face_swap.json"
        elif task_type == "video_insert":
            filename = "perfect_video_insert.json"
        elif task_type == "video_edit":
            filename = "perfect_video_edit.json"
        elif task_type == "t2i-pornmaster-turbo":
            filename = "Pornmaster Z-Image Turbo_t2i_Double checkpoints & realism enhancer_V1_2026_01_24.json"
            
        path = os.path.join(self.workflows_dir, filename)
        if not os.path.exists(path):
            logger.error(f"Workflow file {path} not found")
            return None
            
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            data = self.strip_meta(data)
            
            if isinstance(data, dict) and "nodes" in data and isinstance(data["nodes"], list):
                logger.warning(f"Workflow {filename} seems to be in UI format (contains 'nodes' list). Please export in API format.")
            return data

    def patch_workflow(self, task_type: str, workflow: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        # Deep copy to avoid modifying template
        wf = json.loads(json.dumps(workflow))
        
        # If we have mappings, use them
        mapping = self.mappings.get(task_type, {})
        
        for key, value in params.items():
            if key in mapping:
                node_id = str(mapping[key])
                input_name = mapping.get(f"{key}_input", "image") # Default input name
                if node_id in wf:
                    if "inputs" not in wf[node_id]:
                        wf[node_id]["inputs"] = {}
                    wf[node_id]["inputs"][input_name] = value
            else:
                # Heuristic search
                self.heuristic_patch(wf, key, value)
                
        return wf

    def heuristic_patch(self, workflow: Dict[str, Any], key: str, value: Any):
        # This is a best-effort patcher for API format workflows
        for _, node in workflow.items():
            if not isinstance(node, dict) or "inputs" not in node:
                continue
                
            inputs = node["inputs"]
            class_type = node.get("class_type", "")
            
            if key == "prompt" and ("CLIPTextEncode" in class_type or "Prompt" in class_type or "TextEncode" in class_type):
                if "text" in inputs:
                    inputs["text"] = value
                if "prompt" in inputs:
                    inputs["prompt"] = value
                    
            elif key == "seed" and ("Sampler" in class_type or "Seed" in class_type):
                if "seed" in inputs:
                    inputs["seed"] = value
                if "noise_seed" in inputs:
                    inputs["noise_seed"] = value
                    
            elif key == "steps" and "Sampler" in class_type:
                if "steps" in inputs:
                    inputs["steps"] = value
                    
            elif key == "cfg" and "Sampler" in class_type:
                if "cfg" in inputs:
                    inputs["cfg"] = value
            
            elif key == "image" and "LoadImage" in class_type:
                inputs["image"] = value
            
            elif key == "width" and "EmptyLatentImage" in class_type:
                inputs["width"] = value
                
            elif key == "height" and "EmptyLatentImage" in class_type:
                inputs["height"] = value
