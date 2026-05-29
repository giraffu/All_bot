import json
import logging
import os
from typing import Any, Dict, Optional

from src.lora_catalog import normalize_ltx_video_lora_items
from src.workflow_mapping_validation import (
    load_workflow_mappings,
    resolve_workflow_filename,
    validate_workflow_directory,
)

logger = logging.getLogger(__name__)


LTX_VIDEO_ADDITIONAL_LORA_NODE_IDS = ("256",)
LTX_VIDEO_FIRST_PASS_MODEL_NODE_ID = "191"
LTX_VIDEO_FIRST_PASS_CLIP_NODE_ID = "189"
LTX_VIDEO_MAX_LORA_SLOTS = 10
WAN22_VIDEO_V2_REMOVABLE_NODE_IDS = (
    "9",  # VHS_PruneOutputs
    "2502",  # mini preview gif output, not part of the product contract
    "2501",  # UI-only DaSiWa output switch; API mode rewires extract-last-frame directly
    "2547",  # PreviewAny
    "2548",  # PreviewAny
    "2573",  # UI-only DaSiWa output switch for upscale toggle
    "2587",  # PreviewAny
    "2589",  # PreviewAny
    "2584",  # UI-only DaSiWa output switch for perfect-loop toggle
    "2601",  # UI-only DaSiWa output switch for perf bypass
    "2602",  # UI-only DaSiWa output switch for perf bypass
    "2605",  # UI-only DaSiWa output switch for perf bypass
    "2615",  # UI-only DaSiWa output switch for color-match toggle
    "2623",  # no-op DaSiWa mute toggle
    "2624",  # no-op DaSiWa mute toggle
)


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
                    "images",
                    "face_image",
                    "body_image",
                ]:
                    continue  # Ignore heuristic patch for images to prevent overriding wrong nodes

                # Heuristic search
                self.heuristic_patch(wf, key, value)

        # Dynamic JSON pruning for img2img task to avoid empty nodes and blank inputs
        if task_type in ["img2img", "img2img_lora"]:
            # Handle LoRA dynamically (default to no LoRA)
            lora_name = params.get("lora_name", "")
            if lora_name and str(lora_name).strip() != "":
                if "32" in wf and "inputs" in wf["32"]:
                    wf["32"]["inputs"]["lora_name"] = lora_name
                    if params.get("lora_strength") is not None:
                        wf["32"]["inputs"]["strength_model"] = float(
                            params["lora_strength"]
                        )
            else:
                # Strip LoRA node and connect KSampler (2) directly to Checkpoint (1)
                if "2" in wf and "inputs" in wf["2"]:
                    wf["2"]["inputs"]["model"] = ["1", 0]
                if "32" in wf:
                    wf.pop("32", None)

            # 3 is the TextEncodeQwenImageEditPlus node
            text_encode_node_id = str(mapping.get("prompt", "3"))

            # Clean up image2 if not provided
            if "image2" not in params or not params["image2"]:
                if text_encode_node_id in wf and "inputs" in wf[text_encode_node_id]:
                    wf[text_encode_node_id]["inputs"].pop("image2", None)
                node_to_pop = str(mapping.get("image2", "20"))
                if node_to_pop in wf:
                    wf.pop(node_to_pop, None)
                if "21" in wf:
                    wf.pop("21", None)  # ImageScaleToTotalPixels node 21

            # Clean up image3 if not provided
            if "image3" not in params or not params["image3"]:
                if text_encode_node_id in wf and "inputs" in wf[text_encode_node_id]:
                    wf[text_encode_node_id]["inputs"].pop("image3", None)
                node_to_pop = str(mapping.get("image3", "30"))
                if node_to_pop in wf:
                    wf.pop(node_to_pop, None)
                if "31" in wf:
                    wf.pop("31", None)  # ImageScaleToTotalPixels node 31

        elif task_type == "i2i_draw":
            # Hardcode negative prompt to a space
            if "109" in wf and "inputs" in wf["109"]:
                wf["109"]["inputs"]["text"] = " "

        elif task_type == "ltx_video":
            # Remove the preview override node as it causes AttributeError in API mode (serv.last_node_id is None)
            if "210" in wf:
                wf.pop("210", None)
            if "5" in wf:
                wf.pop("5", None)
            if "59" in wf:
                wf.pop("59", None)
            # In the I2V5 topology, removing node 210 requires reconnecting node 8 to 256.
            # Reconnecting to 7 would create a 7 -> 8 -> 7 cycle.
            if "8" in wf and "inputs" in wf["8"]:
                wf["8"]["inputs"]["model"] = ["256", 0]

            # Prevent caching of output nodes by ensuring a unique filename_prefix per task
            # Using random integer as task_id if not present (since workflow_patcher only gets params)
            unique_id = params.get("seed", random.randint(1, 1125899906842624))
            for node_id, node in wf.items():
                if (
                    isinstance(node, dict)
                    and node.get("class_type") == "VHS_VideoCombine"
                ):
                    if "inputs" in node:
                        node["inputs"]["filename_prefix"] = (
                            f"ltx_video_{unique_id}_{node_id}"
                        )

            lora_items = normalize_ltx_video_lora_items(
                params.get("lora_items"),
                max_items=3,
            )
            if not lora_items:
                lora_name = str(params.get("lora_name") or "").strip()
                if lora_name:
                    lora_strength = params.get("lora_strength")
                    lora_items = normalize_ltx_video_lora_items(
                        [
                            {
                                "name": lora_name,
                                "strength": lora_strength,
                            }
                        ],
                        max_items=3,
                    )

            if lora_items:
                self._patch_ltx_video_lora(wf, lora_items=lora_items)
            else:
                self._strip_ltx_video_lora_nodes(wf)
        elif task_type == "wan22_video_v2":
            self._patch_wan22_video_v2(
                wf,
                params=params,
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

    def _patch_wan22_video_v2(
        self,
        workflow: Dict[str, Any],
        *,
        params: Dict[str, Any],
        unique_id: Any,
    ) -> None:
        # Strip API-irrelevant preview / utility output nodes so Comfy 0.22 focuses
        # on the business outputs (`28` video and optional `2503` last frame).
        for node_id in WAN22_VIDEO_V2_REMOVABLE_NODE_IDS:
            workflow.pop(node_id, None)

        # Keep the task contract fixed at 5 seconds for the v2 launch.
        self._set_node_input(
            workflow,
            node_id="2586",
            input_name="value",
            value=5,
        )
        self._set_node_input(
            workflow,
            node_id="2581",
            input_name="expression",
            value="max(1, round(( a - 1 ) / b))",
        )

        use_end_frame = bool(params.get("use_end_frame")) and bool(params.get("end_image"))
        color_match = bool(params.get("color_match"))
        perfect_loop = bool(params.get("perfect_loop"))
        upscale = bool(params.get("upscale"))
        extract_last_frame = bool(params.get("extract_last_frame"))

        # `I2V - FLF2V switch` is inverted:
        # True -> I2V branch, False -> FLF2V branch.
        self._set_node_input(
            workflow,
            node_id="2557",
            input_name="value",
            value=not use_end_frame,
        )

        start_image = params.get("image")
        if not use_end_frame and start_image:
            # API validation still touches the FLF2V branch, so keep its optional
            # end-frame loader valid even when the branch is disabled.
            self._set_node_input(
                workflow,
                node_id="24",
                input_name="image",
                value=start_image,
            )

        decoded_frames_ref = ["2614", 0] if color_match else ["2612", 0]
        self._set_node_input(
            workflow,
            node_id="2542",
            input_name="clip_frames",
            value=decoded_frames_ref,
        )

        video_frames_ref = ["2574", 0] if perfect_loop else decoded_frames_ref
        if not perfect_loop:
            self._set_node_input(
                workflow,
                node_id="2563",
                input_name="image",
                value=video_frames_ref,
            )
            self._set_node_input(
                workflow,
                node_id="2575",
                input_name="image",
                value=video_frames_ref,
            )

        final_frames_ref = ["2575", 0] if upscale else video_frames_ref

        # Rebuild and gate the last-frame extraction branch in API mode.
        if extract_last_frame:
            self._set_node_input(
                workflow,
                node_id="2700",
                input_name="batch_index",
                value=16384,
            )
            self._set_node_input(
                workflow,
                node_id="2700",
                input_name="length",
                value=1,
            )
            self._set_node_input(
                workflow,
                node_id="2700",
                input_name="image",
                value=final_frames_ref,
            )
            self._set_node_input(
                workflow,
                node_id="2503",
                input_name="images",
                value=["2700", 0],
            )
        else:
            workflow.pop("2503", None)
            workflow.pop("2700", None)

        safe_unique_id = unique_id or "wan22"
        self._set_node_input(
            workflow,
            node_id="28",
            input_name="filename_prefix",
            value=f"wan22_video_v2_{safe_unique_id}_video",
        )
        self._set_node_input(
            workflow,
            node_id="28",
            input_name="images",
            value=final_frames_ref,
        )
        self._set_node_input(
            workflow,
            node_id="2503",
            input_name="filename_prefix",
            value=f"wan22_video_v2_{safe_unique_id}_last_frame",
        )

    def _patch_ltx_video_lora(
        self,
        workflow: Dict[str, Any],
        *,
        lora_items: list[dict[str, Any]],
    ) -> None:
        for node_id in LTX_VIDEO_ADDITIONAL_LORA_NODE_IDS:
            node = workflow.get(node_id)
            if not isinstance(node, dict):
                continue
            inputs = node.setdefault("inputs", {})
            for slot_index in range(1, LTX_VIDEO_MAX_LORA_SLOTS + 1):
                inputs.pop(f"lora_{slot_index}", None)

            for index, item in enumerate(lora_items[:LTX_VIDEO_MAX_LORA_SLOTS], start=1):
                inputs[f"lora_{index}"] = {
                    "on": True,
                    "lora": str(item["name"]),
                    "strength": float(item["strength"]),
                }
            inputs["model"] = [LTX_VIDEO_FIRST_PASS_MODEL_NODE_ID, 0]
            inputs["clip"] = [LTX_VIDEO_FIRST_PASS_CLIP_NODE_ID, 0]

    def _strip_ltx_video_lora_nodes(self, workflow: Dict[str, Any]) -> None:
        for node_id in LTX_VIDEO_ADDITIONAL_LORA_NODE_IDS:
            workflow.pop(node_id, None)

        model_node = workflow.get("8")
        if isinstance(model_node, dict):
            inputs = model_node.get("inputs")
            if isinstance(inputs, dict):
                inputs["model"] = [LTX_VIDEO_FIRST_PASS_MODEL_NODE_ID, 0]

    def heuristic_patch(self, workflow: Dict[str, Any], key: str, value: Any):
        # This is a best-effort patcher for API format workflows
        for node_id, node in workflow.items():
            if not isinstance(node, dict) or "inputs" not in node:
                continue

            inputs = node["inputs"]
            class_type = node.get("class_type", "")

            if key == "prompt" and (
                "CLIPTextEncode" in class_type
                or "Prompt" in class_type
                or "TextEncode" in class_type
            ):
                # Ensure we only patch Positive Prompts, not Negative Prompts
                meta_title = node.get("_meta", {}).get("title", "").lower()
                if "negative" not in meta_title:
                    if "text" in inputs:
                        inputs["text"] = value
                    if "prompt" in inputs:
                        inputs["prompt"] = value

            elif key == "seed" and ("Sampler" in class_type or "Seed" in class_type):
                # Only inject seed if the current value is a placeholder or -1, or if we passed None but we shouldn't because json.loads might convert it
                if "seed" in inputs:
                    if inputs["seed"] == -1 or inputs["seed"] is None:
                        inputs["seed"] = value
                if "noise_seed" in inputs:
                    if inputs["noise_seed"] == -1 or inputs["noise_seed"] is None:
                        inputs["noise_seed"] = value

            elif key == "steps" and "Sampler" in class_type:
                if "steps" in inputs:
                    inputs["steps"] = value

            elif key == "cfg" and "Sampler" in class_type:
                if "cfg" in inputs:
                    inputs["cfg"] = value

            elif key == "width" and "EmptyLatentImage" in class_type:
                inputs["width"] = value

            elif key == "height" and "EmptyLatentImage" in class_type:
                inputs["height"] = value

            elif key == "width" and "FindPerfectResolution" in class_type:
                inputs["desired_width"] = value

            elif key == "height" and "FindPerfectResolution" in class_type:
                inputs["desired_height"] = value

            elif key == "lora_name" and "Power Lora Loader (rgthree)" in class_type:
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

            elif key == "length" and "PainterI2V" in class_type:
                inputs["length"] = value
