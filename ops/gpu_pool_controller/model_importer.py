from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from src.domain_config.wan22_aio_video import (
    WAN22_LEGACY_IMAGE_TO_VIDEO_MODEL_PROFILE,
    WAN22_MODEL_PROFILES,
    WAN22_VIDEO_V2_MODEL_PROFILE,
)
from src.lora_catalog import (
    IMAGE_LORA_MODELS,
    LTX_VIDEO_LORA_OPTIONS,
    VIDEO_LORA_MODELS,
)
from src.workflow_mapping_validation import TASK_TYPE_WORKFLOW_FILENAMES

from .config_loader import ControllerConfig
from .model_repo import ModelRegistry
from .types import DEFAULT_MODEL_REGISTRY_ROOT, GpuNode


MODEL_EXTENSIONS = (".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf")
DEFAULT_WORKFLOW_DIR = Path("workers/comfy_agent/workflows")


@dataclass(frozen=True)
class ModelReference:
    kind: str
    value: str
    source: str
    workflow: str | None = None
    node_id: str | None = None
    class_type: str | None = None
    input_name: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return self.kind, self.value.replace("\\", "/")


@dataclass(frozen=True)
class InventoryEntry:
    node_id: str
    host: str
    model_dir: str
    relative_path: str
    size_bytes: int

    @property
    def remote_path(self) -> str:
        return f"{self.model_dir.rstrip('/')}/{self.relative_path}"


@dataclass(frozen=True)
class ResolvedModel:
    reference: ModelReference
    entry: InventoryEntry
    alternatives: tuple[InventoryEntry, ...] = ()
    sha256: str | None = None
    blob_exists: bool = False


@dataclass(frozen=True)
class BundleImportSpec:
    bundle: str
    version: str
    profiles: tuple[str, ...]
    source_node_id: str
    task_types: tuple[str, ...]
    dynamic_groups: tuple[str, ...] = ()
    exclude_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class BundleImportPlan:
    bundle: str
    version: str
    profiles: tuple[str, ...]
    source_node_id: str
    files: tuple[ResolvedModel, ...]
    missing: tuple[ModelReference, ...]


FIRST_WAVE_BUNDLES: dict[str, BundleImportSpec] = {
    "face_i2i_t2i_baseline": BundleImportSpec(
        bundle="face_i2i_t2i_baseline",
        version="2026-06-10",
        profiles=("face_i2i_t2i",),
        source_node_id="gpu-226",
        task_types=(
            "face_swap",
            "i2i_pro",
            "i2i_draw",
            "face_video",
            "t2i-pornmaster-turbo",
        ),
    ),
    "video_basic_baseline": BundleImportSpec(
        bundle="video_basic_baseline",
        version="2026-06-10",
        profiles=("video_basic",),
        source_node_id="gpu-177",
        task_types=("video_insert", "video_edit", "image_to_video"),
        dynamic_groups=("video_lora", "wan22_legacy"),
        exclude_values=tuple(WAN22_MODEL_PROFILES[WAN22_VIDEO_V2_MODEL_PROFILE].values()),
    ),
    "ltx_video_baseline": BundleImportSpec(
        bundle="ltx_video_baseline",
        version="2026-06-10",
        profiles=("ltx_video",),
        source_node_id="gpu-177",
        task_types=("ltx_video",),
        dynamic_groups=("ltx_lora",),
    ),
    "img2img_lora_baseline": BundleImportSpec(
        bundle="img2img_lora_baseline",
        version="2026-06-10",
        profiles=("img2img_lora",),
        source_node_id="gpu-252",
        task_types=("img2img", "img2img_lora"),
        dynamic_groups=("image_lora",),
    ),
    "i2i_pro_baseline": BundleImportSpec(
        bundle="i2i_pro_baseline",
        version="2026-06-14-test",
        profiles=("i2i_pro",),
        source_node_id="gpu-226",
        task_types=("i2i_pro",),
    ),
    "wan22_video_v2_baseline": BundleImportSpec(
        bundle="wan22_video_v2_baseline",
        version="2026-06-10",
        profiles=("wan22_video_v2",),
        source_node_id="gpu-252",
        task_types=("wan22_video_v2",),
        dynamic_groups=("wan22_v2",),
    ),
}


