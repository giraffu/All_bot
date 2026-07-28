from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .types import (
    Assignment,
    ComfyInstance,
    GpuNode,
    GpuSpec,
    ModelBundle,
    ModelFile,
    TaskProfile,
)


CONFIG_DIR = Path(__file__).resolve().parent / "config"


@dataclass(frozen=True)
class ControllerConfig:
    nodes: dict[str, GpuNode]
    profiles: dict[str, TaskProfile]
    assignments: dict[str, Assignment]
    bundles: dict[str, ModelBundle]
    raw: dict[str, Any]


def _load_structured_file(path: Path) -> Any:
    content = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(content)
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised only without PyYAML
        raise RuntimeError(f"Reading {path} requires PyYAML or JSON config") from exc
    return yaml.safe_load(content) or {}


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    return tuple(str(item).strip() for item in value if str(item).strip())


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _runtime_kind(item: dict[str, Any], node_runtime: str) -> str:
    explicit = item.get("comfy_runtime_kind")
    if explicit:
        return str(explicit)
    runtime = str(item.get("runtime") or node_runtime)
    if runtime in {"host_process", "host_service"}:
        return "host_service"
    if runtime in {"docker", "docker_container"}:
        return "docker_container"
    return runtime


def _default_instance_child_dir(
    item: dict[str, Any],
    name: str,
) -> str | None:
    if item.get(f"{name}_dir"):
        return str(item[f"{name}_dir"])
    instance_dir = item.get("instance_dir")
    if instance_dir:
        return str(Path(str(instance_dir)) / name)
    return None


def _default_health(item: dict[str, Any]) -> dict[str, str]:
    health = dict(item.get("health") or {})
    health.setdefault("system_stats", "/system_stats")
    health.setdefault("queue", "/queue")
    health.setdefault("object_info", "/object_info")
    return health


def _parse_nodes(raw_nodes: dict[str, Any]) -> dict[str, GpuNode]:
    nodes: dict[str, GpuNode] = {}
    for node_id, data in raw_nodes.items():
        gpus = tuple(
            GpuSpec(
                index=int(item["index"]),
                name=str(item["name"]),
                vram_gb=float(item["vram_gb"]),
            )
            for item in data.get("gpus", [])
        )
        comfy = []
        for item in data.get("comfy", []):
            gpu_index = int(item["gpu_index"]) if item.get("gpu_index") is not None else None
            runtime_kind = _runtime_kind(item, str(data["runtime"]))
            container_name = item.get("container_name")
            if container_name is None and runtime_kind == "docker_container" and gpu_index is not None:
                container_name = f"allbot-comfy-gpu{gpu_index}"
            comfy.append(
                ComfyInstance(
                    id=str(item["id"]),
                    port=int(item["port"]),
                    gpu_index=gpu_index,
                    worker_id=item.get("worker_id"),
                    api_url=str(item["api_url"]),
                    ws_url=str(item["ws_url"]),
                    model_dir=str(item.get("model_dir") or data["model_dir"]),
                    runtime=str(item.get("runtime") or data["runtime"]),
                    image=item.get("image"),
                    instance_dir=item.get("instance_dir"),
                    custom_nodes_dir=item.get("custom_nodes_dir"),
                    workflows_dir=item.get("workflows_dir"),
                    input_dir=_default_instance_child_dir(item, "input"),
                    output_dir=_default_instance_child_dir(item, "output"),
                    temp_dir=_default_instance_child_dir(item, "temp"),
                    comfy_runtime_kind=runtime_kind,
                    comfy_runtime_managed=_as_bool(
                        item.get("comfy_runtime_managed"),
                        default=False,
                    ),
                    container_name=container_name,
                    container_port=(
                        int(item["container_port"])
                        if item.get("container_port") is not None
                        else 8188
                    ),
                    compose_template=item.get("compose_template"),
                    runtime_shape=str(
                        item.get("runtime_shape") or "standard_comfy_runtime"
                    ),
                    slot_id=item.get("slot_id"),
                    runtime_root=item.get("runtime_root"),
                    model_cache_endpoint=item.get("model_cache_endpoint"),
                    image_registry=item.get("image_registry"),
                    rollback_state=dict(item.get("rollback_state") or {}),
                    health=_default_health(item),
                    supported_task_types=_as_tuple(item.get("supported_task_types")),
                )
            )
        comfy_instances = tuple(comfy)
        nodes[node_id] = GpuNode(
            id=node_id,
            provider=str(data.get("provider", "lan_ssh")),
            host=str(data["host"]),
            ip=str(data["ip"]),
            ssh_alias=str(data.get("ssh_alias") or data["host"]),
            model_dir=str(data["model_dir"]),
            runtime=str(data["runtime"]),
            gpus=gpus,
            comfy=comfy_instances,
            notes=str(data.get("notes", "")),
        )
    return nodes


