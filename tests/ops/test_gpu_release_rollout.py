import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40


def _load_module():
    path = ROOT / "scripts/gpu_release_rollout.py"
    spec = importlib.util.spec_from_file_location("gpu_release_rollout", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bundle(tmp_path: Path, *, level: str = "attested") -> Path:
    digest = "sha256:" + "1" * 64
    gpu = {
        "schema_version": 2,
        "track": "gpu-execution",
        "source_sha": SHA,
        "artifacts": {
            "i2i_pro": {
                "kind": "image",
                "ref": "ghcr.io/giraffu/allbot-gpu-i2i-pro@" + digest,
                "digest": digest,
                "source_sha": SHA,
                "oci_revision": SHA,
                "dependency_closure": [],
                "task_types": ["i2i_pro"],
                "baked_agent_revision": SHA,
                "baked_workflow_revision": SHA,
                "model_manifest": {"key": "m.json", "size": 1, "sha256": "2" * 64},
                "target_gpu": ["RTX 4090"],
                "startup_args": [],
                "validation_level": level,
                "artifact_attestation": "verified",
                "canary_evidence": "waived" if level == "attested" else "verified",
            }
        },
    }
    def empty(track):
        return {
            "schema_version": 2,
            "track": track,
            "source_sha": SHA,
            "artifacts": {
                "placeholder": {
                    "kind": "external-image",
                    "ref": "docker.io/library/redis@sha256:" + "3" * 64,
                    "digest": "sha256:" + "3" * 64,
                    "dependency_closure": [],
                }
            },
        }
    files = {
        "control-plane-manifest.json": empty("control-plane"),
        "test-execution-manifest.json": empty("test-execution"),
        "gpu-execution-manifest.json": gpu,
    }
    for name, payload in files.items():
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    index = {
        "schema_version": 2,
        "source_sha": SHA,
        "ci_run": "https://github.com/giraffu/All_bot/actions/runs/1",
        "release_channel": "main",
        "source_ref": "refs/heads/main",
        "validation": {"mode": "full", "tests": "passed"},
        "manifests": {
            "control-plane": "control-plane-manifest.json",
            "test-execution": "test-execution-manifest.json",
            "gpu-execution": "gpu-execution-manifest.json",
        },
    }
    path = tmp_path / "release-index.json"
    path.write_text(json.dumps(index), encoding="utf-8")
    return path


def test_direct_rollout_resolves_exact_attested_digest(tmp_path):
    module = _load_module()
    resolved = module.resolve_gpu_artifact(
        _bundle(tmp_path), source_sha=SHA, profile="i2i_pro", strategy="direct"
    )
    plan = module.rollout_plan(resolved, slot="01", operator="runpod")

    assert resolved["ref"].endswith("@" + resolved["digest"])
    assert resolved["runpod_image_env"] == "RUNPOD_IMAGE_NAME_I2I_PRO"
    assert plan["scope"] == "single-slot"
    assert "whole-host restart" in plan["forbidden"]


def test_direct_rollout_accepts_complete_standalone_gpu_manifest(tmp_path):
    index_path = _bundle(tmp_path)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    gpu_path = tmp_path / index["manifests"]["gpu-execution"]

    module = _load_module()
    resolved = module.resolve_gpu_artifact(
        gpu_path, source_sha=SHA, profile="i2i_pro", strategy="direct"
    )

    assert resolved["ref"].endswith("@" + resolved["digest"])
    assert resolved["profile"] == "i2i_pro"


def test_direct_rollout_rejects_incomplete_standalone_gpu_manifest(tmp_path):
    index_path = _bundle(tmp_path)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    gpu_path = tmp_path / index["manifests"]["gpu-execution"]
    gpu = json.loads(gpu_path.read_text(encoding="utf-8"))
    gpu["completeness"] = "incomplete"
    gpu["missing_artifacts"] = ["face_swap"]
    gpu_path.write_text(json.dumps(gpu), encoding="utf-8")

    module = _load_module()
    with pytest.raises(module.GPURolloutError, match="must be complete"):
        module.resolve_gpu_artifact(
            gpu_path, source_sha=SHA, profile="i2i_pro", strategy="direct"
        )


def test_face_swap_profile_has_dedicated_rollout_image_env():
    module = _load_module()

    assert module.PROFILE_IMAGE_ENV["face_swap"] == "RUNPOD_IMAGE_NAME_FACE_SWAP"


def test_standard_rollout_rejects_attestation_without_canary(tmp_path):
    module = _load_module()
    with pytest.raises(module.GPURolloutError, match="business canary"):
        module.resolve_gpu_artifact(
            _bundle(tmp_path), source_sha=SHA, profile="i2i_pro", strategy="standard"
        )


def test_standard_rollout_accepts_canary_verified_artifact(tmp_path):
    module = _load_module()
    resolved = module.resolve_gpu_artifact(
        _bundle(tmp_path, level="canary-verified"),
        source_sha=SHA,
        profile="i2i_pro",
        strategy="standard",
    )
    assert resolved["canary_evidence"] == "verified"
