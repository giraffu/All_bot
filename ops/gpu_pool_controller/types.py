from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GpuSpec:
    index: int
    name: str
    vram_gb: float


@dataclass(frozen=True)
class ComfyInstance:
    id: str
    port: int
    gpu_index: int | None
    worker_id: str | None
    api_url: str
    ws_url: str
    model_dir: str
    runtime: str
    image: str | None = None
    instance_dir: str | None = None
    custom_nodes_dir: str | None = None
    workflows_dir: str | None = None
    supported_task_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class GpuNode:
    id: str
    provider: str
    host: str
    ip: str
    ssh_alias: str
    model_dir: str
    runtime: str
    gpus: tuple[GpuSpec, ...]
    comfy: tuple[ComfyInstance, ...]
    notes: str = ""


@dataclass(frozen=True)
class TaskProfile:
    id: str
    task_types: tuple[str, ...]
    runtime_profile: str
    model_bundles: tuple[str, ...]
    required_nodes: tuple[str, ...] = ()
    workflow: str | None = None
    min_vram_gb: float | None = None
    image_ref: str | None = None


@dataclass(frozen=True)
class Assignment:
    id: str
    enabled: bool
    provider: str
    node_id: str
    comfy_id: str
    worker_id: str
    profile_id: str
    task_types: tuple[str, ...]
    max_parallel_tasks: int = 1
    notes: str = ""


@dataclass(frozen=True)
class ModelFile:
    relative_path: str
    sha256: str
    size_bytes: int
    source_path: str | None = None


@dataclass(frozen=True)
class ModelBundle:
    id: str
    version: str
    profiles: tuple[str, ...]
    source: dict[str, Any] = field(default_factory=dict)
    files: tuple[ModelFile, ...] = ()


@dataclass(frozen=True)
class PlanItem:
    assignment_id: str
    worker_id: str
    node_id: str
    comfy_id: str
    action: str
    task_types: tuple[str, ...]
    model_bundles: tuple[str, ...]
    image_ref: str | None
    warnings: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()


DEFAULT_MODEL_REGISTRY_ROOT = Path("/srv/allbot/model-registry")
DEFAULT_DOCKER_REGISTRY_ROOT = Path("/srv/allbot/docker-registry")
