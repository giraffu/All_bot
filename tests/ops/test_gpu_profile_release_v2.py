import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "gpu_profile_release_v2.py"
SHA = "a" * 40
DIGEST = "sha256:" + "1" * 64


def _load_module():
    spec = importlib.util.spec_from_file_location("gpu_profile_release_v2", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _evidence() -> dict:
    return {
        "profile": "i2i_pro",
        "source_sha": SHA,
        "image_digest": DIGEST,
        "model_manifest": {
            "key": "i2i_pro/manifest.json",
            "size": 12,
            "sha256": "2" * 64,
        },
        "checks": {
            "actual_image_digest": True,
            "baked_agent_revision": True,
            "baked_workflow_revision": True,
            "model_manifest_checksum": True,
            "central_task_type": True,
            "input_download": True,
            "output_upload": True,
            "terminal_callback": True,
            "rollback_drill": True,
        },
        "rollback_target": "ghcr.io/giraffu/old@sha256:" + "3" * 64,
    }


def test_profile_result_requires_full_canary_evidence(tmp_path):
    module = _load_module()
    evidence = _evidence()

    result = module.validate_canary_evidence(
        evidence,
        profile="i2i_pro",
        source_sha=SHA,
        image_ref="ghcr.io/giraffu/i2i@" + DIGEST,
    )

    assert result["baked_agent_revision"] == SHA
    assert result["baked_workflow_revision"] == SHA
    assert result["model_manifest"]["sha256"] == "2" * 64

    evidence["checks"]["input_download"] = False
    with pytest.raises(module.GPUProfileReleaseError, match="input_download"):
        module.validate_canary_evidence(
            evidence,
            profile="i2i_pro",
            source_sha=SHA,
            image_ref="ghcr.io/giraffu/i2i@" + DIGEST,
        )


def test_profile_can_be_published_from_artifact_attestation_without_business_canary():
    module = _load_module()
    evidence = _evidence()
    evidence["checks"] = {
        "actual_image_digest": True,
        "baked_agent_revision": True,
        "baked_workflow_revision": True,
        "model_manifest_checksum": True,
    }

    result = module.validate_artifact_attestation(
        evidence,
        profile="i2i_pro",
        source_sha=SHA,
        image_ref="ghcr.io/giraffu/i2i@" + DIGEST,
    )

    assert result["validation_level"] == "attested"
    assert result["canary_evidence"] == "waived"
    assert result["artifact_attestation"] == "verified"


def test_gpu_manifest_merge_preserves_unselected_profiles_and_replaces_exact_one():
    module = _load_module()
    previous = {
        "schema_version": 2,
        "track": "gpu-execution",
        "source_sha": "b" * 40,
        "artifacts": {"scail2": {"digest": "sha256:" + "4" * 64}},
    }
    result = module.validate_canary_evidence(
        _evidence(),
        profile="i2i_pro",
        source_sha=SHA,
        image_ref="ghcr.io/giraffu/i2i@" + DIGEST,
    )

    merged = module.merge_gpu_manifest(previous, "i2i_pro", result, source_sha=SHA)

    assert merged["source_sha"] == SHA
    assert merged["artifacts"]["scail2"] == previous["artifacts"]["scail2"]
    assert merged["artifacts"]["i2i_pro"]["digest"] == DIGEST
    assert merged["completeness"] == "incomplete"
    assert "i2i_pro" not in merged["missing_artifacts"]
    assert "scail2" not in merged["missing_artifacts"]


def test_gpu_manifest_publish_requires_complete_sha_tag_and_immutable_target(
    monkeypatch, tmp_path
):
    module = _load_module()
    monkeypatch.setattr(
        module,
        "load_catalog",
        lambda _path: {"i2i_pro": {"track": "gpu-execution"}},
    )
    manifest_path = tmp_path / "gpu-execution-manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    manifest = {
        "schema_version": 2,
        "track": "gpu-execution",
        "source_sha": SHA,
        "completeness": "complete",
        "missing_artifacts": [],
        "artifacts": {"i2i_pro": {"source_sha": SHA}},
    }
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[:3] == ["oras", "manifest", "fetch"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="not found")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    target = f"ghcr.io/giraffu/allbot-gpu-release-manifests:{SHA}"
    module.publish_gpu_manifest(
        manifest,
        manifest_path=manifest_path,
        publish_ref=target,
        source_sha=SHA,
        run_func=fake_run,
    )

    assert calls[-1][:3] == ["oras", "push", target]
    with pytest.raises(module.GPUProfileReleaseError, match="source SHA tag"):
        module.publish_gpu_manifest(
            manifest,
            manifest_path=manifest_path,
            publish_ref="ghcr.io/giraffu/allbot-gpu-release-manifests:latest",
            source_sha=SHA,
            run_func=fake_run,
        )