def _parse_profiles(raw_profiles: dict[str, Any]) -> dict[str, TaskProfile]:
    profiles: dict[str, TaskProfile] = {}
    for profile_id, data in raw_profiles.items():
        profiles[profile_id] = TaskProfile(
            id=profile_id,
            task_types=_as_tuple(data.get("task_types")),
            runtime_profile=str(data.get("runtime_profile") or profile_id),
            model_bundles=_as_tuple(data.get("model_bundles")),
            required_nodes=_as_tuple(data.get("required_nodes")),
            workflow=data.get("workflow"),
            min_vram_gb=(
                float(data["min_vram_gb"]) if data.get("min_vram_gb") is not None else None
            ),
            image_ref=data.get("image_ref"),
            all_in_one_image_ref=data.get("all_in_one_image_ref"),
            model_prefix=data.get("model_prefix"),
            model_manifest_key=data.get("model_manifest_key"),
            model_manifest_keys=_as_tuple(data.get("model_manifest_keys")),
            lan_workspace_key=data.get("lan_workspace_key"),
            lan_model_workspace_key=data.get("lan_model_workspace_key"),
            lan_local_model_overrides=tuple(
                dict(item) for item in (data.get("lan_local_model_overrides") or [])
            ),
        )
    return profiles


def _parse_assignments(raw_assignments: list[dict[str, Any]]) -> dict[str, Assignment]:
    assignments: dict[str, Assignment] = {}
    for data in raw_assignments:
        assignment = Assignment(
            id=str(data["id"]),
            enabled=bool(data.get("enabled", True)),
            provider=str(data.get("provider", "lan_ssh")),
            node_id=str(data["node_id"]),
            comfy_id=str(data["comfy_id"]),
            worker_id=str(data["worker_id"]),
            profile_id=str(data["profile_id"]),
            task_types=_as_tuple(data.get("task_types")),
            max_parallel_tasks=int(data.get("max_parallel_tasks", 1)),
            notes=str(data.get("notes", "")),
        )
        assignments[assignment.id] = assignment
    return assignments


def _parse_bundles(raw_bundles: dict[str, Any]) -> dict[str, ModelBundle]:
    bundles: dict[str, ModelBundle] = {}
    for bundle_id, data in raw_bundles.items():
        files = tuple(
            ModelFile(
                relative_path=str(item["relative_path"]),
                sha256=str(item["sha256"]),
                size_bytes=int(item.get("size_bytes", 0)),
                source_path=item.get("source_path"),
            )
            for item in data.get("files", [])
            if item.get("relative_path") and item.get("sha256")
        )
        bundles[bundle_id] = ModelBundle(
            id=bundle_id,
            version=str(data.get("version", "unversioned")),
            profiles=_as_tuple(data.get("profiles")),
            source=dict(data.get("source", {})),
            files=files,
        )
    return bundles


def load_controller_config(config_root: Path | str | None = None) -> ControllerConfig:
    root = Path(config_root) if config_root else CONFIG_DIR
    raw = {
        "nodes": _load_structured_file(root / "nodes.yml"),
        "task_profiles": _load_structured_file(root / "task_profiles.yml"),
        "assignments": _load_structured_file(root / "assignments.yml"),
        "model_bundles": _load_structured_file(root / "model_bundles.yml"),
    }
    return ControllerConfig(
        nodes=_parse_nodes(raw["nodes"].get("nodes", {})),
        profiles=_parse_profiles(raw["task_profiles"].get("profiles", {})),
        assignments=_parse_assignments(raw["assignments"].get("assignments", [])),
        bundles=_parse_bundles(raw["model_bundles"].get("bundles", {})),
        raw=raw,
    )
