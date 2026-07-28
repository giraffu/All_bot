import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "ci_release_v2.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ci_release_v2", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _catalog():
    return {
        "web-api": {"track": "control-plane"},
        "i2i": {"track": "gpu-execution"},
        "i2i_pro": {"track": "gpu-execution"},
        "scail2": {"track": "gpu-execution"},
    }


def test_incomplete_previous_gpu_bundle_stays_incomplete_without_evidence():
    module = _load_module()

    unavailable = module._unavailable_gpu_artifacts(
        _catalog(),
        planned_builds=set(),
        available_results={"web-api", "i2i", "scail2"},
        evidence_results=set(),
    )

    assert unavailable == {"i2i_pro"}


def test_changed_gpu_profile_requires_same_release_evidence():
    module = _load_module()

    unavailable = module._unavailable_gpu_artifacts(
        _catalog(),
        planned_builds={"i2i"},
        available_results={"web-api", "i2i", "i2i_pro", "scail2"},
        evidence_results=set(),
    )

    assert unavailable == {"i2i"}


def test_gpu_evidence_can_fill_a_previous_gap_and_satisfy_rebuild():
    module = _load_module()

    unavailable = module._unavailable_gpu_artifacts(
        _catalog(),
        planned_builds={"i2i_pro"},
        available_results={"web-api", "i2i", "i2i_pro", "scail2"},
        evidence_results={"i2i_pro"},
    )

    assert unavailable == set()


def test_gpu_evidence_only_satisfies_rebuild_when_artifact_matches_target_sha():
    module = _load_module()
    target_sha = "a" * 40
    document = {
        "schema_version": 2,
        "track": "gpu-execution",
        "source_sha": target_sha,
        "artifacts": {
            "i2i": {"source_sha": "b" * 40},
            "i2i_pro": {"source_sha": target_sha},
        },
    }

    artifacts, evidence = module._validated_gpu_evidence(
        document,
        catalog=_catalog(),
        source_sha=target_sha,
    )

    assert set(artifacts) == {"i2i", "i2i_pro"}
    assert evidence == {"i2i_pro"}


def _gpu_artifact(name: str, source_sha: str = "b" * 40):
    digest = "sha256:" + ({"i2i": "1", "i2i_pro": "2", "scail2": "3"}[name] * 64)
    return {
        "kind": "image",
        "ref": f"ghcr.io/giraffu/{name}@{digest}",
        "digest": digest,
        "source_sha": source_sha,
        "oci_revision": source_sha,
        "model_manifest": {
            "key": f"{name}/manifest.json",
            "sha256": "4" * 64,
            "size": 1,
        },
    }


def test_complete_gpu_baseline_can_fill_unchanged_profiles():
    module = _load_module()
    document = {
        "schema_version": 2,
        "track": "gpu-execution",
        "source_sha": "b" * 40,
        "completeness": "complete",
        "missing_artifacts": [],
        "artifacts": {
            name: _gpu_artifact(name)
            for name in ("i2i", "i2i_pro", "scail2")
        },
    }

    artifacts = module._validated_gpu_baseline(document, catalog=_catalog())

    assert set(artifacts) == {"i2i", "i2i_pro", "scail2"}
    assert artifacts["i2i"]["source_sha"] == "b" * 40


def test_historical_gpu_baseline_may_precede_a_new_catalog_profile():
    module = _load_module()
    document = {
        "schema_version": 2,
        "track": "gpu-execution",
        "source_sha": "b" * 40,
        "completeness": "complete",
        "missing_artifacts": [],
        "artifacts": {
            name: _gpu_artifact(name)
            for name in ("i2i", "i2i_pro")
        },
    }

    artifacts = module._validated_gpu_baseline(document, catalog=_catalog())

    assert set(artifacts) == {"i2i", "i2i_pro"}


