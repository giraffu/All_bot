from __future__ import annotations

from .config_loader import ControllerConfig
from .types import Assignment, ComfyInstance, GpuNode, PlanItem, TaskProfile


class GpuPoolPlanner:
    def __init__(self, config: ControllerConfig):
        self.config = config

    def build_plan(self) -> list[PlanItem]:
        return [
            self._plan_assignment(assignment)
            for assignment in self.config.assignments.values()
            if assignment.enabled
        ]

    def _plan_assignment(self, assignment: Assignment) -> PlanItem:
        node = self._node_for(assignment)
        comfy = self._comfy_for(node, assignment)
        profile = self._profile_for(assignment)
        warnings = self._warnings(assignment, node, comfy, profile)
        commands = self._dry_run_commands(assignment, node, comfy, profile)
        return PlanItem(
            assignment_id=assignment.id,
            worker_id=assignment.worker_id,
            node_id=node.id,
            comfy_id=comfy.id,
            action="dry_run_reconcile",
            task_types=assignment.task_types,
            model_bundles=profile.model_bundles,
            image_ref=profile.image_ref,
            warnings=tuple(warnings),
            commands=tuple(commands),
        )

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

    def _profile_for(self, assignment: Assignment) -> TaskProfile:
        try:
            return self.config.profiles[assignment.profile_id]
        except KeyError as exc:
            raise ValueError(
                f"Unknown profile_id for assignment {assignment.id}: {assignment.profile_id}"
            ) from exc

    def _warnings(
        self,
        assignment: Assignment,
        node: GpuNode,
        comfy: ComfyInstance,
        profile: TaskProfile,
    ) -> list[str]:
        warnings: list[str] = []
        missing_tasks = sorted(set(assignment.task_types) - set(profile.task_types))
        if missing_tasks:
            warnings.append(
                f"assignment task types not declared by profile {profile.id}: {','.join(missing_tasks)}"
            )
        if comfy.worker_id and comfy.worker_id != assignment.worker_id:
            warnings.append(
                f"comfy worker_id {comfy.worker_id} differs from assignment worker_id {assignment.worker_id}"
            )
        if comfy.comfy_runtime_kind == "host_service":
            warnings.append(
                "host_service runtime is observation-only; do not generate Docker operations"
            )
        elif comfy.comfy_runtime_kind == "docker_container" and not comfy.comfy_runtime_managed:
            warnings.append(
                "docker runtime is not marked managed; execute requires an explicit maintenance window"
            )
        for bundle_id in profile.model_bundles:
            if bundle_id not in self.config.bundles:
                warnings.append(f"model bundle {bundle_id} is not defined")
        return warnings

    def _dry_run_commands(
        self,
        assignment: Assignment,
        node: GpuNode,
        comfy: ComfyInstance,
        profile: TaskProfile,
    ) -> list[str]:
        tasks = ",".join(assignment.task_types)
        commands = [
            f"# drain before mutation: controller set-agent-state {assignment.worker_id} draining",
            f"# sync model bundles {','.join(profile.model_bundles) or '-'} to {node.ssh_alias}:{comfy.model_dir}",
            f"# render worker env SUPPORTED_TASK_TYPES={tasks}",
        ]
        if comfy.comfy_runtime_kind == "host_service":
            commands.append(
                f"# host_service: no Docker runtime action for {node.id}/{comfy.id}; validate manually"
            )
        elif profile.image_ref:
            commands.append(f"# ensure image available: docker pull {profile.image_ref}")
        commands.append(
            f"# canary: python -m ops.gpu_pool_controller.cli canary --assignment {assignment.id}"
        )
        return commands

    def to_jsonable(self) -> list[dict[str, object]]:
        return [
            {
                "assignment_id": item.assignment_id,
                "worker_id": item.worker_id,
                "node_id": item.node_id,
                "comfy_id": item.comfy_id,
                "action": item.action,
                "task_types": list(item.task_types),
                "model_bundles": list(item.model_bundles),
                "image_ref": item.image_ref,
                "warnings": list(item.warnings),
                "commands": list(item.commands),
            }
            for item in self.build_plan()
        ]
