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
