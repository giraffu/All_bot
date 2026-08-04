from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from typing import Any

from .config_loader import ControllerConfig
from .pipeline_policy import pipeline_environment_for_profile
from .runpod_profile_catalog import (
    RUNPOD_FACE_SWAP_WORKFLOW_OVERRIDES,
    RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES,
    RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES,
)
from .types import Assignment, ComfyInstance, GpuNode, RuntimePlanItem, TaskProfile


DOCKER_RUNTIME_KIND = "docker_container"
HOST_RUNTIME_KIND = "host_service"
STANDARD_RUNTIME_SHAPE = "standard_comfy_runtime"
RUNPOD_AIO_RUNTIME_SHAPE = "runpod_all_in_one"
DEFAULT_LAN_AIO_ENVIRONMENT = "cloud-test"
LAN_AIO_DISABLE_DYNAMIC_VRAM_PROFILES = frozenset(
    {
        "image_to_video",
        "wan22_video_v2",
    }
)
LAN_AIO_RESERVE_VRAM_GB_BY_PROFILE = {
    "ltx_t2v": 5,
    "ltx_unified": 5,
}
LAN_AIO_PYTORCH_CROSS_ATTENTION_PROFILES = frozenset({"ltx_unified"})
LAN_AIO_FAST_DISK_PROFILES = frozenset({"minimax_h3"})
LAN_AIO_DISABLE_PINNED_MEMORY_PROFILES = frozenset({"minimax_h3"})
LAN_AIO_SCAIL2_WORKFLOW_OVERRIDES = json.dumps(
    {
        "scail2_action_transfer": "SCAIL-2_Animation_multi-char_audio.api.json",
        "scail2_action_transfer_long": (
            "SCAIL-2_Animation_WAN-Context-Windows.api.json"
        ),
        "scail2_video_replacement": "SCAIL-2_Replacement_audio.api.json",
        "scail2_face_swap_v2": (
            "SCAIL-2_FaceSwap_v10_firstframe_faceswap_replacement_audio.api.json"
        ),
    },
    separators=(",", ":"),
)
LAN_AIO_SCAIL2_ENV = {
    "COMFYUI_DIR": "/opt/ComfyUI",
}
LAN_AIO_LTX_T2V_ENV = {
    "COMFYUI_DIR": "/opt/ComfyUI",
}
LAN_AIO_MINIMAX_H3_ENV = {
    "COMFYUI_DIR": "/opt/ComfyUI",
}
LAN_AIO_LTX_UNIFIED_WORKFLOW_OVERRIDES = json.dumps(
    {
        "ltx_video": "LTX 2.3 I2V 10Eros LoRA.json",
        "ltx_video_flf2v": "LTX 2.3 FLF2V 10Eros LoRA.json",
        "ltx_video_v2v_audio": "LTX 2.3 V2V Audio 10Eros LoRA.json",
    },
    separators=(",", ":"),
)
LAN_AIO_MINIMAX_H3_WORKFLOW_OVERRIDES = json.dumps(
    {
        "minimax_h3_t2v": "MiniMax H3 T2V.api.json",
        "minimax_h3_i2v": "MiniMax H3 I2V.api.json",
        "minimax_h3_flf2v": "MiniMax H3 FLF2V.api.json",
        "minimax_h3_ref2v": "MiniMax H3 REF2V.api.json",
    },
    separators=(",", ":"),
)
LAN_AIO_ALL_WORKFLOW_OVERRIDES = json.dumps(
    {
        **json.loads(RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES),
        **json.loads(LAN_AIO_LTX_UNIFIED_WORKFLOW_OVERRIDES),
        **json.loads(LAN_AIO_SCAIL2_WORKFLOW_OVERRIDES),
    },
    separators=(",", ":"),
)
LAN_AIO_WORKFLOW_OVERRIDES_BY_PROFILE = {
    "all": LAN_AIO_ALL_WORKFLOW_OVERRIDES,
    "face_swap": RUNPOD_FACE_SWAP_WORKFLOW_OVERRIDES,
    "i2i_pro": RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES,
    "ltx_video": RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES,
    "ltx_unified": LAN_AIO_LTX_UNIFIED_WORKFLOW_OVERRIDES,
    "minimax_h3": LAN_AIO_MINIMAX_H3_WORKFLOW_OVERRIDES,
    "scail2": LAN_AIO_SCAIL2_WORKFLOW_OVERRIDES,
    "scail2_flex": LAN_AIO_SCAIL2_WORKFLOW_OVERRIDES,
}
LAN_AIO_EXTRA_ENV_BY_PROFILE = {
    "all": LAN_AIO_LTX_T2V_ENV,
    "scail2": LAN_AIO_SCAIL2_ENV,
    "scail2_flex": LAN_AIO_SCAIL2_ENV,
    "ltx_t2v": LAN_AIO_LTX_T2V_ENV,
    "ltx_unified": LAN_AIO_LTX_T2V_ENV,
    "minimax_h3": LAN_AIO_MINIMAX_H3_ENV,
}
LAN_AIO_ENVIRONMENTS = {
    "cloud-test": {
        "central_url": "https://worker-central-test.aivison.it.com",
        "user_data_bucket": "user-data-test",
    },
    "cloud-prod": {
        "central_url": "https://worker-central.aivison.it.com",
        "user_data_bucket": "user-data-prod",
    },
}
DEFAULT_LAN_MODEL_CACHE_BUCKET = "allbot-model-cache"


@dataclass(frozen=True)
class RuntimeRenderOverrides:
    host_port: int | None = None
    container_name: str | None = None
    api_url: str | None = None
    ws_url: str | None = None
    runtime_shape: str | None = None
    agent_id: str | None = None
    central_url: str | None = None
    environment: str | None = None
    target_task_types: tuple[str, ...] | None = None
    gpu_index: int | None = None
    gpu_device_id: str | None = None

    def __post_init__(self) -> None:
        if self.host_port is not None and not 1 <= self.host_port <= 65535:
            raise ValueError("--host-port must be between 1 and 65535")
        if self.gpu_index is not None and self.gpu_index < 0:
            raise ValueError("--gpu-index must be non-negative")
        if self.gpu_device_id is not None and not self.gpu_device_id.strip():
            raise ValueError("--gpu-device-id must not be empty")
        if self.runtime_shape is not None and self.runtime_shape not in {
            STANDARD_RUNTIME_SHAPE,
            RUNPOD_AIO_RUNTIME_SHAPE,
        }:
            raise ValueError(
                "--runtime-shape must be standard_comfy_runtime or runpod_all_in_one"
            )
        if (
            self.environment is not None
            and self.environment not in LAN_AIO_ENVIRONMENTS
        ):
            allowed = ", ".join(sorted(LAN_AIO_ENVIRONMENTS))
            raise ValueError(f"--environment must be one of: {allowed}")
        if self.target_task_types is not None and not all(
            task_type.strip() for task_type in self.target_task_types
        ):
            raise ValueError("--target-task-types must not contain empty values")

    @property
    def has_any(self) -> bool:
        return any(
            value is not None
            for value in (
                self.host_port,
                self.container_name,
                self.api_url,
                self.ws_url,
                self.runtime_shape,
                self.agent_id,
                self.central_url,
                self.environment,
                self.target_task_types,
                self.gpu_index,
                self.gpu_device_id,
            )
        )


