import os
import time
from pathlib import Path
from types import SimpleNamespace

from workers.comfy_agent import agent_artifact_lifecycle as lifecycle
from workers.comfy_agent.agent_artifact_lifecycle import (
    ComfyArtifactRef,
    ComfyArtifactRoots,
    artifact_disk_capacity,
    cleanup_artifacts,
    cleanup_stale_artifacts,
    cleanup_stale_files_in_root,
    cleanup_task_artifacts,
    resolve_artifact_path,
)


def _roots(tmp_path: Path) -> ComfyArtifactRoots:
    roots = ComfyArtifactRoots(
        input_dir=str(tmp_path / "input"),
        output_dir=str(tmp_path / "output"),
        temp_dir=str(tmp_path / "temp"),
    )
    for root in (roots.input_dir, roots.output_dir, roots.temp_dir):
        Path(root).mkdir(parents=True)
    return roots


def test_cleanup_artifacts_deletes_only_exact_files_inside_configured_roots(tmp_path):
    roots = _roots(tmp_path)
    target = Path(roots.output_dir) / "task-1" / "result.mp4"
    target.parent.mkdir()
    target.write_bytes(b"video")
    unrelated = Path(roots.output_dir) / "other.mp4"
    unrelated.write_bytes(b"keep")

    removed = cleanup_artifacts(
        roots=roots,
        artifacts=[
            ComfyArtifactRef(
                kind="output",
                filename="result.mp4",
                subfolder="task-1",
            )
        ],
    )

    assert removed == [str(target)]
    assert not target.exists()
    assert unrelated.read_bytes() == b"keep"


def test_cleanup_task_artifacts_deletes_only_files_owned_by_exact_task_id(tmp_path):
    roots = _roots(tmp_path)
    task_id = "a426afe8-cd79-4597-b972-57ab794ea8b8"
    owned = [
        Path(roots.input_dir) / f"{task_id}_input.png",
        Path(roots.output_dir) / f"minimax_h3_ref2v_{task_id}_00001.mp4",
        Path(roots.temp_dir) / "nested" / f"{task_id}_preview.png",
    ]
    for path in owned:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"owned")
    unrelated = Path(roots.output_dir) / "another-task.mp4"
    unrelated.write_bytes(b"keep")

    removed = cleanup_task_artifacts(roots=roots, task_id=task_id)

    assert removed == [str(path.resolve()) for path in owned]
    assert all(not path.exists() for path in owned)
    assert unrelated.read_bytes() == b"keep"


def test_cleanup_task_artifacts_rejects_unsafe_or_ambiguous_task_ids(tmp_path):
    roots = _roots(tmp_path)
    target = Path(roots.output_dir) / "task-result.mp4"
    target.write_bytes(b"keep")

    assert cleanup_task_artifacts(roots=roots, task_id="task") == []
    assert cleanup_task_artifacts(roots=roots, task_id="../task-result") == []
    assert target.read_bytes() == b"keep"


def test_resolve_artifact_path_rejects_parent_traversal(tmp_path):
    roots = _roots(tmp_path)

    assert (
        resolve_artifact_path(
            roots,
            ComfyArtifactRef(
                kind="output",
                filename="outside.mp4",
                subfolder="../",
            ),
        )
        is None
    )


def test_safe_artifact_component_is_bounded_for_comfyui_filenames():
    assert len(lifecycle.safe_artifact_component("x" * 200)) == 80


def test_stale_cleanup_preserves_recent_and_explicitly_protected_files(tmp_path):
    roots = _roots(tmp_path)
    old_output = Path(roots.output_dir) / "old.mp4"
    protected_output = Path(roots.output_dir) / "active.mp4"
    recent_output = Path(roots.output_dir) / "recent.mp4"
    for path in (old_output, protected_output, recent_output):
        path.write_bytes(path.name.encode())
    old_timestamp = time.time() - 7200
    os.utime(old_output, (old_timestamp, old_timestamp))
    os.utime(protected_output, (old_timestamp, old_timestamp))

    removed = cleanup_stale_artifacts(
        roots=roots,
        max_age_seconds_by_kind={"input": 3600, "output": 3600, "temp": 3600},
        protected_artifacts=[ComfyArtifactRef(kind="output", filename="active.mp4")],
    )

    assert removed == [str(old_output)]
    assert protected_output.exists()
    assert recent_output.exists()


def test_stale_root_cleanup_removes_restart_orphans_but_preserves_active_files(
    tmp_path,
):
    cache_root = tmp_path / "prefetch-cache" / "agent-1"
    cache_root.mkdir(parents=True)
    orphan = cache_root / "orphan.png"
    active = cache_root / "active.png"
    recent = cache_root / "recent.png"
    outside = tmp_path / "outside.png"
    for path in (orphan, active, recent, outside):
        path.write_bytes(path.name.encode())
    old_timestamp = time.time() - 7200
    for path in (orphan, active, outside):
        os.utime(path, (old_timestamp, old_timestamp))

    removed = cleanup_stale_files_in_root(
        root_dir=str(cache_root),
        max_age_seconds=3600,
        protected_paths=[str(active), str(outside)],
    )

    assert removed == [str(orphan)]
    assert not orphan.exists()
    assert active.exists()
    assert recent.exists()
    assert outside.exists()


def test_disk_capacity_gate_fails_closed_below_the_reserved_free_space(
    monkeypatch, tmp_path
):
    roots = _roots(tmp_path)
    monkeypatch.setattr(
        lifecycle.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=99),
    )

    has_capacity, observed_free, observed_path = artifact_disk_capacity(
        roots=roots,
        minimum_free_bytes=100,
    )

    assert has_capacity is False
    assert observed_free == 99
    assert observed_path is not None
