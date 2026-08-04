import json
import logging
import os
from typing import Any, Callable, Dict, Optional

from src.workflow_mapping_validation import (
    load_workflow_mappings,
    resolve_workflow_filename,
    validate_workflow_directory,
)
try:
    from .workflow_task_patchers import TASK_SPECIFIC_PATCHERS
except ImportError:
    from workflow_task_patchers import TASK_SPECIFIC_PATCHERS

logger = logging.getLogger(__name__)


class WorkflowPatcher:
    def __init__(self, workflows_dir: str):
        self.workflows_dir = workflows_dir
        self.mappings = self.load_mappings(validate=True)

    def load_mappings(self, *, validate: bool = False) -> Dict[str, Any]:
        if validate:
            return validate_workflow_directory(self.workflows_dir)
        return load_workflow_mappings(self.workflows_dir)

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
        filename = resolve_workflow_filename(task_type)

        path = os.path.join(self.workflows_dir, filename)
        if not os.path.exists(path):
            logger.error(f"Workflow file {path} not found")
            return None

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            data = self.strip_meta(data)

            if (
                isinstance(data, dict)
                and "nodes" in data
                and isinstance(data["nodes"], list)
            ):
                logger.warning(
                    f"Workflow {filename} seems to be in UI format (contains 'nodes' list). Please export in API format."
                )
            return data

    def patch_workflow(
        self, task_type: str, workflow: Dict[str, Any], params: Dict[str, Any]
    ) -> Dict[str, Any]:
        # Deep copy to avoid modifying template
        wf = json.loads(json.dumps(workflow))

        # Inject a random seed to prevent ComfyUI from fully caching the workflow
        # which would result in no output generation and no history record.
        import random

        if "seed" not in params or params["seed"] is None:
            # Use a smaller max integer to prevent "value_bigger_than_max" errors in rgthree nodes
            params["seed"] = random.randint(1, 1125899906842624)

        # Reload mappings to ensure it's up to date
        self.mappings = self.load_mappings(validate=False)

        # If we have mappings, use them
        mapping = self.mappings.get(task_type, {})

        if (
            task_type == "i2i_draw"
            and "prompt" in params
            and isinstance(params["prompt"], str)
        ):
            params["prompt"] = f"{params['prompt']}, 身体姿势保持不变"

        for key, value in params.items():
            if key in mapping:
                node_id = str(mapping[key])
                input_name = mapping.get(f"{key}_input", "image")  # Default input name
                if node_id in wf:
                    if "inputs" not in wf[node_id]:
                        wf[node_id]["inputs"] = {}
                    wf[node_id]["inputs"][input_name] = value
            else:
                # For heuristic patch of images where the mapping wasn't specific enough
                if key in [
                    "image",
                    "image2",
                    "image3",
                    "image4",
                    "images",
                    "face_image",
                    "body_image",
                ]:
                    continue  # Ignore heuristic patch for images to prevent overriding wrong nodes

                # Heuristic search
                self.heuristic_patch(wf, key, value)

        task_specific_patcher = TASK_SPECIFIC_PATCHERS.get(task_type)
        if task_specific_patcher is not None:
            task_specific_patcher(
                wf,
                task_type=task_type,
                params=params,
                mapping=mapping,
                set_node_input=self._set_node_input,
                unique_id=params.get("seed"),
            )

        return wf

    def _set_node_input(
        self,
        workflow: Dict[str, Any],
        *,
        node_id: str,
        input_name: str,
        value: Any,
    ) -> None:
        node = workflow.get(node_id)
        if not isinstance(node, dict):
            return
        inputs = node.setdefault("inputs", {})
        inputs[input_name] = value

    def _patch_prompt_node(
        self,
        *,
        node: dict[str, Any],
        inputs: dict[str, Any],
        class_type: str,
        value: Any,
        **_: Any,
    ) -> None:
        if not (
            "CLIPTextEncode" in class_type
            or "Prompt" in class_type
            or "TextEncode" in class_type
        ):
            return
        meta_title = node.get("_meta", {}).get("title", "").lower()
        if "negative" in meta_title:
            return
        if "text" in inputs:
            inputs["text"] = value
        if "prompt" in inputs:
            inputs["prompt"] = value

    def _patch_seed_node(
        self,
        *,
        inputs: dict[str, Any],
        class_type: str,
        value: Any,
        **_: Any,
    ) -> None:
        if "Sampler" not in class_type and "Seed" not in class_type:
            return
        if "seed" in inputs and inputs["seed"] in (-1, None):
            inputs["seed"] = value
        if "noise_seed" in inputs and inputs["noise_seed"] in (-1, None):
            inputs["noise_seed"] = value

    def _patch_sampler_steps_node(
        self,
        *,
        inputs: dict[str, Any],
        class_type: str,
        value: Any,
        **_: Any,
    ) -> None:
        if "Sampler" in class_type and "steps" in inputs:
            inputs["steps"] = value

    def _patch_sampler_cfg_node(
        self,
        *,
        inputs: dict[str, Any],
        class_type: str,
        value: Any,
        **_: Any,
    ) -> None:
        if "Sampler" in class_type and "cfg" in inputs:
            inputs["cfg"] = value

    def _patch_width_node(
        self,
        *,
        inputs: dict[str, Any],
        class_type: str,
        value: Any,
        **_: Any,
    ) -> None:
        if "EmptyLatentImage" in class_type:
            inputs["width"] = value
        elif "FindPerfectResolution" in class_type:
            inputs["desired_width"] = value

    def _patch_height_node(
        self,
        *,
        inputs: dict[str, Any],
        class_type: str,
        value: Any,
        **_: Any,
    ) -> None:
        if "EmptyLatentImage" in class_type:
            inputs["height"] = value
        elif "FindPerfectResolution" in class_type:
            inputs["desired_height"] = value

    def _patch_lora_name_node(
        self,
        *,
        node_id: str,
        inputs: dict[str, Any],
        class_type: str,
        value: Any,
        **_: Any,
    ) -> None:
        if "Power Lora Loader (rgthree)" not in class_type:
            return
        if str(node_id) == "272":
            inputs["lora_1"] = {
                "on": True,
                "lora": f"{value}_high_noise.safetensors",
                "strength": 1,
            }
        elif str(node_id) == "273":
            inputs["lora_1"] = {
                "on": True,
                "lora": f"{value}_low_noise.safetensors",
                "strength": 1,
            }

    def _patch_length_node(
        self,
        *,
        inputs: dict[str, Any],
        class_type: str,
        value: Any,
        **_: Any,
    ) -> None:
        if "PainterI2V" in class_type:
            inputs["length"] = value

    def _heuristic_patch_handlers(self) -> dict[str, Callable[..., None]]:
        return {
            "prompt": self._patch_prompt_node,
            "seed": self._patch_seed_node,
            "steps": self._patch_sampler_steps_node,
            "cfg": self._patch_sampler_cfg_node,
            "width": self._patch_width_node,
            "height": self._patch_height_node,
            "lora_name": self._patch_lora_name_node,
            "length": self._patch_length_node,
        }

    def heuristic_patch(self, workflow: Dict[str, Any], key: str, value: Any):
        # This is a best-effort patcher for API format workflows
        handler = self._heuristic_patch_handlers().get(key)
        if handler is None:
            return

        for node_id, node in workflow.items():
            if not isinstance(node, dict) or "inputs" not in node:
                continue

            inputs = node["inputs"]
            class_type = node.get("class_type", "")
            handler(
                node_id=str(node_id),
                node=node,
                inputs=inputs,
                class_type=class_type,
                value=value,
            )