class RuntimePlanner:
    def __init__(self, config: ControllerConfig):
        self.config = config

    def build_all_plans(self) -> list[RuntimePlanItem]:
        return [
            self.build_plan(assignment_id)
            for assignment_id, assignment in self.config.assignments.items()
            if assignment.enabled
        ]

    def build_plan(
        self,
        assignment_id: str,
        *,
        target_profile_id: str | None = None,
        overrides: RuntimeRenderOverrides | None = None,
    ) -> RuntimePlanItem:
        overrides = overrides or RuntimeRenderOverrides()
        assignment = self._assignment_for(assignment_id)
        node = self._node_for(assignment)
        comfy = self._comfy_for(node, assignment)
        profile = self._profile_for(target_profile_id or assignment.profile_id)
        self._validate_overrides(
            assignment=assignment,
            comfy=comfy,
            overrides=overrides,
            for_render=False,
        )
        target_task_types = self._target_task_types(
            assignment=assignment,
            profile=profile,
            target_profile_id=target_profile_id,
            overrides=overrides,
        )
        bundle_versions = self._bundle_versions(profile)
        worker_env = self._worker_env(
            assignment=assignment,
            node=node,
            comfy=comfy,
            profile=profile,
            target_task_types=target_task_types,
            bundle_versions=bundle_versions,
            overrides=overrides,
        )
        warnings = self._warnings(
            assignment=assignment,
            node=node,
            comfy=comfy,
            profile=profile,
            target_task_types=target_task_types,
            overrides=overrides,
        )
        return RuntimePlanItem(
            assignment_id=assignment.id,
            worker_id=assignment.worker_id,
            node_id=node.id,
            comfy_id=comfy.id,
            runtime_kind=comfy.comfy_runtime_kind,
            runtime_managed=comfy.comfy_runtime_managed,
            target_profile_id=profile.id,
            target_task_types=target_task_types,
            model_bundle_versions=bundle_versions,
            worker_env=worker_env,
            runtime=self._runtime_payload(node=node, comfy=comfy, overrides=overrides),
            diff=self._diff(
                node=node,
                comfy=comfy,
                profile=profile,
                target_task_types=target_task_types,
                bundle_versions=bundle_versions,
                overrides=overrides,
            ),
            warnings=tuple(warnings),
            commands=tuple(
                self._dry_run_commands(
                    assignment=assignment,
                    node=node,
                    comfy=comfy,
                    profile=profile,
                    target_task_types=target_task_types,
                    overrides=overrides,
                )
            ),
        )

    def render_compose(
        self,
        assignment_id: str,
        *,
        target_profile_id: str | None = None,
        overrides: RuntimeRenderOverrides | None = None,
    ) -> str:
        overrides = overrides or RuntimeRenderOverrides()
        assignment = self._assignment_for(assignment_id)
        node = self._node_for(assignment)
        comfy = self._comfy_for(node, assignment)
        profile = self._profile_for(target_profile_id or assignment.profile_id)
        target_task_types = self._target_task_types(
            assignment=assignment,
            profile=profile,
            target_profile_id=target_profile_id,
            overrides=overrides,
        )
        self._validate_overrides(
            assignment=assignment,
            comfy=comfy,
            overrides=overrides,
            for_render=True,
        )
        if comfy.comfy_runtime_kind != DOCKER_RUNTIME_KIND:
            raise ValueError(
                f"{assignment.id} uses {comfy.comfy_runtime_kind}; "
                "runtime-render only supports docker_container"
            )
        if self._effective_runtime_shape(comfy, overrides) == RUNPOD_AIO_RUNTIME_SHAPE:
            return self._render_runpod_all_in_one_compose(
                assignment=assignment,
                node=node,
                comfy=comfy,
                profile=profile,
                target_task_types=target_task_types,
                overrides=overrides,
            )
        service_name = self._effective_container_name(comfy, overrides)
        image_ref = profile.image_ref or comfy.image
        if not image_ref:
            raise ValueError(
                f"{profile.id} has no image_ref and {comfy.id} has no image"
            )

        bundle_versions = self._bundle_versions(profile)
        host_port = self._effective_host_port(comfy, overrides)
        container_port = comfy.container_port or 8188
        render_mode = self._render_mode(comfy, overrides)
        production_port_unchanged = self._production_port_unchanged(comfy, overrides)
        api_url = self._effective_api_url(node=node, comfy=comfy, overrides=overrides)
        ws_url = self._effective_ws_url(node=node, comfy=comfy, overrides=overrides)
        compose = {
            "name": self._compose_project_name(
                node=node,
                comfy=comfy,
                overrides=overrides,
            ),
            "services": {
                service_name: {
                    "image": image_ref,
                    "container_name": service_name,
                    "restart": "unless-stopped",
                    "ports": [f"{host_port}:{container_port}"],
                    "environment": {
                        "TZ": "Asia/Shanghai",
                        "NVIDIA_VISIBLE_DEVICES": str(
                            self._effective_gpu_device_id(comfy, overrides)
                        ),
                        "COMFY_HOST": "0.0.0.0",
                        "COMFY_PORT": str(container_port),
                        "COMFY_MODEL_DIR": "/data/comfy/models",
                        "COMFY_INPUT_DIR": "/data/comfy/input",
                        "COMFY_OUTPUT_DIR": "/data/comfy/output",
                        "COMFY_TEMP_DIR": "/data/comfy/temp",
                        "COMFY_WORKFLOWS_DIR": "/data/comfy/workflows",
                        "COMFY_CUSTOM_NODES_DIR": "/data/comfy/custom_nodes",
                    },
                    "volumes": self._compose_volumes(comfy),
                    "labels": {
                        "allbot.gpu_pool.managed": "true",
                        "allbot.gpu_pool.node_id": node.id,
                        "allbot.gpu_pool.comfy_id": comfy.id,
                        "allbot.gpu_pool.worker_id": assignment.worker_id,
                        "allbot.gpu_pool.runtime_profile": profile.runtime_profile,
                        "allbot.gpu_pool.render_mode": render_mode,
                        "allbot.gpu_pool.production_port_unchanged": str(
                            production_port_unchanged
                        ).lower(),
                    },
                    "healthcheck": {
                        "test": [
                            "CMD-SHELL",
                            (
                                "curl -fsS "
                                f"http://127.0.0.1:{container_port}"
                                f"{comfy.health.get('system_stats', '/system_stats')} "
                                ">/dev/null || exit 1"
                            ),
                        ],
                        "interval": "30s",
                        "timeout": "8s",
                        "retries": 5,
                        "start_period": "60s",
                    },
                    "gpus": [
                        {
                            "driver": "nvidia",
                            "device_ids": [
                                self._effective_gpu_device_id(comfy, overrides)
                            ],
                            "capabilities": ["gpu"],
                        }
                    ],
                }
            },
            "x-allbot-runtime": {
                "assignment_id": assignment.id,
                "worker_id": assignment.worker_id,
                "runtime_profile": profile.runtime_profile,
                "image_ref": image_ref,
                "model_bundle_versions": bundle_versions,
                "rendered_for": (
                    "canary_dry_run_review"
                    if render_mode == "canary"
                    else "dry_run_review"
                ),
                "render_mode": render_mode,
                "production_port_unchanged": production_port_unchanged,
                "host_port": host_port,
                "container_port": container_port,
                "container_name": service_name,
                "comfy_api_url": api_url,
                "comfy_ws_url": ws_url,
            },
        }
        try:
            import yaml  # type: ignore
        except (
            Exception
        ) as exc:  # pragma: no cover - config loading already requires yaml
            raise RuntimeError("runtime-render requires PyYAML") from exc
        return yaml.safe_dump(compose, allow_unicode=True, sort_keys=False)

    def _render_runpod_all_in_one_compose(
        self,
        *,
        assignment: Assignment,
        node: GpuNode,
        comfy: ComfyInstance,
        profile: TaskProfile,
        target_task_types: tuple[str, ...],
        overrides: RuntimeRenderOverrides,
    ) -> str:
        image_ref = profile.all_in_one_image_ref or profile.image_ref or comfy.image
        if not image_ref:
            raise ValueError(
                f"{profile.id} has no all_in_one_image_ref/image_ref and {comfy.id} has no image"
            )

        bundle_versions = self._bundle_versions(profile)
        host_port = self._effective_host_port(comfy, overrides)
        render_mode = self._render_mode(comfy, overrides)
        production_port_unchanged = self._production_port_unchanged(comfy, overrides)
        container_name = (
            overrides.container_name
            or self._default_runpod_aio_container_name(
                node=node,
                comfy=comfy,
                profile=profile,
                render_mode=render_mode,
            )
        )
        runtime_root = comfy.runtime_root or "/srv/allbot/runpod-runtime"
        slot_id = comfy.slot_id or f"{node.id}-gpu{comfy.gpu_index or 0}"
        workspace_key = profile.lan_workspace_key or profile.runtime_profile
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", workspace_key):
            raise ValueError(
                f"{profile.id} has invalid lan_workspace_key: {workspace_key!r}"
            )
        model_workspace_key = profile.lan_model_workspace_key or workspace_key
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", model_workspace_key):
            raise ValueError(
                f"{profile.id} has invalid lan_model_workspace_key: "
                f"{model_workspace_key!r}"
            )
        workspace_host_dir = (
            f"{runtime_root.rstrip('/')}/slots/{slot_id}/profiles/"
            f"{workspace_key}/workspace"
        )
        model_workspace_host_dir = (
            f"{runtime_root.rstrip('/')}/slots/{slot_id}/profiles/"
            f"{model_workspace_key}/workspace"
        )
        volumes = [f"{workspace_host_dir}:/workspace"]
        model_cache_endpoint = comfy.model_cache_endpoint or "http://192.168.1.115:9010"
        environment = self._effective_lan_aio_environment(overrides)
        environment_settings = LAN_AIO_ENVIRONMENTS[environment]
        central_url = (
            overrides.central_url or environment_settings["central_url"]
        ).rstrip("/")
        user_data_bucket = environment_settings["user_data_bucket"]
        agent_id = overrides.agent_id or assignment.worker_id
        supported_task_types = ",".join(target_task_types)
        preferred_task_types = profile.preferred_task_types
        unsupported_preferred = sorted(
            set(preferred_task_types) - set(target_task_types)
        )
        if unsupported_preferred:
            raise ValueError(
                f"profile {profile.id} preferred task types are not enabled by "
                f"slot {slot_id}: {', '.join(unsupported_preferred)}"
            )
        preferred_task_types_csv = ",".join(preferred_task_types)
        prefetch_task_types = (
            preferred_task_types_csv
            if preferred_task_types
            else supported_task_types
        )
        model_prefix = profile.model_prefix or f"{profile.id}/unversioned"
        model_manifest_key = (
            profile.model_manifest_key or f"{model_prefix.rstrip('/')}/manifest.json"
        )
        model_manifest_keys = profile.model_manifest_keys or (model_manifest_key,)
        workflow_overrides = LAN_AIO_WORKFLOW_OVERRIDES_BY_PROFILE.get(
            profile.runtime_profile
        )
        extra_environment = LAN_AIO_EXTRA_ENV_BY_PROFILE.get(
            profile.runtime_profile, {}
        )
        pipeline_environment = pipeline_environment_for_profile(profile.id)
        comfyui_dir = (
            "/opt/ComfyUI"
            if node.accelerator == "rocm"
            else str(extra_environment.get("COMFYUI_DIR") or "/workspace/ComfyUI")
        )
        model_target_dir = f"{comfyui_dir.rstrip('/')}/models"
        # Keep the model cache as an explicit mount even when the model and
        # runtime workspaces share the same profile directory.  The baked
        # ComfyUI runtime uses /opt/ComfyUI while /workspace only persists its
        # mutable bundle; without this mount the agent sees an empty
        # /opt/ComfyUI/models and downloads the entire manifest into the
        # container layer on every start.
        volumes.append(
            f"{model_workspace_host_dir}/ComfyUI/models:{model_target_dir}"
        )
        state_root = "/workspace/allbot-state"
        gpu_device_id = self._effective_gpu_device_id(comfy, overrides)
        accelerator_environment = (
            {
                "HIP_VISIBLE_DEVICES": gpu_device_id,
                "ROCR_VISIBLE_DEVICES": gpu_device_id,
                "POOL_ACCELERATOR": "rocm",
            }
            if node.accelerator == "rocm"
            else {
                "NVIDIA_VISIBLE_DEVICES": gpu_device_id,
                "POOL_ACCELERATOR": "nvidia",
            }
        )
        accelerator_service = (
            {
                "devices": ["/dev/kfd:/dev/kfd", "/dev/dri:/dev/dri"],
                "group_add": ["video", "render"],
                "ipc": "host",
                "security_opt": ["seccomp=unconfined"],
            }
            if node.accelerator == "rocm"
            else {
                "gpus": [
                    {
                        "driver": "nvidia",
                        "device_ids": [gpu_device_id],
                        "capabilities": ["gpu"],
                    }
                ]
            }
        )
        compose = {
            "name": self._compose_project_name(
                node=node,
                comfy=comfy,
                overrides=overrides,
            ),
            "services": {
                container_name: {
                    "image": image_ref,
                    "container_name": container_name,
                    "restart": "unless-stopped",
                    "command": [
                        "bash",
                        "-lc",
                        (
                            'worker_root="$${RUNPOD_WORKER_ROOT:-/opt/allbot/runpod_worker}"; '
                            "if [ -x /opt/allbot/runpod_baked_runtime_entrypoint.sh ]; then "
                            "exec bash /opt/allbot/runpod_baked_runtime_entrypoint.sh; "
                            "fi; "
                            'model_target="$${RUNPOD_MODEL_TARGET_DIR:-/workspace/ComfyUI/models}"; '
                            'mkdir -p "$${model_target}"; '
                            "if [ -f /opt/allbot-comfyui-dir ]; then "
                            'baked_comfy="$$(cat /opt/allbot-comfyui-dir)"; '
                            'if [ -n "$${baked_comfy}" ] && [ -d "$${baked_comfy}" ]; then '
                            'rm -rf "$${baked_comfy}/models"; '
                            'ln -s "$${model_target}" "$${baked_comfy}/models"; '
                            "fi; "
                            "fi; "
                            "if [ -d /default-comfyui-bundle/ComfyUI ]; then "
                            "rm -rf /default-comfyui-bundle/ComfyUI/models; "
                            'ln -s "$${model_target}" /default-comfyui-bundle/ComfyUI/models; '
                            "fi; "
                            'if [ -f "$${worker_root}/requirements.txt" ]; then '
                            "python3 - <<'PY' || python3 -m pip install --no-cache-dir -r \"$${worker_root}/requirements.txt\"\n"
                            "import fastapi\n"
                            "import minio\n"
                            "import uvicorn\n"
                            "import websockets\n"
                            "PY\n"
                            "fi; "
                            'if [ "$${RUNPOD_MODEL_SYNC_ENABLED:-false}" = "true" ]; then '
                            'python3 "$${worker_root}/scripts/runpod_sync_models_from_r2.py" '
                            '--bucket "$${RUNPOD_MODEL_BUCKET:-}" '
                            '--prefix "$${RUNPOD_MODEL_PREFIX:-img2img_lora/2026-06-10}" '
                            '--target-dir "$${model_target}"; '
                            "fi; "
                            'if [ -f "$${worker_root}/scripts/ensure_wan22_rife_cache.py" ]; then '
                            'python3 "$${worker_root}/scripts/ensure_wan22_rife_cache.py" '
                            '--model-target-dir "$${model_target}"; '
                            "fi; "
                            'entrypoint="$${worker_root}/scripts/runpod_entrypoint.sh"; '
                            'exec bash "$${entrypoint}"'
                        ),
                    ],
                    "ports": [f"{host_port}:8188"],
                    "environment": {
                        "TZ": "Asia/Shanghai",
                        **accelerator_environment,
                        "ALLBOT_RUNPOD_MANAGED": "true",
                        "RUNPOD_ENVIRONMENT": environment,
                        "RUNPOD_TASK_TYPE": profile.runtime_profile,
                        "RUNPOD_POD_ID": f"lan-{slot_id}",
                        "RUNPOD_POD_ID_SAFE": f"lan-{slot_id}",
                        "AGENT_ID": agent_id,
                        "AGENT_SECRET_TOKEN": "${LAN_AIO_AGENT_SECRET_TOKEN:?}",
                        "CENTRAL_API_URL": central_url,
                        "MASTER_API_URL": "http://127.0.0.1:8013",
                        "UPLOAD_SIDECAR_URL": "http://127.0.0.1:8013",
                        "LOCAL_RELAY_HOST": "127.0.0.1",
                        "LOCAL_RELAY_PORT": "8013",
                        "RUNPOD_RELAY_READY_PATH": "/ready",
                        "SUPPORTED_TASK_TYPES": supported_task_types,
                        **(
                            {"PREFERRED_TASK_TYPES": preferred_task_types_csv}
                            if preferred_task_types_csv
                            else {}
                        ),
                        **(
                            {"TASK_TYPE_WORKFLOW_OVERRIDES": workflow_overrides}
                            if workflow_overrides
                            else {}
                        ),
                        **extra_environment,
                        "POOL_NODE_ID": node.id,
                        "POOL_PROVIDER": assignment.provider,
                        "POOL_GPU_INDEX": str(
                            self._effective_gpu_index(comfy, overrides)
                        ),
                        "POOL_GPU_DEVICE_ID": self._effective_gpu_device_id(
                            comfy,
                            overrides,
                        ),
                        "POOL_RUNTIME_PROFILE": profile.runtime_profile,
                        **(
                            {"RESET_COMFY_MEMORY_BEFORE_TASK": "true"}
                            if profile.reset_comfy_memory_before_task
                            else {}
                        ),
                        "POOL_IMAGE_REF": image_ref,
                        "POOL_MODEL_BUNDLE_VERSIONS": json.dumps(
                            bundle_versions,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        "POOL_MANAGED": "true",
                        "COMFY_API_URL": "http://127.0.0.1:8188",
                        "COMFY_WS_URL": "ws://127.0.0.1:8188/ws",
                        "COMFY_INPUT_DIR": f"{state_root}/comfy-input",
                        "COMFY_OUTPUT_DIR": f"{state_root}/comfy-output",
                        "COMFY_EXTRA_ARGS": self._runpod_aio_comfy_extra_args(
                            profile=profile,
                            state_root=state_root,
                            accelerator=node.accelerator,
                        ),
                        "RESULT_SPOOL_DIR": f"{state_root}/spool/{agent_id}",
                        "AGENT_LOG_DIR": f"{state_root}/logs",
                        "PREFETCH_CACHE_DIR": f"{state_root}/prefetch-cache/{agent_id}",
                        "PIPELINE_ENABLED": "true",
                        "PIPELINE_MAX_RUNNING_TASKS": "1",
                        "PIPELINE_MAX_CLAIMED_TASKS": "2",
                        "PIPELINE_DELIVERY_CONCURRENCY": "1",
                        "PIPELINE_TASK_TYPES": supported_task_types,
                        "PREFETCH_ENABLED": "true",
                        "PREFETCH_RESERVE_TASK": "true",
                        "PREFETCH_DEPTH": "1",
                        "PREFETCH_TASK_TYPES": prefetch_task_types,
                        "PREFETCH_CONSUME_WAIT_SECONDS": "10",
                        **pipeline_environment,
                        "CANCEL_LOCK_ON_POP": "true",
                        "NO_PROXY": "*",
                        "no_proxy": "*",
                        "MINIO_ENDPOINT": "${LAN_AIO_MINIO_ENDPOINT:?}",
                        "MINIO_ACCESS_KEY": "${LAN_AIO_MINIO_ACCESS_KEY:?}",
                        "MINIO_SECRET_KEY": "${LAN_AIO_MINIO_SECRET_KEY:?}",
                        "MINIO_INPUT_BUCKET": user_data_bucket,
                        "MINIO_RESULT_BUCKET": user_data_bucket,
                        "MINIO_TEMPLATE_BUCKET": user_data_bucket,
                        "MINIO_SECURE": "true",
                        "RUNPOD_WORKSPACE_DIR": "/workspace",
                        "RUNPOD_VOLUME_COMFYUI_DIR": "/workspace/ComfyUI",
                        "RUNPOD_WORKER_ROOT": "/opt/allbot/runpod_worker",
                        "RUNPOD_PREPARE_COMFYUI_ON_VOLUME": "true",
                        "RUNPOD_COMFY_CUSTOM_NODES_ENABLED": "false",
                        "RUNPOD_MODEL_SYNC_ENABLED": "true",
                        "RUNPOD_MODEL_ENDPOINT": model_cache_endpoint,
                        "RUNPOD_MODEL_ACCESS_KEY": "${LAN_MODEL_CACHE_ACCESS_KEY:?}",
                        "RUNPOD_MODEL_SECRET_KEY": "${LAN_MODEL_CACHE_SECRET_KEY:?}",
                        "RUNPOD_MODEL_BUCKET": DEFAULT_LAN_MODEL_CACHE_BUCKET,
                        "RUNPOD_MODEL_PREFIX": model_prefix,
                        "RUNPOD_MODEL_MANIFEST_KEY": model_manifest_key,
                        "RUNPOD_MODEL_MANIFEST_KEYS": json.dumps(
                            model_manifest_keys,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        **(
                            {
                                "RUNPOD_LAN_LOCAL_MODEL_OVERRIDES": json.dumps(
                                    profile.lan_local_model_overrides,
                                    separators=(",", ":"),
                                )
                            }
                            if profile.lan_local_model_overrides
                            else {}
                        ),
                        "RUNPOD_MODEL_TARGET_DIR": model_target_dir,
                        "RUNPOD_MODEL_SECURE": "false",
                        "RUNPOD_START_SSHD": "false",
                        "RUNPOD_INSTALL_SSHD_IF_MISSING": "false",
                        "RUNPOD_KEEPALIVE_ON_BOOTSTRAP_FAILURE": "false",
                    },
                    "volumes": volumes,
                    "labels": {
                        "allbot.gpu_pool.managed": "true",
                        "allbot.gpu_pool.runtime_shape": RUNPOD_AIO_RUNTIME_SHAPE,
                        "allbot.gpu_pool.node_id": node.id,
                        "allbot.gpu_pool.comfy_id": comfy.id,
                        "allbot.gpu_pool.worker_id": agent_id,
                        "allbot.gpu_pool.original_worker_id": assignment.worker_id,
                        "allbot.gpu_pool.runtime_profile": profile.runtime_profile,
                        "allbot.gpu_pool.render_mode": render_mode,
                        "allbot.gpu_pool.production_port_unchanged": str(
                            production_port_unchanged
                        ).lower(),
                    },
                    "healthcheck": {
                        "test": [
                            "CMD-SHELL",
                            (
                                "curl -fsS http://127.0.0.1:8188/system_stats "
                                ">/dev/null && (curl -fsS "
                                "http://127.0.0.1:8013/ready >/dev/null || "
                                "curl -fsS http://127.0.0.1:8013/health >/dev/null)"
                            ),
                        ],
                        "interval": "30s",
                        "timeout": "8s",
                        "retries": 5,
                        "start_period": "120s",
                    },
                    **accelerator_service,
                }
            },
            "x-allbot-runtime": {
                "assignment_id": assignment.id,
                "worker_id": agent_id,
                "original_worker_id": assignment.worker_id,
                "runtime_shape": RUNPOD_AIO_RUNTIME_SHAPE,
                "slot_id": slot_id,
                "runtime_root": runtime_root,
                "runtime_profile": profile.runtime_profile,
                "accelerator": node.accelerator,
                "environment": environment,
                "image_ref": image_ref,
                "model_cache_endpoint": model_cache_endpoint,
                "model_cache_bucket": DEFAULT_LAN_MODEL_CACHE_BUCKET,
                "model_prefix": model_prefix,
                "model_manifest_key": model_manifest_key,
                "model_manifest_keys": list(model_manifest_keys),
                "lan_local_model_overrides": list(profile.lan_local_model_overrides),
                "model_target_dir": model_target_dir,
                "model_write_scope": [model_target_dir],
                "central_url": central_url,
                "user_data_bucket": user_data_bucket,
                "local_relay_url": "http://127.0.0.1:8013",
                "comfy_api_url": "http://127.0.0.1:8188",
                "model_bundle_versions": bundle_versions,
                "supported_task_types": list(target_task_types),
                "rendered_for": (
                    "canary_dry_run_review"
                    if render_mode == "canary"
                    else "dry_run_review"
                ),
                "render_mode": render_mode,
                "production_port_unchanged": production_port_unchanged,
                "host_port": host_port,
                "container_port": 8188,
                "container_name": container_name,
                "restart_policy": "unless-stopped",
                "process_supervision": "exit_container_when_agent_relay_or_comfy_exits",
                "workspace_host_dir": workspace_host_dir,
                "model_workspace_host_dir": model_workspace_host_dir,
                "secret_policy": "runtime_env_placeholders_only",
            },
        }
        try:
            import yaml  # type: ignore
        except (
            Exception
        ) as exc:  # pragma: no cover - config loading already requires yaml
            raise RuntimeError("runtime-render requires PyYAML") from exc
        return yaml.safe_dump(compose, allow_unicode=True, sort_keys=False)

    def _runpod_aio_comfy_extra_args(
        self,
        *,
        profile: TaskProfile,
        state_root: str,
        accelerator: str,
    ) -> str:
        args = [
            "--input-directory",
            f"{state_root}/comfy-input",
            "--output-directory",
            f"{state_root}/comfy-output",
            "--temp-directory",
            f"{state_root}/comfy-temp",
        ]
        if profile.runtime_profile in LAN_AIO_DISABLE_DYNAMIC_VRAM_PROFILES:
            args.append("--disable-dynamic-vram")
        reserve_vram = LAN_AIO_RESERVE_VRAM_GB_BY_PROFILE.get(profile.runtime_profile)
        if reserve_vram is not None:
            args.extend(["--reserve-vram", str(reserve_vram)])
        if profile.runtime_profile in LAN_AIO_PYTORCH_CROSS_ATTENTION_PROFILES:
            args.append("--use-pytorch-cross-attention")
        if profile.runtime_profile in LAN_AIO_FAST_DISK_PROFILES:
            args.append("--fast-disk")
        if profile.runtime_profile in LAN_AIO_DISABLE_PINNED_MEMORY_PROFILES:
            args.append("--disable-pinned-memory")
        if accelerator == "rocm":
            args.extend(["--lowvram", "--disable-pinned-memory"])
        return " ".join(args)

    def build_dry_run_action(
        self,
        action: str,
        assignment_id: str,
        *,
        target_profile_id: str | None = None,
        execute: bool = False,
    ) -> dict[str, Any]:
        plan = runtime_plan_to_jsonable(
            self.build_plan(assignment_id, target_profile_id=target_profile_id)
        )
        payload: dict[str, Any] = {
            "ok": not execute,
            "action": action,
            "execute": execute,
            "dry_run": not execute,
            "plan": plan,
        }
        if execute:
            payload["error"] = (
                "execute_not_implemented: runtime mutations remain disabled until "
                "Phase 1 canary validation and an explicit maintenance window"
            )
        else:
            payload["message"] = (
                "dry-run only; no remote runtime or worker mutation executed"
            )
        return payload

    def build_rollback_plan(
        self, assignment_id: str, *, execute: bool = False
    ) -> dict[str, Any]:
        assignment = self._assignment_for(assignment_id)
        node = self._node_for(assignment)
        comfy = self._comfy_for(node, assignment)
        warnings = []
        if not comfy.rollback_state:
            warnings.append(
                "rollback_state is empty; nothing can be restored automatically"
            )
        payload: dict[str, Any] = {
            "ok": not execute,
            "action": "rollback-profile",
            "execute": execute,
            "dry_run": not execute,
            "assignment_id": assignment.id,
            "worker_id": assignment.worker_id,
            "node_id": node.id,
            "comfy_id": comfy.id,
            "runtime_kind": comfy.comfy_runtime_kind,
            "rollback_state": comfy.rollback_state,
            "warnings": warnings,
            "commands": self._rollback_commands(
                assignment=assignment, node=node, comfy=comfy
            ),
        }
        if execute:
            payload["error"] = (
                "execute_not_implemented: rollback mutations remain disabled until "
                "runtime-apply is validated"
            )
        return payload

    def _assignment_for(self, assignment_id: str) -> Assignment:
        try:
            return self.config.assignments[assignment_id]
        except KeyError as exc:
            raise ValueError(f"Unknown assignment_id: {assignment_id}") from exc

    def _node_for(self, assignment: Assignment) -> GpuNode:
        try:
            return self.config.nodes[assignment.node_id]
        except KeyError as exc:
            raise ValueError(
                f"Unknown node_id for assignment {assignment.id}: {assignment.node_id}"
            ) from exc

    def _comfy_for(self, node: GpuNode, assignment: Assignment) -> ComfyInstance:
        for comfy in node.comfy:
            if comfy.id == assignment.comfy_id:
                return comfy
        raise ValueError(
            f"Unknown comfy_id for assignment {assignment.id}: {assignment.comfy_id}"
        )

    def _profile_for(self, profile_id: str) -> TaskProfile:
        try:
            return self.config.profiles[profile_id]
        except KeyError as exc:
            raise ValueError(f"Unknown profile_id: {profile_id}") from exc

    def _bundle_versions(self, profile: TaskProfile) -> dict[str, str]:
        versions: dict[str, str] = {}
        for bundle_id in profile.model_bundles:
            bundle = self.config.bundles.get(bundle_id)
            versions[bundle_id] = bundle.version if bundle else "undefined"
        return versions

    def _target_task_types(
        self,
        *,
        assignment: Assignment,
        profile: TaskProfile,
        target_profile_id: str | None,
        overrides: RuntimeRenderOverrides,
    ) -> tuple[str, ...]:
        if overrides.target_task_types:
            return overrides.target_task_types
        return profile.task_types if target_profile_id else assignment.task_types

    def _validate_overrides(
        self,
        *,
        assignment: Assignment,
        comfy: ComfyInstance,
        overrides: RuntimeRenderOverrides,
        for_render: bool,
    ) -> None:
        if comfy.comfy_runtime_kind == HOST_RUNTIME_KIND and (
            for_render or overrides.has_any
        ):
            operation = "runtime-render" if for_render else "runtime-plan override"
            raise ValueError(
                f"{assignment.id} uses host_service; {operation} only supports docker_container"
            )

    def _worker_env(
        self,
        *,
        assignment: Assignment,
        node: GpuNode,
        comfy: ComfyInstance,
        profile: TaskProfile,
        target_task_types: tuple[str, ...],
        bundle_versions: dict[str, str],
        overrides: RuntimeRenderOverrides,
    ) -> dict[str, str]:
        return {
            "AGENT_ID": overrides.agent_id or assignment.worker_id,
            "POOL_MANAGED": "true",
            "POOL_PROVIDER": assignment.provider,
            "POOL_NODE_ID": node.id,
            "POOL_GPU_INDEX": str(self._effective_gpu_index(comfy, overrides)),
            "POOL_GPU_DEVICE_ID": self._effective_gpu_device_id(comfy, overrides),
            "POOL_RUNTIME_PROFILE": profile.runtime_profile,
            "POOL_IMAGE_REF": self._target_image_ref(
                comfy=comfy,
                profile=profile,
                overrides=overrides,
            )
            or "",
            "POOL_MODEL_BUNDLE_VERSIONS": json.dumps(
                bundle_versions,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "SUPPORTED_TASK_TYPES": ",".join(target_task_types),
            "COMFY_API_URL": self._effective_api_url(
                node=node,
                comfy=comfy,
                overrides=overrides,
            ),
            "COMFY_WS_URL": self._effective_ws_url(
                node=node,
                comfy=comfy,
                overrides=overrides,
            ),
        }

    def _runtime_payload(
        self,
        *,
        node: GpuNode,
        comfy: ComfyInstance,
        overrides: RuntimeRenderOverrides,
    ) -> dict[str, Any]:
        host_port = self._effective_host_port(comfy, overrides)
        return {
            "provider": node.provider,
            "host": node.host,
            "ip": node.ip,
            "ssh_alias": node.ssh_alias,
            "kind": comfy.comfy_runtime_kind,
            "managed": comfy.comfy_runtime_managed,
            "shape": self._effective_runtime_shape(comfy, overrides),
            "slot_id": comfy.slot_id,
            "runtime_root": comfy.runtime_root,
            "model_cache_endpoint": comfy.model_cache_endpoint,
            "image_registry": comfy.image_registry,
            "container_name": self._effective_container_name(comfy, overrides),
            "configured_container_name": comfy.container_name,
            "host_port": host_port,
            "configured_host_port": comfy.port,
            "container_port": comfy.container_port,
            "gpu_index": comfy.gpu_index,
            "effective_gpu_index": self._effective_gpu_index(comfy, overrides),
            "effective_gpu_device_id": self._effective_gpu_device_id(comfy, overrides),
            "current_image": comfy.image,
            "model_dir": comfy.model_dir,
            "instance_dir": comfy.instance_dir,
            "custom_nodes_dir": comfy.custom_nodes_dir,
            "workflows_dir": comfy.workflows_dir,
            "input_dir": comfy.input_dir,
            "output_dir": comfy.output_dir,
            "temp_dir": comfy.temp_dir,
            "compose_template": comfy.compose_template,
            "health": comfy.health,
            "render_mode": self._render_mode(comfy, overrides),
            "production_port_unchanged": self._production_port_unchanged(
                comfy,
                overrides,
            ),
            "api_url": self._effective_api_url(
                node=node,
                comfy=comfy,
                overrides=overrides,
            ),
            "ws_url": self._effective_ws_url(
                node=node,
                comfy=comfy,
                overrides=overrides,
            ),
        }

    def _diff(
        self,
        *,
        node: GpuNode,
        comfy: ComfyInstance,
        profile: TaskProfile,
        target_task_types: tuple[str, ...],
        bundle_versions: dict[str, str],
        overrides: RuntimeRenderOverrides,
    ) -> dict[str, Any]:
        current_tasks = tuple(comfy.supported_task_types)
        host_port = self._effective_host_port(comfy, overrides)
        target_image = self._target_image_ref(
            comfy=comfy,
            profile=profile,
            overrides=overrides,
        )
        if self._effective_runtime_shape(comfy, overrides) == RUNPOD_AIO_RUNTIME_SHAPE:
            target_container_name = (
                overrides.container_name
                or self._default_runpod_aio_container_name(
                    node=node,
                    comfy=comfy,
                    profile=profile,
                    render_mode=self._render_mode(comfy, overrides),
                )
            )
        else:
            target_container_name = self._effective_container_name(comfy, overrides)
        return {
            "runtime_image": {
                "current": comfy.image,
                "target": target_image,
                "changed": bool(target_image and comfy.image != target_image),
            },
            "runtime_shape": {
                "configured": comfy.runtime_shape,
                "target": self._effective_runtime_shape(comfy, overrides),
                "changed": self._effective_runtime_shape(comfy, overrides)
                != comfy.runtime_shape,
            },
            "task_types": {
                "current": list(current_tasks),
                "target": list(target_task_types),
                "changed": current_tasks != target_task_types,
            },
            "runtime_profile": {
                "target": profile.runtime_profile,
            },
            "model_bundles": {
                "target": bundle_versions,
            },
            "container": {
                "target_name": target_container_name,
                "current_name": comfy.container_name,
                "host_port": host_port,
                "configured_host_port": comfy.port,
                "container_port": comfy.container_port,
                "effective_gpu_index": self._effective_gpu_index(comfy, overrides),
                "effective_gpu_device_id": self._effective_gpu_device_id(
                    comfy,
                    overrides,
                ),
            },
            "render": {
                "mode": self._render_mode(comfy, overrides),
                "production_port_unchanged": self._production_port_unchanged(
                    comfy,
                    overrides,
                ),
                "api_url": self._effective_api_url(
                    node=node,
                    comfy=comfy,
                    overrides=overrides,
                ),
                "ws_url": self._effective_ws_url(
                    node=node,
                    comfy=comfy,
                    overrides=overrides,
                ),
            },
        }

    def _warnings(
        self,
        *,
        assignment: Assignment,
        node: GpuNode,
        comfy: ComfyInstance,
        profile: TaskProfile,
        target_task_types: tuple[str, ...],
        overrides: RuntimeRenderOverrides,
    ) -> list[str]:
        warnings: list[str] = []
        if comfy.comfy_runtime_kind == HOST_RUNTIME_KIND:
            warnings.append(
                "host_service runtime is observation-only; Docker pull/up/restart is forbidden"
            )
        elif comfy.comfy_runtime_kind != DOCKER_RUNTIME_KIND:
            warnings.append(f"unsupported runtime kind: {comfy.comfy_runtime_kind}")
        elif not comfy.comfy_runtime_managed:
            warnings.append(
                "docker runtime is not marked managed; runtime-apply must remain disabled"
            )
        runtime_shape = self._effective_runtime_shape(comfy, overrides)
        if runtime_shape == RUNPOD_AIO_RUNTIME_SHAPE:
            if not overrides.agent_id:
                warnings.append(
                    "runpod_all_in_one render should pass --agent-id for the temporary canary agent"
                )
            if not comfy.runtime_root:
                warnings.append("runpod_all_in_one runtime_root is not configured")
            if not comfy.model_cache_endpoint:
                warnings.append(
                    "runpod_all_in_one model_cache_endpoint is not configured"
                )
            if not profile.all_in_one_image_ref:
                warnings.append(f"profile {profile.id} has no all_in_one_image_ref")
            if not profile.model_manifest_key:
                warnings.append(f"profile {profile.id} has no model_manifest_key")
            if (
                overrides.environment == "cloud-prod"
                and (
                    overrides.central_url
                    or LAN_AIO_ENVIRONMENTS["cloud-prod"]["central_url"]
                ).find("test")
                >= 0
            ):
                warnings.append("cloud-prod render should not use a test Central URL")
        if self._render_mode(comfy, overrides) == "canary":
            warnings.append(
                "canary render only; production port remains unchanged and no runtime mutation is executed"
            )

        missing_tasks = sorted(set(target_task_types) - set(profile.task_types))
        if missing_tasks:
            warnings.append(
                f"target task types not declared by profile {profile.id}: {','.join(missing_tasks)}"
            )
        for bundle_id in profile.model_bundles:
            if bundle_id not in self.config.bundles:
                warnings.append(f"model bundle {bundle_id} is not defined")
        if (
            comfy.comfy_runtime_kind == DOCKER_RUNTIME_KIND
            and runtime_shape == STANDARD_RUNTIME_SHAPE
        ):
            for field_name in (
                "container_name",
                "model_dir",
                "input_dir",
                "output_dir",
                "temp_dir",
            ):
                if not getattr(comfy, field_name):
                    warnings.append(f"docker runtime missing {field_name}")
            if profile.image_ref is None:
                warnings.append(f"profile {profile.id} has no image_ref")
        if assignment.provider != node.provider:
            warnings.append(
                f"assignment provider {assignment.provider} differs from node provider {node.provider}"
            )
        return warnings

    def _dry_run_commands(
        self,
        *,
        assignment: Assignment,
        node: GpuNode,
        comfy: ComfyInstance,
        profile: TaskProfile,
        target_task_types: tuple[str, ...],
        overrides: RuntimeRenderOverrides,
    ) -> list[str]:
        render_mode = self._render_mode(comfy, overrides)
        api_url = self._effective_api_url(node=node, comfy=comfy, overrides=overrides)
        ws_url = self._effective_ws_url(node=node, comfy=comfy, overrides=overrides)
        if self._effective_runtime_shape(comfy, overrides) == RUNPOD_AIO_RUNTIME_SHAPE:
            agent_id = overrides.agent_id or assignment.worker_id
            target_tasks = ",".join(profile.task_types) or "matching"
            image_ref = self._target_image_ref(
                comfy=comfy,
                profile=profile,
                overrides=overrides,
            )
            model_prefix = profile.model_prefix or f"{profile.id}/unversioned"
            model_manifest_key = (
                profile.model_manifest_key
                or f"{model_prefix.rstrip('/')}/manifest.json"
            )
            commands = [
                (
                    f"# all-in-one canary render: production port {comfy.port} remains unchanged; "
                    f"review host port {self._effective_host_port(comfy, overrides)}"
                ),
                f"# pre-set temp agent disabled: {agent_id}",
                (
                    "# verify LAN model cache manifest "
                    f"{DEFAULT_LAN_MODEL_CACHE_BUCKET}/{model_manifest_key} "
                    f"via {comfy.model_cache_endpoint or 'model_cache_endpoint'}"
                ),
                f"# pull canary image on {node.ssh_alias}: {image_ref or '-'}",
                (
                    "# heartbeat-only: start the rendered compose while temp agent "
                    "control remains disabled"
                ),
                (
                    f"# real canary window: disable {assignment.worker_id}, enable "
                    f"{agent_id}, submit one matching Web task ({target_tasks}), then restore"
                ),
                f"# dry-run render: {self._render_command(assignment, profile, overrides)}",
            ]
            return commands
        if render_mode == "canary":
            commands = [
                (
                    f"# canary render: production port {comfy.port} remains unchanged; "
                    f"review host port {self._effective_host_port(comfy, overrides)}"
                ),
                f"# sync model bundles {','.join(profile.model_bundles) or '-'} to {node.ssh_alias}:{comfy.model_dir}",
                "# render test worker env "
                f"SUPPORTED_TASK_TYPES={','.join(target_task_types)} "
                f"POOL_RUNTIME_PROFILE={profile.runtime_profile} "
                f"COMFY_API_URL={api_url} COMFY_WS_URL={ws_url}",
            ]
            if profile.image_ref:
                commands.append(
                    f"# maintenance window required before live canary: ssh {node.ssh_alias} 'docker pull {profile.image_ref}'"
                )
            commands.append(
                f"# dry-run render: {self._render_command(assignment, profile, overrides)}"
            )
            return commands

        commands = [
            f"# set {assignment.worker_id} draining before any mutation",
            f"# wait until {assignment.worker_id} has no running task and {comfy.api_url}/queue is empty",
            f"# sync model bundles {','.join(profile.model_bundles) or '-'} to {node.ssh_alias}:{comfy.model_dir}",
            "# render worker env "
            f"SUPPORTED_TASK_TYPES={','.join(target_task_types)} "
            f"POOL_RUNTIME_PROFILE={profile.runtime_profile}",
        ]
        if comfy.comfy_runtime_kind == HOST_RUNTIME_KIND:
            commands.append(
                f"# host_service: skip Docker runtime operations for {node.id}/{comfy.id}"
            )
            commands.append(
                f"# manual canary: python scripts/gpu_pool_controller.py canary --assignment {assignment.id}"
            )
        elif comfy.comfy_runtime_kind == DOCKER_RUNTIME_KIND:
            if profile.image_ref:
                commands.append(
                    f"# maintenance window required: ssh {node.ssh_alias} 'docker pull {profile.image_ref}'"
                )
            commands.append(
                f"# dry-run render: {self._render_command(assignment, profile, overrides)}"
            )
            commands.append(
                f"# canary: python scripts/gpu_pool_controller.py canary --assignment {assignment.id}"
            )
        return commands

    def _rollback_commands(
        self,
        *,
        assignment: Assignment,
        node: GpuNode,
        comfy: ComfyInstance,
    ) -> list[str]:
        if not comfy.rollback_state:
            return []
        if comfy.comfy_runtime_kind == HOST_RUNTIME_KIND:
            return [
                f"# restore worker {assignment.worker_id} COMFY_API_URL to previous host service endpoint",
                f"# canary: python scripts/gpu_pool_controller.py canary --assignment {assignment.id}",
            ]
        return [
            f"# set {assignment.worker_id} disabled",
            f"# restore previous compose/image on {node.ssh_alias}:{comfy.container_name}",
            f"# canary: python scripts/gpu_pool_controller.py canary --assignment {assignment.id}",
            f"# set {assignment.worker_id} enabled",
        ]

    def _compose_volumes(self, comfy: ComfyInstance) -> list[str]:
        mounts = [
            (comfy.model_dir, "/data/comfy/models"),
            (comfy.input_dir, "/data/comfy/input"),
            (comfy.output_dir, "/data/comfy/output"),
            (comfy.temp_dir, "/data/comfy/temp"),
            (comfy.custom_nodes_dir, "/data/comfy/custom_nodes"),
            (comfy.workflows_dir, "/data/comfy/workflows"),
        ]
        return [f"{host}:{container}" for host, container in mounts if host]

    def _compose_project_name(
        self,
        *,
        node: GpuNode,
        comfy: ComfyInstance,
        overrides: RuntimeRenderOverrides,
    ) -> str:
        if self._effective_runtime_shape(comfy, overrides) == RUNPOD_AIO_RUNTIME_SHAPE:
            raw = f"allbot-lan-aio-{node.id}-{comfy.id}"
        else:
            raw = f"allbot-comfy-{node.id}-{comfy.id}"
        if self._render_mode(comfy, overrides) == "canary":
            raw = f"{raw}-canary-{self._effective_host_port(comfy, overrides)}"
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", raw).lower()

    def _render_command(
        self,
        assignment: Assignment,
        profile: TaskProfile,
        overrides: RuntimeRenderOverrides,
    ) -> str:
        args = [
            "python scripts/gpu_pool_controller.py runtime-render",
            f"--assignment {assignment.id}",
            f"--profile {profile.id}",
        ]
        if overrides.host_port is not None:
            args.append(f"--host-port {overrides.host_port}")
        if overrides.container_name:
            args.append(f"--container-name {overrides.container_name}")
        if overrides.api_url:
            args.append(f"--api-url {overrides.api_url}")
        if overrides.ws_url:
            args.append(f"--ws-url {overrides.ws_url}")
        if overrides.runtime_shape:
            args.append(f"--runtime-shape {overrides.runtime_shape}")
        if overrides.agent_id:
            args.append(f"--agent-id {overrides.agent_id}")
        if overrides.central_url:
            args.append(f"--central-url {overrides.central_url}")
        if overrides.environment:
            args.append(f"--environment {overrides.environment}")
        if overrides.gpu_index is not None:
            args.append(f"--gpu-index {overrides.gpu_index}")
        if overrides.gpu_device_id:
            args.append(f"--gpu-device-id {shlex.quote(overrides.gpu_device_id)}")
        return " ".join(args)

    def _effective_lan_aio_environment(
        self,
        overrides: RuntimeRenderOverrides,
    ) -> str:
        return overrides.environment or DEFAULT_LAN_AIO_ENVIRONMENT

    def _effective_runtime_shape(
        self,
        comfy: ComfyInstance,
        overrides: RuntimeRenderOverrides,
    ) -> str:
        return overrides.runtime_shape or comfy.runtime_shape or STANDARD_RUNTIME_SHAPE

    def _target_image_ref(
        self,
        *,
        comfy: ComfyInstance,
        profile: TaskProfile,
        overrides: RuntimeRenderOverrides,
    ) -> str | None:
        if self._effective_runtime_shape(comfy, overrides) == RUNPOD_AIO_RUNTIME_SHAPE:
            return profile.all_in_one_image_ref or profile.image_ref or comfy.image
        return profile.image_ref or comfy.image

    def _default_runpod_aio_container_name(
        self,
        *,
        node: GpuNode,
        comfy: ComfyInstance,
        profile: TaskProfile,
        render_mode: str,
    ) -> str:
        raw = (
            f"allbot-lan-aio-{node.id}-gpu{comfy.gpu_index or 0}-"
            f"{profile.runtime_profile}"
        )
        if render_mode == "canary":
            raw = f"{raw}-canary"
        return re.sub(r"[^a-zA-Z0-9_.-]+", "-", raw).lower()

    def _render_mode(
        self,
        comfy: ComfyInstance,
        overrides: RuntimeRenderOverrides,
    ) -> str:
        if overrides.host_port is not None and overrides.host_port != comfy.port:
            return "canary"
        return "standard"

    def _production_port_unchanged(
        self,
        comfy: ComfyInstance,
        overrides: RuntimeRenderOverrides,
    ) -> bool:
        return self._render_mode(comfy, overrides) == "canary"

    def _effective_host_port(
        self,
        comfy: ComfyInstance,
        overrides: RuntimeRenderOverrides,
    ) -> int:
        return overrides.host_port if overrides.host_port is not None else comfy.port

    def _effective_container_name(
        self,
        comfy: ComfyInstance,
        overrides: RuntimeRenderOverrides,
    ) -> str:
        if overrides.container_name:
            return overrides.container_name
        base = comfy.container_name or f"allbot-comfy-gpu{comfy.gpu_index or 0}"
        if self._render_mode(comfy, overrides) == "canary":
            return f"{base}-canary"
        return base

    def _effective_gpu_index(
        self,
        comfy: ComfyInstance,
        overrides: RuntimeRenderOverrides,
    ) -> int:
        if overrides.gpu_index is not None:
            return overrides.gpu_index
        return comfy.gpu_index if comfy.gpu_index is not None else 0

    def _effective_gpu_device_id(
        self,
        comfy: ComfyInstance,
        overrides: RuntimeRenderOverrides,
    ) -> str:
        if overrides.gpu_device_id:
            return overrides.gpu_device_id.strip()
        return str(self._effective_gpu_index(comfy, overrides))

    def _effective_api_url(
        self,
        *,
        node: GpuNode,
        comfy: ComfyInstance,
        overrides: RuntimeRenderOverrides,
    ) -> str:
        if overrides.api_url:
            return overrides.api_url
        if self._render_mode(comfy, overrides) == "canary":
            return f"http://{node.ip}:{self._effective_host_port(comfy, overrides)}"
        return comfy.api_url

    def _effective_ws_url(
        self,
        *,
        node: GpuNode,
        comfy: ComfyInstance,
        overrides: RuntimeRenderOverrides,
    ) -> str:
        if overrides.ws_url:
            return overrides.ws_url
        if self._render_mode(comfy, overrides) == "canary":
            return f"ws://{node.ip}:{self._effective_host_port(comfy, overrides)}/ws"
        return comfy.ws_url


def runtime_plan_to_jsonable(item: RuntimePlanItem) -> dict[str, Any]:
    return {
        "assignment_id": item.assignment_id,
        "worker_id": item.worker_id,
        "node_id": item.node_id,
        "comfy_id": item.comfy_id,
        "runtime_kind": item.runtime_kind,
        "runtime_managed": item.runtime_managed,
        "target_profile_id": item.target_profile_id,
        "target_task_types": list(item.target_task_types),
        "model_bundle_versions": item.model_bundle_versions,
        "worker_env": item.worker_env,
        "runtime": item.runtime,
        "diff": item.diff,
        "warnings": list(item.warnings),
        "commands": list(item.commands),
    }
