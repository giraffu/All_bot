from __future__ import annotations

import json
import re
from typing import Any

from .config_loader import ControllerConfig
from .types import Assignment, ComfyInstance, GpuNode, RuntimePlanItem, TaskProfile


DOCKER_RUNTIME_KIND = "docker_container"
HOST_RUNTIME_KIND = "host_service"


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
    ) -> RuntimePlanItem:
        assignment = self._assignment_for(assignment_id)
        node = self._node_for(assignment)
        comfy = self._comfy_for(node, assignment)
        profile = self._profile_for(target_profile_id or assignment.profile_id)
        target_task_types = (
            profile.task_types if target_profile_id else assignment.task_types
        )
        bundle_versions = self._bundle_versions(profile)
        worker_env = self._worker_env(
            assignment=assignment,
            node=node,
            comfy=comfy,
            profile=profile,
            target_task_types=target_task_types,
            bundle_versions=bundle_versions,
        )
        warnings = self._warnings(
            assignment=assignment,
            node=node,
            comfy=comfy,
            profile=profile,
            target_task_types=target_task_types,
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
            runtime=self._runtime_payload(node=node, comfy=comfy),
            diff=self._diff(
                comfy=comfy,
                profile=profile,
                target_task_types=target_task_types,
                bundle_versions=bundle_versions,
            ),
            warnings=tuple(warnings),
            commands=tuple(
                self._dry_run_commands(
                    assignment=assignment,
                    node=node,
                    comfy=comfy,
                    profile=profile,
                    target_task_types=target_task_types,
                )
            ),
        )

    def render_compose(
        self,
        assignment_id: str,
        *,
        target_profile_id: str | None = None,
    ) -> str:
        assignment = self._assignment_for(assignment_id)
        node = self._node_for(assignment)
        comfy = self._comfy_for(node, assignment)
        profile = self._profile_for(target_profile_id or assignment.profile_id)
        if comfy.comfy_runtime_kind != DOCKER_RUNTIME_KIND:
            raise ValueError(
                f"{assignment.id} uses {comfy.comfy_runtime_kind}; "
                "runtime-render only supports docker_container"
            )
        service_name = comfy.container_name or f"allbot-comfy-gpu{comfy.gpu_index or 0}"
        image_ref = profile.image_ref or comfy.image
        if not image_ref:
            raise ValueError(f"{profile.id} has no image_ref and {comfy.id} has no image")

        bundle_versions = self._bundle_versions(profile)
        compose = {
            "name": self._compose_project_name(node=node, comfy=comfy),
            "services": {
                service_name: {
                    "image": image_ref,
                    "container_name": service_name,
                    "restart": "unless-stopped",
                    "ports": [f"{comfy.port}:{comfy.container_port or 8188}"],
                    "environment": {
                        "TZ": "Asia/Shanghai",
                        "NVIDIA_VISIBLE_DEVICES": str(comfy.gpu_index or 0),
                        "COMFY_HOST": "0.0.0.0",
                        "COMFY_PORT": str(comfy.container_port or 8188),
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
                    },
                    "healthcheck": {
                        "test": [
                            "CMD-SHELL",
                            (
                                "curl -fsS "
                                f"http://127.0.0.1:{comfy.container_port or 8188}"
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
                            "device_ids": [str(comfy.gpu_index or 0)],
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
                "rendered_for": "dry_run_review",
            },
        }
        try:
            import yaml  # type: ignore
        except Exception as exc:  # pragma: no cover - config loading already requires yaml
            raise RuntimeError("runtime-render requires PyYAML") from exc
        return yaml.safe_dump(compose, allow_unicode=True, sort_keys=False)

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
            payload["message"] = "dry-run only; no remote runtime or worker mutation executed"
        return payload

    def build_rollback_plan(self, assignment_id: str, *, execute: bool = False) -> dict[str, Any]:
        assignment = self._assignment_for(assignment_id)
        node = self._node_for(assignment)
        comfy = self._comfy_for(node, assignment)
        warnings = []
        if not comfy.rollback_state:
            warnings.append("rollback_state is empty; nothing can be restored automatically")
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
            "commands": self._rollback_commands(assignment=assignment, node=node, comfy=comfy),
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
            raise ValueError(f"Unknown node_id for assignment {assignment.id}: {assignment.node_id}") from exc

    def _comfy_for(self, node: GpuNode, assignment: Assignment) -> ComfyInstance:
        for comfy in node.comfy:
            if comfy.id == assignment.comfy_id:
                return comfy
        raise ValueError(f"Unknown comfy_id for assignment {assignment.id}: {assignment.comfy_id}")

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

    def _worker_env(
        self,
        *,
        assignment: Assignment,
        node: GpuNode,
        comfy: ComfyInstance,
        profile: TaskProfile,
        target_task_types: tuple[str, ...],
        bundle_versions: dict[str, str],
    ) -> dict[str, str]:
        return {
            "AGENT_ID": assignment.worker_id,
            "POOL_MANAGED": "true",
            "POOL_PROVIDER": assignment.provider,
            "POOL_NODE_ID": node.id,
            "POOL_GPU_INDEX": "" if comfy.gpu_index is None else str(comfy.gpu_index),
            "POOL_RUNTIME_PROFILE": profile.runtime_profile,
            "POOL_IMAGE_REF": profile.image_ref or "",
            "POOL_MODEL_BUNDLE_VERSIONS": json.dumps(
                bundle_versions,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "SUPPORTED_TASK_TYPES": ",".join(target_task_types),
            "COMFY_API_URL": comfy.api_url,
            "COMFY_WS_URL": comfy.ws_url,
        }

    def _runtime_payload(self, *, node: GpuNode, comfy: ComfyInstance) -> dict[str, Any]:
        return {
            "provider": node.provider,
            "host": node.host,
            "ip": node.ip,
            "ssh_alias": node.ssh_alias,
            "kind": comfy.comfy_runtime_kind,
            "managed": comfy.comfy_runtime_managed,
            "container_name": comfy.container_name,
            "host_port": comfy.port,
            "container_port": comfy.container_port,
            "gpu_index": comfy.gpu_index,
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
        }

    def _diff(
        self,
        *,
        comfy: ComfyInstance,
        profile: TaskProfile,
        target_task_types: tuple[str, ...],
        bundle_versions: dict[str, str],
    ) -> dict[str, Any]:
        current_tasks = tuple(comfy.supported_task_types)
        return {
            "runtime_image": {
                "current": comfy.image,
                "target": profile.image_ref,
                "changed": bool(profile.image_ref and comfy.image != profile.image_ref),
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
                "target_name": comfy.container_name,
                "host_port": comfy.port,
                "container_port": comfy.container_port,
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

        missing_tasks = sorted(set(target_task_types) - set(profile.task_types))
        if missing_tasks:
            warnings.append(
                f"target task types not declared by profile {profile.id}: {','.join(missing_tasks)}"
            )
        for bundle_id in profile.model_bundles:
            if bundle_id not in self.config.bundles:
                warnings.append(f"model bundle {bundle_id} is not defined")
        if comfy.comfy_runtime_kind == DOCKER_RUNTIME_KIND:
            for field_name in ("container_name", "model_dir", "input_dir", "output_dir", "temp_dir"):
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
    ) -> list[str]:
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
                "# dry-run render: "
                f"python scripts/gpu_pool_controller.py runtime-render --assignment {assignment.id}"
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

    def _compose_project_name(self, *, node: GpuNode, comfy: ComfyInstance) -> str:
        raw = f"allbot-comfy-{node.id}-{comfy.id}"
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", raw).lower()


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
