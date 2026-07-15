import importlib.util
from pathlib import Path


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
