from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "prepare_gpu_release_v2.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "prepare_gpu_release_v2", MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gpu_preparation_covers_all_profiles_with_eight_shared_images():
    module = _load_module()
    catalog = json.loads(
        (ROOT / "deploy/release-artifacts-v2.json").read_text(
            encoding="utf-8"
        )
    )
    expected = {
        name
        for name, artifact in catalog["artifacts"].items()
        if artifact["track"] == "gpu-execution"
    }
    covered = set(module.WORKFLOWS)
    for profiles in module.SHARED_IMAGE_PROFILES.values():
        covered.update(profiles)

    assert len(module.WORKFLOWS) == 8
    assert covered == expected
    assert module.SHARED_IMAGE_PROFILES == {
        "image_to_video": ("image_to_video", "wan22_video_v2")
    }


def test_gpu_workflow_dispatches_use_exact_sha_and_no_prod_action():
    module = _load_module()
    sha = "a" * 40

    for profile in module.WORKFLOWS:
        inputs = module._workflow_inputs(profile, sha)
        assert sha in " ".join(inputs)
        assert "prod" not in " ".join(inputs).lower()
        if profile == "ltx_t2v":
            assert inputs[:2] == ["-f", f"source_sha={sha}"]
        else:
            assert inputs[:2] == ["-f", f"image_tag={sha}"]


def test_gpu_preparation_defaults_to_a_non_mutating_dry_run():
    result = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--source-sha",
            "a" * 40,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["status"] == "dry-run"
    assert payload["production_deployed"] is False
    assert len(payload["profiles"]) == 8


def test_retry_observes_existing_exact_sha_build_without_dispatching(
    monkeypatch,
    tmp_path,
):
    module = _load_module()
    preparer = module.GPUReleasePreparer(tmp_path, "a" * 40)
    monkeypatch.setattr(preparer, "_remote_exists", lambda _ref: False)
    monkeypatch.setattr(
        preparer,
        "_workflow_runs",
        lambda _workflow: [
            {
                "databaseId": 42,
                "status": "in_progress",
                "conclusion": "",
                "headSha": "a" * 40,
            }
        ],
    )
    dispatched = []
    monkeypatch.setattr(
        module,
        "_run",
        lambda args, **_kwargs: dispatched.append(list(args)) or "",
    )

    before = preparer._dispatch_missing_images()

    assert all(ids == set() for ids in before.values())
    assert dispatched == []
