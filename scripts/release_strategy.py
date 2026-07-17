#!/usr/bin/env python3
"""Risk classification and gate decisions for immutable releases."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


STRATEGIES = ("auto", "standard", "direct", "emergency")
SKIPPABLE_GATES = {
    "ci-tests",
    "test-deploy",
    "test-acceptance",
    "observation",
    "gpu-business-canary",
}
OWNER_TOOL_ARTIFACTS = {
    "dashboard-backend",
    "dashboard-frontend",
    "qqcc-config-backend",
    "qqcc-config-frontend",
}
TEST_REQUIRED_OWNER_TOOL_ARTIFACTS = {
    "qqcc-config-backend",
    "qqcc-config-frontend",
}
PUBLIC_WEB_ARTIFACTS = {"public-web"}
NON_RUNTIME_ARTIFACTS = {
    "python-runtime-base",
    "python-worker-base",
    "postgres",
    "redis",
}
DIRECT_DEFAULT_SKIPS = {
    "test-deploy",
    "test-acceptance",
    "observation",
}


class ReleaseStrategyError(RuntimeError):
    """A requested release strategy is not valid for the selected risk."""


class ReleaseStrategyDecision:
    def __init__(
        self,
        *,
        risk_class: str,
        strategy: str,
        validation_mode: str,
        skipped_gates: Iterable[str],
        reason: str,
        approved_by: str,
        gates: dict[str, str],
    ) -> None:
        self.risk_class = risk_class
        self.strategy = strategy
        self.validation_mode = validation_mode
        self.skipped_gates = tuple(sorted(set(skipped_gates)))
        self.reason = reason
        self.approved_by = approved_by
        self.gates = dict(gates)

    def as_dict(self) -> dict[str, object]:
        return {
            "risk_class": self.risk_class,
            "strategy": self.strategy,
            "validation_mode": self.validation_mode,
            "skipped_gates": list(self.skipped_gates),
            "reason": self.reason or None,
            "approved_by": self.approved_by or None,
            "gates": dict(self.gates),
        }


def classify_risk(*, track: str, artifacts: Iterable[str], locked: bool) -> str:
    selected = set(artifacts) - NON_RUNTIME_ARTIFACTS
    if locked:
        return "locked"
    if track in {"test-execution", "gpu-execution"}:
        return "execution"
    if not selected:
        return "non-runtime"
    classes: set[str] = set()
    if selected & OWNER_TOOL_ARTIFACTS:
        classes.add("owner-tools")
    if selected & PUBLIC_WEB_ARTIFACTS:
        classes.add("public-web")
    if selected - OWNER_TOOL_ARTIFACTS - PUBLIC_WEB_ARTIFACTS:
        classes.add("critical")
    for risk in ("critical", "public-web", "owner-tools"):
        if risk in classes:
            return risk
    return "non-runtime"


def _default_strategy(risk_class: str, artifacts: Iterable[str]) -> str:
    selected = set(artifacts) - NON_RUNTIME_ARTIFACTS
    if risk_class == "owner-tools" and selected & TEST_REQUIRED_OWNER_TOOL_ARTIFACTS:
        return "standard"
    if risk_class in {"owner-tools", "execution"}:
        return "direct"
    return "standard"


def _validate_strategy(risk_class: str, strategy: str) -> None:
    allowed = {
        "locked": {"standard"},
        "critical": {"standard", "emergency"},
        "public-web": {"standard", "direct"},
        "owner-tools": {"standard", "direct"},
        "execution": {"standard", "direct"},
        "non-runtime": {"standard"},
    }[risk_class]
    if strategy not in allowed:
        raise ReleaseStrategyError(
            f"{risk_class} releases do not allow strategy {strategy}"
        )


def decide_release_strategy(
    *,
    track: str,
    artifacts: Iterable[str],
    requested: str = "auto",
    locked: bool,
    validation_mode: str,
    skip_gates: Iterable[str] = (),
    reason: str = "",
    approved_by: str = "",
) -> ReleaseStrategyDecision:
    if requested not in STRATEGIES:
        raise ReleaseStrategyError(f"unknown release strategy: {requested}")
    if validation_mode not in {"full", "build-only"}:
        raise ReleaseStrategyError(
            f"unknown release validation mode: {validation_mode}"
        )
    requested_skips = set(skip_gates)
    unknown = requested_skips - SKIPPABLE_GATES
    if unknown:
        raise ReleaseStrategyError(
            "unknown skippable release gates: " + ", ".join(sorted(unknown))
        )

    selected_artifacts = tuple(artifacts)
    risk_class = classify_risk(
        track=track, artifacts=selected_artifacts, locked=locked
    )
    strategy = (
        _default_strategy(risk_class, selected_artifacts)
        if requested == "auto"
        else requested
    )
    _validate_strategy(risk_class, strategy)

    skipped = set(requested_skips)
    if strategy in {"direct", "emergency"}:
        skipped.update(DIRECT_DEFAULT_SKIPS)
    if track == "gpu-execution" and strategy == "direct":
        skipped.add("gpu-business-canary")
    if strategy == "standard" and skipped:
        raise ReleaseStrategyError("standard releases cannot skip release gates")
    if validation_mode == "build-only" and "ci-tests" not in skipped:
        raise ReleaseStrategyError(
            "build-only artifacts require an explicit ci-tests skip gate"
        )
    if "ci-tests" in skipped and strategy not in {"direct", "emergency"}:
        raise ReleaseStrategyError(
            "ci-tests may only be skipped by direct or emergency releases"
        )

    risk_reason_required = (
        strategy == "emergency"
        or (risk_class == "public-web" and strategy == "direct")
        or "ci-tests" in skipped
    )
    clean_reason = reason.strip()
    clean_approver = approved_by.strip()
    if risk_reason_required and not clean_reason:
        raise ReleaseStrategyError("release risk acceptance requires a reason")
    if risk_reason_required and not clean_approver:
        raise ReleaseStrategyError("release risk acceptance requires approved-by")

    gates = {
        "protected-main-ancestry": "required",
        "artifact-build": "required",
        "immutable-artifact": "required",
        "digest-integrity": "required",
        "configuration-contract": "required",
        "production-confirmation": "required",
        "target-health": "required",
        "transaction-rollback": "required",
        "non-target-integrity": "required",
        "ci-tests": "skipped" if "ci-tests" in skipped else "required",
        "test-deploy": "skipped" if "test-deploy" in skipped else "required",
        "test-acceptance": (
            "skipped" if "test-acceptance" in skipped else "required"
        ),
        "observation": "skipped" if "observation" in skipped else "required",
        "gpu-artifact-attestation": (
            "required" if track == "gpu-execution" else "not-applicable"
        ),
        "gpu-business-canary": (
            "skipped"
            if "gpu-business-canary" in skipped
            else "required"
            if track == "gpu-execution"
            else "not-applicable"
        ),
    }
    return ReleaseStrategyDecision(
        risk_class=risk_class,
        strategy=strategy,
        validation_mode=validation_mode,
        skipped_gates=skipped,
        reason=clean_reason,
        approved_by=clean_approver,
        gates=gates,
    )


def validate_gpu_artifact_assurance(
    strategy: str, artifacts: Mapping[str, Mapping[str, Any]]
) -> None:
    """Require attestation for direct rollout and a business canary for standard."""

    for name, artifact in artifacts.items():
        # A legacy GPU manifest was necessarily canary-verified because the old
        # producer had no attestation-only path.
        level = str(artifact.get("validation_level", "canary-verified"))
        attestation = str(artifact.get("artifact_attestation", "verified"))
        canary = str(artifact.get("canary_evidence", "verified"))
        if attestation != "verified":
            raise ReleaseStrategyError(
                f"GPU artifact {name} has no verified artifact attestation"
            )
        if strategy == "standard" and not (
            level == "canary-verified" and canary == "verified"
        ):
            raise ReleaseStrategyError(
                f"standard GPU release requires business canary evidence for {name}"
            )