KIND_FOLDERS: dict[str, tuple[str, ...]] = {
    "checkpoints": ("checkpoints",),
    "clip": ("clip", "text_encoders"),
    "text_encoders": ("text_encoders", "clip"),
    "diffusion_models": ("diffusion_models", "unet"),
    "unet": ("unet", "diffusion_models"),
    "vae": ("vae", "vae_approx", "checkpoints"),
    "loras": ("loras",),
    "latent_upscale_models": ("latent_upscale_models", "upscale_models"),
    "upscale_models": ("upscale_models", "latent_upscale_models"),
    "sams": ("sams",),
    "ultralytics": ("ultralytics", "yolo", "detection"),
    "depthanything": ("depthanything",),
    "models": (
        "models",
        "latent_upscale_models",
        "upscale_models",
        "sams",
        "ultralytics",
        "depthanything",
        "diffusion_models",
        "unet",
        "checkpoints",
    ),
}


class ModelImportError(RuntimeError):
    pass


class ModelImportPlanner:
    def __init__(
        self,
        config: ControllerConfig,
        *,
        registry: ModelRegistry | None = None,
        workflow_dir: Path | str = DEFAULT_WORKFLOW_DIR,
    ):
        self.config = config
        self.registry = registry or ModelRegistry(DEFAULT_MODEL_REGISTRY_ROOT)
        self.workflow_dir = Path(workflow_dir)

    def workflow_model_check(self) -> dict[str, Any]:
        inventories = self.collect_inventories()
        refs = dedupe_references(
            list(extract_runtime_workflow_references(self.workflow_dir))
            + list(extract_dynamic_references())
        )
        checked = []
        missing = []
        for ref in refs:
            matches = self.resolve_reference_across_nodes(ref, inventories)
            payload = reference_to_json(ref)
            payload["matches"] = [entry_to_json(entry) for entry in matches]
            if matches:
                payload["status"] = "found"
            else:
                payload["status"] = "missing"
                missing.append(payload)
            checked.append(payload)
        return {
            "workflow_dir": str(self.workflow_dir),
            "reference_count": len(refs),
            "found_count": len(checked) - len(missing),
            "missing_count": len(missing),
            "missing": missing,
            "references": checked,
        }

    def build_import_plans(
        self,
        *,
        bundle_ids: Iterable[str] | None = None,
        include_sha256: bool = True,
    ) -> list[BundleImportPlan]:
        specs = self.selected_specs(bundle_ids)
        inventories = self.collect_inventories(
            node_ids=sorted({spec.source_node_id for spec in specs})
        )
        plans = []
        for spec in specs:
            source_inventory = inventories[spec.source_node_id]
            files: list[ResolvedModel] = []
            missing: list[ModelReference] = []
            for ref in self.references_for_spec(spec):
                selected, alternatives = self.resolve_reference_on_node(
                    ref,
                    source_inventory,
                )
                if selected is None:
                    missing.append(ref)
                    continue
                sha256 = (
                    self.remote_sha256(selected.host, selected.remote_path)
                    if include_sha256
                    else None
                )
                files.append(
                    ResolvedModel(
                        reference=ref,
                        entry=selected,
                        alternatives=tuple(alternatives),
                        sha256=sha256,
                        blob_exists=(
                            bool(sha256) and self.registry.blob_path(sha256).exists()
                        ),
                    )
                )
            plans.append(
                BundleImportPlan(
                    bundle=spec.bundle,
                    version=spec.version,
                    profiles=spec.profiles,
                    source_node_id=spec.source_node_id,
                    files=tuple(files),
                    missing=tuple(missing),
                )
            )
        return plans

    def execute_import(
        self,
        *,
        bundle_ids: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        plans = self.build_import_plans(bundle_ids=bundle_ids, include_sha256=True)
        missing = [
            reference_to_json(ref)
            for plan in plans
            for ref in plan.missing
        ]
        if missing:
            raise ModelImportError(
                f"Cannot execute import with {len(missing)} missing model references"
            )

        self.registry.ensure_layout()
        copied: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        manifests: list[str] = []
        for plan in plans:
            manifest_files = []
            for item in plan.files:
                if item.sha256 is None:
                    raise ModelImportError(f"Missing sha256 for {item.entry.remote_path}")
                blob_path = self.registry.blob_path(item.sha256)
                if blob_path.exists():
                    skipped.append(resolved_to_json(item))
                else:
                    self.copy_remote_blob(item.entry, item.sha256)
                    copied.append(resolved_to_json(item))
                manifest_files.append(
                    {
                        "relative_path": item.entry.relative_path,
                        "sha256": item.sha256,
                        "size_bytes": item.entry.size_bytes,
                        "source_node": item.entry.node_id,
                        "source_host": item.entry.host,
                        "source_path": item.entry.remote_path,
                        "reference_kind": item.reference.kind,
                        "reference_value": item.reference.value,
                    }
                )
            path = self.registry.write_bundle_manifest(
                bundle=plan.bundle,
                version=plan.version,
                profiles=list(plan.profiles),
                source={
                    "node_id": plan.source_node_id,
                    "host": self.config.nodes[plan.source_node_id].ssh_alias,
                    "model_dir": self.config.nodes[plan.source_node_id].model_dir,
                },
                files=manifest_files,
            )
            manifests.append(str(path))
        return {
            "copied_count": len(copied),
            "skipped_existing_count": len(skipped),
            "manifest_paths": manifests,
            "copied": copied,
            "skipped_existing": skipped,
        }

    def selected_specs(
        self,
        bundle_ids: Iterable[str] | None,
    ) -> list[BundleImportSpec]:
        selected = list(bundle_ids or FIRST_WAVE_BUNDLES)
        specs = []
        for bundle_id in selected:
            try:
                specs.append(FIRST_WAVE_BUNDLES[bundle_id])
            except KeyError as exc:
                raise ValueError(f"Unknown first-wave bundle: {bundle_id}") from exc
        return specs

    def references_for_spec(self, spec: BundleImportSpec) -> list[ModelReference]:
        refs = [
            ref
            for ref in extract_references_for_task_types(
                self.workflow_dir,
                spec.task_types,
            )
            if ref.value.replace("\\", "/") not in spec.exclude_values
        ]
        refs.extend(extract_dynamic_references(groups=spec.dynamic_groups))
        return dedupe_references(refs)

    def collect_inventories(
        self,
        *,
        node_ids: Iterable[str] | None = None,
    ) -> dict[str, list[InventoryEntry]]:
        selected = list(node_ids or self.config.nodes)
        inventories = {}
        for node_id in selected:
            node = self.config.nodes[node_id]
            inventories[node_id] = self.remote_inventory(node)
        return inventories

    def remote_inventory(self, node: GpuNode) -> list[InventoryEntry]:
        name_args = " -o ".join(f"-name '*{ext}'" for ext in MODEL_EXTENSIONS)
        command = (
            f"find {shlex.quote(node.model_dir)} -type f \\( {name_args} \\) "
            "-printf '%P\\t%s\\n'"
        )
        proc = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                node.ssh_alias,
                command,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise ModelImportError(
                f"Inventory failed for {node.id}/{node.ssh_alias}: {proc.stderr.strip()}"
            )
        entries = []
        for line in proc.stdout.splitlines():
            if "\t" not in line:
                continue
            relative_path, size = line.rsplit("\t", 1)
            entries.append(
                InventoryEntry(
                    node_id=node.id,
                    host=node.ssh_alias,
                    model_dir=node.model_dir,
                    relative_path=relative_path,
                    size_bytes=int(size),
                )
            )
        return sorted(entries, key=lambda item: item.relative_path.lower())

    def resolve_reference_across_nodes(
        self,
        ref: ModelReference,
        inventories: dict[str, list[InventoryEntry]],
    ) -> list[InventoryEntry]:
        matches: list[InventoryEntry] = []
        for entries in inventories.values():
            selected, alternatives = self.resolve_reference_on_node(ref, entries)
            if selected:
                matches.append(selected)
                matches.extend(alternatives)
        return sorted(
            {entry.relative_path + entry.node_id: entry for entry in matches}.values(),
            key=lambda item: (item.node_id, item.relative_path.lower()),
        )

    def resolve_reference_on_node(
        self,
        ref: ModelReference,
        entries: list[InventoryEntry],
    ) -> tuple[InventoryEntry | None, list[InventoryEntry]]:
        value = ref.value.replace("\\", "/").lstrip("/")
        folders = KIND_FOLDERS.get(ref.kind, KIND_FOLDERS["models"])
        scored = []
        for entry in entries:
            score = match_score(entry.relative_path, value, folders)
            if score is not None:
                scored.append((score, entry.relative_path.lower(), entry))
        if not scored:
            return None, []
        scored.sort(key=lambda item: (item[0], item[1]))
        selected = scored[0][2]
        alternatives = [item[2] for item in scored[1:]]
        return selected, alternatives

    def remote_sha256(self, host: str, remote_path: str) -> str:
        proc = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                host,
                f"sha256sum -- {shlex.quote(remote_path)}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise ModelImportError(
                f"sha256 failed for {host}:{remote_path}: {proc.stderr.strip()}"
            )
        return proc.stdout.split()[0]

    def copy_remote_blob(self, entry: InventoryEntry, sha256: str) -> Path:
        blob_path = self.registry.blob_path(sha256)
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        temp_root = self.registry.root / "tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        temp_path = temp_root / f"{sha256}.partial"
        with temp_path.open("wb") as file_obj:
            proc = subprocess.run(
                [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ConnectTimeout=10",
                    entry.host,
                    f"cat -- {shlex.quote(entry.remote_path)}",
                ],
                check=False,
                stdout=file_obj,
            )
        if proc.returncode != 0:
            temp_path.unlink(missing_ok=True)
            raise ModelImportError(f"copy failed for {entry.host}:{entry.remote_path}")
        local_sha = self.registry.sha256_file(temp_path)
        if local_sha != sha256:
            temp_path.unlink(missing_ok=True)
            raise ModelImportError(
                f"sha256 mismatch for {entry.host}:{entry.remote_path}: "
                f"expected {sha256}, got {local_sha}"
            )
        temp_path.replace(blob_path)
        return blob_path


