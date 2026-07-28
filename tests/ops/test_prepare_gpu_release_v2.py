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


def test_gpu_preparation_covers_all_profiles_with_nine_shared_images():
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

    assert len(module.WORKFLOWS) == 9
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
        if profile in {"lan_all", "ltx_t2v"}:
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
    assert len(payload["profiles"]) == 9


def test_gpu_preparation_can_scope_to_only_the_new_lan_profile():
    result = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--source-sha",
            "a" * 40,
            "--profile",
            "lan_all",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["profiles"] == ["lan_all"]


def test_scoped_lan_all_manifest_reuses_explicit_model_and_rollback_sources(
    monkeypatch, tmp_path
):
    module = _load_module()
    preparer = module.GPUReleasePreparer(
        ROOT,
        "a" * 40,
        profiles=["lan_all"],
    )
    digest = "sha256:" + "1" * 64
    rollback_digest = "sha256:" + "2" * 64
    model_manifest = {
        "key": "img2img_lora/2026-06-10/manifest.json",
        "sha256": "3" * 64,
        "size": 1,
    }

    def fake_run(command, *, cwd, check=True):
        if command[:2] == ["oras", "resolve"]:
            return digest
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
        if check:
            result.check_returncode()
        return result.stdout.strip()

    monkeypatch.setattr(module, "_run", fake_run)
    manifest_path = preparer._assemble_manifest(
        ROOT,
        tmp_path,
        {
            "artifacts": {
                "img2img": {"model_manifest": model_manifest},
                "pornmaster_flux2_edit_bf16": {
                    "ref": f"ghcr.io/giraffu/bf16@{rollback_digest}"
                },
            }
        },
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(manifest["artifacts"]) == {"lan_all"}
    assert manifest["completeness"] == "incomplete"
    assert manifest["artifacts"]["lan_all"]["model_manifest"] == model_manifest
    assert (
        manifest["artifacts"]["lan_all"]["rollback_target"]
        == f"ghcr.io/giraffu/bf16@{rollback_digest}"
    )


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


def test_publish_observes_dispatch_run_when_main_advances(
    monkeypatch,
    tmp_path,
):
    module = _load_module()
    preparer = module.GPUReleasePreparer(tmp_path, "a" * 40)
    calls = []

    def fake_workflow_runs(_workflow, *, source_sha_only=True):
        calls.append(source_sha_only)
        return [
            {
                "databaseId": 84,
                "status": "completed",
                "conclusion": "success",
                "headSha": "b" * 40,
            }
        ]

    monkeypatch.setattr(preparer, "_workflow_runs", fake_workflow_runs)

    run_id = preparer._wait_new_workflow(
        "publish-gpu-release-manifest.yml",
        {42},
        timeout_seconds=1,
        source_sha_only=False,
    )

    assert run_id == 84
    assert calls == [False]
