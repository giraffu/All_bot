from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .runpod_profile_catalog import prod_agent_id_from_slot


class RunPodProdWorkerPlanError(ValueError):
    pass


def pod_minimal(pod: dict[str, Any]) -> dict[str, Any]:
    env = pod.get("env") if isinstance(pod.get("env"), dict) else {}
    return {
        "id": pod.get("id") or pod.get("podId"),
        "name": pod.get("name"),
        "desiredStatus": pod.get("desiredStatus") or pod.get("status"),
        "agent_id": env.get("AGENT_ID"),
        "environment": env.get("RUNPOD_ENVIRONMENT"),
        "task_type": env.get("RUNPOD_TASK_TYPE"),
    }


def find_worker(
    workers: list[dict[str, Any]],
    agent_id: str,
) -> dict[str, Any] | None:
    for worker in workers:
        if str(worker.get("agent_id") or "") == agent_id:
            return worker
    return None


def worker_summary(worker: dict[str, Any] | None) -> dict[str, Any]:
    if not worker:
        return {}
    return {
        "agent_id": worker.get("agent_id"),
        "types": worker.get("types"),
        "status": worker.get("status"),
        "provider": worker.get("provider"),
        "node_id": worker.get("node_id"),
        "runtime_profile": worker.get("runtime_profile"),
        "image_ref": worker.get("image_ref"),
        "current_task_id": worker.get("current_task_id"),
        "current_task_type": worker.get("current_task_type"),
    }


def prod_slot_sequence(count: int) -> list[str]:
    return [f"{index:02d}" for index in range(1, count + 1)]


def slot_sort_key(slot: str) -> int:
    return int(slot)


@dataclass(frozen=True)
class RunPodProdWorkerPlanner:
    max_manual_slots: int
    profile: str

    def build_add_plan(
        self,
        *,
        count: int,
        slot_pods: dict[str, dict[str, Any]],
        workers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        existing_slots = set(slot_pods)
        all_slots = prod_slot_sequence(self.max_manual_slots)
        free_slots = [slot for slot in all_slots if slot not in existing_slots]
        if len(free_slots) < count:
            raise RunPodProdWorkerPlanError(
                f"prod-worker add requires {count} free slot(s); only "
                f"{len(free_slots)} available within "
                f"RUNPOD_PROD_MAX_MANUAL_SLOTS={self.max_manual_slots}"
            )
        create_slots = free_slots[:count]
        slots: dict[str, Any] = {}
        for slot in sorted(existing_slots | set(create_slots), key=slot_sort_key):
            agent_id = prod_agent_id_from_slot(
                slot,
                max_manual_slots=self.max_manual_slots,
                profile=self.profile,
            )
            worker = find_worker(workers, agent_id)
            slots[slot] = {
                "agent_id": agent_id,
                "pod": pod_minimal(slot_pods[slot]) if slot in slot_pods else None,
                "worker": worker_summary(worker) if worker else None,
            }
        return {
            "requested_count": count,
            "existing_slots": sorted(existing_slots, key=slot_sort_key),
            "free_slots": free_slots,
            "create_slots": create_slots,
            "enable_slots": [],
            "delete_slots": [],
            "slots": slots,
        }

    def build_scale_plan(
        self,
        *,
        desired: int,
        slot_pods: dict[str, dict[str, Any]],
        workers: list[dict[str, Any]],
        controls: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        desired_slots = set(prod_slot_sequence(desired))
        existing_slots = set(slot_pods)
        create_slots = sorted(
            desired_slots - existing_slots,
            key=slot_sort_key,
        )
        enable_slots = sorted(
            desired_slots & existing_slots,
            key=slot_sort_key,
        )
        delete_slots = sorted(
            existing_slots - desired_slots,
            key=slot_sort_key,
            reverse=True,
        )
        slots: dict[str, Any] = {}
        for slot in sorted(existing_slots | desired_slots, key=slot_sort_key):
            agent_id = prod_agent_id_from_slot(
                slot,
                max_manual_slots=self.max_manual_slots,
                profile=self.profile,
            )
            worker = find_worker(workers, agent_id)
            slots[slot] = {
                "agent_id": agent_id,
                "pod": pod_minimal(slot_pods[slot]) if slot in slot_pods else None,
                "worker": worker_summary(worker) if worker else None,
                "control": controls.get(slot),
            }
        return {
            "desired_slots": sorted(desired_slots, key=slot_sort_key),
            "existing_slots": sorted(existing_slots, key=slot_sort_key),
            "create_slots": create_slots,
            "enable_slots": enable_slots,
            "delete_slots": delete_slots,
            "slots": slots,
        }

    def control_snapshot_slots(
        self,
        *,
        desired: int,
        slot_pods: dict[str, dict[str, Any]],
    ) -> list[str]:
        return sorted(
            set(prod_slot_sequence(desired)) | set(slot_pods),
            key=slot_sort_key,
        )

    def scale_would_execute(self, plan: dict[str, Any]) -> list[str]:
        actions: list[str] = []
        for slot in plan["create_slots"]:
            agent_id = prod_agent_id_from_slot(
                slot,
                max_manual_slots=self.max_manual_slots,
                profile=self.profile,
            )
            actions.extend(
                [
                    f"set Central control for {agent_id} to disabled",
                    f"create cloud-prod RunPod pod for slot {slot}",
                    f"wait for slot {slot} Pod readiness and disabled heartbeat",
                    f"set Central control for {agent_id} to enabled",
                ]
            )
        for slot in plan["enable_slots"]:
            agent_id = prod_agent_id_from_slot(
                slot,
                max_manual_slots=self.max_manual_slots,
                profile=self.profile,
            )
            actions.append(
                f"verify slot {slot} heartbeat and set {agent_id} to enabled"
            )
        for slot in plan["delete_slots"]:
            agent_id = prod_agent_id_from_slot(
                slot,
                max_manual_slots=self.max_manual_slots,
                profile=self.profile,
            )
            actions.extend(
                [
                    f"set Central control for {agent_id} to disabled",
                    f"wait until slot {slot} worker has no current_task_id",
                    f"delete cloud-prod RunPod pod for slot {slot}",
                ]
            )
        if not actions:
            actions.append(
                "no changes; desired RunPod prod worker count already matches"
            )
        return actions

    def add_would_execute(self, plan: dict[str, Any]) -> list[str]:
        actions: list[str] = []
        for slot in plan["create_slots"]:
            agent_id = prod_agent_id_from_slot(
                slot,
                max_manual_slots=self.max_manual_slots,
                profile=self.profile,
            )
            actions.extend(
                [
                    f"set Central control for new {agent_id} to disabled",
                    f"create cloud-prod RunPod pod for new slot {slot}",
                    f"wait for new slot {slot} Pod readiness and disabled heartbeat",
                    f"set Central control for new {agent_id} to enabled",
                ]
            )
        actions.append(
            "leave all existing RunPod slots unchanged; no existing enable/disable/delete"
        )
        return actions