def test_gpu_manifest_publish_accepts_truthful_partial_exact_sha_evidence(tmp_path):
    module = _load_module()
    manifest_path = tmp_path / "gpu-execution-manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    artifact = module.validate_artifact_attestation(
        {
            **_evidence(),
            "checks": {
                "actual_image_digest": True,
                "baked_agent_revision": True,
                "baked_workflow_revision": True,
                "model_manifest_checksum": True,
            },
        },
        profile="i2i_pro",
        source_sha=SHA,
        image_ref="ghcr.io/giraffu/i2i@" + DIGEST,
    )
    monkeypatch_catalog = {
        "i2i_pro": {"track": "gpu-execution"},
        "scail2": {"track": "gpu-execution"},
    }
    original_loader = module.load_catalog
    module.load_catalog = lambda _path: monkeypatch_catalog
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(
            returncode=1 if command[:3] == ["oras", "manifest", "fetch"] else 0,
            stdout="",
            stderr="",
        )

    manifest = {
        "schema_version": 2,
        "track": "gpu-execution",
        "source_sha": SHA,
        "completeness": "incomplete",
        "missing_artifacts": ["scail2"],
        "artifacts": {"i2i_pro": artifact},
    }
    try:
        module.publish_gpu_manifest(
            manifest,
            manifest_path=manifest_path,
            publish_ref=f"ghcr.io/giraffu/allbot-gpu-release-manifests:{SHA}",
            source_sha=SHA,
            run_func=fake_run,
        )
    finally:
        module.load_catalog = original_loader

    assert calls[-1][0:2] == ["oras", "push"]


def test_gpu_manifest_publish_refuses_incomplete_or_existing_target(
    monkeypatch, tmp_path
):
    module = _load_module()
    monkeypatch.setattr(
        module,
        "load_catalog",
        lambda _path: {"i2i_pro": {"track": "gpu-execution"}},
    )
    manifest_path = tmp_path / "gpu-execution-manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    target = f"ghcr.io/giraffu/allbot-gpu-release-manifests:{SHA}"

    with pytest.raises(module.GPUProfileReleaseError, match="manifest shape"):
        module.publish_gpu_manifest(
            {"source_sha": SHA, "completeness": "incomplete"},
            manifest_path=manifest_path,
            publish_ref=target,
            source_sha=SHA,
            run_func=lambda *args, **kwargs: None,
        )

    def existing(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with pytest.raises(module.GPUProfileReleaseError, match="already exists"):
        module.publish_gpu_manifest(
            {
                "schema_version": 2,
                "track": "gpu-execution",
                "source_sha": SHA,
                "completeness": "complete",
                "missing_artifacts": [],
                "artifacts": {"i2i_pro": {"source_sha": SHA}},
            },
            manifest_path=manifest_path,
            publish_ref=target,
            source_sha=SHA,
            run_func=existing,
        )

    with pytest.raises(module.GPUProfileReleaseError, match="same source SHA"):
        module.publish_gpu_manifest(
            {
                "schema_version": 2,
                "track": "gpu-execution",
                "source_sha": SHA,
                "completeness": "complete",
                "missing_artifacts": [],
                "artifacts": {"i2i_pro": {"source_sha": "b" * 40}},
            },
            manifest_path=manifest_path,
            publish_ref=target,
            source_sha=SHA,
            run_func=lambda *args, **kwargs: None,
        )


def test_existing_gpu_manifest_publish_requires_exact_catalog_and_source_sha(monkeypatch):
    module = _load_module()
    artifact = module.validate_artifact_attestation(
        {
            **_evidence(),
            "checks": {
                "actual_image_digest": True,
                "baked_agent_revision": True,
                "baked_workflow_revision": True,
                "model_manifest_checksum": True,
            },
        },
        profile="i2i_pro",
        source_sha=SHA,
        image_ref="ghcr.io/giraffu/i2i@" + DIGEST,
    )
    expected = {"i2i_pro", "scail2"}
    monkeypatch.setattr(
        module,
        "load_catalog",
        lambda _path: {name: {"track": "gpu-execution"} for name in expected},
    )
    manifest = {
        "schema_version": 2,
        "track": "gpu-execution",
        "source_sha": SHA,
        "completeness": "complete",
        "missing_artifacts": [],
        "artifacts": {name: dict(artifact) for name in expected},
    }

    module.validate_complete_gpu_manifest(manifest, source_sha=SHA)

    manifest["artifacts"].pop("scail2")
    with pytest.raises(module.GPUProfileReleaseError, match="catalog profiles"):
        module.validate_complete_gpu_manifest(manifest, source_sha=SHA)

    manifest["artifacts"]["scail2"] = {**artifact, "source_sha": "b" * 40}
    with pytest.raises(module.GPUProfileReleaseError, match="same source SHA"):
        module.validate_complete_gpu_manifest(manifest, source_sha=SHA)


def test_gpu_manifest_publisher_workflow_is_digest_verified_and_main_ancestry_gated():
    workflow = (
        ROOT / ".github/workflows/publish-gpu-release-manifest.yml"
    ).read_text(encoding="utf-8")

    assert "packages: write" in workflow
    assert "git merge-base --is-ancestor" in workflow
    assert "MANIFEST_SHA256" in workflow
    assert "sha256sum --check" in workflow
    assert "base64 --decode" in workflow
    assert "--publish-existing-manifest" in workflow
    assert "allbot-gpu-release-manifests" in workflow
