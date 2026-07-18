import importlib.util
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


def test_main_bundle_refuses_incomplete_gpu_release_but_candidate_can_defer_it():
    module = _load_module()

    module._require_gpu_release_ready("test-candidate", {"i2i_pro"})
    with pytest.raises(module.CIReleaseError, match="main GPU release is incomplete"):
        module._require_gpu_release_ready("main", {"i2i_pro"})
