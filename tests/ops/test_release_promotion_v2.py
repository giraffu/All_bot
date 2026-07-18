import importlib.util
import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "release_promotion_v2.py"
PUBLISH_MODULE_PATH = ROOT / "scripts" / "publish_release_approval_v2.py"
CANDIDATE_SHA = "a" * 40
MAIN_SHA = "b" * 40
BUNDLE_DIGEST = "sha256:" + "c" * 64


def _load_module():
    spec = importlib.util.spec_from_file_location("release_promotion_v2", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_publish_module():
    spec = importlib.util.spec_from_file_location(
        "publish_release_approval_v2", PUBLISH_MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _candidate_bundle(tmp_path: Path) -> Path:
    web_bytes = b"same-tested-web-archive"
    web_checksum = hashlib.sha256(web_bytes).hexdigest()
    manifests = {
        "control-plane": {
            "schema_version": 2,
            "track": "control-plane",
            "source_sha": CANDIDATE_SHA,
            "artifacts": {
                "web-api": {
                    "kind": "image",
                    "ref": "ghcr.io/giraffu/allbot-web-api@sha256:" + "1" * 64,
                    "digest": "sha256:" + "1" * 64,
                    "source_sha": CANDIDATE_SHA,
                    "oci_revision": CANDIDATE_SHA,
                    "dependency_closure": [],
                },
                "dashboard-backend": {
                    "kind": "image",
                    "ref": "ghcr.io/giraffu/allbot-dashboard-backend@sha256:" + "2" * 64,
                    "digest": "sha256:" + "2" * 64,
                    "source_sha": CANDIDATE_SHA,
                    "oci_revision": CANDIDATE_SHA,
                    "dependency_closure": [],
                },
                "public-web": {
                    "kind": "tar",
                    "ref": "public-web-dist.tgz",
                    "sha256": web_checksum,
                    "source_sha": CANDIDATE_SHA,
                    "dependency_closure": [],
                },
            },
        },
        "test-execution": {
            "schema_version": 2,
            "track": "test-execution",
            "source_sha": CANDIDATE_SHA,
            "artifacts": {
                "worker-relay": {
                    "kind": "image",
                    "ref": "ghcr.io/giraffu/allbot-worker-relay@sha256:" + "5" * 64,
                    "digest": "sha256:" + "5" * 64,
                    "source_sha": "0" * 40,
                    "oci_revision": "0" * 40,
                    "dependency_closure": [],
                }
            },
        },
        "gpu-execution": {
            "schema_version": 2,
            "track": "gpu-execution",
            "source_sha": CANDIDATE_SHA,
            "artifacts": {},
            "completeness": "incomplete",
            "missing_artifacts": ["i2i_pro"],
        },
    }
    names = {
        "control-plane": "control-plane-manifest.json",
        "test-execution": "test-execution-manifest.json",
        "gpu-execution": "gpu-execution-manifest.json",
    }
    for track, document in manifests.items():
        (tmp_path / names[track]).write_text(json.dumps(document), encoding="utf-8")
    (tmp_path / "public-web-dist.tgz").write_bytes(web_bytes)
    index = {
        "schema_version": 2,
        "source_sha": CANDIDATE_SHA,
        "ci_run": "https://github.com/giraffu/All_bot/actions/runs/1",
        "release_channel": "test-candidate",
        "source_ref": "refs/heads/codex/test-train",
        "validation": {"mode": "full", "tests": "passed"},
        "manifests": names,
    }
    path = tmp_path / "release-index.json"
    path.write_text(json.dumps(index), encoding="utf-8")
    return path


def _frozen() -> dict:
    return {
        "schema_version": 1,
        "candidate_sha": CANDIDATE_SHA,
        "candidate_bundle_digest": BUNDLE_DIGEST,
        "artifacts": {
            "web-api": {
                "digest": "sha256:" + "1" * 64,
                "source_sha": CANDIDATE_SHA,
            },
            "dashboard-backend": {
                "digest": "sha256:" + "2" * 64,
                "source_sha": CANDIDATE_SHA,
            },
            "public-web": {
                "digest": hashlib.sha256(b"same-tested-web-archive").hexdigest(),
                "source_sha": CANDIDATE_SHA,
            },
        },
    }


def _evidence() -> dict:
    return {
        "schema_version": 1,
        "candidate_sha": CANDIDATE_SHA,
        "candidate_bundle_digest": BUNDLE_DIGEST,
        "test_runtime_state_digest": "sha256:" + "4" * 64,
        "started_at": "2026-07-18T00:00:00+00:00",
        "completed_at": "2026-07-18T01:00:00+00:00",
        "checks": {
            "combination_tests": True,
            "health": True,
            "rollback_drill": True,
            "manual_acceptance": True,
        },
        "artifacts": {
            "web-api": {
                "digest": "sha256:" + "1" * 64,
                "source_sha": CANDIDATE_SHA,
                "status": "verified",
                "evidence_source": "cloud-test/control-plane/current.json",
            },
            "dashboard-backend": {
                "digest": "sha256:" + "2" * 64,
                "source_sha": CANDIDATE_SHA,
                "status": "approved-direct",
                "evidence_source": "owner-tools-direct-policy",
            },
            "public-web": {
                "digest": hashlib.sha256(b"same-tested-web-archive").hexdigest(),
                "source_sha": CANDIDATE_SHA,
                "status": "verified",
                "evidence_source": "cloud-test/pages",
            },
        },
    }


def test_release_approval_preserves_verified_and_direct_assurance():
    module = _load_module()

    approval = module.build_release_approval(
        frozen=_frozen(), evidence=_evidence(), approved_by="operator"
    )

    assert approval["status"] == "approved"
    assert approval["artifacts"]["web-api"]["status"] == "verified"
    assert approval["artifacts"]["dashboard-backend"]["status"] == "approved-direct"


def test_release_approval_rejects_a_digest_not_in_the_frozen_batch():
    module = _load_module()
    evidence = _evidence()
    evidence["artifacts"]["web-api"]["digest"] = "sha256:" + "f" * 64

    with pytest.raises(module.PromotionError, match="web-api.*digest"):
        module.build_release_approval(
            frozen=_frozen(), evidence=evidence, approved_by="operator"
        )


def test_release_approval_requires_every_frozen_artifact():
    module = _load_module()
    evidence = _evidence()
    del evidence["artifacts"]["public-web"]

    with pytest.raises(module.PromotionError, match="artifact set"):
        module.build_release_approval(
            frozen=_frozen(), evidence=evidence, approved_by="operator"
        )


def test_release_approval_preserves_inherited_artifact_source_sha():
    module = _load_module()
    frozen = _frozen()
    evidence = _evidence()
    inherited_sha = "0" * 40
    frozen["artifacts"]["dashboard-backend"]["source_sha"] = inherited_sha
    evidence["artifacts"]["dashboard-backend"]["source_sha"] = inherited_sha

    approval = module.build_release_approval(
        frozen=frozen, evidence=evidence, approved_by="operator"
    )

    assert approval["artifacts"]["dashboard-backend"]["source_sha"] == inherited_sha


def test_release_approval_requires_combination_and_manual_checks():
    module = _load_module()
    evidence = _evidence()
    del evidence["checks"]["combination_tests"]

    with pytest.raises(module.PromotionError, match="combination_tests"):
        module.build_release_approval(
            frozen=_frozen(), evidence=evidence, approved_by="operator"
        )


def test_promoted_bundle_reuses_candidate_artifacts_and_web_bytes(tmp_path):
    module = _load_module()
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    candidate_index = _candidate_bundle(candidate_dir)
    approval = module.build_release_approval(
        frozen=_frozen(), evidence=_evidence(), approved_by="operator"
    )
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    output = tmp_path / "main-release"

    index_path = module.assemble_promoted_release(
        candidate_index_path=candidate_index,
        approval_path=approval_path,
        output_dir=output,
        main_sha=MAIN_SHA,
        candidate_sha=CANDIDATE_SHA,
        candidate_bundle_digest=BUNDLE_DIGEST,
        ci_run="https://github.com/giraffu/All_bot/actions/runs/2",
    )

    index = json.loads(index_path.read_text(encoding="utf-8"))
    control = json.loads((output / "control-plane-manifest.json").read_text())
    assert index["source_sha"] == MAIN_SHA
    assert index["validation"] == {"mode": "promoted", "tests": "candidate-passed"}
    assert index["promotion"]["candidate_sha"] == CANDIDATE_SHA
    assert control["source_sha"] == MAIN_SHA
    assert control["artifacts"]["web-api"]["source_sha"] == CANDIDATE_SHA
    assert (output / "public-web-dist.tgz").read_bytes() == b"same-tested-web-archive"


def test_promoted_bundle_rejects_approval_forged_for_another_digest(tmp_path):
    module = _load_module()
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    candidate_index = _candidate_bundle(candidate_dir)
    approval = module.build_release_approval(
        frozen=_frozen(), evidence=_evidence(), approved_by="operator"
    )
    approval["artifacts"]["web-api"]["digest"] = "sha256:" + "f" * 64
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(module.PromotionError, match="web-api"):
        module.assemble_promoted_release(
            candidate_index_path=candidate_index,
            approval_path=approval_path,
            output_dir=tmp_path / "main-release",
            main_sha=MAIN_SHA,
            candidate_sha=CANDIDATE_SHA,
            candidate_bundle_digest=BUNDLE_DIGEST,
            ci_run="https://github.com/giraffu/All_bot/actions/runs/2",
        )


def test_approval_publisher_validates_exact_candidate_before_oras_push(
    tmp_path, monkeypatch
):
    promotion = _load_module()
    publisher = _load_publish_module()
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    candidate_index = _candidate_bundle(candidate_dir)
    approval = promotion.build_release_approval(
        frozen=_frozen(), evidence=_evidence(), approved_by="operator"
    )
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return type("Result", (), {"returncode": 1, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(publisher.subprocess, "run", fake_run)

    result = publisher.publish_existing_approval(
        source_sha=CANDIDATE_SHA,
        candidate_index_path=candidate_index,
        candidate_bundle_digest=BUNDLE_DIGEST,
        approval_path=approval_path,
        publish_ref=(
            "ghcr.io/giraffu/allbot-release-v2-promotions:" + CANDIDATE_SHA
        ),
    )

    assert result == "published"
    assert calls[-1][0][0:2] == ["oras", "push"]
    assert calls[-1][0][-1] == (
        "approval.json:application/vnd.allbot.release-approval.v1+json"
    )
    assert calls[-1][1]["cwd"] == tmp_path


def test_approval_publisher_rejects_ref_for_another_sha(tmp_path):
    promotion = _load_module()
    publisher = _load_publish_module()
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    candidate_index = _candidate_bundle(candidate_dir)
    approval = promotion.build_release_approval(
        frozen=_frozen(), evidence=_evidence(), approved_by="operator"
    )
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(publisher.ApprovalPublishError, match="exact candidate SHA"):
        publisher.publish_existing_approval(
            source_sha=CANDIDATE_SHA,
            candidate_index_path=candidate_index,
            candidate_bundle_digest=BUNDLE_DIGEST,
            approval_path=approval_path,
            publish_ref="ghcr.io/giraffu/allbot-release-v2-promotions:" + "f" * 40,
        )


def test_promotion_relationship_requires_ancestry_and_identical_tree():
    module = _load_module()

    module.validate_promotion_relationship(is_ancestor=True, tree_equal=True)
    with pytest.raises(module.PromotionError, match="ancestor"):
        module.validate_promotion_relationship(is_ancestor=False, tree_equal=True)
    with pytest.raises(module.PromotionError, match="tree"):
        module.validate_promotion_relationship(is_ancestor=True, tree_equal=False)


def test_main_promotion_workflow_cannot_rebuild_or_redeploy_test():
    workflow = (
        ROOT / ".github" / "workflows" / "promote-tested-candidate.yml"
    ).read_text(encoding="utf-8")
    lowered = workflow.lower()

    assert "docker build" not in lowered
    assert "buildx" not in lowered
    assert "test_train_release.py deploy" not in lowered
    assert "release_promotion_v2.py" in workflow
    assert "git diff --quiet" in workflow


def test_candidate_build_workflow_no_longer_publishes_main_channel():
    workflow = (
        ROOT / ".github" / "workflows" / "modular-release-v2.yml"
    ).read_text(encoding="utf-8")

    assert "branches: [codex/test-train]" in workflow
    assert "options: [test-candidate]" in workflow
    assert "main) channel=main" not in workflow


def test_candidate_workflow_can_publish_a_digest_verified_approval_without_building():
    workflow = (
        ROOT / ".github" / "workflows" / "modular-release-v2.yml"
    ).read_text(encoding="utf-8")
    approval_job = workflow.split("\n  publish-approval:\n", 1)[1]

    assert "packages: write" in workflow
    assert "APPROVAL_BASE64" in approval_job
    assert "APPROVAL_SHA256" in approval_job
    assert "base64 --decode" in approval_job
    assert "sha256sum --check" in approval_job
    assert "git rev-parse origin/codex/test-train" in approval_job
    assert "publish_release_approval_v2.py" in approval_job
    assert "docker build" not in approval_job.lower()
    assert "ci_release_v2.py" not in approval_job
