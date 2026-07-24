from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config_loader import CONFIG_DIR, ControllerConfig, load_controller_config
from .lan_aio_state import (
    LanAioStateStore,
    StateDriftError,
    assess_state_drift,
    catalog_sha256,
)
from .pipeline_policy import pipeline_policy_for_profile
from .runtime import RuntimePlanner, RuntimeRenderOverrides
from scripts.gpu_release_rollout import resolve_gpu_artifact, rollout_plan


LAN_AIO_SLOTS_FILE = "lan_aio_prod_slots.yml"
DEFAULT_CENTRAL_URL = "https://worker-central.aivison.it.com"
DEFAULT_WEB_HEALTH_URL = "https://api.aivison.it.com/api/health"
DEFAULT_REGISTRY_HEALTH_URL = "http://192.168.1.115:5000/v2/"
DEFAULT_MODEL_CACHE_HEALTH_URL = "http://192.168.1.115:9010/minio/health/ready"
REMOTE_WORKERS_TARGET_DIR = "/opt/allbot/runtime/remote_workers"
CONTROL_TTL_SECONDS = 3600
IMAGE_PULL_TIMEOUT_SECONDS = 3600
WARM_CACHE_MARKER_FILE = "model-cache-marker.json"
TAKEOVER_STEPS = (
    "preflight",
    "pull-image",
    "warm-cache",
    "drain-legacy",
    "wait-idle",
    "stop-old",
    "start-disabled",
    "enable-aio",
)
DISABLED_CANARY_START_STEPS = (
    "preflight",
    "pull-image",
    "warm-cache",
    "start-disabled",
)
RETARGETABLE_REPLACE_SLOT_ACTIONS = {
    "render",
    "preflight",
    "pull-image",
    "warm-cache",
    "takeover",
}
SAFE_STALE_CONTAINER_STATES = {"created", "exited", "dead", "removing", "restarting"}
FAILURE_POLICY_AUTO_ROLLBACK = "auto_rollback"
MANAGED_MUTATION_ACTIONS = {
    "configure-registry",
    "pull-image",
    "warm-cache",
    "takeover",
    "drain-aio",
    "disable-aio",
    "enable-aio",
    "restart-aio",
    "recover",
    "release-rollout",
    "canary-start-disabled",
    "canary-stop-disabled",
}
DIRECT_TRANSITION_ACTIONS = {
    "drain-legacy",
    "stop-old",
    "start-disabled",
    "rollback",
}
SSH_BATCH_OPTIONS = (
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=10",
    "-o",
    "ServerAliveInterval=15",
    "-o",
    "ServerAliveCountMax=2",
    "-o",
    "StrictHostKeyChecking=accept-new",
)

ENV_ALLOWLIST = {
    "AGENT_SECRET_TOKEN",
    "MINIO_ENDPOINT",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "LAN_AIO_AGENT_SECRET_TOKEN",
    "LAN_AIO_MINIO_ENDPOINT",
    "LAN_AIO_MINIO_ACCESS_KEY",
    "LAN_AIO_MINIO_SECRET_KEY",
    "LAN_MODEL_CACHE_ACCESS_KEY",
    "LAN_MODEL_CACHE_SECRET_KEY",
    "CIVITAI_API_TOKEN",
    "CIVITAI_API_TOKEN",
}


@dataclass(frozen=True)
class LegacyHotCacheCopy:
    source_container: str
    source_path: str
    target_paths: tuple[str, ...]
    required: bool = True


@dataclass(frozen=True)
class LanAioProdSlot:
    id: str
    enabled: bool
    phase: str
    assignment_id: str
    target_profile_id: str
    host_port: int
    agent_id: str
    container_name: str
    ssh_host: str
    node_id: str
    comfy_id: str
    gpu_index: int | None
    legacy_worker_id: str
    old_runtime_container: str
    old_local_agent_container: str
    remote_dir: str
    rollout_order: int
    legacy_health_port: int | None = None
    legacy_preflight_required: bool = True
    target_task_types: tuple[str, ...] = ()
    legacy_hot_cache_copies: tuple[LegacyHotCacheCopy, ...] = ()
    retargetable: bool = False
    notes: str = ""
    gpu_device_id: str | None = None

    @property
    def remote_compose_file(self) -> str:
        return f"{self.remote_dir}/docker-compose.yml"

    @property
    def remote_env_file(self) -> str:
        return f"{self.remote_dir}/.env.lan-aio-prod"

    @property
    def remote_local_model_env_file(self) -> str:
        return f"{self.remote_dir}/.env.local-model-download"

    @property
    def remote_workers_dir(self) -> str:
        return f"{self.remote_dir}/remote_workers"


def _load_yaml(path: Path) -> Any:
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("LAN AIO slot config requires PyYAML") from exc
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _dump_yaml(payload: Any) -> str:
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("LAN AIO compose patching requires PyYAML") from exc
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


