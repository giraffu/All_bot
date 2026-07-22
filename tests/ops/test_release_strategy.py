import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "release_strategy.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("release_strategy", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("track", "artifacts", "locked", "expected_risk", "expected_strategy"),
    [
        ("control-plane", {"central-api"}, False, "critical", "standard"),
        (
            "control-plane",
            {"dashboard-backend"},
            False,
            "owner-tools",
            "direct",
        ),
        (
            "control-plane",
            {"qqcc-config-backend", "qqcc-config-frontend"},
            False,
            "owner-tools",
            "standard",
        ),
        ("control-plane", {"public-web"}, False, "public-web", "standard"),
        ("test-execution", {"worker-agent"}, False, "execution", "direct"),
        ("gpu-execution", {"i2i_pro"}, False, "execution", "direct"),
        ("control-plane", {"dashboard-backend"}, True, "locked", "standard"),
        (
            "control-plane",
            {"dashboard-backend", "central-api"},
            False,
            "critical",
            "standard",
        ),
    ],
)
def test_classification_uses_the_highest_risk_module(
    track, artifacts, locked, expected_risk, expected_strategy
):
    module = _load_module()

    decision = module.decide_release_strategy(
        track=track,
        artifacts=artifacts,
        requested="auto",
        locked=locked,
        validation_mode="full",
    )

    assert decision.risk_class == expected_risk
    assert decision.strategy == expected_strategy


def test_media_runtime_base_is_non_runtime_release_infrastructure():
    module = _load_module()

    decision = module.decide_release_strategy(
        track="control-plane",
        artifacts={"python-media-runtime-base"},
        requested="auto",
        locked=False,
        validation_mode="full",
    )

    assert decision.risk_class == "non-runtime"
    assert decision.strategy == "standard"


def test_direct_and_emergency_have_default_skips():
    module = _load_module()

    owner = module.decide_release_strategy(
        track="control-plane",
        artifacts={"dashboard-backend"},
        requested="auto",
        locked=False,
        validation_mode="full",
    )
    emergency = module.decide_release_strategy(
        track="control-plane",
        artifacts={"central-api"},
        requested="emergency",
        locked=False,
        validation_mode="full",
        reason="restore API quickly",
    )

    expected = {"test-deploy", "test-acceptance"}
    assert set(owner.skipped_gates) == expected
    assert set(emergency.skipped_gates) == expected
    assert emergency.gates["test-acceptance"] == "skipped"
    assert "observation" not in emergency.gates
    assert emergency.gates["immutable-artifact"] == "required"


def test_qqcc_auto_strategy_handles_one_shot_artifact_iterables():
    module = _load_module()

    decision = module.decide_release_strategy(
        track="control-plane",
        artifacts=(name for name in ("qqcc-config-frontend",)),
        requested="auto",
        locked=False,
        validation_mode="full",
    )

    assert decision.risk_class == "owner-tools"
    assert decision.strategy == "standard"
    assert decision.gates["test-deploy"] == "required"


def test_core_direct_and_locked_emergency_are_forbidden():
    module = _load_module()

    with pytest.raises(module.ReleaseStrategyError, match="critical"):
        module.decide_release_strategy(
            track="control-plane",
            artifacts={"central-api"},
            requested="direct",
            locked=False,
            validation_mode="full",
        )
    with pytest.raises(module.ReleaseStrategyError, match="locked"):
        module.decide_release_strategy(
            track="control-plane",
            artifacts={"web-api"},
            requested="emergency",
            locked=True,
            validation_mode="full",
            reason="unsafe migration",
        )


def test_public_web_direct_and_ci_test_skip_require_a_reason():
    module = _load_module()

    with pytest.raises(module.ReleaseStrategyError, match="reason"):
        module.decide_release_strategy(
            track="control-plane",
            artifacts={"public-web"},
            requested="direct",
            locked=False,
            validation_mode="full",
        )
    decision = module.decide_release_strategy(
        track="control-plane",
        artifacts={"dashboard-backend"},
        requested="direct",
        locked=False,
        validation_mode="build-only",
        skip_gates={"ci-tests"},
        reason="owner tool hotfix",
    )
    assert "ci-tests" in decision.skipped_gates


def test_build_only_requires_explicit_ci_test_skip_and_nonstandard_strategy():
    module = _load_module()

    with pytest.raises(module.ReleaseStrategyError, match="ci-tests"):
        module.decide_release_strategy(
            track="control-plane",
            artifacts={"dashboard-backend"},
            requested="direct",
            locked=False,
            validation_mode="build-only",
        )
    with pytest.raises(module.ReleaseStrategyError, match="standard"):
        module.decide_release_strategy(
            track="control-plane",
            artifacts={"central-api"},
            requested="standard",
            locked=False,
            validation_mode="build-only",
            skip_gates={"ci-tests"},
            reason="skip tests",
        )


def test_gpu_direct_skips_business_canary_but_keeps_attestation():
    module = _load_module()

    decision = module.decide_release_strategy(
        track="gpu-execution",
        artifacts={"i2i_pro"},
        requested="auto",
        locked=False,
        validation_mode="full",
    )

    assert "gpu-business-canary" in decision.skipped_gates
    assert decision.gates["gpu-artifact-attestation"] == "required"


def test_gpu_assurance_allows_attested_direct_but_not_standard():
    module = _load_module()
    artifact = {
        "validation_level": "attested",
        "artifact_attestation": "verified",
        "canary_evidence": "waived",
    }

    module.validate_gpu_artifact_assurance("direct", {"i2i_pro": artifact})
    with pytest.raises(module.ReleaseStrategyError, match="business canary"):
        module.validate_gpu_artifact_assurance("standard", {"i2i_pro": artifact})


def test_gpu_assurance_accepts_legacy_canary_manifest_for_standard():
    module = _load_module()

    module.validate_gpu_artifact_assurance("standard", {"i2i_pro": {}})


def test_promoted_candidate_validation_is_equivalent_to_full_ci():
    module = _load_module()

    decision = module.decide_release_strategy(
        track="control-plane",
        artifacts={"web-api"},
        requested="auto",
        locked=False,
        validation_mode="promoted",
    )

    assert decision.strategy == "standard"
    assert decision.validation_mode == "promoted"
    assert decision.gates["ci-tests"] == "required"