def extract_references_for_task_types(
    workflow_dir: Path,
    task_types: Iterable[str],
) -> list[ModelReference]:
    refs = []
    for task_type in task_types:
        workflow = TASK_TYPE_WORKFLOW_FILENAMES[task_type]
        refs.extend(extract_workflow_references(workflow_dir / workflow, task_type))
    return refs


def extract_runtime_workflow_references(
    workflow_dir: Path,
) -> list[ModelReference]:
    refs = []
    for task_type in sorted(TASK_TYPE_WORKFLOW_FILENAMES):
        refs.extend(extract_references_for_task_types(workflow_dir, [task_type]))
    return refs


def extract_workflow_references(
    path: Path,
    task_type: str,
) -> list[ModelReference]:
    workflow = json.loads(path.read_text(encoding="utf-8"))
    refs: list[ModelReference] = []
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        walk_inputs(
            inputs,
            refs=refs,
            task_type=task_type,
            workflow=path.name,
            node_id=str(node_id),
            class_type=class_type,
        )
    return refs


def walk_inputs(
    value: Any,
    *,
    refs: list[ModelReference],
    task_type: str,
    workflow: str,
    node_id: str,
    class_type: str,
    input_name: str | None = None,
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            walk_inputs(
                item,
                refs=refs,
                task_type=task_type,
                workflow=workflow,
                node_id=node_id,
                class_type=class_type,
                input_name=str(key),
            )
        return
    if isinstance(value, list):
        for item in value:
            walk_inputs(
                item,
                refs=refs,
                task_type=task_type,
                workflow=workflow,
                node_id=node_id,
                class_type=class_type,
                input_name=input_name,
            )
        return
    if not isinstance(value, str) or not value.lower().endswith(MODEL_EXTENSIONS):
        return
    refs.append(
        ModelReference(
            kind=kind_for_input(class_type, input_name or ""),
            value=value,
            source=f"workflow:{task_type}",
            workflow=workflow,
            node_id=node_id,
            class_type=class_type,
            input_name=input_name,
        )
    )


def kind_for_input(class_type: str, input_name: str) -> str:
    if input_name == "ckpt_name":
        return "checkpoints"
    if input_name == "unet_name":
        if class_type == "DiffusionModelLoaderKJ":
            return "diffusion_models"
        return "unet"
    if input_name in {"clip_name", "clip_name1", "clip_name2", "text_encoder"}:
        return "clip"
    if input_name == "vae_name":
        return "vae"
    if input_name in {"lora_name", "lora"}:
        return "loras"
    if input_name in {"model", "model_name"}:
        if class_type == "SAMLoader":
            return "sams"
        if class_type == "UltralyticsDetectorProvider":
            return "ultralytics"
        if class_type == "UpscaleModelLoader":
            return "upscale_models"
        if class_type == "LatentUpscaleModelLoader":
            return "latent_upscale_models"
        if class_type == "DownloadAndLoadDepthAnythingV2Model":
            return "depthanything"
        if class_type == "DiffusionModelLoaderKJ":
            return "diffusion_models"
    return "models"


def extract_dynamic_references(
    groups: Iterable[str] | None = None,
) -> list[ModelReference]:
    selected = (
        {"image_lora", "video_lora", "ltx_lora", "wan22_legacy", "wan22_v2"}
        if groups is None
        else set(groups)
    )
    refs: list[ModelReference] = []
    if "image_lora" in selected:
        refs.extend(
            ModelReference("loras", name, "catalog:image_lora")
            for name in IMAGE_LORA_MODELS
            if name
        )
    if "video_lora" in selected:
        for name in VIDEO_LORA_MODELS:
            if not name:
                continue
            refs.append(ModelReference("loras", f"{name}_high_noise.safetensors", "catalog:video_lora"))
            refs.append(ModelReference("loras", f"{name}_low_noise.safetensors", "catalog:video_lora"))
    if "ltx_lora" in selected:
        refs.extend(
            ModelReference("loras", str(option["path"]), "catalog:ltx_lora")
            for option in LTX_VIDEO_LORA_OPTIONS.values()
            if option.get("path")
        )
    if "wan22_legacy" in selected:
        refs.extend(wan22_profile_references(WAN22_LEGACY_IMAGE_TO_VIDEO_MODEL_PROFILE))
    if "wan22_v2" in selected:
        refs.extend(wan22_profile_references(WAN22_VIDEO_V2_MODEL_PROFILE))
    return refs


def wan22_profile_references(profile: str) -> list[ModelReference]:
    models = WAN22_MODEL_PROFILES[profile]
    return [
        ModelReference("unet", models["high"], f"domain:wan22:{profile}"),
        ModelReference("unet", models["low"], f"domain:wan22:{profile}"),
    ]


def dedupe_references(refs: Iterable[ModelReference]) -> list[ModelReference]:
    merged: dict[tuple[str, str], ModelReference] = {}
    for ref in refs:
        if ref.key not in merged:
            merged[ref.key] = ref
    return sorted(merged.values(), key=lambda item: (item.kind, item.value.lower()))


def match_score(
    relative_path: str,
    value: str,
    folders: tuple[str, ...],
) -> int | None:
    rel = relative_path.replace("\\", "/")
    candidates = [f"{folder}/{value}" for folder in folders]
    if rel in candidates:
        return candidates.index(rel)
    for index, folder in enumerate(folders):
        prefix = f"{folder}/"
        if rel.startswith(prefix) and rel.endswith(f"/{value}"):
            return 100 + index
    if rel == value or rel.endswith(f"/{value}"):
        return 1000
    return None


def reference_to_json(ref: ModelReference) -> dict[str, Any]:
    return {
        "kind": ref.kind,
        "value": ref.value,
        "source": ref.source,
        "workflow": ref.workflow,
        "node_id": ref.node_id,
        "class_type": ref.class_type,
        "input_name": ref.input_name,
    }


def entry_to_json(entry: InventoryEntry) -> dict[str, Any]:
    return {
        "node_id": entry.node_id,
        "host": entry.host,
        "model_dir": entry.model_dir,
        "relative_path": entry.relative_path,
        "remote_path": entry.remote_path,
        "size_bytes": entry.size_bytes,
    }


def resolved_to_json(item: ResolvedModel) -> dict[str, Any]:
    return {
        "reference": reference_to_json(item.reference),
        "entry": entry_to_json(item.entry),
        "sha256": item.sha256,
        "blob_exists": item.blob_exists,
        "alternatives": [entry_to_json(entry) for entry in item.alternatives],
    }


def plan_to_json(plan: BundleImportPlan) -> dict[str, Any]:
    return {
        "bundle": plan.bundle,
        "version": plan.version,
        "profiles": list(plan.profiles),
        "source_node_id": plan.source_node_id,
        "file_count": len(plan.files),
        "missing_count": len(plan.missing),
        "missing": [reference_to_json(ref) for ref in plan.missing],
        "files": [resolved_to_json(item) for item in plan.files],
    }
