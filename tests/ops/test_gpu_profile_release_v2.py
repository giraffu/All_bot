import importlib.util
from pathlib import Path

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