def _sanitize(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _agent_node_label(node_id: str) -> str:
    return _sanitize(node_id).replace("_", "")


def _new_operation_id(action: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{_sanitize(action).lower()}-{uuid.uuid4().hex[:8]}"


def _parse_legacy_hot_cache_copies(
    raw: list[dict[str, Any]],
    *,
    default_source_container: str,
) -> tuple[LegacyHotCacheCopy, ...]:
    copies: list[LegacyHotCacheCopy] = []
    for item in raw:
        target_paths = tuple(str(path) for path in item.get("target_paths") or [])
        if not target_paths:
            raise RuntimeError("legacy_hot_cache_copies item requires target_paths")
        source_path = str(item.get("source_path") or "")
        if not source_path:
            raise RuntimeError("legacy_hot_cache_copies item requires source_path")
        copies.append(
            LegacyHotCacheCopy(
                source_container=str(
                    item.get("source_container") or default_source_container
                ),
                source_path=source_path,
                target_paths=target_paths,
                required=bool(item.get("required", True)),
            )
        )
    return tuple(copies)


def load_lan_aio_prod_slots(
    *,
    config_root: Path | str | None = None,
    include_disabled: bool = False,
) -> dict[str, LanAioProdSlot]:
    root = Path(config_root) if config_root else CONFIG_DIR
    config = load_controller_config(root)
    raw = _load_yaml(root / LAN_AIO_SLOTS_FILE)
    stable_catalog = int(raw.get("version") or 1) >= 2
    slots: dict[str, LanAioProdSlot] = {}
    for item in raw.get("slots", []):
        assignment_id = str(item["assignment_id"])
        assignment = config.assignments[assignment_id]
        node = config.nodes[assignment.node_id]
        comfy = next(unit for unit in node.comfy if unit.id == assignment.comfy_id)
        target_profile_id = str(item.get("target_profile_id") or assignment.profile_id)
        profile_label = _sanitize(target_profile_id)
        configured_gpu_index = comfy.gpu_index if comfy.gpu_index is not None else 0
        runtime_gpu_index = (
            int(item["gpu_index"])
            if item.get("gpu_index") is not None
            else comfy.gpu_index
        )
        configured_phase = str(item.get("phase") or "canary_ready")
        policy_blocked = (
            configured_phase == "maintenance_disabled"
            or configured_phase.startswith("blocked_")
        )
        slot = LanAioProdSlot(
            id=str(item["id"]),
            enabled=(not policy_blocked)
            if stable_catalog
            else bool(item.get("enabled", True)),
            phase=(
                configured_phase
                if policy_blocked or not stable_catalog
                else "catalog_ready"
            ),
            assignment_id=assignment_id,
            target_profile_id=target_profile_id,
            host_port=int(item.get("host_port") or (8190 + int(configured_gpu_index))),
            agent_id=str(
                item.get("agent_id")
                or f"lan_aio_prod_{_sanitize(node.id)}_gpu{configured_gpu_index}_{profile_label}_01"
            ),
            container_name=str(
                item.get("container_name")
                or f"allbot-lan-aio-{node.id}-gpu{configured_gpu_index}-{target_profile_id}-prod"
            ),
            ssh_host=str(item.get("ssh_host") or node.ssh_alias),
            node_id=node.id,
            comfy_id=comfy.id,
            gpu_index=runtime_gpu_index,
            legacy_worker_id=str(item.get("legacy_worker_id") or assignment.worker_id),
            old_runtime_container=str(
                item.get("old_runtime_container") or f"comfy{configured_gpu_index}"
            ),
            old_local_agent_container=str(item.get("old_local_agent_container") or ""),
            remote_dir=str(
                item.get("remote_dir")
                or f"/srv/allbot/runpod-runtime/aio-prod/{node.id}-gpu{configured_gpu_index}-{profile_label}"
            ),
            rollout_order=int(item.get("rollout_order") or 1000),
            legacy_health_port=(
                int(item["legacy_health_port"])
                if item.get("legacy_health_port") is not None
                else None
            ),
            legacy_preflight_required=bool(item.get("legacy_preflight_required", True)),
            target_task_types=tuple(
                str(task_type) for task_type in item.get("target_task_types") or []
            ),
            legacy_hot_cache_copies=_parse_legacy_hot_cache_copies(
                item.get("legacy_hot_cache_copies") or [],
                default_source_container=str(
                    item.get("old_runtime_container") or f"comfy{configured_gpu_index}"
                ),
            ),
            retargetable=(
                not policy_blocked
                if stable_catalog
                else bool(item.get("retargetable", False))
            ),
            notes=str(item.get("notes") or ""),
            gpu_device_id=_optional_str(item.get("gpu_device_id")),
        )
        if slot.enabled or include_disabled:
            slots[slot.id] = slot
    return dict(sorted(slots.items(), key=lambda entry: entry[1].rollout_order))


def slot_to_jsonable(
    slot: LanAioProdSlot,
    config: ControllerConfig,
) -> dict[str, Any]:
    profile = config.profiles.get(slot.target_profile_id)
    return {
        "id": slot.id,
        "enabled": slot.enabled,
        "phase": slot.phase,
        "assignment_id": slot.assignment_id,
        "target_profile_id": slot.target_profile_id,
        "host_port": slot.host_port,
        "agent_id": slot.agent_id,
        "container_name": slot.container_name,
        "ssh_host": slot.ssh_host,
        "node_id": slot.node_id,
        "comfy_id": slot.comfy_id,
        "gpu_index": slot.gpu_index,
        "gpu_device_id": slot.gpu_device_id,
        "legacy_worker_id": slot.legacy_worker_id,
        "old_runtime_container": slot.old_runtime_container,
        "old_local_agent_container": slot.old_local_agent_container,
        "remote_dir": slot.remote_dir,
        "legacy_health_port": slot.legacy_health_port,
        "legacy_preflight_required": slot.legacy_preflight_required,
        "target_task_types": list(slot.target_task_types),
        "retargetable": slot.retargetable,
        "physical_slot_key": physical_slot_key(slot),
        "legacy_hot_cache_copies": [
            {
                "source_container": copy.source_container,
                "source_path": copy.source_path,
                "target_paths": list(copy.target_paths),
                "required": copy.required,
            }
            for copy in slot.legacy_hot_cache_copies
        ],
        "has_all_in_one_image": bool(profile and profile.all_in_one_image_ref),
        "all_in_one_image_ref": profile.all_in_one_image_ref if profile else None,
        "model_prefix": profile.model_prefix if profile else None,
        "model_manifest_key": profile.model_manifest_key if profile else None,
        "min_vram_gb": profile.min_vram_gb if profile else None,
        "notes": slot.notes,
    }


def physical_slot_key(slot: LanAioProdSlot) -> str:
    gpu_label = f"gpu{slot.gpu_index}" if slot.gpu_index is not None else slot.comfy_id
    return f"{slot.node_id}:{gpu_label}"


def slot_mutation_blocked(slot: LanAioProdSlot) -> bool:
    # Hardware history and capacity classifications are recorded in the catalog,
    # but no longer prohibit an operator-requested LAN AIO action.
    return False


def load_env_allowlist(paths: list[Path]) -> dict[str, str]:
    values: dict[str, str] = {}
    for path in paths:
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.removeprefix("export ").strip()
            if key not in ENV_ALLOWLIST:
                continue
            values[key] = value.strip().strip('"').strip("'")
    values.setdefault(
        "LAN_AIO_AGENT_SECRET_TOKEN",
        values.get("AGENT_SECRET_TOKEN", ""),
    )
    values.setdefault("LAN_AIO_MINIO_ENDPOINT", values.get("MINIO_ENDPOINT", ""))
    values.setdefault("LAN_AIO_MINIO_ACCESS_KEY", values.get("MINIO_ACCESS_KEY", ""))
    values.setdefault("LAN_AIO_MINIO_SECRET_KEY", values.get("MINIO_SECRET_KEY", ""))
    for key, value in os.environ.items():
        if key in ENV_ALLOWLIST and value:
            values[key] = value
    return values


def runtime_env_content(values: dict[str, str]) -> str:
    required = [
        "LAN_AIO_AGENT_SECRET_TOKEN",
        "LAN_AIO_MINIO_ENDPOINT",
        "LAN_AIO_MINIO_ACCESS_KEY",
        "LAN_AIO_MINIO_SECRET_KEY",
        "LAN_MODEL_CACHE_ACCESS_KEY",
        "LAN_MODEL_CACHE_SECRET_KEY",
    ]
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise RuntimeError("missing runtime env values: " + ", ".join(missing))
    lines = []
    for key in required:
        value = values[key]
        if "\n" in value or "\r" in value:
            raise RuntimeError(f"refusing newline in runtime env value {key}")
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


class LanAioProdOps:
    def __init__(
        self,
        *,
        config_root: Path | None,
        prod_env_file: Path,
        aio_env_file: Path,
        model_env_file: Path,
        central_url: str = DEFAULT_CENTRAL_URL,
        web_health_url: str = DEFAULT_WEB_HEALTH_URL,
        state_dir: Path | None = None,
    ) -> None:
        self.config_root = config_root
        self.config = load_controller_config(config_root)
        self.slots = load_lan_aio_prod_slots(
            config_root=config_root,
            include_disabled=True,
        )
        self.prod_env_file = prod_env_file
        self.aio_env_file = aio_env_file
        self.model_env_file = model_env_file
        self.central_url = central_url.rstrip("/")
        self.web_health_url = web_health_url
        self.catalog_path = (config_root or CONFIG_DIR) / LAN_AIO_SLOTS_FILE
        self.catalog_sha256 = catalog_sha256(self.catalog_path)
        self.state_store = LanAioStateStore(state_dir)
        self.env_values = load_env_allowlist(
            [self.prod_env_file, self.model_env_file, self.aio_env_file]
        )

    def select_slots(
        self,
        slot_id: str | None,
        *,
        include_disabled: bool = False,
    ) -> list[LanAioProdSlot]:
        if slot_id:
            if slot_id not in self.slots:
                raise KeyError(f"unknown LAN AIO prod slot: {slot_id}")
            slot = self.slots[slot_id]
            if not slot.enabled and not include_disabled:
                raise RuntimeError(
                    f"slot {slot.id} is disabled ({slot.phase}); pass --include-disabled to inspect it"
                )
            return [slot]
        return [
            slot for slot in self.slots.values() if include_disabled or slot.enabled
        ]

    def list_payload(self, *, include_disabled: bool = False) -> dict[str, Any]:
        slots = self.select_slots(None, include_disabled=include_disabled)
        return {
            "ok": True,
            "slots": [slot_to_jsonable(slot, self.config) for slot in slots],
        }

    def render_compose(self, slot: LanAioProdSlot) -> str:
        rendered = RuntimePlanner(self.config).render_compose(
            slot.assignment_id,
            target_profile_id=slot.target_profile_id,
            overrides=RuntimeRenderOverrides(
                host_port=slot.host_port,
                container_name=slot.container_name,
                runtime_shape="runpod_all_in_one",
                agent_id=slot.agent_id,
                environment="cloud-prod",
                target_task_types=slot.target_task_types or None,
                gpu_index=slot.gpu_index,
                gpu_device_id=slot.gpu_device_id,
            ),
        )
        rendered = patch_baked_remote_workers(rendered, slot)
        assert_prod_compose(rendered, slot)
        return rendered

    def retarget_slot(
        self,
        candidate: LanAioProdSlot,
        replacement_target_slot_id: str,
    ) -> LanAioProdSlot:
        if slot_mutation_blocked(candidate):
            raise RuntimeError(
                f"slot {candidate.id} is blocked by catalog policy ({candidate.phase})"
            )
        if replacement_target_slot_id not in self.slots:
            raise KeyError(
                f"unknown LAN AIO replacement target slot: {replacement_target_slot_id}"
            )
        target = self.slots[replacement_target_slot_id]
        if target.id == candidate.id:
            raise RuntimeError(
                "replacement target must be different from the candidate slot"
            )
        if target.node_id != candidate.node_id:
            raise RuntimeError(
                "replacement target must be on the same GPU node: "
                f"{candidate.node_id} != {target.node_id}"
            )
        if target.target_profile_id == candidate.target_profile_id:
            raise RuntimeError(
                "replacement target already has the candidate profile: "
                f"{candidate.target_profile_id}"
            )

        target_gpu_index = target.gpu_index if target.gpu_index is not None else 0
        profile_label = _sanitize(candidate.target_profile_id)
        dir_profile_label = profile_label.replace("_", "-")
        node_dir_label = target.node_id.replace("-", "")
        remote_parent = posixpath.dirname(target.remote_dir.rstrip("/"))
        retargeted_slot_id = (
            f"{target.node_id}-gpu{target_gpu_index}-{candidate.target_profile_id}"
        )
        if candidate.id == retargeted_slot_id:
            notes = (
                f"Prepared {candidate.target_profile_id} candidate "
                f"{retargeted_slot_id} replacing {target.id}. Review and commit "
                "this YAML patch before production takeover."
            )
        else:
            notes = (
                f"Retargeted {candidate.target_profile_id} candidate from "
                f"{candidate.id} to {retargeted_slot_id} replacing {target.id}. "
                "Review and commit this YAML patch before production takeover."
            )
        return LanAioProdSlot(
            id=retargeted_slot_id,
            enabled=candidate.enabled,
            phase=candidate.phase,
            assignment_id=target.assignment_id,
            target_profile_id=candidate.target_profile_id,
            host_port=target.host_port,
            agent_id=(
                f"lan_aio_prod_{_agent_node_label(target.node_id)}_gpu{target_gpu_index}_"
                f"{profile_label}_01"
            ),
            container_name=(
                f"allbot-lan-aio-{target.node_id}-gpu{target_gpu_index}-"
                f"{candidate.target_profile_id}-prod"
            ),
            ssh_host=target.ssh_host,
            node_id=target.node_id,
            comfy_id=target.comfy_id,
            gpu_index=target.gpu_index,
            legacy_worker_id=target.agent_id,
            old_runtime_container=target.container_name,
            old_local_agent_container="",
            remote_dir=(
                f"{remote_parent}/{node_dir_label}-gpu{target_gpu_index}-"
                f"{dir_profile_label}"
            ),
            rollout_order=target.rollout_order + 1,
            legacy_health_port=target.host_port,
            legacy_preflight_required=target.legacy_preflight_required,
            target_task_types=candidate.target_task_types,
            legacy_hot_cache_copies=candidate.legacy_hot_cache_copies,
            retargetable=candidate.retargetable,
            gpu_device_id=target.gpu_device_id,
            notes=notes,
        )

    def candidate_plan(
        self,
        *,
        node_id: str,
        profile: str,
        replace_slot_id: str,
    ) -> dict[str, Any]:
        target = self.slots.get(replace_slot_id)
        if target is None:
            raise KeyError(
                f"unknown LAN AIO replacement target slot: {replace_slot_id}"
            )
        if target.node_id != node_id:
            raise RuntimeError(
                "candidate node must match replacement target node: "
                f"{node_id} != {target.node_id}"
            )
        ledger = self.state_store.load_current()
        if ledger is not None:
            physical_slot = physical_slot_key(target)
            ledger_target = (
                ((ledger.get("physical_slots") or {}).get(physical_slot) or {})
                .get("current", {})
                .get("slot_id")
            )
            if ledger_target != target.id:
                raise RuntimeError(
                    "replacement target is not current in the local ledger: "
                    f"expected {ledger_target or 'missing'}, got {target.id}"
                )
        elif not target.enabled:
            raise RuntimeError(
                f"replacement target {target.id} is not an enabled current slot"
            )
        profile_config = self.config.profiles.get(profile)
        if profile_config is None:
            raise KeyError(f"unknown LAN AIO profile: {profile}")
        if not profile_config.all_in_one_image_ref:
            raise RuntimeError(f"profile {profile} has no all_in_one_image_ref")
        if not profile_config.model_manifest_key:
            raise RuntimeError(f"profile {profile} has no model_manifest_key")

        candidate_template = self._candidate_template_for_plan(
            node_id=node_id,
            profile=profile,
            target=target,
        )
        candidate = self.retarget_slot(candidate_template, target.id)
        if not candidate.target_task_types:
            candidate = replace(
                candidate,
                target_task_types=tuple(profile_config.task_types),
            )
        yaml_item = self._slot_yaml_item(candidate, phase="candidate")
        metadata = self._runtime_metadata(candidate)
        return {
            "ok": True,
            "action": "candidate-plan",
            "node_id": node_id,
            "profile": profile,
            "replace_slot": replace_slot_id,
            "candidate_slot": yaml_item,
            "yaml_patch": _dump_yaml({"slots": [yaml_item]}),
            "render_summary": {
                "id": candidate.id,
                "node_id": candidate.node_id,
                "physical_slot_key": physical_slot_key(candidate),
                "gpu_index": candidate.gpu_index,
                "gpu_device_id": candidate.gpu_device_id,
                "host_port": candidate.host_port,
                "agent_id": candidate.agent_id,
                "container_name": candidate.container_name,
                "remote_dir": candidate.remote_dir,
                "target_profile_id": candidate.target_profile_id,
                "target_task_types": list(candidate.target_task_types),
                "image_ref": metadata.get("image_ref"),
                "model_prefix": metadata.get("model_prefix"),
                "model_manifest_key": metadata.get("model_manifest_key"),
                "workspace_host_dir": metadata.get("workspace_host_dir"),
            },
            "preflight_commands": [
                (
                    "python scripts/lan_aio_fleet_prod_ops.py render "
                    f"--slot {candidate.id} --include-disabled"
                ),
                (
                    "python scripts/lan_aio_fleet_prod_ops.py preflight "
                    f"--slot {candidate.id} --include-disabled --execute"
                ),
                (
                    "python scripts/lan_aio_fleet_prod_ops.py takeover "
                    f"--slot {candidate.id} --replace-slot {target.id} --include-disabled"
                ),
            ],
        }

    def _candidate_template_for_plan(
        self,
        *,
        node_id: str,
        profile: str,
        target: LanAioProdSlot,
    ) -> LanAioProdSlot:
        candidates = [
            slot
            for slot in self.slots.values()
            if slot.node_id == node_id
            and slot.target_profile_id == profile
            and slot.retargetable
            and slot.id != target.id
        ]
        if candidates:
            target_physical_slot_key = physical_slot_key(target)
            same_physical_slot_candidates = [
                slot
                for slot in candidates
                if physical_slot_key(slot) == target_physical_slot_key
            ]
            if same_physical_slot_candidates:
                return sorted(
                    same_physical_slot_candidates,
                    key=lambda item: item.rollout_order,
                )[0]
            return sorted(candidates, key=lambda item: item.rollout_order)[0]

        profile_config = self.config.profiles[profile]
        target_gpu_index = target.gpu_index if target.gpu_index is not None else 0
        profile_label = _sanitize(profile)
        dir_profile_label = profile_label.replace("_", "-")
        node_dir_label = target.node_id.replace("-", "")
        remote_parent = posixpath.dirname(target.remote_dir.rstrip("/"))
        return LanAioProdSlot(
            id=f"{target.node_id}-gpu{target_gpu_index}-{profile}",
            enabled=False,
            phase="candidate",
            assignment_id=target.assignment_id,
            target_profile_id=profile,
            host_port=target.host_port,
            agent_id=(
                f"lan_aio_prod_{_agent_node_label(target.node_id)}_gpu{target_gpu_index}_"
                f"{profile_label}_01"
            ),
            container_name=(
                f"allbot-lan-aio-{target.node_id}-gpu{target_gpu_index}-{profile}-prod"
            ),
            ssh_host=target.ssh_host,
            node_id=target.node_id,
            comfy_id=target.comfy_id,
            gpu_index=target.gpu_index,
            gpu_device_id=target.gpu_device_id,
            legacy_worker_id=target.agent_id,
            old_runtime_container=target.container_name,
            old_local_agent_container="",
            remote_dir=(
                f"{remote_parent}/{node_dir_label}-gpu{target_gpu_index}-"
                f"{dir_profile_label}"
            ),
            rollout_order=target.rollout_order + 1,
            legacy_health_port=target.host_port,
            legacy_preflight_required=target.legacy_preflight_required,
            target_task_types=tuple(profile_config.task_types),
            retargetable=True,
            notes=(
                f"Generated candidate plan for {profile} replacing {target.id}. "
                "Review and commit this YAML patch before production takeover."
            ),
        )

    def _slot_yaml_item(
        self,
        slot: LanAioProdSlot,
        *,
        phase: str,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {
            "id": slot.id,
            "enabled": False,
            "phase": phase,
            "retargetable": True,
            "assignment_id": slot.assignment_id,
            "target_profile_id": slot.target_profile_id,
        }
        if slot.target_task_types:
            item["target_task_types"] = list(slot.target_task_types)
        if slot.gpu_index is not None:
            item["gpu_index"] = slot.gpu_index
        if slot.gpu_device_id is not None:
            item["gpu_device_id"] = slot.gpu_device_id
        item.update(
            {
                "host_port": slot.host_port,
                "legacy_health_port": slot.legacy_health_port,
                "legacy_preflight_required": slot.legacy_preflight_required,
                "agent_id": slot.agent_id,
                "container_name": slot.container_name,
                "remote_dir": slot.remote_dir,
                "rollout_order": slot.rollout_order,
            }
        )
        return {key: value for key, value in item.items() if value not in (None, "")}

    def status_payload(self, slots: list[LanAioProdSlot]) -> dict[str, Any]:
        workers = self._system_workers()
        payload = {
            "ok": True,
            "central_url": self.central_url,
            "slots": [],
        }
        for slot in slots:
            worker_targets = {slot.legacy_worker_id, slot.agent_id}
            worker_rows = [
                _worker_summary(worker)
                for worker in workers
                if worker.get("agent_id") in worker_targets
            ]
            payload["slots"].append(
                {
                    "slot": slot_to_jsonable(slot, self.config),
                    "workers": worker_rows,
                    "control": {
                        "legacy": self._control_state(slot.legacy_worker_id),
                        "aio": self._control_state(slot.agent_id),
                    },
                    "remote_containers": self._remote_container_status(slot),
                    "model_cache": self._remote_cache_marker(slot),
                }
            )
        return payload

    def live_current_snapshot(
        self,
        physical_slots: set[str],
    ) -> dict[str, Any]:
        current: dict[str, str | None] = {}
        errors: dict[str, str] = {}
        observations: dict[str, list[dict[str, Any]]] = {}
        try:
            workers = {
                str(item.get("agent_id")): item
                for item in self._system_workers()
                if item.get("agent_id")
            }
        except Exception as exc:
            return {
                "current": {physical_slot: None for physical_slot in physical_slots},
                "errors": {
                    physical_slot: f"Central worker status unavailable: {exc}"
                    for physical_slot in physical_slots
                },
                "observations": {},
            }
        for physical_slot in sorted(physical_slots):
            siblings = [
                slot
                for slot in self.slots.values()
                if physical_slot_key(slot) == physical_slot
            ]
            if not siblings:
                current[physical_slot] = None
                errors[physical_slot] = "physical slot is absent from catalog"
                continue
            slot_observations: list[dict[str, Any]] = []
            try:
                for slot in siblings:
                    state = self._remote_target_container_state(slot)
                    slot_observations.append(
                        {
                            "slot_id": slot.id,
                            "container_name": slot.container_name,
                            **state,
                        }
                    )
            except Exception as exc:
                current[physical_slot] = None
                errors[physical_slot] = str(exc)
                observations[physical_slot] = slot_observations
                continue
            running = [item for item in slot_observations if bool(item.get("running"))]
            observations[physical_slot] = slot_observations
            if len(running) == 1:
                live_slot_id = str(running[0]["slot_id"])
                live_slot = self.slots[live_slot_id]
                worker = workers.get(live_slot.agent_id)
                if worker is None:
                    current[physical_slot] = None
                    errors[physical_slot] = (
                        f"running container has no Central worker: {live_slot.agent_id}"
                    )
                    continue
                expected_worker = {
                    "node_id": live_slot.node_id,
                    "provider": "lan_ssh",
                    "runtime_profile": self.config.profiles[
                        live_slot.target_profile_id
                    ].runtime_profile,
                }
                metadata_errors = [
                    f"{key}={worker.get(key)!r} expected={value!r}"
                    for key, value in expected_worker.items()
                    if worker.get(key) != value
                ]
                if worker.get("pool_managed") not in (True, "true", "True", "1", 1):
                    metadata_errors.append(
                        f"pool_managed={worker.get('pool_managed')!r}"
                    )
                running[0]["worker"] = _worker_summary(worker)
                if metadata_errors:
                    current[physical_slot] = None
                    errors[physical_slot] = (
                        "Central worker metadata mismatch: "
                        + ", ".join(metadata_errors)
                    )
                    continue
                current[physical_slot] = live_slot_id
            elif not running:
                current[physical_slot] = None
            else:
                current[physical_slot] = None
                errors[physical_slot] = "multiple running catalog slots: " + ", ".join(
                    str(item["slot_id"]) for item in running
                )
        return {
            "current": current,
            "errors": errors,
            "observations": observations,
        }

    def state_status_payload(self, physical_slots: set[str]) -> dict[str, Any]:
        ledger = self.state_store.load_current()
        scoped_ledger = ledger
        if ledger is not None:
            scoped_ledger = {
                **ledger,
                "physical_slots": {
                    key: value
                    for key, value in (ledger.get("physical_slots") or {}).items()
                    if key in physical_slots
                },
            }
        live = self.live_current_snapshot(physical_slots)
        report = assess_state_drift(
            live_current=live["current"],
            live_errors=live["errors"],
            ledger=scoped_ledger,
            catalog_slot_ids=set(self.slots),
            catalog_sha256=self.catalog_sha256,
        )
        unfinished = self.state_store.unfinished_operations()
        if unfinished:
            report["status"] = "blocked"
            report["drift"].append(
                {
                    "physical_slot": None,
                    "kind": "unfinished_operation",
                    "operation_ids": unfinished,
                }
            )
        report["state_dir"] = str(self.state_store.state_dir)
        report["current_path"] = str(self.state_store.current_path)
        report["live_observations"] = live["observations"]
        return report

    def _current_entry_for_slot(self, slot: LanAioProdSlot) -> dict[str, Any]:
        profile = self.config.profiles[slot.target_profile_id]
        entry: dict[str, Any] = {
            "slot_id": slot.id,
            "profile": slot.target_profile_id,
            "agent_id": slot.agent_id,
            "container_name": slot.container_name,
            "host_port": slot.host_port,
            "state": "running",
            "image_ref": profile.all_in_one_image_ref,
            "model_manifest_key": profile.model_manifest_key,
            "last_verified_at": datetime.now(timezone.utc).isoformat(),
        }
        if slot.gpu_device_id:
            entry["gpu_device_id"] = slot.gpu_device_id
        try:
            metadata = self._runtime_metadata(slot)
        except Exception:
            metadata = {}
        if metadata.get("workspace_host_dir"):
            entry["workspace_host_dir"] = metadata["workspace_host_dir"]
        return {key: value for key, value in entry.items() if value is not None}

    @staticmethod
    def _cache_marker_from_result(result: dict[str, Any]) -> dict[str, Any] | None:
        if isinstance(result.get("model_cache"), dict):
            return dict(result["model_cache"])
        for step in result.get("steps") or []:
            if step.get("action") != "warm-cache":
                continue
            payload = step.get("payload") or {}
            if isinstance(payload.get("model_cache"), dict):
                return dict(payload["model_cache"])
        return None

    @staticmethod
    def _upsert_cached_profile(
        physical_state: dict[str, Any],
        marker: dict[str, Any],
    ) -> None:
        profile = str(marker.get("profile") or "")
        if not profile:
            return
        cache_entry = {
            "profile": profile,
            "cache_state": marker.get("status") or "ready",
            "image_ref": marker.get("image_ref"),
            "model_manifest_key": marker.get("model_manifest_key"),
            "workspace_host_dir": marker.get("workspace_host_dir"),
            "synced_at": marker.get("synced_at"),
        }
        cache_entry = {
            key: value for key, value in cache_entry.items() if value is not None
        }
        cached_profiles = list(physical_state.get("cached_profiles") or [])
        cached_profiles = [
            item for item in cached_profiles if item.get("profile") != profile
        ]
        cached_profiles.append(cache_entry)
        physical_state["cached_profiles"] = sorted(
            cached_profiles, key=lambda item: str(item.get("profile") or "")
        )

    def execute_managed_mutation(
        self,
        *,
        action: str,
        slots: list[LanAioProdSlot],
        operation_id: str,
        execute: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        physical_slots = {physical_slot_key(slot) for slot in slots}
        if not physical_slots:
            raise RuntimeError("managed LAN AIO mutation requires a physical slot")
        with self.state_store.mutation_lock():
            report = self.state_status_payload(physical_slots)
            # Live/catalog/ledger divergence and incomplete historical operations are
            # retained as audit observations. They no longer prevent an explicitly
            # requested single-slot mutation.
            ledger = self.state_store.load_current() or {"physical_slots": {}}
            request = {
                "slots": [slot.id for slot in slots],
                "catalog_sha256": self.catalog_sha256,
                "live_before": report.get("live_current"),
            }
            self.state_store.begin_operation(
                operation_id,
                action=action,
                physical_slots=sorted(physical_slots),
                request=request,
            )
            try:
                result = execute()
                live_after = self.live_current_snapshot(physical_slots)

                updated = dict(ledger)
                updated["catalog_sha256"] = self.catalog_sha256
                updated_physical = {
                    key: dict(value)
                    for key, value in (ledger.get("physical_slots") or {}).items()
                }
                updated["physical_slots"] = updated_physical
                for physical_slot in physical_slots:
                    physical_state = updated_physical.setdefault(physical_slot, {})
                    observed_slot_id = (live_after.get("current") or {}).get(
                        physical_slot
                    )
                    observed_slot = self.slots.get(str(observed_slot_id or ""))
                    if action == "canary-stop-disabled" and observed_slot is None:
                        physical_state["current"] = {}
                        physical_state["intentionally_empty"] = {
                            "reason": "disabled canary stopped after local acceptance",
                            "recorded_at": datetime.now(timezone.utc).isoformat(),
                            "operation_id": operation_id,
                        }
                    else:
                        physical_state["current"] = (
                            self._current_entry_for_slot(observed_slot)
                            if observed_slot is not None
                            else {}
                        )
                        if observed_slot is not None:
                            physical_state.pop("intentionally_empty", None)
                    physical_state["last_verified_at"] = datetime.now(
                        timezone.utc
                    ).isoformat()
                    physical_state["last_operation_id"] = operation_id
                marker = self._cache_marker_from_result(result)
                if marker:
                    marker_physical_slot = str(marker.get("physical_slot_key") or "")
                    if marker_physical_slot in updated_physical:
                        self._upsert_cached_profile(
                            updated_physical[marker_physical_slot], marker
                        )
                self.state_store.write_current(
                    updated,
                    operation_id=operation_id,
                )
                self.state_store.finish_operation(
                    operation_id,
                    status="succeeded",
                    result={
                        "payload": result,
                        "live_after": live_after.get("current"),
                    },
                )
            except Exception as exc:
                history_path = self.state_store.history_dir / f"{operation_id}.json"
                if history_path.exists():
                    try:
                        history = json.loads(history_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        history = {}
                    if history.get("status") == "in_progress":
                        status = (
                            "rolled_back"
                            if "recovery_status=succeeded" in str(exc)
                            else "failed"
                        )
                        self.state_store.finish_operation(
                            operation_id,
                            status=status,
                            error=str(exc),
                        )
                raise
        return {**result, "operation_id": operation_id}

    def current_slot_id(self, physical_slot: str) -> str:
        ledger = self.state_store.load_current()
        if ledger is None:
            raise StateDriftError(
                "LAN AIO current ledger is missing; run state-init before mutation"
            )
        slot_id = (
            ((ledger.get("physical_slots") or {}).get(physical_slot) or {})
            .get("current", {})
            .get("slot_id")
        )
        if not slot_id:
            raise StateDriftError(
                f"LAN AIO ledger has no current slot for {physical_slot}"
            )
        if slot_id not in self.slots:
            raise StateDriftError(
                f"LAN AIO ledger current slot is absent from catalog: {slot_id}"
            )
        return str(slot_id)

    def recovery_guard_slot_id(
        self,
        physical_slot: str,
        *,
        selected_slot_id: str | None = None,
    ) -> str:
        """Resolve the recover guard, including an explicitly reconciled empty slot."""

        ledger = self.state_store.load_current()
        if ledger is None:
            raise StateDriftError(
                "LAN AIO current ledger is missing; run state-init before mutation"
            )
        physical_state = (ledger.get("physical_slots") or {}).get(physical_slot) or {}
        current_slot_id = (physical_state.get("current") or {}).get("slot_id")
        if current_slot_id:
            return self.current_slot_id(physical_slot)
        if not physical_state.get("intentionally_empty") or not selected_slot_id:
            raise StateDriftError(
                f"LAN AIO ledger has no current slot for {physical_slot}"
            )
        selected = self.slots.get(selected_slot_id)
        if selected is None or physical_slot_key(selected) != physical_slot:
            raise StateDriftError(
                "LAN AIO explicitly selected recovery slot does not match "
                f"{physical_slot}: {selected_slot_id}"
            )
        return selected.id

    def initialize_state_from_legacy(
        self,
        legacy_state_file: Path,
        *,
        operation_id: str,
    ) -> dict[str, Any]:
        if self.state_store.load_current() is not None:
            raise RuntimeError(
                f"LAN AIO current state already exists: {self.state_store.current_path}"
            )
        legacy = _load_yaml(legacy_state_file)
        current = self.state_store.migrate_legacy_state(
            legacy,
            catalog_sha256=self.catalog_sha256,
            operation_id=operation_id,
        )
        physical_slots = set(current.get("physical_slots") or {})
        report = self.state_status_payload(physical_slots)
        return {
            "ok": report.get("status") == "passed",
            "action": "state-init",
            "operation_id": operation_id,
            "current_path": str(self.state_store.current_path),
            "state": report,
        }

    def reconcile_state_from_live(
        self,
        *,
        operation_id: str,
        reason: str,
        allow_empty_physical_slots: set[str] | None = None,
    ) -> dict[str, Any]:
        if not reason.strip():
            raise RuntimeError("state-reconcile requires a non-empty reason")
        ledger = self.state_store.load_current()
        if ledger is None:
            raise RuntimeError(
                "state-reconcile requires existing current.yml; run state-init"
            )
        physical_slots = set(ledger.get("physical_slots") or {})
        if not physical_slots:
            raise RuntimeError("state-reconcile found no physical slots in current.yml")
        allowed_empty = set(allow_empty_physical_slots or ())
        ledger_physical_slots = ledger.get("physical_slots") or {}
        preserved_empty = {
            physical_slot
            for physical_slot, physical_state in ledger_physical_slots.items()
            if physical_state.get("intentionally_empty")
            and not (physical_state.get("current") or {}).get("slot_id")
        }
        effective_allowed_empty = allowed_empty | preserved_empty
        unknown_empty = allowed_empty - physical_slots
        if unknown_empty:
            raise RuntimeError(
                "state-reconcile empty physical slot is absent from current.yml: "
                + ", ".join(sorted(unknown_empty))
            )
        with self.state_store.mutation_lock():
            unfinished = self.state_store.unfinished_operations()
            live = self.live_current_snapshot(physical_slots)
            errors = dict(live.get("errors") or {})
            for physical_slot in physical_slots:
                if (
                    not (live.get("current") or {}).get(physical_slot)
                    and physical_slot not in effective_allowed_empty
                ):
                    errors.setdefault(physical_slot, "no running catalog slot detected")
            if errors:
                raise StateDriftError(
                    "state-reconcile requires unambiguous live state: "
                    + "; ".join(
                        f"{key}={value}" for key, value in sorted(errors.items())
                    )
                )
            for unfinished_operation_id in unfinished:
                self.state_store.finish_operation(
                    unfinished_operation_id,
                    status="failed",
                    error=(
                        f"superseded by {operation_id} after explicit live inspection: "
                        f"{reason}"
                    ),
                )
            self.state_store.begin_operation(
                operation_id,
                action="state-reconcile",
                physical_slots=sorted(physical_slots),
                request={
                    "reason": reason,
                    "live_current": live["current"],
                    "allowed_empty_physical_slots": sorted(allowed_empty),
                    "preserved_empty_physical_slots": sorted(preserved_empty),
                    "catalog_sha256": self.catalog_sha256,
                    "superseded_operations": unfinished,
                },
            )
            updated = dict(ledger)
            updated["catalog_sha256"] = self.catalog_sha256
            updated_physical = {
                key: dict(value)
                for key, value in (ledger.get("physical_slots") or {}).items()
            }
            updated["physical_slots"] = updated_physical
            for physical_slot, slot_id in live["current"].items():
                physical_state = updated_physical.setdefault(physical_slot, {})
                if slot_id:
                    slot = self.slots[str(slot_id)]
                    physical_state["current"] = self._current_entry_for_slot(slot)
                    physical_state.pop("intentionally_empty", None)
                elif physical_slot in allowed_empty:
                    physical_state["current"] = {}
                    physical_state["intentionally_empty"] = {
                        "reason": reason,
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                        "operation_id": operation_id,
                    }
                elif physical_slot in preserved_empty:
                    continue
                else:  # guarded by the ambiguity check above
                    continue
                physical_state["last_verified_at"] = datetime.now(
                    timezone.utc
                ).isoformat()
                physical_state["last_operation_id"] = operation_id
            self.state_store.write_current(updated, operation_id=operation_id)
            self.state_store.finish_operation(
                operation_id,
                status="succeeded",
                result={
                    "live_current": live["current"],
                    "reason": reason,
                    "superseded_operations": unfinished,
                },
            )
        return {
            "ok": True,
            "action": "state-reconcile",
            "operation_id": operation_id,
            "current_path": str(self.state_store.current_path),
            "live_current": live["current"],
        }

    def preflight_payload(
        self,
        slots: list[LanAioProdSlot],
        *,
        execute: bool,
    ) -> dict[str, Any]:
        if not execute:
            return {
                "ok": True,
                "dry_run": True,
                "checks": [
                    "prod Central health",
                    "prod Web health",
                    "LAN registry health",
                    "LAN model cache health",
                    "per-slot legacy ComfyUI /system_stats and /queue",
                    "per-slot Docker daemon sees 192.168.1.115:5000 insecure registry",
                    "runtime-render cloud-prod compose for each enabled slot",
                ],
                "slots": [slot.id for slot in slots],
            }
        checks: list[dict[str, Any]] = []
        for name, url in (
            ("prod_central_health", f"{self.central_url}/health"),
            ("prod_web_health", self.web_health_url),
            ("lan_registry_health", DEFAULT_REGISTRY_HEALTH_URL),
            ("lan_model_cache_health", DEFAULT_MODEL_CACHE_HEALTH_URL),
        ):
            checks.append(self._http_check(name, url))
        results = []
        for slot in slots:
            self.render_compose(slot)
            port = _legacy_port_for_slot(self.config, slot)
            image_ref = self.config.profiles[
                slot.target_profile_id
            ].all_in_one_image_ref
            legacy_checks = []
            if slot.legacy_preflight_required:
                legacy_checks.extend(
                    [
                        self._remote_check(
                            slot,
                            "legacy_system_stats",
                            f"curl -fsS --max-time 8 http://127.0.0.1:{port}/system_stats >/dev/null",
                            attempts=5,
                            retry_delay_seconds=3.0,
                        ),
                        self._remote_check(
                            slot,
                            "legacy_queue",
                            f"curl -fsS --max-time 8 http://127.0.0.1:{port}/queue >/dev/null",
                            attempts=5,
                            retry_delay_seconds=3.0,
                        ),
                    ]
                )
            else:
                legacy_checks.append(
                    self._remote_check(
                        slot,
                        "legacy_health_optional",
                        (
                            f"curl -fsS --max-time 8 http://127.0.0.1:{port}/queue "
                            ">/dev/null 2>&1 && echo legacy_port_ready || "
                            "echo legacy_port_not_required"
                        ),
                    )
                )
            port_owner_check = self._host_port_owner_check(
                slot,
                allowed_containers={slot.container_name, slot.old_runtime_container},
            )
            slot_checks = [
                *legacy_checks,
                port_owner_check,
                self._image_readiness_check(slot, image_ref),
                self._remote_check(slot, "disk_root", "df -h / | tail -1"),
            ]
            results.append(
                {
                    "slot": slot.id,
                    "ssh_host": slot.ssh_host,
                    "legacy_port": port,
                    "checks": slot_checks,
                }
            )
        ok = all(item["ok"] for item in checks) and all(
            check["ok"] for slot_result in results for check in slot_result["checks"]
        )
        return {"ok": ok, "dry_run": False, "checks": checks, "slots": results}

    def dry_run_action(
        self, action: str, slots: list[LanAioProdSlot]
    ) -> dict[str, Any]:
        operations: list[str] = []
        for slot in slots:
            if action == "takeover":
                operations.extend(
                    f"run {step} for {slot.id}" for step in TAKEOVER_STEPS
                )
            elif action == "canary-start-disabled":
                operations.extend(
                    f"run {step} for {slot.id}" for step in DISABLED_CANARY_START_STEPS
                )
                operations.append(f"keep {slot.agent_id}=disabled")
            elif action == "canary-stop-disabled":
                operations.extend(
                    [
                        f"set {slot.agent_id}=disabled",
                        f"wait for {slot.agent_id} and ComfyUI queue to become idle",
                        f"stop disabled canary container {slot.container_name}",
                        f"record {physical_slot_key(slot)} intentionally empty",
                    ]
                )
            elif action == "configure-registry":
                operations.extend(
                    [
                        f"backup {slot.ssh_host}:/etc/docker/daemon.json",
                        f"add 192.168.1.115:5000 to {slot.ssh_host} Docker insecure registries",
                        f"restart Docker on {slot.ssh_host}",
                        "verify only candidates running before the Docker restart recover; "
                        "keep intentionally empty slots empty",
                    ]
                )
            elif action == "pull-image":
                image_ref = self.config.profiles[
                    slot.target_profile_id
                ].all_in_one_image_ref
                operations.append(f"ssh {slot.ssh_host} docker pull {image_ref}")
            elif action == "warm-cache":
                operations.extend(
                    [
                        f"render runtime metadata for {slot.id}",
                        "use remote_workers baked into the exact profile image",
                        f"copy model-cache env to {slot.ssh_host}:{slot.remote_env_file}",
                        f"docker run --rm without ports or agent for {slot.target_profile_id}",
                        f"sync {slot.target_profile_id} manifest models into the slot workspace",
                        f"write {WARM_CACHE_MARKER_FILE} under {slot.remote_dir}",
                    ]
                )
            elif action == "start-disabled":
                operations.extend(
                    [
                        f"render compose for {slot.id}",
                        "use remote_workers baked into the exact profile image",
                        f"copy env/compose to {slot.ssh_host}:{slot.remote_dir}",
                        f"set {slot.agent_id}=disabled",
                        f"docker compose up -d {slot.container_name}",
                        f"preseed {len(slot.legacy_hot_cache_copies)} legacy hot cache file(s)",
                        f"verify disabled heartbeat for {slot.agent_id}",
                    ]
                )
            elif action == "drain-legacy":
                operations.append(f"set {slot.legacy_worker_id}=draining")
            elif action == "enable-aio":
                operations.extend(
                    [
                        f"set {slot.legacy_worker_id}=disabled",
                        f"verify {slot.legacy_worker_id} is idle and disabled",
                        f"verify old runtime {slot.old_runtime_container} is not using GPU memory",
                        f"set {slot.agent_id}=enabled",
                    ]
                )
            elif action == "drain-aio":
                operations.append(f"set {slot.agent_id}=draining")
            elif action == "disable-aio":
                operations.append(f"set {slot.agent_id}=disabled")
            elif action == "restart-aio":
                operations.extend(
                    [
                        f"set {slot.agent_id}=disabled",
                        f"restart LAN AIO container {slot.container_name} on {slot.ssh_host}",
                        f"verify {slot.container_name} health and disabled heartbeat",
                        f"set {slot.agent_id}=enabled",
                    ]
                )
            elif action == "rollback":
                operations.extend(
                    [
                        f"set {slot.agent_id}=disabled",
                        f"ssh {slot.ssh_host} docker start {slot.old_runtime_container}",
                        f"local docker start {slot.old_local_agent_container}",
                        f"set {slot.legacy_worker_id}=enabled",
                    ]
                )
            elif action == "stop-old":
                operations.extend(
                    [
                        f"set {slot.legacy_worker_id}=disabled",
                        f"ssh {slot.ssh_host} docker stop {slot.old_runtime_container}",
                    ]
                )
                if slot.old_local_agent_container:
                    operations.append(
                        f"local docker stop {slot.old_local_agent_container}"
                    )
        return {"ok": True, "dry_run": True, "action": action, "operations": operations}

    def drain_legacy(self, slots: list[LanAioProdSlot]) -> dict[str, Any]:
        for slot in slots:
            self._set_control(
                slot.legacy_worker_id,
                "draining",
                "lan_aio_fleet_drain_legacy",
                ttl_seconds=CONTROL_TTL_SECONDS,
            )
        return {
            "ok": True,
            "action": "drain-legacy",
            "slots": [slot.id for slot in slots],
        }

    def enable_aio(self, slots: list[LanAioProdSlot]) -> dict[str, Any]:
        gated = []
        for slot in slots:
            self._set_control(
                slot.legacy_worker_id,
                "disabled",
                "lan_aio_fleet_disable_legacy",
                ttl_seconds=CONTROL_TTL_SECONDS,
            )
            gate = self._assert_enable_aio_gate(slot)
            self._set_control(slot.agent_id, "enabled", "lan_aio_fleet_enable_aio")
            gated.append(gate)
        return {
            "ok": True,
            "action": "enable-aio",
            "slots": [slot.id for slot in slots],
            "gates": gated,
        }

    def drain_aio(self, slots: list[LanAioProdSlot]) -> dict[str, Any]:
        for slot in slots:
            self._set_control(
                slot.agent_id,
                "draining",
                "lan_aio_fleet_drain_aio",
                ttl_seconds=CONTROL_TTL_SECONDS,
            )
        return {"ok": True, "action": "drain-aio", "slots": [slot.id for slot in slots]}

    def disable_aio(self, slots: list[LanAioProdSlot]) -> dict[str, Any]:
        for slot in slots:
            self._set_control(
                slot.agent_id,
                "disabled",
                "lan_aio_fleet_disable_aio",
                ttl_seconds=CONTROL_TTL_SECONDS,
            )
        return {
            "ok": True,
            "action": "disable-aio",
            "slots": [slot.id for slot in slots],
        }

    def restart_aio(self, slots: list[LanAioProdSlot]) -> dict[str, Any]:
        if len(slots) != 1:
            raise RuntimeError("restart-aio requires exactly one --slot")
        slot = slots[0]
        self._set_control(
            slot.agent_id,
            "disabled",
            "lan_aio_fleet_restart_disable_aio",
            ttl_seconds=CONTROL_TTL_SECONDS,
        )
        self._wait_worker_ids_idle({slot.agent_id})
        self._write_remote_runtime_files(slot)
        port_owner_check = self._host_port_owner_check(
            slot,
            allowed_containers={slot.container_name},
        )
        if not port_owner_check["ok"]:
            raise RuntimeError(str(port_owner_check["error"]))
        self._remote_compose(slot, "up -d --force-recreate")
        self._wait_container_health(slot)
        self._verify_disabled_heartbeat(slot)
        self._set_control(
            slot.agent_id,
            "enabled",
            "lan_aio_fleet_restart_enable_aio",
        )
        return {"ok": True, "action": "restart-aio", "slot": slot.id}

    def release_rollout(
        self,
        slot: LanAioProdSlot,
        resolved: dict[str, Any],
        *,
        rollback_ref: str | None = None,
    ) -> dict[str, Any]:
        """Recreate one LAN slot from an exact release digest with local rollback."""

        release_profile = {
            "img2img_lora": "img2img",
        }.get(slot.target_profile_id, slot.target_profile_id)
        if release_profile != resolved["profile"]:
            raise RuntimeError(
                "release profile does not match selected LAN slot: "
                f"{resolved['profile']} != {slot.target_profile_id}"
            )
        old_profile = self.config.profiles[slot.target_profile_id]
        old_ref = old_profile.all_in_one_image_ref
        if not old_ref:
            raise RuntimeError("selected LAN slot has no rollback image reference")
        current_repository = old_ref.split("@", 1)[0]
        current_tail = current_repository.rsplit("/", 1)[-1]
        if ":" in current_tail:
            current_repository = current_repository.rsplit(":", 1)[0]
        if rollback_ref is None:
            old_ref = self._exact_remote_image_ref(slot, old_ref)
        else:
            if not re.search(r"@sha256:[0-9a-f]{64}$", rollback_ref):
                raise RuntimeError(
                    "explicit LAN rollback ref must be an exact digest-pinned image"
                )
            rollback_repository = rollback_ref.split("@", 1)[0]
            if current_repository != rollback_repository:
                raise RuntimeError(
                    "explicit LAN rollback ref must use the same repository as "
                    "the current image"
                )
            old_ref = rollback_ref
        target_ref = str(resolved["ref"])
        target_repository = target_ref.split("@", 1)[0]
        if target_repository != current_repository:
            target_ref = f"{current_repository}@{resolved['digest']}"
        runtime_resolved = {**resolved, "ref": target_ref}
        rollback_profile = replace(old_profile, all_in_one_image_ref=old_ref)
        target_profile = replace(
            old_profile,
            all_in_one_image_ref=target_ref,
            model_manifest_key=str(
                resolved.get("model_manifest_key") or old_profile.model_manifest_key
            ),
        )
        if rollback_ref is not None:
            self.config.profiles[slot.target_profile_id] = rollback_profile
            self.pull_image([slot])
        self.config.profiles[slot.target_profile_id] = target_profile
        try:
            self.pull_image([slot])
            self._set_control(
                slot.agent_id,
                "disabled",
                "lan_aio_release_rollout_disable",
                ttl_seconds=CONTROL_TTL_SECONDS,
            )
            self._wait_worker_ids_idle({slot.agent_id})
            self._write_remote_runtime_files(slot)
            self._remote_compose(slot, "up -d --force-recreate")
            self._wait_container_health(slot)
            self._verify_release_runtime(slot, runtime_resolved)
            self._verify_disabled_heartbeat(slot)
            self._set_control(
                slot.agent_id,
                "enabled",
                "lan_aio_release_rollout_enable",
            )
        except Exception as rollout_error:
            self.config.profiles[slot.target_profile_id] = rollback_profile
            try:
                self._set_control(
                    slot.agent_id,
                    "disabled",
                    "lan_aio_release_rollout_rollback",
                    ttl_seconds=CONTROL_TTL_SECONDS,
                )
                self._write_remote_runtime_files(slot)
                self._remote_compose(slot, "up -d --force-recreate")
                self._wait_container_health(slot)
                self._verify_exact_runtime_ref(slot, old_ref)
                self._verify_disabled_heartbeat(slot)
                self._set_control(
                    slot.agent_id,
                    "enabled",
                    "lan_aio_release_rollout_rollback_complete",
                )
            except Exception as rollback_error:
                self._set_control(
                    slot.agent_id,
                    "disabled",
                    "lan_aio_release_rollout_rollback_failed",
                    ttl_seconds=CONTROL_TTL_SECONDS,
                )
                raise RuntimeError(
                    f"slot rollout failed ({rollout_error}); rollback failed "
                    f"({rollback_error}); slot remains disabled"
                ) from rollback_error
            raise RuntimeError(
                f"slot rollout failed and old image was restored: {rollout_error}"
            ) from rollout_error
        return {
            "ok": True,
            "action": "release-rollout",
            "slot": slot.id,
            "old_ref": old_ref,
            "target_ref": target_ref,
            "digest": resolved["digest"],
            "oci_revision": resolved["oci_revision"],
            "validation_level": resolved["validation_level"],
        }

    def _verify_release_runtime(
        self, slot: LanAioProdSlot, resolved: dict[str, Any]
    ) -> None:
        ref = shlex.quote(str(resolved["ref"]))
        container = shlex.quote(slot.container_name)
        revision = shlex.quote(str(resolved["oci_revision"]))
        command = (
            "set -euo pipefail; "
            f"test \"$(docker inspect -f '{{{{.Config.Image}}}}' {container})\" = {ref}; "
            "actual_revision=$(docker image inspect "
            f"{ref} -f '{{{{index .Config.Labels \"org.opencontainers.image.revision\"}}}}'); "
            f'test "$actual_revision" = {revision}; '
            f"{self._pipeline_runtime_contract_checks(slot, container)}"
        )
        self._ssh(slot.ssh_host, command)

    def _verify_exact_runtime_ref(self, slot: LanAioProdSlot, image_ref: str) -> None:
        container = shlex.quote(slot.container_name)
        ref = shlex.quote(image_ref)
        self._ssh(
            slot.ssh_host,
            (
                "set -euo pipefail; "
                f"test \"$(docker inspect -f '{{{{.Config.Image}}}}' {container})\" = {ref}; "
                f"{self._pipeline_runtime_contract_checks(slot, container)}"
            ),
        )

    @staticmethod
    def _pipeline_runtime_contract_checks(
        slot: LanAioProdSlot,
        container: str,
    ) -> str:
        policy = pipeline_policy_for_profile(slot.target_profile_id)
        if not policy:
            return ":"
        expected = (
            f"PIPELINE_PROFILE_POLICY={policy}",
            "PIPELINE_MAX_RUNNING_TASKS=1",
            "PIPELINE_MAX_CLAIMED_TASKS=2",
            "PIPELINE_DELIVERY_CONCURRENCY=1",
        )
        checks = " ".join(
            f"printf '%s\\n' \"$pipeline_env\" | grep -Fxq {shlex.quote(value)};"
            for value in expected
        )
        return (
            'pipeline_env="$(docker inspect -f '
            "'{{range .Config.Env}}{{println .}}{{end}}' "
            f'{container})"; {checks}'
        )

    def _exact_remote_image_ref(self, slot: LanAioProdSlot, image_ref: str) -> str:
        if re.search(r"@sha256:[0-9a-f]{64}$", image_ref):
            return image_ref
        output = self._ssh(
            slot.ssh_host,
            (
                "docker image inspect "
                f"{shlex.quote(image_ref)} "
                "-f '{{index .RepoDigests 0}}'"
            ),
            capture=True,
        ).strip()
        if not re.search(r"@sha256:[0-9a-f]{64}$", output):
            raise RuntimeError(
                "selected LAN slot has no exact digest-pinned rollback image"
            )
        return output

    def configure_registry(self, slots: list[LanAioProdSlot]) -> dict[str, Any]:
        touched_hosts: dict[str, list[LanAioProdSlot]] = {}
        for slot in slots:
            touched_hosts.setdefault(slot.ssh_host, []).append(slot)
        running_before = {
            slot.id: self._ssh(
                slot.ssh_host,
                (
                    "docker inspect -f '{{.State.Running}}' "
                    f"'{slot.container_name}' 2>/dev/null || true"
                ),
                capture=True,
            ).strip()
            == "true"
            for slot in slots
        }
        for host, host_slots in touched_hosts.items():
            self._configure_registry_on_host(host)
            for slot in host_slots:
                # Docker restart may leave the retained rollback container stopped.
                # Only candidates that were running before the restart must recover;
                # an intentionally empty slot must remain empty.
                if running_before[slot.id]:
                    self._wait_container_health(slot)
        return {
            "ok": True,
            "action": "configure-registry",
            "hosts": sorted(touched_hosts),
            "recovered_running_slots": sorted(
                slot.id for slot in slots if running_before[slot.id]
            ),
        }

    def pull_image(self, slots: list[LanAioProdSlot]) -> dict[str, Any]:
        pulled = []
        for slot in slots:
            image_ref = self.config.profiles[
                slot.target_profile_id
            ].all_in_one_image_ref
            if not image_ref:
                raise RuntimeError(
                    f"profile {slot.target_profile_id} has no all_in_one_image_ref"
                )
            if self._remote_image_present(slot, image_ref):
                pulled.append(
                    {
                        "slot": slot.id,
                        "image_ref": image_ref,
                        "status": "already_present",
                    }
                )
                continue
            try:
                pull_pattern = re.escape(f"docker pull {image_ref}")
                self._ssh(
                    slot.ssh_host,
                    f"pkill -f '^{pull_pattern}$' || true; "
                    f"timeout {IMAGE_PULL_TIMEOUT_SECONDS} docker pull '{image_ref}'",
                    capture=True,
                )
            except subprocess.CalledProcessError as exc:
                if not self._local_image_present(image_ref):
                    error = (exc.stderr or exc.stdout or "").strip()
                    raise RuntimeError(
                        "failed to pull LAN AIO image on remote host and runner "
                        f"does not have a local copy: slot={slot.id} image={image_ref} "
                        f"error={error or exc.returncode}"
                    ) from exc
                load_output = self._load_local_image_to_remote(slot, image_ref)
                pulled.append(
                    {
                        "slot": slot.id,
                        "image_ref": image_ref,
                        "status": "loaded_from_runner",
                        "output": load_output.strip() if load_output.strip() else None,
                    }
                )
                continue
            pulled.append({"slot": slot.id, "image_ref": image_ref, "status": "pulled"})
        return {"ok": True, "action": "pull-image", "pulled": pulled}

    def warm_cache(self, slots: list[LanAioProdSlot]) -> dict[str, Any]:
        if len(slots) != 1:
            raise RuntimeError("warm-cache requires exactly one --slot")
        slot = slots[0]
        metadata = self._runtime_metadata(slot)
        image_ref = os.environ.get("LAN_AIO_WARM_CACHE_IMAGE_REF") or str(
            metadata.get("image_ref") or ""
        )
        if "@sha256:" in image_ref:
            metadata = {**metadata, "image_ref": image_ref}
        if not image_ref:
            raise RuntimeError(f"profile {slot.target_profile_id} has no image_ref")
        env_content = runtime_env_content(self.env_values)
        local_model_env_content = ""
        if metadata.get("lan_local_model_overrides"):
            token = self.env_values.get("CIVITAI_API_TOKEN", "")
            if not token:
                raise RuntimeError(
                    "missing CIVITAI_API_TOKEN for LAN local model override"
                )
            if "\n" in token or "\r" in token:
                raise RuntimeError("refusing newline in CIVITAI_API_TOKEN")
            local_model_env_content = f"CIVITAI_API_TOKEN={token}\n"
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env.lan-aio-prod"
            env_file.write_text(env_content, encoding="utf-8")
            self._ssh(
                slot.ssh_host,
                f"mkdir -p '{slot.remote_dir}' && chmod 700 '{slot.remote_dir}'",
            )
            self._scp(env_file, slot.ssh_host, slot.remote_env_file)
            self._ssh(slot.ssh_host, f"chmod 600 '{slot.remote_env_file}'")
            if local_model_env_content:
                local_model_env_file = Path(tmp) / ".env.local-model-download"
                local_model_env_file.write_text(
                    local_model_env_content, encoding="utf-8"
                )
                self._scp(
                    local_model_env_file,
                    slot.ssh_host,
                    slot.remote_local_model_env_file,
                )
                self._ssh(
                    slot.ssh_host,
                    f"chmod 600 '{slot.remote_local_model_env_file}'",
                )
        try:
            self._ssh(slot.ssh_host, self._warm_cache_command(slot, metadata))
        finally:
            if local_model_env_content:
                self._ssh(
                    slot.ssh_host,
                    f"rm -f '{slot.remote_local_model_env_file}'",
                )
        marker = {
            "ok": True,
            "slot": slot.id,
            "physical_slot_key": physical_slot_key(slot),
            "profile": slot.target_profile_id,
            "image_ref": image_ref,
            "model_cache_bucket": metadata.get("model_cache_bucket"),
            "model_prefix": metadata.get("model_prefix"),
            "model_manifest_key": metadata.get("model_manifest_key"),
            "workspace_host_dir": metadata.get("workspace_host_dir"),
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_cache_marker(slot, marker)
        return {
            "ok": True,
            "action": "warm-cache",
            "slot": slot.id,
            "model_cache": marker,
        }

    def _wait_worker_ids_idle(self, targets: set[str]) -> None:
        deadline = time.time() + 7200
        while time.time() < deadline:
            workers = {item.get("agent_id"): item for item in self._system_workers()}
            busy = {}
            for agent_id in targets:
                worker = workers.get(agent_id, {})
                if str(worker.get("status") or "").lower() == "running" or worker.get(
                    "current_task_type"
                ):
                    busy[agent_id] = worker.get("current_task_id") or worker.get(
                        "current_task_type"
                    )
            if not busy:
                return
            print("Waiting for workers:", ", ".join(sorted(busy)), file=sys.stderr)
            time.sleep(15)
        raise TimeoutError("timed out waiting for legacy workers to become idle")

    def wait_idle(self, slots: list[LanAioProdSlot]) -> dict[str, Any]:
        targets = {slot.legacy_worker_id for slot in slots}
        self._wait_worker_ids_idle(targets)
        return {"ok": True, "action": "wait-idle", "targets": sorted(targets)}

    def start_disabled(self, slots: list[LanAioProdSlot]) -> dict[str, Any]:
        if len(slots) != 1:
            raise RuntimeError("start-disabled requires exactly one --slot")
        slot = slots[0]
        self._set_control(
            slot.agent_id,
            "disabled",
            "lan_aio_fleet_start_disabled",
            ttl_seconds=CONTROL_TTL_SECONDS,
        )
        self._write_remote_runtime_files(slot)
        stale_target_container = self._ensure_target_container_recreate_safe(slot)
        port_owner_check = self._host_port_owner_check(slot, allowed_containers=set())
        if not port_owner_check["ok"]:
            raise RuntimeError(str(port_owner_check["error"]))
        self._remote_compose(slot, "up -d --force-recreate")
        self._wait_container_health(slot)
        hot_cache_copies = self._preseed_legacy_hot_caches(slot)
        self._verify_disabled_heartbeat(slot)
        return {
            "ok": True,
            "action": "start-disabled",
            "slot": slot.id,
            "stale_target_container": stale_target_container,
            "legacy_hot_cache_copies": hot_cache_copies,
        }

    def start_disabled_canary(self, slots: list[LanAioProdSlot]) -> dict[str, Any]:
        if len(slots) != 1:
            raise RuntimeError("canary-start-disabled requires exactly one --slot")
        slot = slots[0]
        steps: list[dict[str, Any]] = []
        preflight = self.preflight_payload([slot], execute=True)
        steps.append({"action": "preflight", "payload": preflight})
        if not preflight.get("ok"):
            raise RuntimeError(f"disabled canary preflight failed for {slot.id}")
        try:
            for action, callback in (
                ("pull-image", self.pull_image),
                ("warm-cache", self.warm_cache),
                ("start-disabled", self.start_disabled),
            ):
                steps.append({"action": action, "payload": callback([slot])})
        except Exception as exc:
            self._set_control(
                slot.agent_id,
                "disabled",
                "lan_aio_disabled_canary_start_failed",
                ttl_seconds=CONTROL_TTL_SECONDS,
            )
            self._ssh(
                slot.ssh_host,
                f"docker stop '{slot.container_name}' >/dev/null 2>&1 || true",
            )
            raise RuntimeError(
                "disabled canary start failed; candidate was stopped and intake "
                f"remains disabled: {exc}"
            ) from exc
        return {
            "ok": True,
            "action": "canary-start-disabled",
            "slot": slot.id,
            "steps": steps,
            "intake": "disabled",
        }

    def _verify_comfy_queue_idle(self, slot: LanAioProdSlot) -> None:
        checker = (
            "import json,sys; payload=json.load(sys.stdin); "
            "running=payload.get('queue_running') or []; "
            "pending=payload.get('queue_pending') or []; "
            "raise SystemExit(1 if running or pending else 0)"
        )
        command = (
            f"curl -fsS --max-time 8 http://127.0.0.1:{slot.host_port}/queue "
            f"| python3 -c {shlex.quote(checker)}"
        )
        last_error: Exception | None = None
        for attempt in range(5):
            try:
                self._ssh(slot.ssh_host, command)
                return
            except Exception as exc:
                last_error = exc
                if attempt < 4:
                    self._sleep(5.0)
        raise RuntimeError(
            f"ComfyUI queue did not become verifiably idle for {slot.id}"
        ) from last_error

    def stop_disabled_canary(self, slots: list[LanAioProdSlot]) -> dict[str, Any]:
        if len(slots) != 1:
            raise RuntimeError("canary-stop-disabled requires exactly one --slot")
        slot = slots[0]
        self.disable_aio([slot])
        self._wait_worker_ids_idle({slot.agent_id})
        self._verify_comfy_queue_idle(slot)
        self._ssh(
            slot.ssh_host,
            f"docker stop '{slot.container_name}' >/dev/null",
        )
        return {
            "ok": True,
            "action": "canary-stop-disabled",
            "slot": slot.id,
            "intake": "disabled",
        }

    def rollback(self, slots: list[LanAioProdSlot]) -> dict[str, Any]:
        for slot in slots:
            self._set_control(
                slot.agent_id,
                "disabled",
                "lan_aio_fleet_rollback_disable_aio",
                ttl_seconds=CONTROL_TTL_SECONDS,
            )
            self._ssh(
                slot.ssh_host,
                f"docker stop '{slot.container_name}' >/dev/null 2>&1 || true",
            )
            self._ssh(
                slot.ssh_host, f"docker start '{slot.old_runtime_container}' >/dev/null"
            )
            if slot.old_local_agent_container:
                self._local(
                    ["docker", "start", slot.old_local_agent_container], capture=True
                )
            self._set_control(
                slot.legacy_worker_id,
                "enabled",
                "lan_aio_fleet_rollback_enable_legacy",
            )
        return {
            "ok": True,
            "action": "rollback",
            "recovery_status": "succeeded",
            "slots": [slot.id for slot in slots],
        }

    def stop_old(self, slots: list[LanAioProdSlot]) -> dict[str, Any]:
        for slot in slots:
            self._set_control(
                slot.legacy_worker_id,
                "disabled",
                "lan_aio_fleet_stop_old_disable_legacy",
                ttl_seconds=CONTROL_TTL_SECONDS,
            )
            self._ssh(
                slot.ssh_host,
                f"docker stop '{slot.old_runtime_container}' >/dev/null || true",
            )
            if slot.old_local_agent_container:
                self._local(
                    ["docker", "stop", slot.old_local_agent_container], capture=True
                )
        return {"ok": True, "action": "stop-old", "slots": [slot.id for slot in slots]}

    def takeover(
        self,
        slots: list[LanAioProdSlot],
        *,
        failure_policy: str = FAILURE_POLICY_AUTO_ROLLBACK,
    ) -> dict[str, Any]:
        if len(slots) != 1:
            raise RuntimeError("takeover requires exactly one --slot")
        slot = slots[0]
        results: list[dict[str, Any]] = []
        recovery_armed = False

        print(f"[lan-aio-takeover] preflight started for {slot.id}", flush=True)
        preflight = self.preflight_payload([slot], execute=True)
        results.append({"action": "preflight", "payload": preflight})
        if not preflight.get("ok"):
            print(
                "[lan-aio-takeover] preflight failed "
                + json.dumps(preflight, ensure_ascii=False, separators=(",", ":")),
                flush=True,
            )
            raise RuntimeError(f"takeover preflight failed for {slot.id}")

        step_handlers = (
            ("pull-image", self.pull_image),
            ("warm-cache", self.warm_cache),
            ("drain-legacy", self.drain_legacy),
            ("wait-idle", self.wait_idle),
            ("stop-old", self.stop_old),
            ("start-disabled", self.start_disabled),
            ("enable-aio", self.enable_aio),
        )
        try:
            for action, handler in step_handlers:
                if action in {"stop-old", "start-disabled", "enable-aio"}:
                    recovery_armed = True
                print(f"[lan-aio-takeover] {action} started for {slot.id}", flush=True)
                payload = handler([slot])
                results.append({"action": action, "payload": payload})
        except Exception as exc:
            if failure_policy != FAILURE_POLICY_AUTO_ROLLBACK or not recovery_armed:
                raise
            print(
                f"[lan-aio-takeover] failure after stop-old window for {slot.id}; "
                "auto rollback started",
                flush=True,
            )
            try:
                recovery = self.rollback([slot])
            except Exception as recovery_exc:
                results.append(
                    {
                        "action": "recover",
                        "payload": {
                            "ok": False,
                            "recovery_status": "failed",
                            "error": str(recovery_exc),
                        },
                    }
                )
                raise RuntimeError(
                    "takeover failed; recovery_status=failed; "
                    f"original={exc}; recovery_error={recovery_exc}"
                ) from exc
            results.append({"action": "recover", "payload": recovery})
            print(
                f"[lan-aio-takeover] auto rollback completed for {slot.id}",
                flush=True,
            )
            raise RuntimeError(
                f"takeover failed during protected window; "
                f"recovery_status={recovery.get('recovery_status', 'succeeded')}; "
                f"original={exc}"
            ) from exc

        return {"ok": True, "action": "takeover", "slot": slot.id, "steps": results}

    def recover_physical_slot(
        self,
        *,
        physical_slot: str,
        prefer: str = "old",
        selected_slot_id: str | None = None,
    ) -> dict[str, Any]:
        if prefer not in {"old", "candidate"}:
            raise RuntimeError("recover --prefer must be old or candidate")
        sibling_slots = [
            slot
            for slot in self.slots.values()
            if physical_slot_key(slot) == physical_slot
        ]
        if not sibling_slots:
            raise KeyError(f"unknown LAN AIO physical slot: {physical_slot}")
        if selected_slot_id:
            selected = next(
                (slot for slot in sibling_slots if slot.id == selected_slot_id),
                None,
            )
            if selected is None:
                raise KeyError(
                    f"LAN AIO slot {selected_slot_id} is not on physical slot {physical_slot}"
                )
            if slot_mutation_blocked(selected):
                raise RuntimeError(
                    f"LAN AIO slot is not recoverable: {selected.id} phase={selected.phase}"
                )
        elif prefer == "old":
            selected = next(
                (
                    slot
                    for slot in sorted(
                        sibling_slots, key=lambda item: item.rollout_order
                    )
                    if slot.enabled and slot.phase in {"prod_enabled", "aio_enabled"}
                ),
                None,
            )
        else:
            selected = next(
                (
                    slot
                    for slot in sorted(
                        sibling_slots, key=lambda item: item.rollout_order
                    )
                    if slot.retargetable
                ),
                None,
            )
        if selected is None:
            raise RuntimeError(
                f"no recoverable {prefer} slot found for physical slot {physical_slot}"
            )
        for slot in sibling_slots:
            if slot.id == selected.id:
                continue
            self._set_control(
                slot.agent_id,
                "disabled",
                "lan_aio_fleet_recover_disable_sibling",
                ttl_seconds=CONTROL_TTL_SECONDS,
            )
            self._ssh(
                slot.ssh_host,
                f"docker stop '{slot.container_name}' >/dev/null 2>&1 || true",
            )
        self._set_control(
            selected.agent_id,
            "disabled",
            "lan_aio_fleet_recover_start_disabled",
            ttl_seconds=CONTROL_TTL_SECONDS,
        )
        target_state = self._remote_target_container_state(selected)
        if not target_state.get("exists"):
            start_payload = self.start_disabled([selected])
        else:
            status = str(target_state.get("status") or "unknown").lower()
            if not bool(target_state.get("running")):
                if status not in SAFE_STALE_CONTAINER_STATES:
                    raise RuntimeError(
                        "target container exists but is not safe to start: "
                        f"{selected.container_name} status={status}"
                    )
                desired_image_ref = self.config.profiles[
                    selected.target_profile_id
                ].all_in_one_image_ref
                actual_image_ref = self._remote_target_container_image_ref(selected)
                if desired_image_ref and actual_image_ref != desired_image_ref:
                    start_payload = self.start_disabled([selected])
                else:
                    self._ssh(
                        selected.ssh_host,
                        f"docker start '{selected.container_name}' >/dev/null",
                    )
                    self._wait_container_health(selected)
                    self._verify_disabled_heartbeat(selected)
                    start_payload = {
                        "ok": True,
                        "action": "docker-start",
                        "slot": selected.id,
                        "previous_state": status,
                    }
            else:
                desired_image_ref = self.config.profiles[
                    selected.target_profile_id
                ].all_in_one_image_ref
                actual_image_ref = self._remote_target_container_image_ref(selected)
                if desired_image_ref and actual_image_ref != desired_image_ref:
                    start_payload = self.start_disabled([selected])
                else:
                    self._wait_container_health(selected)
                    self._verify_disabled_heartbeat(selected)
                    start_payload = {
                        "ok": True,
                        "action": "already-running",
                        "slot": selected.id,
                        "previous_state": status,
                    }
        self._set_control(
            selected.agent_id,
            "enabled",
            f"lan_aio_fleet_recover_prefer_{prefer}",
        )
        return {
            "ok": True,
            "action": "recover",
            "physical_slot": physical_slot,
            "prefer": prefer,
            "selected_slot": selected.id,
            "start": start_payload,
            "recovery_status": "succeeded",
        }

    def _system_workers(self) -> list[dict[str, Any]]:
        payload = self._json_get(f"{self.central_url}/system/workers")
        return [item for item in payload.get("workers", []) if isinstance(item, dict)]

    def _runtime_metadata(self, slot: LanAioProdSlot) -> dict[str, Any]:
        try:
            import yaml  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("LAN AIO runtime metadata requires PyYAML") from exc
        rendered = self.render_compose(slot)
        payload = yaml.safe_load(rendered) or {}
        metadata = payload.get("x-allbot-runtime")
        if not isinstance(metadata, dict):
            raise RuntimeError(
                f"rendered compose missing x-allbot-runtime for {slot.id}"
            )
        return metadata

    def _warm_cache_container_name(self, slot: LanAioProdSlot) -> str:
        return f"allbot-lan-aio-cache-{_sanitize(slot.id).lower()}"

    def _warm_cache_command(
        self,
        slot: LanAioProdSlot,
        metadata: dict[str, Any],
    ) -> str:
        workspace_host_dir = str(metadata["workspace_host_dir"])
        workspace_parent_dir = posixpath.dirname(workspace_host_dir.rstrip("/")) or "/"
        workspace_models_dir = f"{workspace_host_dir.rstrip('/')}/ComfyUI/models"
        model_workspace_host_dir = str(
            metadata.get("model_workspace_host_dir") or workspace_host_dir
        )
        model_host_dir = f"{model_workspace_host_dir.rstrip('/')}/ComfyUI/models"
        model_target_dir = str(metadata["model_target_dir"])
        image_ref = str(metadata["image_ref"])
        container_name = self._warm_cache_container_name(slot)
        inner_script = "\n".join(
            [
                "set -euo pipefail",
                f"remote_root={shlex.quote(REMOTE_WORKERS_TARGET_DIR)}",
                'export RUNPOD_MODEL_ACCESS_KEY="${RUNPOD_MODEL_ACCESS_KEY:-${LAN_MODEL_CACHE_ACCESS_KEY:-}}"',
                'export RUNPOD_MODEL_SECRET_KEY="${RUNPOD_MODEL_SECRET_KEY:-${LAN_MODEL_CACHE_SECRET_KEY:-}}"',
                'test -n "${RUNPOD_MODEL_ACCESS_KEY:-}"',
                'test -n "${RUNPOD_MODEL_SECRET_KEY:-}"',
                'mkdir -p "${RUNPOD_MODEL_TARGET_DIR:?}"',
                (
                    'python3 "$remote_root/scripts/runpod_sync_local_models.py" '
                    '--target-dir "$RUNPOD_MODEL_TARGET_DIR" '
                    if metadata.get("lan_local_model_overrides")
                    else ""
                ),
                (
                    "python3 - <<'PY' || "
                    'python3 -m pip install --no-cache-dir -r "$remote_root/requirements.txt"\n'
                    "import minio\n"
                    "PY"
                ),
                (
                    'python3 "$remote_root/scripts/runpod_sync_models_from_r2.py" '
                    '--bucket "$RUNPOD_MODEL_BUCKET" '
                    '--prefix "$RUNPOD_MODEL_PREFIX" '
                    '--target-dir "$RUNPOD_MODEL_TARGET_DIR"'
                ),
            ]
        )
        docker_command = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--env-file",
            slot.remote_env_file,
            "-e",
            f"RUNPOD_MODEL_ENDPOINT={metadata['model_cache_endpoint']}",
            "-e",
            f"RUNPOD_MODEL_BUCKET={metadata['model_cache_bucket']}",
            "-e",
            f"RUNPOD_MODEL_PREFIX={metadata['model_prefix']}",
            "-e",
            f"RUNPOD_MODEL_MANIFEST_KEY={metadata['model_manifest_key']}",
            "-e",
            f"RUNPOD_MODEL_TARGET_DIR={model_target_dir}",
            "-e",
            "RUNPOD_MODEL_SECURE=false",
            "-e",
            f"RUNPOD_REMOTE_WORKER_ROOT={REMOTE_WORKERS_TARGET_DIR}",
            "-v",
            f"{workspace_host_dir}:/workspace",
        ]
        if metadata.get("lan_local_model_overrides"):
            docker_command.extend(
                [
                    "--env-file",
                    slot.remote_local_model_env_file,
                    "-e",
                    f"RUNPOD_LAN_LOCAL_MODEL_OVERRIDES={json.dumps(metadata['lan_local_model_overrides'], separators=(',', ':'))}",
                ]
            )
        if model_workspace_host_dir != workspace_host_dir:
            docker_command.extend(["-v", f"{model_host_dir}:{model_target_dir}"])
        docker_command.extend([image_ref, "bash", "-lc", inner_script])

        def prepare_writable_directory(
            target_dir: str,
            writable_root: str,
            mount_root: str,
            *,
            require_host_write: bool = True,
        ) -> list[str]:
            fallback_script = "; ".join(
                [
                    f"mkdir -p {shlex.quote(target_dir)}",
                    (
                        'chown -R "$ALLBOT_HOST_UID:$ALLBOT_HOST_GID" '
                        f"{shlex.quote(writable_root)}"
                    ),
                ]
            )
            fallback_command = " ".join(
                [
                    "docker run --rm",
                    '-e "ALLBOT_HOST_UID=$host_uid"',
                    '-e "ALLBOT_HOST_GID=$host_gid"',
                    f"-v {shlex.quote(mount_root)}:{shlex.quote(mount_root)}",
                    shlex.quote(image_ref),
                    "bash -lc",
                    shlex.quote(fallback_script),
                ]
            )
            commands = [
                f"mkdir -p {shlex.quote(target_dir)} || {fallback_command}",
                f"test -d {shlex.quote(target_dir)}",
            ]
            if require_host_write:
                commands.append(f"test -w {shlex.quote(target_dir)}")
            return commands

        directory_setup = prepare_writable_directory(
            workspace_models_dir,
            workspace_host_dir,
            workspace_parent_dir,
        )
        if model_workspace_host_dir != workspace_host_dir:
            model_workspace_parent_dir = (
                posixpath.dirname(model_workspace_host_dir.rstrip("/")) or "/"
            )
            directory_setup.extend(
                prepare_writable_directory(
                    model_host_dir,
                    model_workspace_host_dir,
                    model_workspace_parent_dir,
                    require_host_write=False,
                )
            )
        script = "\n".join(
            [
                "set -euo pipefail",
                "host_uid=$(id -u)",
                "host_gid=$(id -g)",
                *directory_setup,
                f"docker rm -f {shlex.quote(container_name)} >/dev/null 2>&1 || true",
                " ".join(shlex.quote(part) for part in docker_command),
            ]
        )
        return "bash -lc " + shlex.quote(script)

    def _write_cache_marker(
        self,
        slot: LanAioProdSlot,
        marker: dict[str, Any],
    ) -> None:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".json"
        ) as file_obj:
            json.dump(marker, file_obj, ensure_ascii=False, indent=2)
            file_obj.write("\n")
            file_obj.flush()
            self._scp(
                Path(file_obj.name),
                slot.ssh_host,
                f"{slot.remote_dir}/{WARM_CACHE_MARKER_FILE}",
            )

    def _remote_cache_marker(self, slot: LanAioProdSlot) -> dict[str, Any]:
        marker_path = f"{slot.remote_dir}/{WARM_CACHE_MARKER_FILE}"
        try:
            output = self._ssh(
                slot.ssh_host,
                f"test -f '{marker_path}' && cat '{marker_path}' || true",
                capture=True,
            )
        except Exception as exc:
            return {"status": "unavailable", "error": str(exc)}
        if not output.strip():
            return {"status": "missing"}
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return {"status": "invalid", "raw": output.strip()[:500]}
        payload.setdefault("status", "ready" if payload.get("ok") else "unknown")
        return payload

    def _control_state(self, agent_id: str) -> str:
        token = self.env_values.get(
            "LAN_AIO_AGENT_SECRET_TOKEN"
        ) or self.env_values.get("AGENT_SECRET_TOKEN")
        if not token:
            return "unknown_missing_token"
        try:
            payload = self._json_get(
                f"{self.central_url}/api/agent/task/control/{agent_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        except Exception:
            return "unknown"
        for candidate in (
            payload,
            payload.get("control") if isinstance(payload.get("control"), dict) else {},
            payload.get("data") if isinstance(payload.get("data"), dict) else {},
        ):
            if isinstance(candidate, dict) and candidate.get("state"):
                return str(candidate["state"])
        return "unknown"

    def _set_control(
        self,
        agent_id: str,
        state: str,
        reason: str,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        token = self.env_values.get(
            "LAN_AIO_AGENT_SECRET_TOKEN"
        ) or self.env_values.get("AGENT_SECRET_TOKEN")
        if not token:
            raise RuntimeError("missing LAN_AIO_AGENT_SECRET_TOKEN/AGENT_SECRET_TOKEN")
        body: dict[str, Any] = {"state": state, "reason": reason}
        if ttl_seconds and state != "enabled":
            body["ttl_seconds"] = ttl_seconds
        request = urllib.request.Request(
            f"{self.central_url}/api/agent/task/control/{agent_id}",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "allbot-lan-aio-fleet-prod/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            response.read()

    def _json_get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: int = 15,
    ) -> dict[str, Any]:
        request_headers = {
            "User-Agent": "allbot-lan-aio-fleet-prod/1.0",
            **(headers or {}),
        }
        request = urllib.request.Request(url, headers=request_headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _http_ok(self, url: str) -> None:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "allbot-lan-aio-fleet-prod/1.0"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status >= 400:
                raise RuntimeError(f"{url} returned HTTP {response.status}")

    def _http_check(self, name: str, url: str) -> dict[str, Any]:
        try:
            self._http_ok(url)
        except Exception as exc:
            return {"name": name, "ok": False, "error": str(exc)}
        return {"name": name, "ok": True}

    def _remote_check(
        self,
        slot: LanAioProdSlot,
        name: str,
        command: str,
        *,
        attempts: int = 1,
        retry_delay_seconds: float = 0.0,
    ) -> dict[str, Any]:
        attempts = max(1, int(attempts))
        last_error = ""
        for attempt in range(1, attempts + 1):
            try:
                output = self._ssh(slot.ssh_host, command, capture=True)
                break
            except subprocess.CalledProcessError as exc:
                last_error = (exc.stderr or exc.stdout or "").strip()
                if not last_error:
                    last_error = f"remote check failed with exit code {exc.returncode}"
            except Exception as exc:
                last_error = str(exc)
            if attempt < attempts:
                self._sleep(retry_delay_seconds)
        else:
            if attempts > 1:
                last_error = f"failed after {attempts} attempts: {last_error}"
            return {"name": name, "ok": False, "error": last_error}
        result: dict[str, Any] = {"name": name, "ok": True}
        if output.strip():
            result["output"] = output.strip()
        return result

    def _remote_command_ok(self, slot: LanAioProdSlot, command: str) -> bool:
        try:
            self._ssh(slot.ssh_host, command, capture=True)
        except Exception:
            return False
        return True

    def _local_image_present(self, image_ref: str | None) -> bool:
        if not image_ref:
            return False
        try:
            self._local(["docker", "image", "inspect", image_ref], capture=True)
        except Exception:
            return False
        return True

    def _image_readiness_check(
        self,
        slot: LanAioProdSlot,
        image_ref: str | None,
    ) -> dict[str, Any]:
        registry_configured = self._remote_command_ok(
            slot,
            "docker info 2>/dev/null | grep -q '192.168.1.115:5000'",
        )
        remote_image_present = (
            self._remote_image_present(slot, image_ref) if image_ref else False
        )
        runner_image_present = self._local_image_present(image_ref)
        ok = bool(registry_configured or remote_image_present or runner_image_present)
        result: dict[str, Any] = {
            "name": "docker_registry_or_image_present",
            "ok": ok,
            "image_ref": image_ref,
            "registry_configured": registry_configured,
            "remote_image_present": remote_image_present,
            "runner_image_present": runner_image_present,
        }
        if not ok:
            result["error"] = (
                "LAN AIO image unavailable: remote Docker is not configured for "
                "192.168.1.115:5000, remote image is missing, and runner local "
                f"image is missing: {image_ref}"
            )
        elif runner_image_present and not (registry_configured or remote_image_present):
            result["output"] = "runner_local_image_available_for_stream_load"
        return result

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def _remote_container_status(self, slot: LanAioProdSlot) -> list[str]:
        pattern = (
            f"^({re.escape(slot.container_name)}|{re.escape(slot.old_runtime_container)})( |$)|"
            "node_exporter|dcgm_exporter"
        )
        command = (
            "docker ps -a --format '{{.Names}} {{.Status}} {{.Ports}}' "
            f"| grep -E '{pattern}' || true"
        )
        try:
            output = self._ssh(slot.ssh_host, command, capture=True)
        except Exception as exc:
            return [f"status_unavailable: {exc}"]
        lines = [line for line in output.splitlines() if line.strip()]
        try:
            owners = self._remote_published_port_owners(slot, slot.host_port)
        except Exception:
            owners = []
        for owner in owners:
            owner_name = str(owner.get("name") or "").strip()
            if not owner_name:
                continue
            if any(
                line == owner_name or line.startswith(f"{owner_name} ")
                for line in lines
            ):
                continue
            owner_line = " ".join(
                part
                for part in (
                    owner_name,
                    str(owner.get("status") or "").strip(),
                    str(owner.get("ports") or "").strip(),
                    "host_port_owner",
                )
                if part
            )
            if owner_line and owner_line not in lines:
                lines.append(owner_line)
        return lines

    def _remote_published_port_owners(
        self,
        slot: LanAioProdSlot,
        host_port: int,
    ) -> list[dict[str, Any]]:
        command = (
            f"docker ps --filter publish={int(host_port)} --format '{{{{json .}}}}'"
        )
        output = self._ssh(slot.ssh_host, command, capture=True)
        owners: list[dict[str, Any]] = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                name, _, ports = line.partition(" ")
                owners.append({"name": name, "ports": ports.strip()})
                continue
            name = str(row.get("Names") or "").strip()
            if not name:
                continue
            owners.append(
                {
                    "name": name,
                    "ports": str(row.get("Ports") or "").strip(),
                    "image": str(row.get("Image") or "").strip(),
                    "status": str(row.get("Status") or "").strip(),
                }
            )
        return owners

    def _host_port_owner_check(
        self,
        slot: LanAioProdSlot,
        *,
        allowed_containers: set[str],
    ) -> dict[str, Any]:
        allowed = {name for name in allowed_containers if name}
        try:
            owners = self._remote_published_port_owners(slot, slot.host_port)
        except Exception as exc:
            return {
                "name": "host_port_owner",
                "ok": False,
                "host_port": slot.host_port,
                "allowed_containers": sorted(allowed),
                "owners": [],
                "error": str(exc),
            }
        unexpected = [owner for owner in owners if owner.get("name") not in allowed]
        result: dict[str, Any] = {
            "name": "host_port_owner",
            "ok": not unexpected,
            "host_port": slot.host_port,
            "allowed_containers": sorted(allowed),
            "owners": owners,
        }
        if unexpected:
            result["unexpected_owners"] = unexpected
            result["error"] = (
                f"host port {slot.host_port} is published by unexpected container(s): "
                + ", ".join(str(owner.get("name")) for owner in unexpected)
            )
        return result

    def _remote_target_container_state(
        self,
        slot: LanAioProdSlot,
    ) -> dict[str, Any]:
        command = (
            "docker inspect -f "
            "'{{.Name}}|{{.State.Status}}|{{.State.Running}}' "
            f"{shlex.quote(slot.container_name)} 2>/dev/null || true"
        )
        output = self._ssh(slot.ssh_host, command, capture=True).strip()
        if not output:
            return {"exists": False, "name": slot.container_name, "status": "missing"}
        name, _, tail = output.partition("|")
        status, _, running = tail.partition("|")
        normalized_name = name.strip().removeprefix("/")
        return {
            "exists": True,
            "name": normalized_name,
            "status": status.strip().lower() or "unknown",
            "running": running.strip().lower() == "true",
        }

    def _remote_target_container_image_ref(self, slot: LanAioProdSlot) -> str:
        return self._ssh(
            slot.ssh_host,
            (
                "docker inspect -f '{{.Config.Image}}' "
                f"{shlex.quote(slot.container_name)}"
            ),
            capture=True,
        ).strip()

    def _remove_remote_container(
        self,
        slot: LanAioProdSlot,
        container_name: str,
    ) -> None:
        self._ssh(slot.ssh_host, f"docker rm -f {shlex.quote(container_name)} >/dev/null")

    def _ensure_target_container_recreate_safe(
        self,
        slot: LanAioProdSlot,
    ) -> dict[str, Any]:
        state = self._remote_target_container_state(slot)
        if not state.get("exists"):
            return {
                "status": "not_present",
                "container_name": slot.container_name,
                "previous_state": "missing",
            }
        state_name = str(state.get("name") or "")
        status = str(state.get("status") or "unknown").lower()
        if state_name != slot.container_name:
            raise RuntimeError(
                "target container inspect returned mismatched name: "
                f"{state_name!r} != {slot.container_name!r}"
            )
        if (
            (bool(state.get("running")) and status != "restarting")
            or status not in SAFE_STALE_CONTAINER_STATES
        ):
            raise RuntimeError(
                "target container already exists and is not safe to remove: "
                f"{slot.container_name} status={status}"
            )
        self._remove_remote_container(slot, slot.container_name)
        return {
            "status": "removed",
            "container_name": slot.container_name,
            "previous_state": status,
        }

    def _remote_image_present(self, slot: LanAioProdSlot, image_ref: str) -> bool:
        try:
            self._ssh(
                slot.ssh_host,
                f"docker image inspect '{image_ref}' >/dev/null 2>&1",
            )
        except Exception:
            return False
        return True

    def _load_local_image_to_remote(self, slot: LanAioProdSlot, image_ref: str) -> str:
        save_proc = subprocess.Popen(
            ["docker", "save", image_ref],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert save_proc.stdout is not None
        load_proc = subprocess.Popen(
            ["ssh", *SSH_BATCH_OPTIONS, slot.ssh_host, "docker load"],
            stdin=save_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        save_proc.stdout.close()
        load_stdout, load_stderr = load_proc.communicate()
        save_stderr = b""
        if save_proc.stderr is not None:
            save_stderr = save_proc.stderr.read()
        save_returncode = save_proc.wait()
        if save_returncode != 0:
            raise subprocess.CalledProcessError(
                save_returncode,
                ["docker", "save", image_ref],
                stderr=save_stderr.decode("utf-8", errors="replace"),
            )
        if load_proc.returncode != 0:
            raise subprocess.CalledProcessError(
                load_proc.returncode,
                ["ssh", *SSH_BATCH_OPTIONS, slot.ssh_host, "docker load"],
                output=load_stdout.decode("utf-8", errors="replace"),
                stderr=load_stderr.decode("utf-8", errors="replace"),
            )
        return "\n".join(
            item
            for item in (
                load_stdout.decode("utf-8", errors="replace").strip(),
                load_stderr.decode("utf-8", errors="replace").strip(),
            )
            if item
        )

    def _assert_enable_aio_gate(self, slot: LanAioProdSlot) -> dict[str, Any]:
        legacy_control = self._control_state(slot.legacy_worker_id)
        if legacy_control != "disabled":
            raise RuntimeError(
                f"refusing to enable {slot.agent_id}: "
                f"{slot.legacy_worker_id} control is {legacy_control!r}, expected 'disabled'"
            )
        workers = {item.get("agent_id"): item for item in self._system_workers()}
        legacy_worker = workers.get(slot.legacy_worker_id, {})
        if str(
            legacy_worker.get("status") or ""
        ).lower() == "running" or legacy_worker.get("current_task_type"):
            raise RuntimeError(
                f"refusing to enable {slot.agent_id}: "
                f"{slot.legacy_worker_id} is still running "
                f"{legacy_worker.get('current_task_id') or legacy_worker.get('current_task_type')}"
            )
        aio_worker = workers.get(slot.agent_id)
        if not aio_worker:
            raise RuntimeError(
                f"refusing to enable {slot.agent_id}: disabled heartbeat is not visible"
            )
        if str(aio_worker.get("status") or "").lower() == "running" or aio_worker.get(
            "current_task_type"
        ):
            raise RuntimeError(
                f"refusing to enable {slot.agent_id}: AIO worker is not idle"
            )
        gpu_processes = self._old_runtime_gpu_memory_processes(slot)
        if gpu_processes:
            raise RuntimeError(
                f"refusing to enable {slot.agent_id}: old runtime container "
                f"{slot.old_runtime_container} still has GPU memory processes: {gpu_processes}"
            )
        return {
            "slot": slot.id,
            "legacy_control": legacy_control,
            "legacy_worker_status": legacy_worker.get("status"),
            "aio_worker_status": aio_worker.get("status"),
            "old_runtime_gpu_processes": gpu_processes,
        }

    def _old_runtime_gpu_memory_processes(
        self,
        slot: LanAioProdSlot,
    ) -> list[dict[str, Any]]:
        command = f"""bash -lc 'set -euo pipefail
container={shlex.quote(slot.old_runtime_container)}
if ! docker inspect "$container" >/dev/null 2>&1; then
  true
else
  status="$(docker inspect -f "{{{{.State.Status}}}}" "$container" 2>/dev/null || true)"
  if [ "$status" != running ]; then
    true
  else
    tmp="$(mktemp)"
    cleanup() {{ rm -f "$tmp"; }}
    trap cleanup EXIT
    docker top "$container" -eo pid 2>/dev/null | awk "NR>1 {{print \\$1}}" > "$tmp" || true
    if [ -s "$tmp" ]; then
      nvidia-smi --query-compute-apps=pid,used_gpu_memory --format=csv,noheader,nounits 2>/dev/null |
      while IFS=, read -r pid memory_mib; do
        pid="$(printf "%s" "$pid" | tr -d "[:space:]")"
        memory_mib="$(printf "%s" "$memory_mib" | tr -d "[:space:]")"
        if [ -n "$pid" ] && grep -qx "$pid" "$tmp"; then
          printf "%s,%s\\n" "$pid" "$memory_mib"
        fi
      done || true
    fi
  fi
fi
'"""
        output = self._ssh(slot.ssh_host, command, capture=True)
        processes = []
        for line in output.splitlines():
            if not line.strip():
                continue
            pid, _, memory_mib = line.partition(",")
            processes.append(
                {
                    "pid": pid.strip(),
                    "used_gpu_memory_mib": memory_mib.strip(),
                }
            )
        return processes

    def _write_remote_runtime_files(self, slot: LanAioProdSlot) -> None:
        compose = self.render_compose(slot)
        env_content = runtime_env_content(self.env_values)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            compose_file = tmp_dir / "docker-compose.yml"
            env_file = tmp_dir / ".env.lan-aio-prod"
            compose_file.write_text(compose, encoding="utf-8")
            env_file.write_text(env_content, encoding="utf-8")
            self._ssh(
                slot.ssh_host,
                f"mkdir -p '{slot.remote_dir}' && chmod 700 '{slot.remote_dir}'",
            )
            self._scp(compose_file, slot.ssh_host, slot.remote_compose_file)
            self._scp(env_file, slot.ssh_host, slot.remote_env_file)
            self._ssh(slot.ssh_host, f"chmod 600 '{slot.remote_env_file}'")

    def _remote_compose(self, slot: LanAioProdSlot, op: str) -> None:
        command = (
            f"cd '{slot.remote_dir}' && "
            "if docker compose version >/dev/null 2>&1; then "
            f"docker compose --env-file '{slot.remote_env_file}' -f '{slot.remote_compose_file}' {op}; "
            "else "
            f"docker-compose --env-file '{slot.remote_env_file}' -f '{slot.remote_compose_file}' {op}; "
            "fi"
        )
        self._ssh(slot.ssh_host, command)

    def _configure_registry_on_host(self, host: str) -> None:
        sudo_password = os.environ.get("LAN_AIO_GPU_SUDO_PASSWORD", "")
        script = r"""
set -euo pipefail
sudo_cmd() {
  if sudo -n true >/dev/null 2>&1; then
    sudo "$@"
    return
  fi
  if [ -z "${LAN_AIO_GPU_SUDO_PASSWORD:-}" ]; then
    echo "sudo password is required to update Docker daemon" >&2
    return 1
  fi
  printf '%s\n' "$LAN_AIO_GPU_SUDO_PASSWORD" | sudo -S -p '' "$@"
}
backup="/etc/docker/daemon.json.allbot-lan-aio-fleet-$(date +%Y%m%d%H%M%S).bak"
if [ -f /etc/docker/daemon.json ]; then
  sudo_cmd cp -a /etc/docker/daemon.json "$backup"
fi
python3 - <<'PY' >/tmp/allbot-daemon.json
import json
from pathlib import Path

path = Path("/etc/docker/daemon.json")
data = json.loads(path.read_text() or "{}") if path.exists() else {}
registries = list(data.get("insecure-registries") or [])
if "192.168.1.115:5000" not in registries:
    registries.append("192.168.1.115:5000")
data["insecure-registries"] = sorted(registries)
proxies = dict(data.get("proxies") or {})
no_proxy = [
    entry.strip()
    for entry in str(proxies.get("no-proxy") or "").split(",")
    if entry.strip()
]
for entry in ("192.168.1.115", "192.168.1.115:5000"):
    if entry not in no_proxy:
        no_proxy.append(entry)
proxies["no-proxy"] = ",".join(no_proxy)
data["proxies"] = proxies
print(json.dumps(data, indent=2, sort_keys=True))
PY
sudo_cmd install -m 0644 /tmp/allbot-daemon.json /etc/docker/daemon.json
python3 - <<'PY' >/tmp/allbot-lan-aio-registry-proxy.conf
import shlex
import subprocess

raw = subprocess.check_output(
    ["systemctl", "show", "--property=Environment", "--value", "docker"],
    text=True,
).strip()
environment = {}
for item in shlex.split(raw):
    if "=" in item:
        key, value = item.split("=", 1)
        environment[key] = value
no_proxy = [entry.strip() for entry in environment.get("NO_PROXY", "").split(",")]
for entry in ("192.168.1.115", "192.168.1.115:5000"):
    if entry not in no_proxy:
        no_proxy.append(entry)
merged = ",".join(entry for entry in no_proxy if entry)
print("[Service]")
print(f'Environment="NO_PROXY={merged}"')
print(f'Environment="no_proxy={merged}"')
PY
sudo_cmd install -d -m 0755 /etc/systemd/system/docker.service.d
sudo_cmd install -m 0644 /tmp/allbot-lan-aio-registry-proxy.conf /etc/systemd/system/docker.service.d/zz-allbot-lan-aio-registry.conf
sudo_cmd systemctl daemon-reload
sudo_cmd systemctl restart docker
deadline=$((SECONDS + 240))
while [ "$SECONDS" -lt "$deadline" ]; do
  if docker info 2>/dev/null | grep -q "192.168.1.115:5000" && \
    docker info --format '{{.NoProxy}}' 2>/dev/null | grep -q "192.168.1.115:5000"; then
    exit 0
  fi
  sleep 3
done
docker info 2>/dev/null | grep -q "192.168.1.115:5000"
"""
        self._local(
            [
                "ssh",
                host,
                "IFS= read -r LAN_AIO_GPU_SUDO_PASSWORD; "
                "export LAN_AIO_GPU_SUDO_PASSWORD; bash -s",
            ],
            input_text=f"{sudo_password}\n{script}\n",
        )

    def _wait_container_health(self, slot: LanAioProdSlot) -> None:
        command = f"""bash -lc 'set -euo pipefail
deadline=$((SECONDS + 1800))
while [ "$SECONDS" -lt "$deadline" ]; do
  health="$(docker inspect -f "{{{{if .State.Health}}}}{{{{.State.Health.Status}}}}{{{{else}}}}{{{{.State.Status}}}}{{{{end}}}}" "{slot.container_name}" 2>/dev/null || true)"
  [ "$health" = healthy ] && break
  echo "Waiting for {slot.container_name} health: ${{health:-missing}}"
  sleep 15
done
docker inspect -f "{{{{if .State.Health}}}}{{{{.State.Health.Status}}}}{{{{else}}}}{{{{.State.Status}}}}{{{{end}}}}" "{slot.container_name}" | grep -q healthy
curl -fsS http://127.0.0.1:{slot.host_port}/system_stats >/dev/null
docker exec "{slot.container_name}" bash -lc "curl -fsS http://127.0.0.1:8013/ready >/dev/null || curl -fsS http://127.0.0.1:8013/health >/dev/null"
'"""
        self._ssh(slot.ssh_host, command)

    def _preseed_legacy_hot_caches(self, slot: LanAioProdSlot) -> list[dict[str, Any]]:
        copied: list[dict[str, Any]] = []
        for index, copy in enumerate(slot.legacy_hot_cache_copies, start=1):
            tmp_pattern = f"/tmp/allbot-hot-cache-{_sanitize(slot.id)}-{index}.XXXXXX"
            source_is_host_path = copy.source_container in {"__host__", "host"}
            source = (
                copy.source_path
                if source_is_host_path
                else f"{copy.source_container}:{copy.source_path}"
            )
            lines = [
                "set -euo pipefail",
                f"tmp=$(mktemp {shlex.quote(tmp_pattern)})",
                'cleanup() { rm -f "$tmp"; }',
                "trap cleanup EXIT",
            ]
            if source_is_host_path:
                lines.append(f'if ! cp {shlex.quote(copy.source_path)} "$tmp"; then')
            else:
                lines.append(f'if ! docker cp {shlex.quote(source)} "$tmp"; then')
            if copy.required:
                lines.extend(
                    [
                        f"  echo 'required legacy hot cache source missing: {source}' >&2",
                        "  exit 1",
                    ]
                )
            else:
                lines.extend(
                    [
                        f"  echo 'optional legacy hot cache source missing: {source}' >&2",
                        "  exit 0",
                    ]
                )
            lines.append("fi")
            lines.append('test -s "$tmp"')
            for target_path in copy.target_paths:
                target_dir = posixpath.dirname(target_path)
                target = f"{slot.container_name}:{target_path}"
                lines.append(
                    f"docker exec {shlex.quote(slot.container_name)} "
                    f"bash -lc {shlex.quote('mkdir -p ' + shlex.quote(target_dir))}"
                )
                lines.append(f'docker cp "$tmp" {shlex.quote(target)}')
                lines.append(
                    f"docker exec {shlex.quote(slot.container_name)} "
                    f"bash -lc {shlex.quote('test -s ' + shlex.quote(target_path))}"
                )
            self._ssh(slot.ssh_host, "bash -lc " + shlex.quote("\n".join(lines)))
            copied.append(
                {
                    "source_container": copy.source_container,
                    "source_path": copy.source_path,
                    "target_paths": list(copy.target_paths),
                }
            )
        return copied

    def _verify_disabled_heartbeat(self, slot: LanAioProdSlot) -> None:
        deadline = time.time() + 180
        while time.time() < deadline:
            if self._control_state(slot.agent_id) != "disabled":
                raise RuntimeError(f"{slot.agent_id} control state is not disabled")
            worker = next(
                (
                    item
                    for item in self._system_workers()
                    if item.get("agent_id") == slot.agent_id
                ),
                None,
            )
            if not worker:
                time.sleep(5)
                continue
            if str(worker.get("status") or "").lower() == "running" or worker.get(
                "current_task_type"
            ):
                raise RuntimeError(f"{slot.agent_id} picked work while disabled")
            expected = {
                "node_id": slot.node_id,
                "provider": "lan_ssh",
                "runtime_profile": self.config.profiles[
                    slot.target_profile_id
                ].runtime_profile,
            }
            errors = [
                f"{key}={worker.get(key)!r}"
                for key, value in expected.items()
                if worker.get(key) != value
            ]
            if worker.get("pool_managed") not in (True, "true", "True", "1", 1):
                errors.append(f"pool_managed={worker.get('pool_managed')!r}")
            if errors:
                raise RuntimeError(
                    f"{slot.agent_id} heartbeat missing metadata: " + ", ".join(errors)
                )
            return
        raise TimeoutError(
            f"timed out waiting for disabled heartbeat from {slot.agent_id}"
        )

    def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
        return self._local(["ssh", *SSH_BATCH_OPTIONS, host, command], capture=capture)

    def _scp(self, source: Path, host: str, remote_path: str) -> None:
        self._local(
            ["scp", *SSH_BATCH_OPTIONS, str(source), f"{host}:{remote_path}"],
            capture=True,
        )

    def _local(
        self,
        cmd: list[str],
        *,
        capture: bool = False,
        input_text: str | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> str:
        kwargs: dict[str, Any] = {
            "check": True,
            "text": True,
        }
        if input_text is not None:
            kwargs["input"] = input_text
        if extra_env:
            kwargs["env"] = {**os.environ, **extra_env}
        if capture:
            kwargs["stdout"] = subprocess.PIPE
            kwargs["stderr"] = subprocess.PIPE
        completed = subprocess.run(cmd, **kwargs)
        return str(completed.stdout or "")


def patch_baked_remote_workers(rendered: str, slot: LanAioProdSlot) -> str:
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("LAN AIO compose patching requires PyYAML") from exc
    compose = yaml.safe_load(rendered) or {}
    service = compose.get("services", {}).get(slot.container_name)
    if not isinstance(service, dict):
        raise RuntimeError(f"compose service not found: {slot.container_name}")
    environment = service.setdefault("environment", {})
    environment["RUNPOD_REMOTE_WORKER_ROOT"] = REMOTE_WORKERS_TARGET_DIR
    environment["PYTHONPATH"] = REMOTE_WORKERS_TARGET_DIR
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    volumes = service.setdefault("volumes", [])
    volumes[:] = [
        value
        for value in volumes
        if not str(value).startswith(f"{slot.remote_workers_dir}:")
    ]
    runtime = compose.setdefault("x-allbot-runtime", {})
    runtime["remote_workers_bundle"] = {
        "source": "image",
        "target": REMOTE_WORKERS_TARGET_DIR,
        "mode": "baked_immutable_artifact",
    }
    return _dump_yaml(compose)


def assert_prod_compose(rendered: str, slot: LanAioProdSlot) -> None:
    forbidden = ["cloud-test", "user-data-test"]
    present = [item for item in forbidden if item in rendered]
    if present:
        raise RuntimeError(
            "rendered compose contains forbidden prod value: " + ", ".join(present)
        )
    required = [
        "RUNPOD_ENVIRONMENT: cloud-prod",
        "CENTRAL_API_URL: https://worker-central.aivison.it.com",
        "MINIO_RESULT_BUCKET: user-data-prod",
        f"AGENT_ID: {slot.agent_id}",
        f"container_name: {slot.container_name}",
    ]
    missing = [item for item in required if item not in rendered]
    if missing:
        raise RuntimeError("rendered compose missing: " + ", ".join(missing))


def _worker_summary(worker: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "agent_id",
        "status",
        "current_task_id",
        "current_task_type",
        "node_id",
        "provider",
        "runtime_profile",
        "types",
        "supported_task_types",
        "pool_managed",
        "image_ref",
    ]
    return {key: worker.get(key) for key in keys}


def _legacy_port_for_slot(config: ControllerConfig, slot: LanAioProdSlot) -> int:
    if slot.legacy_health_port is not None:
        return slot.legacy_health_port
    assignment = config.assignments[slot.assignment_id]
    node = config.nodes[assignment.node_id]
    comfy = next(unit for unit in node.comfy if unit.id == assignment.comfy_id)
    return comfy.port


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AllBot LAN AIO production fleet ops")
    parser.add_argument(
        "action",
        choices=(
            "list",
            "status",
            "render",
            "preflight",
            "configure-registry",
            "pull-image",
            "warm-cache",
            "drain-legacy",
            "wait-idle",
            "takeover",
            "start-disabled",
            "enable-aio",
            "drain-aio",
            "disable-aio",
            "restart-aio",
            "rollback",
            "stop-old",
            "recover",
            "candidate-plan",
            "release-rollout",
            "canary-start-disabled",
            "canary-stop-disabled",
            "state-init",
            "state-reconcile",
        ),
    )
    parser.add_argument("--slot", default=None)
    parser.add_argument("--replace-slot", default=None)
    parser.add_argument("--node-id", default=None)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--physical-slot", default=None)
    parser.add_argument("--operation-id", default=None)
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument(
        "--legacy-state-file",
        type=Path,
        default=CONFIG_DIR / "lan_aio_fleet_state.legacy.yml",
    )
    parser.add_argument("--reason", default=None)
    parser.add_argument("--prefer", choices=("old", "candidate"), default="old")
    parser.add_argument(
        "--failure-policy",
        choices=(FAILURE_POLICY_AUTO_ROLLBACK, "none"),
        default=FAILURE_POLICY_AUTO_ROLLBACK,
    )
    parser.add_argument("--include-disabled", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--config-root", type=Path, default=None)
    parser.add_argument("--compose-out", type=Path, default=None)
    parser.add_argument("--prod-env-file", type=Path, default=Path(".env.cloud.prod"))
    parser.add_argument("--aio-env-file", type=Path, default=Path(".env.lan-aio-prod"))
    parser.add_argument(
        "--model-env-file", type=Path, default=Path(".env.lan.model-cache")
    )
    parser.add_argument("--release-index", type=Path, default=None)
    parser.add_argument("--sha", default=None)
    parser.add_argument("--rollback-ref", default=None)
    parser.add_argument("--strategy", choices=("direct", "standard"), default="direct")
    return parser


def _print_json_payload(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _build_ops_from_args(args: argparse.Namespace) -> LanAioProdOps:
    return LanAioProdOps(
        config_root=args.config_root,
        prod_env_file=args.prod_env_file,
        aio_env_file=args.aio_env_file,
        model_env_file=args.model_env_file,
        state_dir=args.state_dir,
    )


def _handle_candidate_plan(args: argparse.Namespace, ops: LanAioProdOps) -> int:
    if not args.node_id or not args.profile or not args.replace_slot:
        raise SystemExit(
            "candidate-plan requires --node-id, --profile and --replace-slot"
        )
    _print_json_payload(
        ops.candidate_plan(
            node_id=args.node_id,
            profile=args.profile,
            replace_slot_id=args.replace_slot,
        )
    )
    return 0


def _resolve_recover_target(
    args: argparse.Namespace,
    ops: LanAioProdOps,
) -> tuple[str, str | None]:
    selected_slot_id = None
    physical_slot = args.physical_slot
    if args.slot:
        selected_slot = ops.select_slots(args.slot, include_disabled=True)[0]
        selected_slot_id = selected_slot.id
        selected_physical_slot = physical_slot_key(selected_slot)
        if physical_slot and physical_slot != selected_physical_slot:
            raise SystemExit(
                "--slot does not belong to --physical-slot: "
                f"{selected_slot_id} -> {selected_physical_slot}, got {physical_slot}"
            )
        physical_slot = selected_physical_slot
    if args.operation_id and not physical_slot:
        raise SystemExit(
            "recover --operation-id is accepted for audit logs, but this CLI "
            "currently requires --physical-slot to avoid broad recovery"
        )
    if not physical_slot:
        raise SystemExit("recover requires --physical-slot")
    return physical_slot, selected_slot_id


def _recover_dry_run_payload(
    *,
    args: argparse.Namespace,
    physical_slot: str,
    selected_slot_id: str | None,
) -> dict[str, Any]:
    return {
        "ok": True,
        "dry_run": True,
        "action": "recover",
        "physical_slot": physical_slot,
        "prefer": args.prefer,
        "selected_slot": selected_slot_id,
        "operations": [
            (f"disable sibling LAN AIO agents on {physical_slot}"),
            (f"start selected {args.prefer} container on {physical_slot}"),
            (f"enable selected LAN AIO agent on {physical_slot}"),
        ],
    }


def _handle_recover(args: argparse.Namespace, ops: LanAioProdOps) -> int:
    physical_slot, selected_slot_id = _resolve_recover_target(args, ops)
    if not args.execute:
        _print_json_payload(
            _recover_dry_run_payload(
                args=args,
                physical_slot=physical_slot,
                selected_slot_id=selected_slot_id,
            )
        )
        return 0
    guard_slot_id = ops.recovery_guard_slot_id(
        physical_slot,
        selected_slot_id=selected_slot_id,
    )
    if selected_slot_id is None and args.prefer == "old":
        selected_slot_id = guard_slot_id
    guard_slot = ops.slots[guard_slot_id]
    operation_id = args.operation_id or _new_operation_id("recover")
    _print_json_payload(
        ops.execute_managed_mutation(
            action="recover",
            slots=[guard_slot],
            operation_id=operation_id,
            execute=lambda: ops.recover_physical_slot(
                physical_slot=physical_slot,
                prefer=args.prefer,
                selected_slot_id=selected_slot_id,
            ),
        )
    )
    return 0


def _handle_state_action(args: argparse.Namespace, ops: LanAioProdOps) -> int:
    operation_id = args.operation_id or _new_operation_id(args.action)
    if not args.execute:
        payload = {
            "ok": True,
            "dry_run": True,
            "action": args.action,
            "state_dir": str(ops.state_store.state_dir),
            "operation_id": operation_id,
        }
        if args.action == "state-init":
            payload["legacy_state_file"] = str(args.legacy_state_file)
        else:
            payload["reason"] = args.reason
        _print_json_payload(payload)
        return 0
    if args.action == "state-init":
        _print_json_payload(
            ops.initialize_state_from_legacy(
                args.legacy_state_file,
                operation_id=operation_id,
            )
        )
        return 0
    if not args.reason:
        raise SystemExit("state-reconcile --execute requires --reason")
    _print_json_payload(
        ops.reconcile_state_from_live(
            operation_id=operation_id,
            reason=args.reason,
            allow_empty_physical_slots=(
                {args.physical_slot} if args.physical_slot else set()
            ),
        )
    )
    return 0


def _select_action_slots(
    args: argparse.Namespace,
    ops: LanAioProdOps,
) -> list[LanAioProdSlot]:
    slots = ops.select_slots(args.slot, include_disabled=args.include_disabled)
    if args.action in RETARGETABLE_REPLACE_SLOT_ACTIONS and len(slots) == 1:
        candidate = slots[0]
        physical_slot = physical_slot_key(candidate)
        ledger = ops.state_store.load_current()
        if ledger is None:
            if args.replace_slot:
                ledger_current_slot_id = args.replace_slot
            elif args.action == "render" and not args.execute:
                return slots
            else:
                ledger_current_slot_id = ops.current_slot_id(physical_slot)
        else:
            physical_state = (ledger.get("physical_slots") or {}).get(
                physical_slot
            ) or {}
            if (
                args.action == "preflight"
                and not (physical_state.get("current") or {}).get("slot_id")
                and physical_state.get("intentionally_empty")
            ):
                return slots
            ledger_current_slot_id = ops.current_slot_id(physical_slot)
            if args.replace_slot and args.replace_slot != ledger_current_slot_id:
                raise SystemExit(
                    "--replace-slot does not match the local current ledger: "
                    f"expected {ledger_current_slot_id}, got {args.replace_slot}"
                )
        if candidate.id == ledger_current_slot_id and args.action == "takeover":
            raise SystemExit(
                f"takeover target is already current in the local ledger: {candidate.id}"
            )
        if candidate.id == ledger_current_slot_id:
            return slots
        return [ops.retarget_slot(candidate, ledger_current_slot_id)]
    if not args.replace_slot:
        return slots
    if args.action not in RETARGETABLE_REPLACE_SLOT_ACTIONS:
        allowed = ", ".join(sorted(RETARGETABLE_REPLACE_SLOT_ACTIONS))
        raise SystemExit(f"--replace-slot is only supported for: {allowed}")
    if len(slots) != 1:
        raise SystemExit("--replace-slot requires exactly one --slot")
    return [ops.retarget_slot(slots[0], args.replace_slot)]


def _run_raw_execute_action(
    args: argparse.Namespace,
    ops: LanAioProdOps,
    slots: list[LanAioProdSlot],
) -> dict[str, Any]:
    if args.action == "configure-registry":
        return ops.configure_registry(slots)
    if args.action == "pull-image":
        return ops.pull_image(slots)
    if args.action == "warm-cache":
        return ops.warm_cache(slots)
    if args.action == "drain-legacy":
        return ops.drain_legacy(slots)
    if args.action == "wait-idle":
        return ops.wait_idle(slots)
    if args.action == "takeover":
        return ops.takeover(slots, failure_policy=args.failure_policy)
    if args.action == "canary-start-disabled":
        return ops.start_disabled_canary(slots)
    if args.action == "canary-stop-disabled":
        return ops.stop_disabled_canary(slots)
    if args.action == "start-disabled":
        return ops.start_disabled(slots)
    if args.action == "enable-aio":
        return ops.enable_aio(slots)
    if args.action == "drain-aio":
        return ops.drain_aio(slots)
    if args.action == "disable-aio":
        return ops.disable_aio(slots)
    if args.action == "restart-aio":
        return ops.restart_aio(slots)
    if args.action == "rollback":
        return ops.rollback(slots)
    if args.action == "stop-old":
        return ops.stop_old(slots)
    raise SystemExit(f"unsupported action: {args.action}")


def _run_lan_aio_prod_action(args: argparse.Namespace, ops: LanAioProdOps) -> int:
    if args.action == "list":
        _print_json_payload(ops.list_payload(include_disabled=args.include_disabled))
        return 0
    if args.action == "candidate-plan":
        return _handle_candidate_plan(args, ops)
    if args.action in {"state-init", "state-reconcile"}:
        return _handle_state_action(args, ops)
    if args.action == "recover":
        return _handle_recover(args, ops)
    if args.action == "release-rollout":
        if not args.slot or not args.release_index or not args.sha or not args.profile:
            raise SystemExit(
                "release-rollout requires --slot, --profile, --release-index and --sha"
            )
        slot = ops.select_slots(args.slot, include_disabled=True)[0]
        resolved = resolve_gpu_artifact(
            args.release_index,
            source_sha=args.sha,
            profile=args.profile,
            strategy=args.strategy,
        )
        if not args.execute:
            _print_json_payload(rollout_plan(resolved, slot=slot.id, operator="lan"))
            return 0
        operation_id = args.operation_id or _new_operation_id("release-rollout")
        _print_json_payload(
            ops.execute_managed_mutation(
                action="release-rollout",
                slots=[slot],
                operation_id=operation_id,
                execute=lambda: ops.release_rollout(
                    slot,
                    resolved,
                    rollback_ref=args.rollback_ref,
                ),
            )
        )
        return 0
    slots = _select_action_slots(args, ops)
    if args.action == "status":
        payload = ops.status_payload(slots)
        physical_slots = {physical_slot_key(slot) for slot in slots}
        payload["state"] = ops.state_status_payload(physical_slots)
        payload["ok"] = (
            bool(payload.get("ok")) and payload["state"]["status"] == "passed"
        )
        _print_json_payload(payload)
        return 0
    if args.action == "render":
        if len(slots) != 1:
            raise SystemExit("render requires exactly one --slot")
        rendered = ops.render_compose(slots[0])
        if args.compose_out:
            args.compose_out.write_text(rendered, encoding="utf-8")
            _print_json_payload({"ok": True, "compose_out": str(args.compose_out)})
        else:
            print(rendered)
        return 0
    if args.action == "preflight":
        _print_json_payload(ops.preflight_payload(slots, execute=args.execute))
        return 0
    if not args.execute:
        _print_json_payload(ops.dry_run_action(args.action, slots))
        return 0
    if args.action in DIRECT_TRANSITION_ACTIONS:
        raise SystemExit(
            f"direct {args.action} --execute is disabled; use takeover or recover "
            "so the local state ledger remains transactional"
        )
    if args.action == "wait-idle":
        _print_json_payload(ops.wait_idle(slots))
        return 0
    if args.action not in MANAGED_MUTATION_ACTIONS:
        raise SystemExit(f"unmanaged LAN AIO mutation action: {args.action}")
    operation_id = args.operation_id or _new_operation_id(args.action)
    payload = ops.execute_managed_mutation(
        action=args.action,
        slots=slots,
        operation_id=operation_id,
        execute=lambda: _run_raw_execute_action(args, ops, slots),
    )
    _print_json_payload(payload)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ops = _build_ops_from_args(args)
    return _run_lan_aio_prod_action(args, ops)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