def test_inherited_gpu_baseline_is_materialized_for_bundle_assembler(tmp_path):
    module = _load_module()
    results = {"web-api": {"kind": "image"}}
    inherited = {
        name: _gpu_artifact(name)
        for name in ("i2i", "i2i_pro", "scail2")
    }

    module._record_artifacts(inherited, results=results, results_dir=tmp_path)

    assert set(results) == {"web-api", "i2i", "i2i_pro", "scail2"}
    for name, artifact in inherited.items():
        assert (tmp_path / f"{name}.json").is_file()
        assert json.loads(
            (tmp_path / f"{name}.json").read_text(encoding="utf-8")
        ) == artifact


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda doc: doc["artifacts"].update(
                unknown=_gpu_artifact("i2i")
            ),
            "historical catalog subset",
        ),
        (
            lambda doc: doc["artifacts"]["i2i"].update(
                ref="ghcr.io/giraffu/i2i:latest"
            ),
            "digest-pinned",
        ),
        (
            lambda doc: doc["artifacts"]["i2i"].update(
                digest="sha256:" + "9" * 64
            ),
            "does not match",
        ),
    ],
)
def test_gpu_baseline_rejects_incomplete_or_mutable_artifacts(mutation, message):
    module = _load_module()
    document = {
        "schema_version": 2,
        "track": "gpu-execution",
        "source_sha": "b" * 40,
        "completeness": "complete",
        "missing_artifacts": [],
        "artifacts": {
            name: _gpu_artifact(name)
            for name in ("i2i", "i2i_pro", "scail2")
        },
    }
    mutation(document)

    with pytest.raises(module.CIReleaseError, match=message):
        module._validated_gpu_baseline(document, catalog=_catalog())


def test_changed_gpu_profile_is_not_satisfied_by_historical_baseline():
    module = _load_module()
    baseline = {name: _gpu_artifact(name) for name in ("i2i", "i2i_pro", "scail2")}

    unavailable = module._unavailable_gpu_artifacts(
        _catalog(),
        planned_builds={"i2i"},
        available_results={"web-api", *baseline},
        evidence_results=set(),
    )

    assert unavailable == {"i2i"}


def test_main_workflow_resolves_complete_gpu_baseline_from_all_ancestors():
    workflow = (ROOT / ".github/workflows/modular-release-v2.yml").read_text(
        encoding="utf-8"
    )

    assert 'git rev-list --topo-order "${SOURCE_SHA}^"' in workflow
    assert "release_channel' \"$index\")\" = main" in workflow
    assert "actual_profiles" in workflow
    assert "unexpected_profiles" in workflow
    assert "comm -23" in workflow
    assert "gpu-baseline-standalone/gpu-execution-manifest.json" in workflow
    assert 'oras repo tags "$gpu_manifest_repository"' in workflow
    assert "[ \"$(jq -r '.completeness' \"$manifest\")\" = complete ]" in workflow
    assert 'oras manifest fetch "$current_manifest_ref"' in workflow
    assert '--gpu-baseline-manifest "$GPU_BASELINE_MANIFEST"' in workflow


def test_main_bundle_refuses_incomplete_gpu_release_but_candidate_can_defer_it():
    module = _load_module()

    module._require_gpu_release_ready("test-candidate", {"i2i_pro"})
    with pytest.raises(module.CIReleaseError, match="main GPU release is incomplete"):
        module._require_gpu_release_ready("main", {"i2i_pro"})


def test_module_scoped_workflow_does_not_treat_historical_gpu_diff_as_rebuild():
    workflow = (ROOT / ".github/workflows/modular-release-v2.yml").read_text(
        encoding="utf-8"
    )

    assert "release_artifact" in workflow
    assert '--release-artifact "$RELEASE_ARTIFACT"' in workflow
    assert 'if [ -n "$RELEASE_ARTIFACT" ]; then' in workflow
    assert (
        "github.event_name == 'workflow_dispatch' && inputs.release_artifact != ''"
        in workflow
    )


def test_scoped_retry_reuses_exact_revision_image(monkeypatch):
    module = _load_module()
    sha = "a" * 40
    digest = "sha256:" + "1" * 64
    monkeypatch.setattr(module, "_registry_ref_exists", lambda _ref: True)
    monkeypatch.setattr(module, "_digest", lambda _ref: digest)
    monkeypatch.setattr(
        module,
        "_run",
        lambda _command: json.dumps(
            {"org.opencontainers.image.revision": sha}
        ),
    )

    result = module._build_image(
        name="qqcc-bot",
        metadata={"image": "allbot-qqcc-bot", "dependency_closure": []},
        source_sha=sha,
        image_prefix="ghcr.io/giraffu",
        results={},
        allow_existing=True,
    )

    assert result["digest"] == digest
    assert result["source_sha"] == sha


def test_scoped_retry_rejects_existing_image_from_another_revision(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(module, "_registry_ref_exists", lambda _ref: True)
    monkeypatch.setattr(
        module,
        "_run",
        lambda _command: json.dumps(
            {"org.opencontainers.image.revision": "b" * 40}
        ),
    )

    with pytest.raises(module.CIReleaseError, match="revision does not match"):
        module._build_image(
            name="qqcc-bot",
            metadata={"image": "allbot-qqcc-bot"},
            source_sha="a" * 40,
            image_prefix="ghcr.io/giraffu",
            results={},
            allow_existing=True,
        )
