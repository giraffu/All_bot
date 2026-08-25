from __future__ import annotations

import re
import shutil
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

ARTIFACT_KINDS = ("input", "output", "temp")
UNSAFE_COMPONENT_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class ComfyArtifactRef:
    kind: str
    filename: str
    subfolder: str = ""


@dataclass(frozen=True)
class ComfyArtifactRoots:
    input_dir: str = ""
    output_dir: str = ""
    temp_dir: str = ""

    def for_kind(self, kind: str) -> str:
        if kind not in ARTIFACT_KINDS:
            return ""
        return str(getattr(self, f"{kind}_dir", "") or "")


def safe_artifact_component(value: str) -> str:
    return UNSAFE_COMPONENT_RE.sub("_", value).strip("._")[:80]


def artifact_ref_from_comfy_response(
    response: object,
    *,
    fallback_name: str,
) -> ComfyArtifactRef:
    payload = response if isinstance(response, dict) else {}
    return ComfyArtifactRef(
        kind=str(payload.get("type") or "input"),
        filename=str(payload.get("name") or fallback_name),
        subfolder=str(payload.get("subfolder") or ""),
    )


def resolve_artifact_path(
    roots: ComfyArtifactRoots,
    artifact: ComfyArtifactRef,
) -> Path | None:
    root_value = roots.for_kind(artifact.kind)
    if not root_value or not artifact.filename:
        return None
    root = Path(root_value).resolve(strict=False)
    candidate = (root / artifact.subfolder / artifact.filename).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if candidate == root:
        return None
    return candidate


def _remove_empty_parents(path: Path, *, root: Path) -> None:
    parent = path.parent
    while parent != root:
        try:
            parent.rmdir()
        except OSError:
            return
        parent = parent.parent


def cleanup_artifacts(
    *,
    roots: ComfyArtifactRoots,
    artifacts: Iterable[ComfyArtifactRef],
) -> list[str]:
    removed: list[str] = []
    seen: set[Path] = set()
    first_error: OSError | None = None
    for artifact in artifacts:
        path = resolve_artifact_path(roots, artifact)
        if path is None or path in seen:
            continue
        seen.add(path)
        try:
            if not path.is_file() and not path.is_symlink():
                continue
            path.unlink()
            removed.append(str(path))
            root = Path(roots.for_kind(artifact.kind)).resolve(strict=False)
            _remove_empty_parents(path, root=root)
        except FileNotFoundError:
            continue
        except OSError as exc:
            first_error = first_error or exc
    if first_error is not None:
        raise RuntimeError(
            "one or more ComfyUI artifacts could not be removed"
        ) from first_error
    return removed


def cleanup_stale_artifacts(
    *,
    roots: ComfyArtifactRoots,
    max_age_seconds_by_kind: Mapping[str, float],
    protected_artifacts: Iterable[ComfyArtifactRef] = (),
    now: float | None = None,
) -> list[str]:
    current_time = time.time() if now is None else now
    protected_paths = {
        path
        for artifact in protected_artifacts
        if (path := resolve_artifact_path(roots, artifact)) is not None
    }
    removed: list[str] = []
    for kind in ARTIFACT_KINDS:
        root_value = roots.for_kind(kind)
        max_age = float(max_age_seconds_by_kind.get(kind, 0))
        if not root_value or max_age <= 0:
            continue
        root = Path(root_value).resolve(strict=False)
        if not root.is_dir():
            continue
        cutoff = current_time - max_age
        for path in root.rglob("*"):
            try:
                resolved = path.resolve(strict=False)
                if (
                    resolved in protected_paths
                    or not path.is_file()
                    or path.stat().st_mtime >= cutoff
                ):
                    continue
                path.unlink()
                removed.append(str(resolved))
            except FileNotFoundError:
                continue
        for directory in sorted(
            (candidate for candidate in root.rglob("*") if candidate.is_dir()),
            key=lambda candidate: len(candidate.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                continue
    return removed


def artifact_disk_capacity(
    *,
    roots: ComfyArtifactRoots,
    minimum_free_bytes: int,
) -> tuple[bool, int | None, str | None]:
    checked_devices: set[int] = set()
    minimum_observed: tuple[int, str] | None = None
    for kind in ARTIFACT_KINDS:
        root_value = roots.for_kind(kind)
        if not root_value:
            continue
        root = Path(root_value)
        try:
            stat = root.stat()
            if stat.st_dev in checked_devices:
                continue
            checked_devices.add(stat.st_dev)
            free_bytes = int(shutil.disk_usage(root).free)
        except OSError:
            continue
        if minimum_observed is None or free_bytes < minimum_observed[0]:
            minimum_observed = (free_bytes, str(root.resolve(strict=False)))
    if minimum_observed is None:
        return True, None, None
    free_bytes, path = minimum_observed
    return free_bytes >= max(0, minimum_free_bytes), free_bytes, path
