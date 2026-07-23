#!/usr/bin/env python3
"""Plan and execute AllBot immutable releases.

The public seam is intentionally small: ``plan``, ``preflight``, ``deploy``,
``promote``, ``deploy-module``, ``rollback``, ``recover`` and ``validate-env``. Application code is delivered
only through digest-pinned images from a CI-produced release manifest. Git
checkouts on runtime hosts are used solely for the matching deployment contract
(compose, policy and helpers).
"""

from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import select
import shlex
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping, Sequence
import urllib.error
import urllib.parse
import urllib.request

try:
    from scripts.release_artifacts_v2 import (
        load_catalog,
        plan_builds as plan_artifact_builds,
    )
    from scripts.release_manifest_v2 import (
        ManifestV2Error,
        TRACKS as RELEASE_TRACKS,
        load_release_index,
        select_artifacts,
        validate_promotion as validate_v2_promotion,
    )
    from scripts.release_strategy import (
        ReleaseStrategyDecision,
        ReleaseStrategyError,
        STRATEGIES as RELEASE_STRATEGIES,
        decide_release_strategy,
        validate_gpu_artifact_assurance,
    )
    from scripts.gpu_release_rollout import PROFILE_IMAGE_ENV
except ModuleNotFoundError:  # direct ``python scripts/release.py`` execution
    from release_artifacts_v2 import (  # type: ignore[no-redef]
        load_catalog,
        plan_builds as plan_artifact_builds,
    )
    from release_manifest_v2 import (  # type: ignore[no-redef]
        ManifestV2Error,
        TRACKS as RELEASE_TRACKS,
        load_release_index,
        select_artifacts,
        validate_promotion as validate_v2_promotion,
    )
    from release_strategy import (  # type: ignore[no-redef]
        ReleaseStrategyDecision,
        ReleaseStrategyError,
        STRATEGIES as RELEASE_STRATEGIES,
        decide_release_strategy,
        validate_gpu_artifact_assurance,
    )
    from gpu_release_rollout import PROFILE_IMAGE_ENV  # type: ignore[no-redef]


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "deploy" / "release-policy.yml"
DEFAULT_SCHEMA = ROOT / "deploy" / "env.schema.yml"
DEFAULT_WEB_RUNTIME_CONFIG = ROOT / "frontend" / "runtime-config.yml"
DEFAULT_SERVICE_ENV_CONTRACT = ROOT / "deploy" / "service-env-contract.yml"
DEFAULT_ENV_DEFAULTS = ROOT / "deploy" / "env.defaults"
RUNTIME_ENV_HELPER = ROOT / "scripts" / "runtime_env_contract.py"
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_IMAGE_RE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
DEFAULT_BUNDLE_REPOSITORY = "ghcr.io/giraffu/allbot-release-v2"
PG_DUMP_IMAGE = (
    "docker.io/library/postgres@"
    "sha256:3a82e1f56c8f0f5616a11103ac3d47e632c3938698946a7ad26da0df1334744a"
)
PLAN_TOKEN_TTL_SECONDS = 600
PLAN_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
PROMOTE_DIRECT_ARTIFACTS = {
    "dashboard-backend",
    "dashboard-frontend",
    "support-bot",
}
REQUIRED_IMAGES = {
    "app",
    "central",
    "dashboard_backend",
    "dashboard_frontend",
    "worker",
}
REQUIRED_VENDOR_IMAGES = {"imgproxy", "postgres", "redis"}
RUNTIME_BASE_ARTIFACTS = {
    "python-runtime-base",
    "python-media-runtime-base",
    "python-worker-base",
}
NON_DEPLOYABLE_ARTIFACTS = RUNTIME_BASE_ARTIFACTS | {"postgres", "redis"}
CONTROL_ARTIFACT_ENV = {
    "central-api": "ALLBOT_CENTRAL_IMAGE",
    "web-api": "ALLBOT_WEB_API_IMAGE",
    "payment-api": "ALLBOT_PAYMENT_API_IMAGE",
    "main-bot": "ALLBOT_MAIN_BOT_IMAGE",
    "qqcc-bot": "ALLBOT_QQCC_BOT_IMAGE",
    "private-bot-worker": "ALLBOT_PRIVATE_BOT_WORKER_IMAGE",
    "paid-group-bot": "ALLBOT_PAID_GROUP_BOT_IMAGE",
    "support-bot": "ALLBOT_SUPPORT_BOT_IMAGE",
    "dashboard-backend": "ALLBOT_DASHBOARD_BACKEND_IMAGE",
    "qqcc-config-backend": "ALLBOT_QQCC_CONFIG_BACKEND_IMAGE",
    "dashboard-frontend": "ALLBOT_DASHBOARD_FRONTEND_IMAGE",
    "qqcc-config-frontend": "ALLBOT_QQCC_CONFIG_FRONTEND_IMAGE",
    "imgproxy": "ALLBOT_IMGPROXY_IMAGE",
    "postgres": "ALLBOT_POSTGRES_IMAGE",
    "redis": "ALLBOT_REDIS_IMAGE",
}
CONTROL_ARTIFACT_SERVICE = {
    "main-bot": "bot",
    "private-bot-worker": "qqcc-private-bot-worker",
    "paid-group-bot": "paid-group-guard-bot",
    "support-bot": "support-bot",
    "public-web": "web-static",
}
PROMOTE_ARTIFACT_SERVICE = {
    "central-api": "central-api",
    "web-api": "web-api",
    "payment-api": "payment-api",
    "imgproxy": "imgproxy",
    "dashboard-backend": "dashboard-backend",
    "dashboard-frontend": "dashboard-frontend",
    "main-bot": "bot",
    "qqcc-bot": "qqcc-bot",
    "qqcc-config-backend": "qqcc-config-backend",
    "qqcc-config-frontend": "qqcc-config-frontend",
    "private-bot-worker": "qqcc-private-bot-worker",
    "paid-group-bot": "paid-group-guard-bot",
    "support-bot": "support-bot",
}
GENERATION_MAINTENANCE_ARTIFACTS = {
    "central-api",
    "web-api",
    "main-bot",
    "qqcc-bot",
    "private-bot-worker",
}
REQUIRED_ISOLATED_SECRET_KEYS = {
    "AGENT_SECRET_TOKEN",
    "API_TOKEN",
    "AUTH_TOKEN",
    "DASHBOARD_SECRET_KEY",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "QQCC_CONFIG_SECRET_KEY",
    "R2_ACCESS_KEY",
    "R2_SECRET_KEY",
}
REQUIRED_ACCEPTANCE_CHECKS = {
    "health",
    "bot_interaction",
    "image_task",
    "video_task",
    "concurrency_lock",
    "locale",
    "web_static",
    "worker_heartbeat",
    "rollback_drill",
}
CORE_ACCEPTANCE_CHECKS = {
    "health",
    "image_task",
    "video_task",
    "concurrency_lock",
    "rollback_drill",
}
BOT_ACCEPTANCE_CHECKS = {"bot_interaction", "locale"}
WEB_ACCEPTANCE_CHECKS = {"health", "web_static", "rollback_drill"}
WORKER_ACCEPTANCE_CHECKS = {"health", "worker_heartbeat", "rollback_drill"}
ENVIRONMENT = {
    "test": {
        "host": "allbot-do-sgp1-test-control",
        "env_file": "/etc/allbot/test.env",
        "state_root": "/var/lib/allbot/test",
        "project": "allbot-test",
        "overlay": "deploy/docker-compose-cloud-test.overlay.yml",
        "available_services": {
            "central-api",
            "web-api",
            "bot",
            "qqcc-bot",
            "qqcc-config-backend",
            "qqcc-config-frontend",
            "qqcc-private-bot-worker",
            "imgproxy",
        },
    },
    "prod": {
        "host": "allbot-do-sgp1-control",
        "env_file": "/etc/allbot/prod.env",
        "state_root": "/var/lib/allbot/prod",
        "project": "allbot-prod",
        "overlay": "deploy/docker-compose-cloud-prod.overlay.yml",
        "available_services": {
            "central-api",
            "web-api",
            "payment-api",
            "dashboard-backend",
            "dashboard-frontend",
            "qqcc-config-backend",
            "qqcc-config-frontend",
            "bot",
            "qqcc-bot",
            "qqcc-private-bot-worker",
            "paid-group-guard-bot",
            "support-bot",
            "imgproxy",
        },
    },
}

COMPOSE_PROFILE_SERVICES = {
    "bot": {"bot"},
    "owner-tools": {
        "dashboard-backend",
        "dashboard-frontend",
        "qqcc-config-backend",
        "qqcc-config-frontend",
    },
    "paid-group": {"paid-group-guard-bot"},
    "qqcc-bot": {"qqcc-bot"},
    "qqcc-private-bots": {"qqcc-private-bot-worker"},
}


def compose_profile_flags(services: Iterable[str]) -> str:
    """Activate only profiles that contain an enabled target service."""

    selected = set(services)
    return " ".join(
        f"--profile {shlex.quote(profile)}"
        for profile, profile_services in COMPOSE_PROFILE_SERVICES.items()
        if selected & profile_services
    )


DASHBOARD_FAST_TRACK_BACKEND_PATTERNS = (
    "dashboard/backend/**",
    "deploy/docker/Dockerfile.dashboard-backend",
    "ops/gpu_pool_controller/runpod_profile_catalog.py",
)
DASHBOARD_FAST_TRACK_FRONTEND_PATTERNS = (
    "dashboard/frontend/**",
    "deploy/docker/Dockerfile.dashboard-frontend",
    "deploy/docker/nginx.dashboard.conf.template",
    "deploy/docker/select-dashboard-spa.sh",
)
DASHBOARD_FAST_TRACK_METADATA_PATTERNS = (
    "scripts/release.py",
    "deploy/release-policy.yml",
    "tests/**",
    "docs/**",
    ".codex/**",
    "AGENTS.md",
    "README.md",
)

CONTROL_PLANE_REPAIR_FAST_TRACK_RUNTIME_PATHS = {
    "deploy/docker/Dockerfile.control-plane",
    "deploy/release-artifacts-v2.json",
}
CONTROL_PLANE_REPAIR_FAST_TRACK_METADATA_PATTERNS = (
    "scripts/release.py",
    "tests/**",
    "docs/**",
    ".codex/**",
    "AGENTS.md",
    "README.md",
)

WEB_PAGES_TARGETS = {
    "test": {
        "project": "allbot-web-cf-test",
        "branch": "test",
        "canonical_url": "https://web-cf-test.aivison.it.com",
    },
    "prod": {
        "project": "allbot-web-prod",
        "branch": "main",
        "canonical_url": "https://web.aivison.it.com",
    },
}
PUBLIC_WEB_RUNTIME_FIELDS = {
    "api_base_url",
    "storage_url",
    "imgproxy_url",
    "telegram_bot_username",
    "tonconnect_manifest_url",
    "tonconnect_twa_return_url",
    "enable_free_edit_v2",
    "enable_free_edit_v3",
    "enable_scail2_long_action_transfer",
}


class ReleaseError(RuntimeError):
    """A safe, redacted release contract failure."""


class ReleaseImpact:
    def __init__(
        self,
        *,
        services: Iterable[str] = (),
        level: str = "none",
        requires_db_upgrade: bool = False,
        blockers: Iterable[str] = (),
        unknown_paths: Iterable[str] = (),
        matched_rules: Iterable[str] = (),
    ) -> None:
        self.services = set(services)
        self.level = level
        self.requires_db_upgrade = requires_db_upgrade
        self.blockers = set(blockers)
        self.unknown_paths = list(unknown_paths)
        self.matched_rules = list(matched_rules)

    def as_dict(self) -> dict[str, Any]:
        return {
            "services": sorted(self.services),
            "level": self.level,
            "requires_db_upgrade": self.requires_db_upgrade,
            "blockers": sorted(self.blockers),
            "unknown_paths": self.unknown_paths,
            "matched_rules": self.matched_rules,
        }


class ExecutionProfile:
    """Internal release path selection; the public CLI remains unchanged."""

    def __init__(self, name: str, reasons: Iterable[str]) -> None:
        if name not in {"streamlined", "strict"}:
            raise ReleaseError("unsupported release execution profile")
        self.name = name
        self.reasons = tuple(dict.fromkeys(str(reason) for reason in reasons))

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "reasons": list(self.reasons)}


STRICT_EXECUTION_RULES = {
    "database-migrations",
    "deployment-contract",
    "initial-release",
    "initial-artifact",
    "reviewed-additive-migration",
    "test-data-service-repair",
    "dashboard-lan-runner-change",
}


def dashboard_lan_runner_paths_changed(paths: Iterable[str]) -> bool:
    patterns = (
        "ops/gpu_pool_controller/**",
        "scripts/gpu_pool_controller.py",
        "scripts/gpu_release_rollout.py",
        "scripts/lan_aio_*.py",
        "scripts/lan_aio_*.sh",
        "scripts/lan_*_aio_*.sh",
    )
    return any(
        fnmatch.fnmatchcase(path.removeprefix("./"), pattern)
        for path in paths
        for pattern in patterns
    )


def resolve_execution_profile(
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    runtime_snapshot: Mapping[str, Any] | None,
) -> ExecutionProfile:
    """Choose the narrow rolling path only for a fully known main bundle."""

    reasons: list[str] = []
    track = str(manifest.get("track", "control-plane"))
    validation = manifest.get("validation")
    if manifest.get("schema_version") != 2:
        reasons.append("legacy-release-schema")
    if track != "control-plane":
        reasons.append(f"specialized-track:{track}")
    if (
        manifest.get("release_channel") != "main"
        or manifest.get("source_ref") != "refs/heads/main"
    ):
        reasons.append("unprotected-release-source")
    if not isinstance(validation, Mapping) or (
        validation.get("mode") != "full" or validation.get("tests") != "passed"
    ):
        reasons.append("incomplete-bundle-validation")
    if impact.requires_db_upgrade:
        reasons.append("database-migration")
    if impact.blockers:
        reasons.append("release-blocker")
    if impact.unknown_paths:
        reasons.append("unknown-impact")
    for rule in sorted(STRICT_EXECUTION_RULES & set(impact.matched_rules)):
        if rule not in reasons:
            reasons.append(rule)
    artifacts = manifest.get("artifacts")
    if isinstance(artifacts, Mapping):
        for name in manifest.get("selected_artifacts", []):
            artifact = artifacts.get(name)
            if isinstance(artifact, Mapping) and (
                artifact.get("execution_profile") == "strict"
                or artifact.get("requires_strict") is True
            ):
                reasons.append(f"strict-artifact:{name}")
    if not isinstance(runtime_snapshot, Mapping):
        reasons.append("target-config-not-checked")
    elif runtime_snapshot.get("drift"):
        reasons.append("target-config-drift")
    if reasons:
        return ExecutionProfile("strict", reasons)
    return ExecutionProfile(
        "streamlined", ("eligible-known-control-plane-change",)
    )


class IndependentModuleRelease:
    """A strict module boundary and the rollback baseline it owns."""

    def __init__(
        self,
        *,
        name: str,
        module_names: Iterable[str] = (),
        artifacts: Iterable[str],
        previous_sha: str,
        source_shas: Iterable[str] = (),
        initial_artifacts: Iterable[str] = (),
    ) -> None:
        self.name = name
        self.module_names = set(module_names) or set(name.split("+"))
        self.artifacts = set(artifacts)
        self.previous_sha = previous_sha
        self.source_shas = set(source_shas) or {previous_sha}
        self.initial_artifacts = set(initial_artifacts)


def expand_independent_module_request(
    policy: Mapping[str, Any], requested: set[str]
) -> tuple[str, set[str]] | None:
    """Expand one or more complete independent module aliases."""

    if not requested:
        return None
    configured = policy.get("independent_modules")
    if not isinstance(configured, Mapping):
        return None
    modules: dict[str, set[str]] = {}
    module_names: set[str] = set()
    module_artifacts: set[str] = set()
    for raw_name, raw_config in configured.items():
        if not isinstance(raw_config, Mapping):
            raise ReleaseError("independent module policy is invalid")
        artifacts_value = raw_config.get("artifacts")
        if not isinstance(artifacts_value, list) or not all(
            isinstance(value, str) and value for value in artifacts_value
        ):
            raise ReleaseError("independent module policy is invalid")
        name = str(raw_name)
        artifacts = set(artifacts_value)
        modules[name] = artifacts
        module_names.add(name)
        module_artifacts.update(artifacts)
    if requested <= module_names:
        names = sorted(requested)
        return "+".join(names), set().union(*(modules[name] for name in names))
    matches = [
        (name, artifacts)
        for name, artifacts in modules.items()
        if requested == artifacts
    ]
    if not matches:
        if requested & module_names or requested <= module_artifacts:
            raise ReleaseError(
                "independent release requires exactly one complete module group"
            )
        return None
    if len(matches) != 1:
        raise ReleaseError("independent module selection is ambiguous")
    return matches[0]


def resolve_independent_module_release(
    policy: Mapping[str, Any],
    requested: set[str],
    state: Mapping[str, Any] | None,
) -> IndependentModuleRelease | None:
    """Resolve one explicit independent module against its deployed artifacts."""

    expanded = expand_independent_module_request(policy, requested)
    if expanded is None:
        return None
    if not isinstance(state, Mapping) or state.get("schema_version") != 2:
        raise ReleaseError(
            "independent module release requires an existing schema-v2 deployment state"
        )
    state_artifacts = state.get("artifacts")
    if not isinstance(state_artifacts, Mapping):
        raise ReleaseError("independent module deployment state has no artifacts")
    name, artifacts = expanded
    configured = policy.get("independent_modules")
    configured_initial_artifacts: set[str] = set()
    if not isinstance(configured, Mapping):
        raise ReleaseError("independent module policy is invalid")
    for module_name in name.split("+"):
        module_config = configured.get(module_name)
        if not isinstance(module_config, Mapping):
            raise ReleaseError("independent module policy is invalid")
        raw_initial = module_config.get("initial_artifacts", [])
        if not isinstance(raw_initial, list) or not all(
            isinstance(value, str) and value for value in raw_initial
        ):
            raise ReleaseError("independent module policy is invalid")
        configured_initial_artifacts.update(raw_initial)
    if not configured_initial_artifacts <= artifacts:
        raise ReleaseError("independent module initial artifacts are invalid")
    fallback_sha = str(state.get("git_sha", ""))
    current_sha = validate_full_sha(fallback_sha)
    baselines: set[str] = set()
    initial_artifacts: set[str] = set()
    for artifact_name in artifacts:
        artifact_state = state_artifacts.get(artifact_name)
        if not isinstance(artifact_state, Mapping):
            if artifact_name in configured_initial_artifacts:
                initial_artifacts.add(artifact_name)
                baselines.add(current_sha)
                continue
            raise ReleaseError(
                f"independent module {name} has no deployed {artifact_name} baseline"
            )
        baseline = str(artifact_state.get("source_sha") or fallback_sha)
        baselines.add(validate_full_sha(baseline))
    return IndependentModuleRelease(
        name=name,
        module_names=name.split("+"),
        artifacts=artifacts,
        previous_sha=next(iter(baselines)) if len(baselines) == 1 else current_sha,
        source_shas=baselines,
        initial_artifacts=initial_artifacts,
    )


def validate_independent_release_paths(
    policy: Mapping[str, Any],
    selection: IndependentModuleRelease,
    changed_paths: Iterable[str],
    *,
    target_sha: str | None = None,
) -> None:
    """Fail closed when a strict module diff crosses a shared runtime contract."""

    blockers = policy.get("independent_release_blockers", [])
    if not isinstance(blockers, list):
        raise ReleaseError("independent release blocker policy is invalid")
    normalized_paths = [path.removeprefix("./") for path in changed_paths]
    for raw_blocker in blockers:
        if not isinstance(raw_blocker, Mapping):
            raise ReleaseError("independent release blocker policy is invalid")
        name = str(raw_blocker.get("name", ""))
        patterns = raw_blocker.get("patterns")
        modules = raw_blocker.get("modules")
        if (
            not name
            or not isinstance(patterns, list)
            or not all(isinstance(pattern, str) and pattern for pattern in patterns)
            or (
                modules is not None
                and (
                    not isinstance(modules, list)
                    or not all(isinstance(module, str) for module in modules)
                )
            )
        ):
            raise ReleaseError("independent release blocker policy is invalid")
        if isinstance(modules, list) and not selection.module_names.intersection(modules):
            continue
        matches = sorted(
            path
            for path in normalized_paths
            if any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)
        )
        if name == "database-migrations" and matches and target_sha:
            non_target = reviewed_non_target_migration_paths(
                policy,
                selection,
                matches,
                target_sha=target_sha,
            )
            reviewed = reviewed_additive_migration_paths(
                policy,
                selection,
                matches,
                target_sha=target_sha,
            )
            if non_target | reviewed == set(matches):
                continue
        if (
            matches
            and target_sha
            and independent_contract_snapshot_matches(
                policy,
                matches,
                target_sha=target_sha,
            )
        ):
            continue
        if matches:
            raise ReleaseError(
                f"independent module {selection.name} is blocked by {name}: "
                + ", ".join(matches)
            )


def reviewed_additive_migration_paths(
    policy: Mapping[str, Any],
    selection: IndependentModuleRelease,
    changed_paths: Iterable[str],
    *,
    target_sha: str,
) -> set[str]:
    """Return exact reviewed additive migrations for this module and SHA."""

    return _reviewed_independent_migration_paths(
        policy,
        selection,
        changed_paths,
        target_sha=target_sha,
        policy_key="independent_additive_migration_snapshots",
        error_label="independent additive migration policy is invalid",
    )


def reviewed_non_target_migration_paths(
    policy: Mapping[str, Any],
    selection: IndependentModuleRelease,
    changed_paths: Iterable[str],
    *,
    target_sha: str,
) -> set[str]:
    """Return pinned migrations reviewed as unrelated to the selected module."""

    return _reviewed_independent_migration_paths(
        policy,
        selection,
        changed_paths,
        target_sha=target_sha,
        policy_key="independent_non_target_migration_snapshots",
        error_label="independent non-target migration policy is invalid",
    )


def _reviewed_independent_migration_paths(
    policy: Mapping[str, Any],
    selection: IndependentModuleRelease,
    changed_paths: Iterable[str],
    *,
    target_sha: str,
    policy_key: str,
    error_label: str,
) -> set[str]:
    configured = policy.get(policy_key)
    if not isinstance(configured, Mapping):
        return set()
    target_sha = validate_full_sha(target_sha)
    migration_paths = {
        path.removeprefix("./")
        for path in changed_paths
        if path.removeprefix("./").startswith("migrations/")
        or path.removeprefix("./") == "alembic.ini"
    }
    if not migration_paths:
        return set()
    snapshots: dict[str, str] = {}
    for module_name in selection.module_names:
        raw_snapshots = configured.get(module_name, {})
        if not isinstance(raw_snapshots, Mapping):
            raise ReleaseError(error_label)
        for path, expected in raw_snapshots.items():
            if not isinstance(path, str) or not re.fullmatch(
                r"[0-9a-f]{64}", str(expected)
            ):
                raise ReleaseError(error_label)
            snapshots[path] = str(expected)
    reviewed_paths = migration_paths.intersection(snapshots)
    if not reviewed_paths:
        return set()
    for path in reviewed_paths:
        result = _run(["git", "show", f"{target_sha}:{path}"], check=False)
        if result.returncode != 0:
            return set()
        if hashlib.sha256(result.stdout.encode()).hexdigest() != snapshots[path]:
            return set()
    return reviewed_paths


def independent_contract_snapshot_matches(
    policy: Mapping[str, Any],
    changed_paths: Iterable[str],
    *,
    target_sha: str,
) -> bool:
    """Recognize reviewed owner-only contract snapshots without widening paths."""

    snapshots = policy.get("independent_contract_snapshots")
    if not isinstance(snapshots, Mapping):
        return False
    target_sha = validate_full_sha(target_sha)
    paths = set(changed_paths)
    if not paths or not paths <= set(snapshots):
        return False
    for path in paths:
        expected = snapshots.get(path)
        if expected is not None and not re.fullmatch(r"[0-9a-f]{64}", str(expected)):
            raise ReleaseError("independent contract snapshot policy is invalid")
        result = _run(
            ["git", "show", f"{target_sha}:{path}"],
            check=False,
        )
        if expected is None:
            if result.returncode == 0:
                return False
            continue
        if result.returncode != 0:
            return False
        if hashlib.sha256(result.stdout.encode()).hexdigest() != expected:
            return False
    return True


def _selected_artifact_names(
    manifest: Mapping[str, Any], impact: ReleaseImpact
) -> set[str]:
    if manifest.get("schema_version") == 2:
        return set(manifest.get("selected_artifacts", []))
    names: set[str] = set()
    service_to_artifact = {
        service: artifact for artifact, service in CONTROL_ARTIFACT_SERVICE.items()
    }
    for service in impact.services:
        names.add(service_to_artifact.get(service, service))
    return names


def _release_contract_is_locked(impact: ReleaseImpact) -> bool:
    locked_rules = {
        "database-migrations",
        "deployment-contract",
        "initial-release",
        "test-data-service-repair",
    }
    return bool(
        impact.requires_db_upgrade
        or impact.unknown_paths
        or locked_rules & set(impact.matched_rules)
    )


def _release_validation_mode(manifest: Mapping[str, Any]) -> str:
    validation = manifest.get("validation")
    if isinstance(validation, Mapping):
        return str(validation.get("mode", "full"))
    return "full"


def resolve_release_strategy(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
) -> ReleaseStrategyDecision:
    requested = str(getattr(args, "strategy", "auto"))
    if getattr(args, "dashboard_fast_track", False):
        if requested not in {"auto", "direct"}:
            raise ReleaseError(
                "--dashboard-fast-track conflicts with the requested release strategy"
            )
        requested = "direct"
    try:
        decision = decide_release_strategy(
            track=str(manifest.get("track", "control-plane")),
            artifacts=_selected_artifact_names(manifest, impact),
            requested=requested,
            locked=_release_contract_is_locked(impact),
            validation_mode=_release_validation_mode(manifest),
            skip_gates=_split_services(getattr(args, "skip_gate", [])),
            reason=str(getattr(args, "reason", "")),
        )
    except ReleaseStrategyError as exc:
        raise ReleaseError(str(exc)) from exc
    if manifest.get("track") == "gpu-execution":
        selected = {
            name: manifest["artifacts"][name]
            for name in manifest.get("selected_artifacts", [])
        }
        try:
            validate_gpu_artifact_assurance(decision.strategy, selected)
        except ReleaseStrategyError as exc:
            raise ReleaseError(str(exc)) from exc
    args.release_decision = decision
    return decision


def release_requires_test(decision: ReleaseStrategyDecision) -> bool:
    return decision.gates.get("test-acceptance") == "required"


PreflightCheck = Callable[
    [argparse.Namespace, "ReleaseImpact", Mapping[str, Any], Mapping[str, str]],
    list[str],
]


class PreflightDependencies:
    """Read-only adapters used by the release safety gate."""

    def __init__(
        self,
        *,
        operator: PreflightCheck,
        cloud: PreflightCheck,
        worker: PreflightCheck,
        pages: PreflightCheck,
        rollback: PreflightCheck,
    ) -> None:
        self.operator = operator
        self.cloud = cloud
        self.worker = worker
        self.pages = pages
        self.rollback = rollback


TransactionAction = Callable[[], Any]
TransactionJournalWriter = Callable[[Mapping[str, Any]], None]


class ReleaseTransactionDependencies:
    """Mutation and compensation adapters for one release transaction."""

    def __init__(
        self,
        *,
        cloud: TransactionAction,
        worker: TransactionAction,
        pages: TransactionAction,
        state: TransactionAction,
        rollback_pages: TransactionAction,
        rollback_worker: TransactionAction,
        rollback_cloud: TransactionAction,
        validate_recovery: TransactionAction,
        clear_maintenance: TransactionAction,
        journal: TransactionJournalWriter,
        enable_maintenance: TransactionAction | None = None,
    ) -> None:
        self.cloud = cloud
        self.worker = worker
        self.pages = pages
        self.state = state
        self.rollback_pages = rollback_pages
        self.rollback_worker = rollback_worker
        self.rollback_cloud = rollback_cloud
        self.validate_recovery = validate_recovery
        self.clear_maintenance = clear_maintenance
        self.journal = journal
        self.enable_maintenance = enable_maintenance or (lambda: None)


def new_release_transaction(
    *,
    environment: str,
    target_sha: str,
    previous_sha: str | None,
    previous_kind: str,
    previous_pages_deployment_id: str | None,
) -> dict[str, Any]:
    if environment not in ENVIRONMENT:
        raise ReleaseError(f"unsupported transaction environment: {environment}")
    if previous_kind not in {"legacy", "immutable"}:
        raise ReleaseError("transaction previous_kind must be legacy or immutable")
    return {
        "schema_version": 1,
        "transaction_id": target_sha,
        "environment": environment,
        "target_sha": target_sha,
        "previous": {
            "kind": previous_kind,
            "git_sha": previous_sha,
            "pages_deployment_id": previous_pages_deployment_id,
        },
        "phase": "preflight_passed",
        "status": "in_progress",
        "attempted_stages": [],
        "completed_stages": [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _journal_transition(
    transaction: dict[str, Any],
    writer: TransactionJournalWriter,
    *,
    phase: str,
    status: str | None = None,
) -> None:
    transaction["phase"] = phase
    if status is not None:
        transaction["status"] = status
    transaction["updated_at"] = datetime.now(timezone.utc).isoformat()
    writer(transaction)


def execute_release_transaction(
    transaction: dict[str, Any],
    dependencies: ReleaseTransactionDependencies,
) -> Mapping[str, Any] | None:
    """Execute cloud -> worker -> Pages -> state with reverse compensation."""

    attempted: list[str] = transaction["attempted_stages"]
    completed: list[str] = transaction["completed_stages"]
    _journal_transition(
        transaction,
        dependencies.journal,
        phase="preflight_passed",
        status="in_progress",
    )
    pages_result: Mapping[str, Any] | None = None
    stages = (
        ("cloud", dependencies.cloud),
        ("worker", dependencies.worker),
        ("pages", dependencies.pages),
        ("state", dependencies.state),
    )
    try:
        for name, action in stages:
            attempted.append(name)
            _journal_transition(
                transaction, dependencies.journal, phase=f"{name}_started"
            )
            stage_started = time.monotonic()
            print(
                f"[release] stage={name} status=started",
                file=sys.stderr,
                flush=True,
            )
            try:
                value = action()
            except Exception:
                stage_duration = max(0.0, time.monotonic() - stage_started)
                timings = transaction.setdefault("phase_timings_seconds", {})
                if isinstance(timings, dict):
                    timings[name] = stage_duration
                print(
                    f"[release] stage={name} status=failed "
                    f"elapsed={stage_duration:.3f}s",
                    file=sys.stderr,
                    flush=True,
                )
                raise
            stage_duration = max(0.0, time.monotonic() - stage_started)
            timings = transaction.setdefault("phase_timings_seconds", {})
            if isinstance(timings, dict):
                timings[name] = stage_duration
                if isinstance(value, Mapping):
                    remote_timings = value.get("phase_timings_seconds")
                    if isinstance(remote_timings, Mapping):
                        timings.update(
                            {
                                str(phase): float(duration)
                                for phase, duration in remote_timings.items()
                                if isinstance(duration, (int, float))
                            }
                        )
            print(
                f"[release] stage={name} status=completed "
                f"elapsed={stage_duration:.3f}s",
                file=sys.stderr,
                flush=True,
            )
            if name == "pages" and isinstance(value, Mapping):
                pages_result = value
                transaction["pages_deployment"] = dict(value)
            completed.append(name)
            _journal_transition(
                transaction, dependencies.journal, phase=f"{name}_completed"
            )
        dependencies.clear_maintenance()
        _journal_transition(
            transaction,
            dependencies.journal,
            phase="maintenance_released",
            status="committed",
        )
        return pages_result
    except Exception as exc:
        failed_stage = attempted[-1] if attempted else "transaction"
        transaction["failed_stage"] = failed_stage
        transaction["failure_type"] = type(exc).__name__
        transaction["failure_detail"] = _safe_failure_detail(exc)
        rollback_failures: list[str] = []
        streamlined = transaction.get("execution_profile") == "streamlined"
        if not streamlined:
            try:
                dependencies.enable_maintenance()
            except Exception:
                rollback_failures.append("maintenance_enable")
        try:
            _journal_transition(
                transaction,
                dependencies.journal,
                phase="rolling_back",
                status="rolling_back",
            )
        except Exception:
            rollback_failures.append("journal")
        compensation = {
            "pages": dependencies.rollback_pages,
            "worker": dependencies.rollback_worker,
            "cloud": dependencies.rollback_cloud,
        }
        for name in ("pages", "worker", "cloud"):
            if name not in attempted:
                continue
            try:
                compensation[name]()
            except Exception:
                rollback_failures.append(name)
        if rollback_failures:
            if streamlined:
                try:
                    dependencies.enable_maintenance()
                except Exception:
                    rollback_failures.append("maintenance_enable")
            transaction["rollback_failures"] = rollback_failures
            _journal_transition(
                transaction,
                dependencies.journal,
                phase="rollback_failed",
                status="rollback_failed",
            )
            raise ReleaseError(
                "release failed and rollback incomplete; maintenance remains enabled; "
                f"failed_stage={failed_stage}; detail={transaction['failure_detail']}"
            ) from exc
        try:
            dependencies.validate_recovery()
            _journal_transition(
                transaction,
                dependencies.journal,
                phase="recovery_verified_maintenance_held",
                status="rolling_back",
            )
            dependencies.clear_maintenance()
        except Exception as recovery_exc:
            if streamlined:
                try:
                    dependencies.enable_maintenance()
                except Exception:
                    pass
            transaction["rollback_failures"] = ["recovery_validation"]
            _journal_transition(
                transaction,
                dependencies.journal,
                phase="rollback_failed",
                status="rollback_failed",
            )
            raise ReleaseError(
                "release failed and rollback incomplete; maintenance remains enabled; "
                f"failed_stage={failed_stage}; detail={transaction['failure_detail']}"
            ) from recovery_exc
        _journal_transition(
            transaction,
            dependencies.journal,
            phase="recovery_verified",
            status="rolled_back",
        )
        raise ReleaseError(
            "release failed and was recovered to the previous stack; "
            f"failed_stage={failed_stage}; detail={transaction['failure_detail']}"
        ) from exc


def recover_release_transaction(
    transaction: dict[str, Any],
    dependencies: ReleaseTransactionDependencies,
) -> None:
    """Idempotently compensate a persisted transaction; never resume it forward."""

    if transaction.get("status") == "committed":
        raise ReleaseError(
            "a committed transaction cannot be recovered forward or backward"
        )
    if transaction.get("status") == "rolled_back":
        try:
            dependencies.validate_recovery()
            dependencies.clear_maintenance()
        except Exception as exc:
            _journal_transition(
                transaction,
                dependencies.journal,
                phase="rollback_failed",
                status="rollback_failed",
            )
            raise ReleaseError(
                "recovered transaction validation failed; maintenance remains enabled"
            ) from exc
        _journal_transition(
            transaction,
            dependencies.journal,
            phase="recovery_verified",
            status="rolled_back",
        )
        return

    attempted = transaction.get("attempted_stages")
    if not isinstance(attempted, list):
        raise ReleaseError("transaction attempted_stages is invalid")
    compensation = {
        "pages": dependencies.rollback_pages,
        "worker": dependencies.rollback_worker,
        "cloud": dependencies.rollback_cloud,
    }
    try:
        dependencies.enable_maintenance()
    except Exception as exc:
        transaction["rollback_failures"] = ["maintenance_enable"]
        _journal_transition(
            transaction,
            dependencies.journal,
            phase="rollback_failed",
            status="rollback_failed",
        )
        raise ReleaseError("rollback incomplete; maintenance remains enabled") from exc
    _journal_transition(
        transaction,
        dependencies.journal,
        phase="rolling_back",
        status="rolling_back",
    )
    failures: list[str] = []
    for name in ("pages", "worker", "cloud"):
        if name not in attempted:
            continue
        try:
            compensation[name]()
        except Exception:
            failures.append(name)
    if not failures:
        try:
            dependencies.validate_recovery()
            _journal_transition(
                transaction,
                dependencies.journal,
                phase="recovery_verified_maintenance_held",
                status="rolling_back",
            )
            dependencies.clear_maintenance()
        except Exception:
            failures.append("recovery_validation")
    if failures:
        transaction["rollback_failures"] = failures
        _journal_transition(
            transaction,
            dependencies.journal,
            phase="rollback_failed",
            status="rollback_failed",
        )
        raise ReleaseError("rollback incomplete; maintenance remains enabled")
    _journal_transition(
        transaction,
        dependencies.journal,
        phase="recovery_verified",
        status="rolled_back",
    )


def _transaction_path(
    environment: str,
    transaction_id: str,
    track: str | None = None,
) -> str:
    validate_full_sha(transaction_id)
    track_segment = f"{track}/" if track in RELEASE_TRACKS else ""
    return (
        f"/var/lib/allbot/deployments/{environment}/transactions/"
        f"{track_segment}{transaction_id}.json"
    )


def _transaction_state_path(
    environment: str,
    transaction_id: str,
    track: str | None = None,
) -> str:
    validate_full_sha(transaction_id)
    track_segment = f"{track}/" if track in RELEASE_TRACKS else ""
    return (
        f"/var/lib/allbot/deployments/{environment}/transactions/"
        f"{track_segment}{transaction_id}.state.json"
    )


NON_SECRET_TRANSACTION_AUDIT_FIELDS = frozenset(
    {"pending_secret_rotation_acceptance"}
)


def _assert_secret_free_transaction(value: Any, *, path: str = "transaction") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized not in NON_SECRET_TRANSACTION_AUDIT_FIELDS and any(
                marker in normalized
                for marker in ("token", "secret", "password", "env_values")
            ):
                raise ReleaseError(
                    f"transaction journal contains forbidden field: {path}.{key}"
                )
            _assert_secret_free_transaction(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_secret_free_transaction(child, path=f"{path}[{index}]")
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ReleaseError(f"transaction journal contains unsupported value at {path}")


def _write_transaction_journal(
    args: argparse.Namespace, transaction: Mapping[str, Any]
) -> None:
    _assert_secret_free_transaction(transaction)
    transaction_id = str(transaction.get("transaction_id", ""))
    track = transaction.get("track")
    path = _transaction_path(
        args.env,
        transaction_id,
        str(track) if track in RELEASE_TRACKS else None,
    )
    payload = (
        json.dumps(transaction, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    host = args.remote_host or ENVIRONMENT[args.env]["host"]
    command = (
        f"set -e; install -d -m 755 {shlex.quote(str(Path(path).parent))}; "
        f"cat > {shlex.quote(path + '.tmp')}; "
        f"mv -f {shlex.quote(path + '.tmp')} {shlex.quote(path)}"
    )
    _run(["ssh", "-o", "BatchMode=yes", host, command], input_text=payload)


def _read_transaction_journal(
    args: argparse.Namespace, transaction_id: str
) -> dict[str, Any]:
    requested_track = getattr(args, "track", None)
    paths = [
        _transaction_path(
            args.env,
            transaction_id,
            requested_track if requested_track in RELEASE_TRACKS else None,
        )
    ]
    if requested_track in RELEASE_TRACKS:
        paths.append(_transaction_path(args.env, transaction_id))
    host = args.remote_host or ENVIRONMENT[args.env]["host"]
    result = None
    for path in paths:
        candidate = _run(
            ["ssh", "-o", "BatchMode=yes", host, f"cat {shlex.quote(path)}"],
            check=False,
        )
        if candidate.returncode == 0:
            result = candidate
            break
    if result is None:
        raise ReleaseError("release transaction journal is unavailable")
    try:
        transaction = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ReleaseError("release transaction journal is invalid") from exc
    if (
        not isinstance(transaction, dict)
        or transaction.get("schema_version") not in {1, 2}
        or transaction.get("environment") != args.env
        or transaction.get("transaction_id") != transaction_id
        or (
            requested_track in RELEASE_TRACKS
            and transaction.get("track") not in {None, requested_track}
        )
    ):
        raise ReleaseError("release transaction journal identity is invalid")
    _assert_secret_free_transaction(transaction)
    return transaction


def load_structured_file(path: Path) -> dict[str, Any]:
    """Load JSON-compatible YAML without making PyYAML a host prerequisite."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"invalid structured file: {path}") from exc
    if not isinstance(value, dict):
        raise ReleaseError(f"structured file must contain an object: {path}")
    return value


def load_promote_policy(path: Path, target_sha: str) -> dict[str, Any]:
    """Load the daily-promotion policy from the immutable candidate revision.

    Daily promotion may be invoked from a checkout that is behind the selected
    main bundle.  The policy that authorizes reviewed contract snapshots must
    therefore travel with that bundle, rather than with the caller's checkout.
    """

    resolved_path = path.resolve()
    if resolved_path != DEFAULT_POLICY.resolve():
        return load_structured_file(resolved_path)
    target_sha = validate_full_sha(target_sha)
    relative_path = resolved_path.relative_to(ROOT).as_posix()
    result = _run(["git", "show", f"{target_sha}:{relative_path}"], check=False)
    if result.returncode != 0:
        raise ReleaseError("candidate release policy is unavailable")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ReleaseError("candidate release policy is invalid") from exc
    if not isinstance(value, dict):
        raise ReleaseError("candidate release policy must contain an object")
    return value


def validate_release_policy_environment(
    policy: Mapping[str, Any], environment: str
) -> None:
    policy_environment = policy.get("environment")
    if policy_environment is None:
        return
    if policy_environment not in ENVIRONMENT:
        raise ReleaseError(
            f"release policy declares unsupported environment: {policy_environment}"
        )
    if policy_environment != environment:
        raise ReleaseError(
            f"release policy is only valid for {policy_environment}, not {environment}"
        )


def _matches(path: str, patterns: Sequence[str]) -> bool:
    normalized = path.removeprefix("./")
    return any(fnmatch.fnmatchcase(normalized, pattern) for pattern in patterns)


def plan_changed_paths(
    policy: Mapping[str, Any], paths: Iterable[str]
) -> ReleaseImpact:
    levels = list(policy.get("level_order", []))
    if not levels:
        raise ReleaseError("release policy has no level_order")
    level_index = {name: index for index, name in enumerate(levels)}
    all_services = set(policy.get("all_services", []))
    services: set[str] = set()
    blockers: set[str] = set()
    unknown_paths: list[str] = []
    matched_rules: list[str] = []
    highest_level = "none"
    requires_db_upgrade = False

    for changed_path in dict.fromkeys(str(path) for path in paths):
        path_matched = False
        for rule in policy.get("rules", []):
            if not _matches(changed_path, rule.get("patterns", [])):
                continue
            path_matched = True
            name = str(rule.get("name", "unnamed"))
            if name not in matched_rules:
                matched_rules.append(name)
            rule_services = rule.get("services", [])
            services.update(all_services if rule_services == "all" else rule_services)
            blockers.update(rule.get("blockers", []))
            requires_db_upgrade = bool(
                requires_db_upgrade or rule.get("requires_db_upgrade", False)
            )
            rule_level = str(rule.get("level", "none"))
            if rule_level not in level_index:
                raise ReleaseError(f"unknown release level in policy: {rule_level}")
            if level_index[rule_level] > level_index[highest_level]:
                highest_level = rule_level
        if not path_matched:
            unknown_paths.append(changed_path)

    if unknown_paths:
        fallback = policy.get("unknown", {})
        fallback_services = fallback.get("services", "all")
        services.update(
            all_services if fallback_services == "all" else fallback_services
        )
        fallback_level = str(fallback.get("level", "maintenance"))
        if level_index[fallback_level] > level_index[highest_level]:
            highest_level = fallback_level

    return ReleaseImpact(
        services=services,
        level=highest_level,
        requires_db_upgrade=requires_db_upgrade,
        blockers=blockers,
        unknown_paths=unknown_paths,
        matched_rules=matched_rules,
    )


def plan_dashboard_fast_track(paths: Iterable[str]) -> ReleaseImpact:
    """Build a fail-closed production plan for Dashboard-only releases."""

    services: set[str] = set()
    rejected: list[str] = []
    for raw_path in dict.fromkeys(str(path) for path in paths):
        path = raw_path.removeprefix("./")
        if _matches(path, DASHBOARD_FAST_TRACK_BACKEND_PATTERNS):
            services.add("dashboard-backend")
        elif _matches(path, DASHBOARD_FAST_TRACK_FRONTEND_PATTERNS):
            services.add("dashboard-frontend")
        elif not _matches(path, DASHBOARD_FAST_TRACK_METADATA_PATTERNS):
            rejected.append(path)
    if rejected:
        raise ReleaseError(
            "dashboard fast-track rejects non-Dashboard paths: "
            + ", ".join(sorted(rejected))
        )
    if not services:
        raise ReleaseError("dashboard fast-track has no Dashboard runtime changes")
    return ReleaseImpact(
        services=services,
        level="rolling",
        matched_rules=["dashboard-fast-track"],
    )


def plan_control_plane_repair_fast_track(paths: Iterable[str]) -> ReleaseImpact:
    """Allow only the private-worker image closure repair and release metadata."""

    runtime_paths: set[str] = set()
    rejected: list[str] = []
    for raw_path in dict.fromkeys(str(path) for path in paths):
        path = raw_path.removeprefix("./")
        if path in CONTROL_PLANE_REPAIR_FAST_TRACK_RUNTIME_PATHS:
            runtime_paths.add(path)
        elif not _matches(path, CONTROL_PLANE_REPAIR_FAST_TRACK_METADATA_PATTERNS):
            rejected.append(path)
    if rejected:
        raise ReleaseError(
            "control-plane repair fast-track rejects paths outside the image "
            "closure repair: " + ", ".join(sorted(rejected))
        )
    if runtime_paths != CONTROL_PLANE_REPAIR_FAST_TRACK_RUNTIME_PATHS:
        raise ReleaseError(
            "control-plane repair fast-track requires both private image closure changes"
        )
    return ReleaseImpact(
        level="maintenance",
        matched_rules=["control-plane-repair-fast-track"],
    )


def _dockerfile_target_section(dockerfile: str, target: str) -> str:
    marker = re.compile(
        rf"^FROM\s+.+\s+AS\s+{re.escape(target)}\s*$", re.MULTILINE
    ).search(dockerfile)
    if marker is None:
        raise ReleaseError(f"Dockerfile target is unavailable: {target}")
    next_stage = re.compile(r"^FROM\s+", re.MULTILINE).search(dockerfile, marker.end())
    end = next_stage.start() if next_stage else len(dockerfile)
    return dockerfile[marker.start() : end].strip()


def _dockerfile_global_preamble(dockerfile: str) -> str:
    first_stage = re.compile(r"^FROM\s+", re.MULTILINE).search(dockerfile)
    if first_stage is None:
        raise ReleaseError("control-plane Dockerfile has no build stage")
    return dockerfile[: first_stage.start()].strip()


def validate_control_plane_repair_equivalence(
    *,
    test_state: Mapping[str, Any],
    manifest: Mapping[str, Any],
    tested_artifact_catalog: Mapping[str, Mapping[str, Any]],
    target_artifact_catalog: Mapping[str, Mapping[str, Any]],
    changed_paths: Sequence[str],
    tested_dockerfile: str,
    target_dockerfile: str,
    smoke_private_image: Callable[[str], None],
) -> dict[str, Any]:
    """Prove that only the private worker runtime closure changed after test."""

    plan_control_plane_repair_fast_track(changed_paths)
    if (
        test_state.get("status") != "verified"
        or test_state.get("release_channel", "main") != "main"
        or test_state.get("track") != "control-plane"
    ):
        raise ReleaseError(
            "control-plane repair fast-track requires a verified main-channel test state"
        )
    tested_sha = validate_full_sha(str(test_state.get("git_sha", "")))
    target_sha = validate_full_sha(str(manifest.get("git_sha", "")))
    if tested_sha == target_sha:
        raise ReleaseError(
            "control-plane repair fast-track is unnecessary for the tested SHA"
        )
    if _dockerfile_global_preamble(tested_dockerfile) != _dockerfile_global_preamble(
        target_dockerfile
    ):
        raise ReleaseError(
            "control-plane Dockerfile global preamble changed after test"
        )
    selected = list(manifest.get("selected_artifacts", []))
    tested_artifacts = test_state.get("artifacts")
    if not isinstance(tested_artifacts, Mapping) or set(selected) != set(
        tested_artifacts
    ):
        raise ReleaseError(
            "control-plane repair fast-track requires the complete verified artifact set"
        )

    equivalent: list[str] = []
    smoked: list[str] = []
    for name in selected:
        tested = tested_artifacts.get(name)
        target = manifest.get("artifacts", {}).get(name)
        if (
            not isinstance(tested, Mapping)
            or tested.get("status") != "verified"
            or not isinstance(target, Mapping)
        ):
            raise ReleaseError(f"verified artifact metadata is invalid: {name}")
        target_digest = target.get("digest") or target.get("sha256")
        if tested.get("digest") == target_digest:
            equivalent.append(name)
            continue
        if name == "private-bot-worker":
            tested_spec = tested_artifact_catalog.get(name)
            target_spec = target_artifact_catalog.get(name)
            if not isinstance(tested_spec, Mapping) or not isinstance(
                target_spec, Mapping
            ):
                raise ReleaseError(
                    "private-bot-worker release catalog entry is unavailable"
                )
            tested_without_inputs = {
                key: value for key, value in tested_spec.items() if key != "inputs"
            }
            target_without_inputs = {
                key: value for key, value in target_spec.items() if key != "inputs"
            }
            tested_inputs = set(tested_spec.get("inputs", []))
            target_inputs = set(target_spec.get("inputs", []))
            if (
                tested_without_inputs != target_without_inputs
                or target_inputs != tested_inputs | {"qqcc_bot/**"}
            ):
                raise ReleaseError(
                    "private-bot-worker catalog change exceeds the qqcc_bot input closure"
                )
            tested_private_section = _dockerfile_target_section(
                tested_dockerfile, "private-bot-worker"
            )
            private_section = _dockerfile_target_section(
                target_dockerfile, "private-bot-worker"
            )
            runtime_copy = "COPY qqcc_bot /app/qqcc_bot"
            if private_section.count(runtime_copy) != 1:
                raise ReleaseError(
                    "private-bot-worker is missing the qqcc_bot runtime copy"
                )
            normalized_private_section = private_section.replace(
                runtime_copy + "\n", "", 1
            )
            if normalized_private_section != tested_private_section:
                raise ReleaseError(
                    "private-bot-worker Docker target change exceeds the qqcc_bot runtime copy"
                )
            ref = str(target.get("ref", ""))
            if not DIGEST_IMAGE_RE.fullmatch(ref):
                raise ReleaseError(
                    "private-bot-worker fast-track image is not digest-pinned"
                )
            smoke_private_image(ref)
            smoked.append(name)
            continue

        tested_spec = tested_artifact_catalog.get(name)
        spec = target_artifact_catalog.get(name)
        if (
            tested_spec != spec
            or not isinstance(spec, Mapping)
            or spec.get("kind") != "image"
            or spec.get("dockerfile") != "deploy/docker/Dockerfile.control-plane"
            or not str(spec.get("target", ""))
        ):
            raise ReleaseError(
                f"changed artifact cannot use control-plane repair fast-track: {name}"
            )
        inputs = spec.get("inputs", [])
        if any(_matches(path, inputs) for path in changed_paths):
            raise ReleaseError(
                f"{name} runtime inputs changed after the verified test release"
            )
        target_name = str(spec["target"])
        if _dockerfile_target_section(
            tested_dockerfile, target_name
        ) != _dockerfile_target_section(target_dockerfile, target_name):
            raise ReleaseError(f"{name} target changed after the verified test release")
        equivalent.append(name)

    if smoked != ["private-bot-worker"]:
        raise ReleaseError(
            "control-plane repair fast-track requires a changed private-bot-worker"
        )
    return {
        "tested_sha": tested_sha,
        "target_sha": target_sha,
        "equivalent_artifacts": sorted(equivalent),
        "smoked_artifacts": smoked,
    }


def merge_requested_services(
    *, computed: Iterable[str], requested: Iterable[str]
) -> set[str]:
    """Explicit service selection may widen, never narrow, automatic impact."""

    return set(computed) | set(requested)


def validate_full_sha(value: str) -> str:
    value = value.lower()
    if not FULL_SHA_RE.fullmatch(value):
        raise ReleaseError("release SHA must be a full 40-character lowercase Git SHA")
    return value


def resolve_latest_protected_main_sha() -> str:
    """Resolve one exact origin/main revision for a module release transaction."""

    fetched = _run(["git", "fetch", "--prune", "origin", "main"], check=False)
    if fetched.returncode != 0:
        raise ReleaseError("latest protected main revision is unavailable")
    result = _run(["git", "rev-parse", "--verify", "origin/main"], check=False)
    if result.returncode != 0:
        raise ReleaseError("latest protected main revision is unavailable")
    return validate_full_sha(result.stdout.strip())


def resolve_latest_promote_candidate(bundle_repository: str) -> str:
    """Lock the newest immutable main bundle without using a mutable tag."""

    fetched = _run(["git", "fetch", "--prune", "origin", "main"], check=False)
    if fetched.returncode != 0:
        raise ReleaseError("latest protected main revision is unavailable")
    head_result = _run(
        ["git", "rev-parse", "--verify", "origin/main"], check=False
    )
    if head_result.returncode != 0:
        raise ReleaseError("latest protected main revision is unavailable")
    main_head = validate_full_sha(head_result.stdout.strip())
    tags_result = _run(
        ["oras", "repo", "tags", bundle_repository], check=False
    )
    if tags_result.returncode != 0:
        raise ReleaseError("immutable main bundle tags are unavailable")
    bundle_shas = {
        value.strip()
        for value in tags_result.stdout.splitlines()
        if FULL_SHA_RE.fullmatch(value.strip())
    }
    history_result = _run(
        ["git", "rev-list", "--first-parent", main_head], check=False
    )
    if history_result.returncode != 0:
        raise ReleaseError("protected main history is unavailable")
    for candidate in history_result.stdout.splitlines():
        if candidate in bundle_shas:
            return validate_full_sha(candidate)
    raise ReleaseError("protected main has no immutable release bundle")


def resolve_promote_artifact_assurance(
    artifacts: Iterable[str],
) -> dict[str, dict[str, str]]:
    """Return the fixed daily-promotion strategy for each runtime artifact."""

    return {
        name: {
            "strategy": "direct" if name in PROMOTE_DIRECT_ARTIFACTS else "standard",
            "assurance": "waived" if name in PROMOTE_DIRECT_ARTIFACTS else "tested",
        }
        for name in sorted(set(artifacts))
    }


def inspect_promote_runtime_artifacts(
    args: argparse.Namespace,
) -> dict[str, dict[str, str]]:
    """Read actual AllBot production container identity without exposing env."""

    project = ENVIRONMENT["prod"]["project"]
    lines = ["set -euo pipefail"]
    requested = getattr(args, "promote_target_artifacts", None)
    selected = set(requested) if isinstance(requested, (set, list, tuple)) else None
    for artifact, service in sorted(PROMOTE_ARTIFACT_SERVICE.items()):
        if selected is not None and artifact not in selected:
            continue
        lines.extend(
            [
                (
                    'ids="$(docker ps -q '
                    f"--filter label=com.docker.compose.project={shlex.quote(project)} "
                    f'--filter label=com.docker.compose.service={shlex.quote(service)})"'
                ),
                'set -- $ids; [ "$#" -le 1 ]',
                'if [ "$#" -eq 1 ]; then',
                '  id="$1"',
                "  image=\"$(docker inspect --format '{{.Config.Image}}' \"$id\")\"",
                "  started=\"$(docker inspect --format '{{.State.StartedAt}}' \"$id\")\"",
                "  health=\"$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \"$id\")\"",
                "  revision=\"$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \"$id\" | sed -n 's/^ALLBOT_CONFIG_REVISION=//p')\"",
                "  oci=\"$(docker image inspect --format '{{index .Config.Labels \"org.opencontainers.image.revision\"}}' \"$image\" 2>/dev/null || true)\"",
                (
                    "  printf '%s\\t%s\\t%s\\t%s\\t%s\\t%s\\t%s\\n' "
                    f"{shlex.quote(artifact)} \"$id\" \"$image\" \"$started\" \"$health\" \"$revision\" \"$oci\""
                ),
                "fi",
            ]
        )
    host = args.remote_host or ENVIRONMENT["prod"]["host"]
    result = _run(
        ["ssh", "-o", "BatchMode=yes", host, "bash -s"],
        input_text="\n".join(lines) + "\n",
        check=False,
    )
    if result.returncode:
        raise ReleaseError("production runtime identity inspection failed")
    observed: dict[str, dict[str, str]] = {}
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) != 7 or fields[0] not in PROMOTE_ARTIFACT_SERVICE:
            raise ReleaseError("production runtime identity output is invalid")
        (
            artifact,
            container_id,
            ref,
            started_at,
            health,
            config_revision,
            oci_revision,
        ) = fields
        observed[artifact] = {
            "container_id": container_id,
            "ref": ref,
            "digest": ref.rsplit("@", 1)[-1] if "@" in ref else "",
            "started_at": started_at,
            "health": health,
            "config_revision": config_revision,
            "oci_revision": oci_revision,
        }
    return observed


def resolve_automatic_promote_modules(
    args: argparse.Namespace,
) -> tuple[list[str], dict[str, dict[str, str]]]:
    """Map live production drift to complete public module aliases."""

    manifest_path = _resolve_manifest_path(args, allow_fetch=True)
    try:
        release = load_release_index(manifest_path, expected_sha=args.sha)
    except ManifestV2Error as exc:
        raise ReleaseError(str(exc)) from exc
    artifacts = release.manifests["control-plane"]["artifacts"]
    runtime = inspect_promote_runtime_artifacts(args)
    policy = (
        load_promote_policy(Path(args.policy), str(args.sha))
        if getattr(args, "command", None) == "promote"
        else load_structured_file(Path(args.policy))
    )
    modules = policy.get("independent_modules")
    if not isinstance(modules, Mapping):
        raise ReleaseError("independent module policy is invalid")
    current_state = _read_current_state(args, track_scoped=True)
    current_artifacts = (
        current_state.get("artifacts") if isinstance(current_state, Mapping) else {}
    )
    recorded_pages = (
        current_state.get("web_deployment")
        if isinstance(current_state, Mapping)
        else None
    )
    pages_current = ""
    if isinstance(recorded_pages, Mapping) and recorded_pages.get("deployment_id"):
        try:
            pages_current = _current_pages_deployment_id(args)
        except ReleaseError:
            pages_current = ""
    selected: list[str] = []
    for raw_name, raw_module in modules.items():
        if not isinstance(raw_module, Mapping) or not isinstance(
            raw_module.get("artifacts"), list
        ):
            raise ReleaseError("independent module policy is invalid")
        if raw_module.get("automatic", True) is False:
            continue
        differs = False
        for artifact_name in raw_module["artifacts"]:
            target = artifacts.get(artifact_name)
            if not isinstance(target, Mapping):
                raise ReleaseError(f"release bundle has no {artifact_name} artifact")
            target_identity = target.get("digest") or target.get("sha256")
            if artifact_name == "public-web":
                current = (
                    current_artifacts.get(artifact_name)
                    if isinstance(current_artifacts, Mapping)
                    else None
                )
                current_identity = (
                    current.get("digest") if isinstance(current, Mapping) else None
                )
                if (
                    not isinstance(recorded_pages, Mapping)
                    or pages_current != str(recorded_pages.get("deployment_id", ""))
                ):
                    current_identity = None
            else:
                current_identity = runtime.get(artifact_name, {}).get("digest")
            differs = differs or not target_identity or current_identity != target_identity
        if differs:
            selected.append(str(raw_name))
    return sorted(selected), runtime


def verify_promote_no_change(args: argparse.Namespace) -> dict[str, Any]:
    """Verify the complete live candidate before returning a no-change result."""

    manifest_path = _resolve_manifest_path(args, allow_fetch=True)
    manifest = _load_v2_track(
        manifest_path,
        sha=args.sha,
        track="control-plane",
        modules=[],
        select_all_when_empty=True,
    )
    validate_deploy_module_approval(manifest)
    validate_release_channel(manifest, environment="prod", purpose="promote")
    verify_git_release(
        args.sha,
        release_channel=manifest["release_channel"],
        source_ref=manifest["source_ref"],
    )
    verify_release_ci(manifest, args.sha)
    _values, config_revision, snapshot = _remote_runtime_env_snapshot(args)
    if snapshot.get("drift"):
        raise ReleaseError(
            "target host environment has unapplied drift; use config-plan/config-apply"
        )
    runtime = getattr(args, "promote_runtime_artifacts", {})
    unhealthy = sorted(
        name
        for name, state in runtime.items()
        if state.get("health") not in {"healthy", "running"}
    )
    if unhealthy:
        raise ReleaseError(
            "production target health is not exact: " + ", ".join(unhealthy)
        )
    service_revisions = snapshot.get("service_revisions", {})
    mismatched_config = sorted(
        name
        for name, state in runtime.items()
        if state.get("config_revision")
        and isinstance(service_revisions, Mapping)
        and service_revisions.get(name) != state.get("config_revision")
    )
    if mismatched_config:
        raise ReleaseError(
            "production target config revision is not exact: "
            + ", ".join(mismatched_config)
        )
    return {
        "status": "no-change",
        "candidate_sha": args.sha,
        "modules": [],
        "config_revision": config_revision,
        "health": "verified",
        "mutation": False,
    }


def verify_promote_selected_no_change(
    args: argparse.Namespace,
    manifest: Mapping[str, Any],
    runtime_snapshot: Mapping[str, Any],
    config_revision: str,
) -> dict[str, Any] | None:
    """Return no-change only when every explicitly selected target is live-exact."""

    runtime = getattr(args, "promote_runtime_artifacts", None)
    if not isinstance(runtime, Mapping):
        runtime = inspect_promote_runtime_artifacts(args)
        args.promote_runtime_artifacts = runtime
    current = getattr(args, "previous_state", None)
    current_artifacts = (
        current.get("artifacts") if isinstance(current, Mapping) else {}
    )
    service_revisions = runtime_snapshot.get("service_revisions", {})
    for name in manifest.get("selected_artifacts", []):
        target = manifest.get("artifacts", {}).get(name)
        if not isinstance(target, Mapping):
            return None
        expected = target.get("digest") or target.get("sha256")
        if name == "public-web":
            previous = (
                current_artifacts.get(name)
                if isinstance(current_artifacts, Mapping)
                else None
            )
            if not isinstance(previous, Mapping) or previous.get("digest") != expected:
                return None
            web = current.get("web_deployment") if isinstance(current, Mapping) else None
            if (
                not isinstance(web, Mapping)
                or not web.get("deployment_id")
                or _current_pages_deployment_id(args) != str(web["deployment_id"])
            ):
                return None
            continue
        observed = runtime.get(name)
        if (
            not isinstance(observed, Mapping)
            or observed.get("digest") != expected
            or observed.get("health") not in {"healthy", "running"}
        ):
            return None
        expected_revision = (
            service_revisions.get(name)
            if isinstance(service_revisions, Mapping)
            else None
        )
        if expected_revision and observed.get("config_revision") != expected_revision:
            return None
    return {
        "status": "no-change",
        "environment": "prod",
        "candidate_sha": manifest["git_sha"],
        "modules": sorted(_split_services(args.modules)),
        "config_revision": config_revision,
        "health": "verified",
        "mutation": False,
    }


def build_promote_previous_artifacts(
    args: argparse.Namespace,
    manifest: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Capture the real per-artifact rollback identity for a promotion."""

    runtime = getattr(args, "promote_runtime_artifacts", None)
    if not isinstance(runtime, Mapping):
        runtime = inspect_promote_runtime_artifacts(args)
        args.promote_runtime_artifacts = runtime
    current = getattr(args, "previous_state", None)
    current_artifacts = (
        current.get("artifacts") if isinstance(current, Mapping) else {}
    )
    result: dict[str, dict[str, Any]] = {}
    initial_artifacts = set(getattr(args, "promote_initial_artifacts", set()))
    for name in manifest.get("selected_artifacts", []):
        recorded = (
            current_artifacts.get(name)
            if isinstance(current_artifacts, Mapping)
            else None
        )
        if name == "public-web":
            web = current.get("web_deployment") if isinstance(current, Mapping) else None
            if not isinstance(recorded, Mapping) or not isinstance(web, Mapping):
                raise ReleaseError("public-web rollback identity is unavailable")
            result[name] = {
                "digest": recorded.get("digest"),
                "source_sha": recorded.get("source_sha"),
                "deployment_id": web.get("deployment_id"),
                "runtime_config_revision": web.get("runtime_config_revision"),
            }
            continue
        observed = runtime.get(name)
        if not isinstance(observed, Mapping) or not DIGEST_IMAGE_RE.fullmatch(
            str(observed.get("ref", ""))
        ):
            if name in initial_artifacts:
                result[name] = {"absent": True}
                continue
            raise ReleaseError(f"{name} rollback runtime identity is unavailable")
        source_sha = (
            str(recorded.get("source_sha", ""))
            if isinstance(recorded, Mapping)
            else ""
        )
        if not source_sha and FULL_SHA_RE.fullmatch(
            str(observed.get("oci_revision", ""))
        ):
            source_sha = str(observed["oci_revision"])
        if source_sha:
            validate_full_sha(source_sha)
        active_revision = _active_service_config_revision(args, name)
        result[name] = {
            "ref": observed["ref"],
            "digest": observed["digest"],
            "source_sha": source_sha or None,
            "oci_revision": observed.get("oci_revision") or None,
            "config_revision": active_revision
            or observed.get("config_revision")
            or None,
            "container_id": observed.get("container_id"),
            "started_at": observed.get("started_at"),
            "health": observed.get("health"),
        }
    return result


def _active_service_config_revision(
    args: argparse.Namespace, artifact_name: str
) -> str | None:
    """Return the revision that Compose will inject when recreating a service."""

    snapshot = getattr(args, "runtime_env_snapshot", None)
    revisions = (
        snapshot.get("service_revisions") if isinstance(snapshot, Mapping) else None
    )
    revision = revisions.get(artifact_name) if isinstance(revisions, Mapping) else None
    return str(revision) if revision else None


def render_promote_rollback_release_env(
    release_env: str,
    previous_artifacts: Mapping[str, Mapping[str, Any]],
) -> str:
    """Pin a transaction-local rollback contract to each observed old image."""

    lines = release_env.splitlines()
    replacements = {
        CONTROL_ARTIFACT_ENV[name]: str(value["ref"])
        for name, value in previous_artifacts.items()
        if name in CONTROL_ARTIFACT_ENV and value.get("ref")
    }
    rendered: list[str] = []
    for line in lines:
        key, separator, _value = line.partition("=")
        rendered.append(
            f"{key}={replacements[key]}" if separator and key in replacements else line
        )
    return "\n".join(rendered) + "\n"


def _prepare_promote_rollback_materials(
    args: argparse.Namespace,
    transaction: Mapping[str, Any],
    rollback_release_env: str,
) -> None:
    """Pull old exact refs and persist rollback contract after all read-only gates."""

    previous = transaction.get("previous")
    artifacts = previous.get("artifacts") if isinstance(previous, Mapping) else None
    path = (
        previous.get("rollback_release_env_path")
        if isinstance(previous, Mapping)
        else None
    )
    if not isinstance(artifacts, Mapping) or not isinstance(path, str):
        raise ReleaseError("promote rollback snapshot is invalid")
    image_refs = sorted(
        str(value["ref"])
        for value in artifacts.values()
        if isinstance(value, Mapping) and value.get("ref")
    )
    pulls = "".join(
        f"docker pull {shlex.quote(ref)} >/dev/null\n"
        f"docker image inspect {shlex.quote(ref)} >/dev/null\n"
        for ref in image_refs
    )
    encoded_env = base64.b64encode(rollback_release_env.encode()).decode("ascii")
    script = (
        "set -euo pipefail\n"
        + pulls
        + f"install -d -m 755 {shlex.quote(str(Path(path).parent))}\n"
        + f"umask 022; printf %s {encoded_env} | base64 -d > {shlex.quote(path + '.tmp')}\n"
        + f"mv -f {shlex.quote(path + '.tmp')} {shlex.quote(path)}\n"
    )
    host = args.remote_host or ENVIRONMENT["prod"]["host"]
    _run(
        ["ssh", "-o", "BatchMode=yes", host, "bash -s"],
        input_text=script,
    )


def validate_release_channel(
    manifest: Mapping[str, Any],
    *,
    environment: str,
    purpose: str,
    dashboard_fast_track: bool = False,
) -> tuple[str, str]:
    """Fail closed when a test-train bundle approaches a promotion seam."""

    channel = str(manifest.get("release_channel", "main"))
    source_ref = str(
        manifest.get(
            "source_ref",
            "refs/heads/main" if channel == "main" else "",
        )
    )
    expected = {
        "main": "refs/heads/main",
        "test-candidate": "refs/heads/codex/test-train",
    }
    if channel not in expected or source_ref != expected[channel]:
        raise ReleaseError("release channel or source_ref is invalid")
    if channel == "test-candidate":
        if environment == "prod":
            raise ReleaseError("test-candidate bundles are forbidden in production")
        if purpose == "verify-test":
            raise ReleaseError("test-candidate bundles cannot pass verify-test")
        if dashboard_fast_track:
            raise ReleaseError("test-candidate bundles cannot use Dashboard fast-track")
    return channel, source_ref


def validate_release_manifest(manifest: Mapping[str, Any], expected_sha: str) -> None:
    expected_sha = validate_full_sha(expected_sha)
    if manifest.get("schema_version") != 1:
        raise ReleaseError("release manifest schema_version must be 1")
    if manifest.get("git_sha") != expected_sha:
        raise ReleaseError("release manifest git_sha does not match requested SHA")
    images = manifest.get("images")
    if not isinstance(images, Mapping) or not REQUIRED_IMAGES <= set(images):
        missing = sorted(REQUIRED_IMAGES - set(images or {}))
        raise ReleaseError(
            "release manifest is missing image entries: " + ", ".join(missing)
        )
    mutable = sorted(
        name
        for name in REQUIRED_IMAGES
        if not DIGEST_IMAGE_RE.fullmatch(str(images[name]))
    )
    if mutable:
        raise ReleaseError(
            "release images must be digest-pinned (digest-pinned): "
            + ", ".join(mutable)
        )
    vendor_images = manifest.get("vendor_images")
    if not isinstance(vendor_images, Mapping) or not REQUIRED_VENDOR_IMAGES <= set(
        vendor_images
    ):
        missing = sorted(REQUIRED_VENDOR_IMAGES - set(vendor_images or {}))
        raise ReleaseError(
            "release manifest is missing vendor image entries: " + ", ".join(missing)
        )
    mutable_vendor = sorted(
        name
        for name in REQUIRED_VENDOR_IMAGES
        if not DIGEST_IMAGE_RE.fullmatch(str(vendor_images[name]))
    )
    if mutable_vendor:
        raise ReleaseError(
            "vendor images must be digest-pinned (digest-pinned): "
            + ", ".join(mutable_vendor)
        )
    web_hash = str(manifest.get("web_artifact_sha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", web_hash):
        raise ReleaseError("release manifest web_artifact_sha256 is invalid")
    if not str(manifest.get("ci_run", "")).startswith("https://github.com/"):
        raise ReleaseError(
            "release manifest ci_run must identify the successful CI run"
        )


def parse_env_text(text: str) -> dict[str, str]:
    lines = text.splitlines()
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ReleaseError(f"invalid environment assignment at line {line_number}")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ReleaseError(f"invalid environment key at line {line_number}")
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def parse_env_file(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReleaseError(f"environment file is unavailable: {path}") from exc
    return parse_env_text(text)


def validate_environment(
    schema: Mapping[str, Any], environment: str, values: Mapping[str, str]
) -> str:
    if environment not in schema.get("environments", {}):
        raise ReleaseError(f"unknown environment contract: {environment}")
    common = schema.get("common", {})
    environment_schema = schema["environments"][environment]
    required = list(common.get("required", [])) + list(
        environment_schema.get("required", [])
    )
    errors: list[str] = []
    missing = sorted(key for key in required if not values.get(key, "").strip())
    if missing:
        errors.append("missing required keys: " + ", ".join(missing))
    forbidden_values = {
        str(item).lower() for item in common.get("forbidden_values", [])
    }
    unsafe = sorted(
        key
        for key in required
        if values.get(key, "").strip().lower() in forbidden_values
    )
    if unsafe:
        errors.append("unsafe placeholder values: " + ", ".join(unsafe))
    for key, expected in environment_schema.get("expected", {}).items():
        if values.get(key) != expected:
            errors.append(f"{key} must match the {environment} contract")
    for key, forbidden in environment_schema.get("forbidden_values_by_key", {}).items():
        if values.get(key, "").strip().lower() in {
            str(item).lower() for item in forbidden
        }:
            errors.append(f"{key} uses a value forbidden by the {environment} contract")
    if environment == "prod":
        test_sentinel = re.compile(r"(?:^|[-_.:/])test(?:[-_.:/]|$)", re.IGNORECASE)
        contaminated = sorted(
            key
            for key, value in values.items()
            if value.strip()
            and (key.endswith("_TEST") or test_sentinel.search(value.strip()))
        )
        if contaminated:
            errors.append(
                "production contract contains test sentinel keys: "
                + ", ".join(contaminated)
            )
    types = schema.get("types", {})
    boolean_values = {"true", "false", "1", "0", "yes", "no"}
    for key in types.get("boolean", []):
        if key in values and values[key].strip().lower() not in boolean_values:
            errors.append(f"{key} must be a boolean")
    for key in types.get("integer", []):
        if key in values and not re.fullmatch(r"[0-9]+", values[key].strip()):
            errors.append(f"{key} must be a non-negative integer")
    for left, right in schema.get("forbidden_equal_pairs", []):
        if values.get(left) and values.get(left) == values.get(right):
            errors.append(f"{left} and {right} must use independent values")
    worker_schema = schema.get("worker", {})
    selection_key = str(worker_schema.get("selection_key", ""))
    worker_services = _split_services([values.get(selection_key, "")])
    if worker_services:
        worker_required = list(worker_schema.get("required_when_selected", []))
        for service in sorted(worker_services):
            match = re.fullmatch(r"worker-(0[1-8])", service)
            if not match:
                errors.append(f"{selection_key} contains an invalid worker slot")
                continue
            slot = match.group(1)
            worker_required.extend(
                str(template).format(slot=slot)
                for template in worker_schema.get("per_slot_required_templates", [])
            )
            for template in worker_schema.get("per_slot_boolean_templates", []):
                key = str(template).format(slot=slot)
                if key in values and values[key].strip().lower() not in boolean_values:
                    errors.append(f"{key} must be a boolean")
            for template in worker_schema.get("per_slot_integer_templates", []):
                key = str(template).format(slot=slot)
                if key in values and not re.fullmatch(r"[0-9]+", values[key].strip()):
                    errors.append(f"{key} must be a non-negative integer")
        missing_worker = sorted(
            key for key in worker_required if not values.get(key, "").strip()
        )
        if missing_worker:
            errors.append("missing worker keys: " + ", ".join(missing_worker))
    if errors:
        raise ReleaseError("; ".join(errors))
    digest_input = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


def render_release_env(manifest: Mapping[str, Any], config_revision: str) -> str:
    images = manifest["images"]
    vendor_images = manifest["vendor_images"]
    return "\n".join(
        (
            f"ALLBOT_RELEASE_SHA={manifest['git_sha']}",
            f"ALLBOT_CONFIG_REVISION={config_revision}",
            f"ALLBOT_APP_IMAGE={images['app']}",
            f"ALLBOT_CENTRAL_IMAGE={images['central']}",
            f"ALLBOT_DASHBOARD_BACKEND_IMAGE={images['dashboard_backend']}",
            f"ALLBOT_DASHBOARD_FRONTEND_IMAGE={images['dashboard_frontend']}",
            f"ALLBOT_WORKER_IMAGE={images['worker']}",
            f"ALLBOT_IMGPROXY_IMAGE={vendor_images['imgproxy']}",
            f"ALLBOT_POSTGRES_IMAGE={vendor_images['postgres']}",
            f"ALLBOT_REDIS_IMAGE={vendor_images['redis']}",
            "",
        )
    )


def render_track_release_env(
    manifest: Mapping[str, Any],
    config_revision: str,
    *,
    service_env_root: str | None = None,
    allow_legacy_missing_dashboard_profile_pins: bool = False,
) -> str:
    """Render only image variables owned by one schema-v2 track.

    The legacy-pin exception is restricted to rollback-material recovery. It
    lets an already deployed baseline from before the pin contract remain
    recoverable by projecting the old, unpinned behavior as an empty mapping;
    normal plan/preflight/deploy rendering stays strict.
    """

    track = str(manifest.get("track", ""))
    artifacts = manifest.get("artifacts", {})
    lines = [
        f"ALLBOT_RELEASE_SHA={manifest['source_sha']}",
        f"ALLBOT_CONFIG_REVISION={config_revision}",
        f"ALLBOT_RELEASE_TRACK={track}",
    ]
    if service_env_root:
        lines.append(f"ALLBOT_SERVICE_ENV_ROOT={service_env_root}")
    artifact_source_shas = {
        str(name): str(artifact.get("source_sha", manifest["source_sha"]))
        for name, artifact in artifacts.items()
        if isinstance(artifact, Mapping)
    }
    lines.append(
        "ALLBOT_ARTIFACT_SOURCE_SHAS_JSON="
        + json.dumps(artifact_source_shas, sort_keys=True, separators=(",", ":"))
    )
    promotion = manifest.get("promotion")
    if isinstance(promotion, Mapping) and promotion.get("candidate_sha"):
        lines.append("ALLBOT_PROMOTED_CANDIDATE_SHA=" + str(promotion["candidate_sha"]))
    if track == "control-plane":
        for name, variable in CONTROL_ARTIFACT_ENV.items():
            artifact = artifacts.get(name)
            if isinstance(artifact, Mapping) and artifact.get("kind") in {
                "image",
                "external-image",
            }:
                lines.append(f"{variable}={artifact['ref']}")
        pins = manifest.get("runpod_profile_pins", {})
        expected_pin_envs = set(PROFILE_IMAGE_ENV.values())
        dashboard_selected = "dashboard-backend" in manifest.get(
            "selected_artifacts", []
        )
        if (
            dashboard_selected
            and manifest.get("release_channel") == "main"
            and not allow_legacy_missing_dashboard_profile_pins
            and (
                not isinstance(pins, Mapping)
                or set(pins) != expected_pin_envs
                or any(
                    not isinstance(ref, str) or not DIGEST_IMAGE_RE.fullmatch(ref)
                    for ref in pins.values()
                )
            )
        ):
            raise ReleaseError(
                "main Dashboard release requires complete digest-pinned RunPod profile pins"
            )
        if isinstance(pins, Mapping) and pins:
            lines.append(
                "RUNPOD_RELEASE_PROFILE_PINS_JSON="
                + json.dumps(dict(pins), sort_keys=True, separators=(",", ":"))
            )
        elif allow_legacy_missing_dashboard_profile_pins:
            lines.append("RUNPOD_RELEASE_PROFILE_PINS_JSON={}")
    elif track == "test-execution":
        for name, variable in {
            "worker-agent": "ALLBOT_WORKER_AGENT_IMAGE",
            "worker-relay": "ALLBOT_WORKER_RELAY_IMAGE",
        }.items():
            artifact = artifacts.get(name)
            if isinstance(artifact, Mapping):
                lines.append(f"{variable}={artifact['ref']}")
    return "\n".join((*lines, ""))


_SSH_CONTROL_PATH: str | None = None
_SSH_CONTROL_HOSTS: set[str] = set()


def _ssh_destination(args: Sequence[str]) -> str | None:
    takes_value = {"-B", "-b", "-c", "-D", "-E", "-e", "-F", "-I", "-i", "-J", "-L", "-l", "-m", "-O", "-o", "-p", "-Q", "-R", "-S", "-W", "-w"}
    index = 1
    while index < len(args):
        value = str(args[index])
        if value in takes_value:
            index += 2
            continue
        if value.startswith("-"):
            index += 1
            continue
        return value
    return None


def _run(
    args: Sequence[str],
    *,
    cwd: Path = ROOT,
    input_text: str | None = None,
    env: Mapping[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = list(args)
    if command and command[0] == "ssh" and _SSH_CONTROL_PATH:
        destination = _ssh_destination(command)
        if destination:
            _SSH_CONTROL_HOSTS.add(destination)
        command[1:1] = [
            "-o",
            "ControlMaster=auto",
            "-o",
            "ControlPersist=30",
            "-o",
            f"ControlPath={_SSH_CONTROL_PATH}",
        ]
    process_env = None
    if env is not None:
        process_env = os.environ.copy()
        process_env.update(env)
    result = subprocess.run(
        command,
        cwd=cwd,
        input=input_text,
        env=process_env,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (
            result.stderr.strip().splitlines()[-1:]
            or result.stdout.strip().splitlines()[-1:]
        )
        raise ReleaseError("command failed: " + (detail[0] if detail else args[0]))
    return result


def _safe_failure_detail(error: BaseException | str) -> str:
    """Return one useful, bounded error line without echoing credential material."""

    raw = str(error).strip().splitlines()
    detail = raw[-1].strip() if raw else type(error).__name__
    if re.search(
        r"(?i)(authorization:|bearer\s+|password\s*=|token\s*=|secret\s*=|"
        r"postgres(?:ql)?://[^@\s]+@|redis://[^@\s]+@)",
        detail,
    ):
        return "remote command failed; sensitive detail redacted"
    return detail[:400] or type(error).__name__


def _run_with_progress(
    args: Sequence[str], *, input_text: str
) -> subprocess.CompletedProcess[str]:
    """Run a long command while streaming only explicit, non-secret phase markers."""

    command = list(args)
    if command and command[0] == "ssh" and _SSH_CONTROL_PATH:
        destination = _ssh_destination(command)
        if destination:
            _SSH_CONTROL_HOSTS.add(destination)
        command[1:1] = [
            "-o",
            "ControlMaster=auto",
            "-o",
            "ControlPersist=30",
            "-o",
            f"ControlPath={_SSH_CONTROL_PATH}",
        ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    process.stdin.write(input_text)
    process.stdin.close()
    output: dict[Any, list[str]] = {
        process.stdout: [],
        process.stderr: [],
    }
    streams = set(output)
    while streams:
        readable, _, _ = select.select(list(streams), [], [], 1.0)
        for stream in readable:
            line = stream.readline()
            if not line:
                streams.remove(stream)
                continue
            output[stream].append(line)
            if line.startswith("ALLBOT_PROGRESS:"):
                print(line.rstrip(), file=sys.stderr, flush=True)
    returncode = process.wait()
    return subprocess.CompletedProcess(
        command,
        returncode,
        stdout="".join(output[process.stdout]),
        stderr="".join(output[process.stderr]),
    )


def release_remote_branch(source_ref: str) -> str:
    prefix = "refs/heads/"
    if not source_ref.startswith(prefix):
        raise ReleaseError("release source_ref must identify a branch")
    branch = source_ref.removeprefix(prefix)
    if branch not in {"main", "codex/test-train"}:
        raise ReleaseError("release source_ref is not trusted")
    return branch


def verify_git_release(
    sha: str,
    *,
    release_channel: str = "main",
    source_ref: str = "refs/heads/main",
) -> None:
    validate_release_channel(
        {
            "release_channel": release_channel,
            "source_ref": source_ref,
        },
        environment="test",
        purpose="deploy",
    )
    branch = release_remote_branch(source_ref)
    remote_ref = f"origin/{branch}"
    _run(["git", "cat-file", "-e", f"{sha}^{{commit}}"])
    result = _run(
        ["git", "merge-base", "--is-ancestor", sha, remote_ref],
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseError(f"release SHA is not reachable from {remote_ref}")
    remote_refs = _run(["git", "branch", "-r", "--contains", sha]).stdout
    if remote_ref not in {line.strip() for line in remote_refs.splitlines()}:
        raise ReleaseError("release SHA has not been pushed to origin")


def verify_operator_worktree_clean(
    *,
    source_ref: str = "refs/heads/main",
    environment: str = "test",
    command: str = "deploy",
) -> None:
    if _run(["git", "status", "--porcelain"]).stdout.strip():
        raise ReleaseError("execute mode refuses an uncommitted operator worktree")
    head = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
    remote_refs = [f"origin/{release_remote_branch(source_ref)}"]
    # The integration checkout remains on test-train. A failed first candidate
    # may need to restore a main-channel bundle before any accepted candidate
    # exists, so narrowly allow that test-only rollback from the train checkout.
    if (
        environment == "test"
        and command == "rollback"
        and source_ref == "refs/heads/main"
    ):
        remote_refs.append("origin/codex/test-train")
    if all(
        _run(
            ["git", "merge-base", "--is-ancestor", head, remote_ref],
            check=False,
        ).returncode
        for remote_ref in remote_refs
    ):
        raise ReleaseError(
            "operator checkout must be clean and reachable from "
            + " or ".join(remote_refs)
        )


def verify_release_ci(manifest: Mapping[str, Any], sha: str) -> None:
    match = re.fullmatch(
        r"https://github\.com/giraffu/All_bot/actions/runs/([0-9]+)",
        str(manifest.get("ci_run", "")),
    )
    if not match:
        raise ReleaseError("release manifest CI run URL is not trusted")
    result = _run(
        [
            "gh",
            "run",
            "view",
            match.group(1),
            "--repo",
            "giraffu/All_bot",
            "--json",
            "conclusion,headBranch,headSha,status",
        ],
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseError("release CI status is unavailable")
    try:
        status = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ReleaseError("release CI status response is invalid") from exc
    if (
        status.get("status") != "completed"
        or status.get("conclusion") != "success"
        or status.get("headSha") != sha
    ):
        raise ReleaseError("release CI is incomplete, unsuccessful, or for another SHA")
    if (
        manifest.get("release_channel") == "test-candidate"
        and status.get("headBranch") != "codex/test-train"
    ):
        raise ReleaseError("test-candidate release CI used an untrusted source branch")


def git_changed_paths(from_sha: str | None, target_sha: str) -> list[str]:
    if from_sha:
        validate_full_sha(from_sha)
        output = _run(
            [
                "git",
                "diff",
                "--name-only",
                "-z",
                "--diff-filter=ACDMRT",
                from_sha,
                target_sha,
            ]
        ).stdout
        return [path for path in output.split("\0") if path]
    return []


def _target_first_parent_sha(target_sha: str) -> str:
    target_sha = validate_full_sha(target_sha)
    result = _run(
        ["git", "rev-parse", "--verify", f"{target_sha}^1"],
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseError(
            "dashboard fast-track target must have a verifiable first parent"
        )
    try:
        return validate_full_sha(result.stdout.strip())
    except ReleaseError as exc:
        raise ReleaseError(
            "dashboard fast-track target first parent is invalid"
        ) from exc


def _split_services(values: Sequence[str]) -> set[str]:
    selected: set[str] = set()
    for value in values:
        selected.update(item for item in re.split(r"[\s,]+", value) if item)
    return selected


def legacy_worker_containers(environment: str, selected: Iterable[str]) -> list[str]:
    if environment not in ENVIRONMENT:
        raise ReleaseError(f"unsupported worker environment: {environment}")
    slots = sorted(
        int(match.group(1))
        for service in selected
        if (match := re.fullmatch(r"worker-(0[1-8])", service))
    )
    if environment == "test":
        agent_prefix = "cloud-comfy-agent-test-"
        relay = "cloud-worker-relay-test"
    else:
        agent_prefix = "cloud-prod-comfy-agent-"
        relay = "cloud-prod-worker-relay"
    return [
        *(f"{agent_prefix}{slot}" for slot in slots),
        relay,
    ]


def cloud_services_for_release(environment: str, impact: ReleaseImpact) -> set[str]:
    selected = set(impact.services) & set(
        ENVIRONMENT[environment]["available_services"]
    )
    if (
        environment == "test"
        and "initial-release" in impact.matched_rules
        and "track:test-execution" not in impact.matched_rules
    ):
        # The legacy test stack owns PostgreSQL and Redis.  They must join the
        # first immutable handoff so the new project can reuse the existing
        # data volumes instead of starting against an empty network/volume.
        selected.update({"postgres", "redis"})
    return selected


def filter_enabled_cloud_services(
    environment: str,
    selected: Iterable[str],
    values: Mapping[str, str],
) -> tuple[set[str], set[str]]:
    """Remove only optional runtimes that the validated env leaves disabled."""

    chosen = set(selected)
    optional_enabled = {
        "qqcc-bot": bool(values.get("QQCC_BOT_TOKEN", "").strip()),
        "qqcc-private-bot-worker": values.get("PRIVATE_QQCC_BOT_ENABLED", "false")
        .strip()
        .lower()
        in {"1", "true", "yes", "on"},
        "paid-group-guard-bot": bool(values.get("PAID_GROUP_BOT_TOKEN", "").strip()),
        "support-bot": bool(values.get("SUPPORT_BOT_TOKEN", "").strip()),
    }
    disabled = {
        service
        for service, enabled in optional_enabled.items()
        if service in chosen and not enabled
    }
    return chosen - disabled, disabled


def disabled_optional_cloud_services(
    environment: str, values: Mapping[str, str]
) -> set[str]:
    """Return every optional runtime disabled in this environment.

    Runtime state describes the environment, not only the services selected by
    the current partial release.  Use the complete environment service catalog
    so a central-api-only deployment still prunes a disabled private worker.
    """

    _, disabled = filter_enabled_cloud_services(
        environment,
        ENVIRONMENT[environment]["available_services"],
        values,
    )
    return disabled


def filter_inactive_control_artifacts(
    environment: str,
    manifest: Mapping[str, Any],
    disabled_services: Iterable[str],
) -> tuple[dict[str, Any], set[str]]:
    """Remove artifacts that cannot represent a running service in this env."""

    filtered = dict(manifest)
    if manifest.get("schema_version") != 2 or manifest.get("track") != "control-plane":
        return filtered, set()
    artifacts = manifest.get("artifacts")
    selected = manifest.get("selected_artifacts")
    if not isinstance(artifacts, Mapping) or not isinstance(selected, list):
        raise ReleaseError("control-plane artifact selection is invalid")
    available = set(ENVIRONMENT[environment]["available_services"]) | {"web-static"}
    disabled = set(disabled_services)
    inactive = {
        str(name)
        for name in artifacts
        if (service := CONTROL_ARTIFACT_SERVICE.get(str(name), str(name)))
        not in available
        or service in disabled
    }
    filtered["selected_artifacts"] = [
        str(name) for name in selected if str(name) not in inactive
    ]
    return filtered, inactive


def legacy_cloud_containers(environment: str, selected: Iterable[str]) -> list[str]:
    suffix = "test" if environment == "test" else "prod"
    names = {
        "postgres": f"cloud-postgres-{suffix}",
        "redis": f"cloud-redis-{suffix}",
        "central-api": f"cloud-central-api-{suffix}",
        "web-api": f"cloud-web-api-{suffix}",
        "payment-api": f"cloud-payment-api-{suffix}",
        "dashboard-backend": f"cloud-dashboard-backend-{suffix}",
        "dashboard-frontend": f"cloud-dashboard-frontend-{suffix}",
        "qqcc-config-backend": f"cloud-qqcc-config-backend-{suffix}",
        "qqcc-config-frontend": f"cloud-qqcc-config-frontend-{suffix}",
        "imgproxy": f"cloud-imgproxy-{suffix}",
        "bot": f"cloud-tg-bot-{suffix}",
        "qqcc-bot": f"cloud-qqcc-bot-{suffix}",
        "qqcc-private-bot-worker": f"cloud-qqcc-private-bot-worker-{suffix}",
        "paid-group-guard-bot": f"cloud-paid-group-guard-bot-{suffix}",
        "support-bot": f"cloud-support-bot-{suffix}",
    }
    chosen = set(selected)
    return [name for service, name in names.items() if service in chosen]


def hold_maintenance_for_worker_cutover(
    environment: str, impact: ReleaseImpact
) -> bool:
    return (
        environment == "test"
        and impact.level == "maintenance"
        and "worker" in impact.services
    )


def maintenance_files(environment: str, *, initial_cutover: bool) -> list[str]:
    if environment not in ENVIRONMENT:
        raise ReleaseError(f"unsupported maintenance environment: {environment}")
    paths = [f"{ENVIRONMENT[environment]['state_root']}/runtime/GENERATION_MAINTENANCE"]
    if environment == "prod" and initial_cutover:
        paths.append(
            "/home/deploy/APP/All_bot/runtime/cloud-prod/GENERATION_MAINTENANCE"
        )
    return paths


def local_env_file(args: argparse.Namespace) -> Path:
    if args.env_file:
        return Path(args.env_file).expanduser()
    return Path.home() / ".config" / "allbot" / f"{args.env}.env"


def _token_file(path_value: str) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_file():
        raise ReleaseError(f"Cloudflare Pages token file is unavailable: {path}")
    if path.stat().st_mode & 0o077:
        raise ReleaseError("Cloudflare Pages token file permissions must be 600")
    if not path.read_text(encoding="utf-8").strip():
        raise ReleaseError("Cloudflare Pages token file is empty")
    return path


def _pages_api_request(
    args: argparse.Namespace,
    method: str,
    path: str,
    *,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    token_path = _token_file(args.cloudflare_token_file)
    token = token_path.read_text(encoding="utf-8").strip()
    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{args.cloudflare_account_id}/{path.lstrip('/')}"
    )
    data = None
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(dict(payload), sort_keys=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            document = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise ReleaseError("Cloudflare Pages API request failed") from exc
    if not isinstance(document, dict) or document.get("success") is not True:
        raise ReleaseError("Cloudflare Pages API response was unsuccessful")
    return document


def _plan_token_cache_root() -> Path:
    configured = os.environ.get("ALLBOT_RELEASE_PLAN_CACHE", "").strip()
    return (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".cache" / "allbot" / "release-plans"
    )


def _optional_file_sha256(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value).expanduser()
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plan_token_identity(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "environment": getattr(args, "env", None),
        "git_sha": getattr(args, "sha", None),
        "track": getattr(args, "track", None),
        "modules": sorted(_split_services(getattr(args, "modules", []))),
        "services": sorted(_split_services(getattr(args, "services", []))),
        "strategy": getattr(args, "strategy", "auto"),
        "skip_gates": sorted(getattr(args, "skip_gate", [])),
        "reason": getattr(args, "reason", "") or "",
        "skip_git_checks": bool(getattr(args, "skip_git_checks", False)),
        "skip_ci_checks": bool(getattr(args, "skip_ci_checks", False)),
        "skip_env_checks": bool(getattr(args, "skip_env_checks", False)),
        "dashboard_fast_track": bool(
            getattr(args, "dashboard_fast_track", False)
        ),
        "control_plane_repair_fast_track": bool(
            getattr(args, "control_plane_repair_fast_track", False)
        ),
        "repair_test_data_services": bool(
            getattr(args, "repair_test_data_services", False)
        ),
        "confirm_legacy_cutover": bool(
            getattr(args, "confirm_legacy_cutover", False)
        ),
        "manifest_input_sha256": _optional_file_sha256(
            getattr(args, "manifest", None)
        ),
        "web_artifact_sha256": _optional_file_sha256(
            getattr(args, "web_artifact", None)
        ),
        "policy_sha256": _optional_file_sha256(getattr(args, "policy", None)),
        "schema_sha256": _optional_file_sha256(getattr(args, "schema", None)),
    }


def _plan_token_path(token: str) -> Path:
    if not PLAN_TOKEN_RE.fullmatch(token):
        raise ReleaseError("plan token is invalid")
    return _plan_token_cache_root() / f"{token}.json"


def _write_plan_token_record(path: Path, record: Mapping[str, Any]) -> None:
    _assert_secret_free_transaction(record, path="plan")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    payload = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists():
        temporary = path.with_suffix(".json.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        descriptor = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                output.write(payload)
            temporary.chmod(0o600)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(payload)
    path.chmod(0o600)


def _create_plan_token(
    args: argparse.Namespace,
    *,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    previous_sha: str,
    config_revision: str,
    runtime_snapshot: Mapping[str, Any] | None,
) -> tuple[str, datetime]:
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=PLAN_TOKEN_TTL_SECONDS)
    token = "rp_" + secrets.token_urlsafe(32)
    web_artifact = _resolved_web_artifact(args, manifest)
    web_artifact_sha256 = (
        hashlib.sha256(web_artifact.read_bytes()).hexdigest()
        if "public-web" in manifest.get("selected_artifacts", [])
        and web_artifact.is_file()
        else None
    )
    record: dict[str, Any] = {
        "schema_version": 1,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "identity": _plan_token_identity(args),
        "impact": impact.as_dict(),
        "manifest": dict(manifest),
        "previous_sha": previous_sha or None,
        "config_revision": config_revision,
        "runtime_snapshot": (
            dict(runtime_snapshot) if isinstance(runtime_snapshot, Mapping) else None
        ),
        "resolved_web_artifact_sha256": web_artifact_sha256,
        "previous_state": (
            dict(args.previous_state)
            if isinstance(getattr(args, "previous_state", None), Mapping)
            else None
        ),
        "changed_paths": list(getattr(args, "changed_paths", [])),
        "promote_initial_artifacts": sorted(
            getattr(args, "promote_initial_artifacts", set())
        ),
        "preflight": None,
    }
    _write_plan_token_record(_plan_token_path(token), record)
    return token, expires_at


def _load_plan_token(args: argparse.Namespace, token: str) -> dict[str, Any]:
    path = _plan_token_path(token)
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise ReleaseError("plan token is unavailable or has unsafe permissions")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError("plan token record is invalid") from exc
    if not isinstance(record, dict) or record.get("schema_version") != 1:
        raise ReleaseError("plan token record is invalid")
    if record.get("identity") != _plan_token_identity(args):
        raise ReleaseError("plan token does not match the requested release")
    expires_at_value = record.get("expires_at")
    try:
        expires_at = datetime.fromisoformat(str(expires_at_value))
    except ValueError as exc:
        raise ReleaseError("plan token expiry is invalid") from exc
    if expires_at.tzinfo is None or expires_at <= datetime.now(timezone.utc):
        raise ReleaseError("plan token has expired")
    impact = record.get("impact")
    manifest = record.get("manifest")
    if not isinstance(impact, Mapping) or not isinstance(manifest, Mapping):
        raise ReleaseError("plan token record is incomplete")
    expected_web_checksum = record.get("resolved_web_artifact_sha256")
    if expected_web_checksum is not None:
        resolved_web = _resolved_web_artifact(args, manifest)
        if (
            not resolved_web.is_file()
            or hashlib.sha256(resolved_web.read_bytes()).hexdigest()
            != expected_web_checksum
        ):
            raise ReleaseError(
                "plan token Public Web artifact changed; run plan again"
            )
    _assert_secret_free_transaction(record, path="plan")
    return record


def _cache_plan_preflight(
    args: argparse.Namespace,
    token: str,
    preflight: Mapping[str, Any],
) -> None:
    if preflight.get("status") != "passed":
        raise ReleaseError("only a passed preflight can be cached")
    record = _load_plan_token(args, token)
    record["preflight"] = dict(preflight)
    record["preflight_cached_at"] = datetime.now(timezone.utc).isoformat()
    _write_plan_token_record(_plan_token_path(token), record)


def _impact_from_plan_token(record: Mapping[str, Any]) -> ReleaseImpact:
    raw = record.get("impact")
    if not isinstance(raw, Mapping):
        raise ReleaseError("plan token impact is invalid")
    return ReleaseImpact(
        services=raw.get("services", []),
        level=str(raw.get("level", "none")),
        requires_db_upgrade=bool(raw.get("requires_db_upgrade", False)),
        blockers=raw.get("blockers", []),
        unknown_paths=raw.get("unknown_paths", []),
        matched_rules=raw.get("matched_rules", []),
    )


def _operator_preflight(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    _environment_values: Mapping[str, str],
) -> list[str]:
    blockers: list[str] = []
    profile = getattr(args, "execution_profile", None)
    streamlined = isinstance(profile, ExecutionProfile) and profile.name == "streamlined"
    if not streamlined:
        env_path = local_env_file(args)
        if not env_path.is_file():
            blockers.append("operator-env-file-unavailable")
        elif env_path.stat().st_mode & 0o077:
            blockers.append("operator-env-file-permissions-not-600")
        if getattr(args, "local_env_error", False):
            blockers.append("operator-env-contract-invalid")
    if not args.skip_ci_checks and not (
        args.env == "prod"
        and getattr(args, "command", "") == "promote"
        and isinstance(profile, ExecutionProfile)
        and profile.name == "streamlined"
    ):
        try:
            verify_release_ci(manifest, str(manifest["git_sha"]))
        except ReleaseError:
            blockers.append("operator-release-ci-unavailable")
    try:
        if args.env == "prod":
            decision = getattr(args, "release_decision", None)
            promotion_required = (
                isinstance(decision, ReleaseStrategyDecision)
                and release_requires_test(decision)
            ) or (
                not isinstance(decision, ReleaseStrategyDecision)
                and not getattr(args, "dashboard_fast_track", False)
            )
            if promotion_required:
                _promotion_check(args, manifest)
        elif not streamlined:
            _test_rollback_check(args, manifest)
    except ReleaseError as exc:
        message = str(exc)
        if "marked verified" in message:
            blockers.append("promotion-test-release-not-verified")
        else:
            blockers.append("promotion-release-state-invalid")
    if "web-static" in impact.services and not args.skip_web:
        try:
            _token_file(args.cloudflare_token_file)
        except ReleaseError:
            blockers.append("operator-pages-token-invalid")
        artifact = _resolved_web_artifact(args, manifest)
        try:
            _verify_web_artifact(artifact, _manifest_web_checksum(manifest))
        except ReleaseError:
            blockers.append("operator-web-artifact-invalid")
    return blockers


def _cloud_preflight(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    environment_values: Mapping[str, str],
) -> list[str]:
    selected_cloud_services, _ = filter_enabled_cloud_services(
        args.env,
        cloud_services_for_release(args.env, impact),
        environment_values,
    )
    if not selected_cloud_services:
        return []
    environment = ENVIRONMENT[args.env]
    host = args.remote_host or environment["host"]
    root = args.remote_checkout_root
    env_file = args.remote_env_file or environment["env_file"]
    initial = "initial-release" in impact.matched_rules
    transaction_path = _transaction_path(
        args.env,
        str(manifest["git_sha"]),
        str(manifest.get("track")) if manifest.get("track") in RELEASE_TRACKS else None,
    )
    commit_object = str(manifest["git_sha"]) + "^{commit}"
    script = f"""set -u
test -d {shlex.quote(root)}/repo/.git || echo cloud-release-host-not-bootstrapped
if test -d {shlex.quote(root)}/repo/.git; then git -C {shlex.quote(root)}/repo cat-file -e {shlex.quote(commit_object)} 2>/dev/null || echo cloud-release-sha-unavailable; fi
test -f {shlex.quote(env_file)} || echo cloud-env-file-unavailable
if test -f {shlex.quote(env_file)}; then test "$(stat -c %a {shlex.quote(env_file)})" = 600 || echo cloud-env-file-permissions-not-600; fi
command -v git >/dev/null || echo cloud-git-unavailable
command -v docker >/dev/null || echo cloud-docker-unavailable
docker compose version >/dev/null 2>&1 || echo cloud-compose-v2-unavailable
test -f /home/deploy/.ssh/allbot_release_ed25519 || echo cloud-readonly-deploy-key-unavailable
test -f /home/deploy/.docker/config.json || echo cloud-ghcr-credentials-unavailable
if test -f {shlex.quote(transaction_path)} && ! grep -Eq '\"status\"[[:space:]]*:[[:space:]]*\"(committed|rolled_back)\"' {shlex.quote(transaction_path)}; then echo cloud-unfinished-release-transaction; fi
"""
    if (
        args.env == "prod"
        and "dashboard-backend" in selected_cloud_services
        and "dashboard-lan-runner-change" in impact.matched_rules
    ):
        runner_key = str(
            Path(environment_values["DASHBOARD_LAN_AIO_RUNNER_KEY_DIR"]) / "id_ed25519"
        )
        runner_host = environment_values["DASHBOARD_LAN_AIO_RUNNER_HOST"]
        runner_port = environment_values.get(
            "DASHBOARD_LAN_AIO_RUNNER_SSH_PORT",
            "2222",
        )
        runner_root = environment_values.get(
            "DASHBOARD_LAN_AIO_RUNNER_PROJECT_ROOT",
            "/home/hfy/APP/All_bot",
        )
        quoted_runner_key = shlex.quote(runner_key)
        runner_contract = " && ".join(
            f"test -r {shlex.quote(str(Path(runner_root) / path))}"
            for path in (
                "scripts/lan_aio_fleet_prod_ops.py",
                ".env.cloud.prod",
                ".env.lan.model-cache",
            )
        )
        script += (
            f"test -r {quoted_runner_key} || "
            "echo cloud-lan-aio-runner-key-unavailable\n"
            f"if test -f {quoted_runner_key}; then "
            f'test "$(stat -c %a {quoted_runner_key})" = 600 || '
            "echo cloud-lan-aio-runner-key-permissions-not-600; fi\n"
            f"if test -r {quoted_runner_key}; then "
            f"ssh -p {shlex.quote(runner_port)} -i {quoted_runner_key} "
            "-o BatchMode=yes -o ConnectTimeout=10 "
            "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
            f"{shlex.quote(runner_host)} {shlex.quote(runner_contract)} </dev/null "
            ">/dev/null 2>&1 || echo cloud-lan-aio-runner-unreachable; fi\n"
        )
    if args.env == "prod" and initial:
        script += (
            f"compgen -G {shlex.quote(root + '/legacy-prod-*')} >/dev/null "
            "|| echo cloud-legacy-archive-unavailable\n"
        )
    previous_sha = str(getattr(args, "previous_sha", "") or "")
    if not initial and FULL_SHA_RE.fullmatch(previous_sha):
        previous_release_envs = _cloud_release_env_candidates(
            previous_sha,
            str(manifest.get("track"))
            if manifest.get("track") in RELEASE_TRACKS
            else None,
        )
        missing_release_env = " && ".join(
            f"! test -f {shlex.quote(path)}" for path in previous_release_envs
        )
        script += (
            f"test -d {shlex.quote(root + '/releases/' + previous_sha)} "
            "|| echo cloud-rollback-checkout-unavailable\n"
            f"if {missing_release_env}; then "
            "echo cloud-rollback-release-env-unavailable; fi\n"
        )
    result = _run(
        ["ssh", "-o", "BatchMode=yes", host, "bash -s"],
        input_text=script,
        check=False,
    )
    if result.returncode != 0:
        return ["cloud-readonly-preflight-unavailable"]
    allowed = {
        "cloud-release-host-not-bootstrapped",
        "cloud-release-sha-unavailable",
        "cloud-env-file-unavailable",
        "cloud-env-file-permissions-not-600",
        "cloud-git-unavailable",
        "cloud-docker-unavailable",
        "cloud-compose-v2-unavailable",
        "cloud-readonly-deploy-key-unavailable",
        "cloud-ghcr-credentials-unavailable",
        "cloud-legacy-archive-unavailable",
        "cloud-unfinished-release-transaction",
        "cloud-rollback-checkout-unavailable",
        "cloud-rollback-release-env-unavailable",
        "cloud-lan-aio-runner-key-unavailable",
        "cloud-lan-aio-runner-key-permissions-not-600",
        "cloud-lan-aio-runner-unreachable",
    }
    return sorted({line.strip() for line in result.stdout.splitlines()} & allowed)


def _relay_container_owns_port(container: str, port: str) -> bool:
    probe = """import glob,os
port=int(os.environ['PORT'])
inodes=set()
for table in ('/proc/net/tcp','/proc/net/tcp6'):
    try:
        rows=open(table,encoding='ascii').read().splitlines()[1:]
    except OSError:
        continue
    for row in rows:
        fields=row.split()
        if int(fields[1].rsplit(':',1)[1],16)==port and fields[3]=='0A':
            inodes.add(fields[9])
owned=False
for fd in glob.glob('/proc/[0-9]*/fd/*'):
    try:
        target=os.readlink(fd)
    except OSError:
        continue
    if target.startswith('socket:[') and target[8:-1] in inodes:
        owned=True
        break
raise SystemExit(0 if owned else 1)
"""
    return (
        _run(
            ["docker", "exec", "-e", f"PORT={port}", container, "python", "-c", probe],
            check=False,
        ).returncode
        == 0
    )


def _worker_preflight(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    environment_values: Mapping[str, str],
) -> list[str]:
    if "worker" not in impact.services:
        return []
    blockers: list[str] = []
    root = Path(args.worker_checkout_root).expanduser()
    if not (root / "repo" / ".git").is_dir():
        blockers.append("worker-release-host-not-bootstrapped")
    env_path = local_env_file(args)
    if not env_path.is_file():
        blockers.append("worker-env-file-unavailable")
    selected = _split_services([environment_values.get("ALLBOT_WORKER_SERVICES", "")])
    if not selected:
        blockers.append("worker-service-allowlist-unavailable")
        return blockers
    initial = "initial-release" in impact.matched_rules
    expected_relay = ""
    if initial:
        expected_relay = legacy_worker_containers(args.env, selected)[-1]
        if _run(["docker", "inspect", expected_relay], check=False).returncode != 0:
            blockers.append("worker-legacy-relay-unavailable")
    else:
        result = _run(
            [
                "docker",
                "ps",
                "-q",
                "--filter",
                f"label=com.docker.compose.project=allbot-worker-{args.env}",
                "--filter",
                "label=com.docker.compose.service=worker-relay",
            ],
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            blockers.append("worker-immutable-relay-unavailable")
        elif result.stdout.splitlines():
            expected_relay = result.stdout.splitlines()[0].strip()
        previous_sha = str(getattr(args, "previous_sha", "") or "")
        if FULL_SHA_RE.fullmatch(previous_sha):
            if not (root / "releases" / previous_sha).is_dir():
                blockers.append("worker-rollback-checkout-unavailable")
            release_env_root = root / "release-env"
            if (
                manifest.get("schema_version") == 2
                and manifest.get("track") in RELEASE_TRACKS
            ):
                release_env_root /= str(manifest["track"])
            if not (release_env_root / previous_sha / "release.env").is_file():
                blockers.append("worker-rollback-release-env-unavailable")
    port = environment_values.get("ALLBOT_WORKER_RELAY_PORT", "").strip()
    if not port.isdigit():
        blockers.append("worker-relay-port-invalid")
    else:
        if not expected_relay or not _relay_container_owns_port(expected_relay, port):
            blockers.append("worker-relay-owner-mismatch")
        probe = _run(
            [
                "curl",
                "-fsS",
                "--max-time",
                "5",
                f"http://127.0.0.1:{port}/health",
            ],
            check=False,
        )
        if probe.returncode != 0 and "worker-relay-owner-mismatch" not in blockers:
            blockers.append("worker-relay-owner-mismatch")
    return blockers


def _pages_preflight(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    _manifest: Mapping[str, Any],
    _environment_values: Mapping[str, str],
) -> list[str]:
    if "web-static" not in impact.services or args.skip_web:
        return []
    target = WEB_PAGES_TARGETS[args.env]
    project_path = f"pages/projects/{target['project']}"
    try:
        project = _pages_api_request(args, "GET", project_path).get("result")
        domains = _pages_api_request(args, "GET", project_path + "/domains").get(
            "result"
        )
    except ReleaseError:
        return ["pages-readonly-preflight-unavailable"]
    if not isinstance(project, Mapping):
        return ["pages-project-invalid"]
    blockers: list[str] = []
    source = project.get("source")
    config = source.get("config") if isinstance(source, Mapping) else None
    if project.get("production_branch") != target["branch"]:
        blockers.append("pages-production-branch-mismatch")
    if not isinstance(config, Mapping):
        blockers.append("pages-source-config-unavailable")
    else:
        if config.get("production_deployments_enabled") is not False:
            blockers.append("pages-automatic-production-enabled")
        if config.get("preview_deployment_setting") != "none":
            blockers.append("pages-automatic-preview-enabled")
    canonical = project.get("canonical_deployment")
    if not isinstance(canonical, Mapping) or not canonical.get("id"):
        blockers.append("pages-canonical-deployment-unavailable")
    expected_domain = urllib.parse.urlparse(target["canonical_url"]).hostname
    active_domains = {
        str(item.get("name"))
        for item in domains or []
        if isinstance(item, Mapping) and item.get("status") == "active"
    }
    if expected_domain not in active_domains:
        blockers.append("pages-canonical-domain-inactive")
    return blockers


def _rollback_preflight(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    _manifest: Mapping[str, Any],
    _environment_values: Mapping[str, str],
) -> list[str]:
    if args.env != "prod":
        return []
    if getattr(args, "command", "") == "promote":
        runtime = getattr(args, "promote_runtime_artifacts", {})
        initial_artifacts = set(
            getattr(args, "promote_initial_artifacts", set())
        )
        blockers: list[str] = []
        for name in _manifest.get("selected_artifacts", []):
            if name == "public-web":
                state = getattr(args, "previous_state", None)
                web = state.get("web_deployment") if isinstance(state, Mapping) else None
                if not isinstance(web, Mapping) or not web.get("deployment_id"):
                    blockers.append("rollback-previous-web-deployment-unavailable")
            elif not isinstance(runtime.get(name), Mapping) or not DIGEST_IMAGE_RE.fullmatch(
                str(runtime[name].get("ref", ""))
            ):
                if name not in initial_artifacts:
                    blockers.append(f"rollback-{name}-runtime-unavailable")
        return blockers
    previous_sha = str(getattr(args, "previous_sha", "") or "")
    if "initial-release" in impact.matched_rules:
        return []
    if not FULL_SHA_RE.fullmatch(previous_sha):
        return ["rollback-previous-release-state-unavailable"]
    cache = Path(args.bundle_cache).expanduser() / previous_sha
    manifest_available = any(
        path.is_file()
        for path in (
            cache / "release.json",
            cache / "release" / "release.json",
            cache / "release-v2" / "release-index.json",
        )
    )
    web_available = any(
        path.is_file()
        for path in (
            cache / "web-dist.tgz",
            cache / "release" / "web-dist.tgz",
            cache / "release-v2" / "public-web-dist.tgz",
        )
    )
    blockers = []
    if not manifest_available:
        blockers.append("rollback-previous-manifest-unavailable")
    if "web-static" in impact.services and not web_available:
        blockers.append("rollback-previous-web-artifact-unavailable")
    return blockers


def _default_preflight_dependencies() -> PreflightDependencies:
    return PreflightDependencies(
        operator=_operator_preflight,
        cloud=_cloud_preflight,
        worker=_worker_preflight,
        pages=_pages_preflight,
        rollback=_rollback_preflight,
    )


def preflight_release(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    environment_values: Mapping[str, str],
    *,
    dependencies: PreflightDependencies | None = None,
) -> dict[str, Any]:
    dependencies = dependencies or _default_preflight_dependencies()
    decision = getattr(args, "release_decision", None)
    if not isinstance(decision, ReleaseStrategyDecision):
        decision = resolve_release_strategy(args, impact, manifest)
    impact_blockers = sorted(set(impact.blockers))
    checks: dict[str, dict[str, Any]] = {
        "impact": {
            "status": "blocked" if impact_blockers else "passed",
            "blockers": impact_blockers,
        }
    }
    blockers: list[str] = list(impact_blockers)
    profile = getattr(args, "execution_profile", None)
    streamlined = (
        isinstance(profile, ExecutionProfile) and profile.name == "streamlined"
    )
    for name in ("operator", "cloud", "worker", "pages", "rollback"):
        if name == "worker" and args.env == "prod":
            checks[name] = {"status": "skipped", "blockers": []}
            continue
        if streamlined and name in {"cloud", "rollback"}:
            checks[name] = {"status": "skipped", "blockers": []}
            continue
        check = getattr(dependencies, name)
        stage_blockers = sorted(set(check(args, impact, manifest, environment_values)))
        checks[name] = {
            "status": "blocked" if stage_blockers else "passed",
            "blockers": stage_blockers,
        }
        blockers.extend(stage_blockers)
    blockers = sorted(set(blockers))
    operator_passed = checks["operator"]["status"] == "passed"
    runtime_passed = all(
        checks[name]["status"] in {"passed", "skipped"}
        for name in ("cloud", "worker", "pages")
    )
    gate_statuses: dict[str, str] = {}
    for gate, requirement in decision.gates.items():
        if requirement == "not-applicable":
            continue
        if requirement in {"skipped", "forbidden"}:
            gate_statuses[gate] = requirement
            continue
        if gate == "production-confirmation":
            gate_statuses[gate] = (
                "passed"
                if args.env != "prod" or bool(getattr(args, "confirm_prod", False))
                else "required"
            )
        elif gate == "configuration-contract":
            gate_statuses[gate] = (
                "passed" if checks["cloud"]["status"] == "passed" else "required"
            )
        elif gate == "target-health":
            gate_statuses[gate] = "passed" if runtime_passed else "required"
        elif gate == "transaction-rollback":
            gate_statuses[gate] = (
                "passed" if checks["rollback"]["status"] == "passed" else "required"
            )
        else:
            gate_statuses[gate] = "passed" if operator_passed else "required"
    if decision.risk_class == "locked":
        gate_statuses["risk-bypass"] = "forbidden"
    return {
        "schema_version": 1,
        "environment": args.env,
        "git_sha": manifest["git_sha"],
        "status": "blocked" if blockers else "passed",
        "mutation_allowed": not blockers,
        "checks": checks,
        "gate_requirements": dict(decision.gates),
        "gates": gate_statuses,
        "risk_class": decision.risk_class,
        "strategy": decision.strategy,
        "validation_mode": decision.validation_mode,
        "skipped_gates": list(decision.skipped_gates),
        "execution_profile": profile.name if isinstance(profile, ExecutionProfile) else "strict",
        "execution_profile_reasons": (
            list(profile.reasons) if isinstance(profile, ExecutionProfile) else []
        ),
        "blockers": blockers,
    }


def require_preflight(report: Mapping[str, Any]) -> None:
    blockers = report.get("blockers")
    if blockers:
        raise ReleaseError("preflight blocked: " + ", ".join(map(str, blockers)))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"invalid JSON file: {path}") from exc
    if not isinstance(value, dict):
        raise ReleaseError(f"JSON file must contain an object: {path}")
    return value


def _resolve_manifest_path(
    args: argparse.Namespace, *, allow_fetch: bool = False
) -> Path:
    if args.manifest:
        return Path(args.manifest)
    cache = Path(args.bundle_cache).expanduser() / args.sha
    candidates = (
        cache / "release-index.json",
        cache / "release-v2" / "release-index.json",
        cache / "release" / "release-index.json",
        cache / "release.json",
        cache / "release" / "release.json",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    if not allow_fetch:
        raise ReleaseError(
            "release manifest is unavailable in the local bundle cache; "
            "preflight and deploy never pull release materials"
        )
    cache.mkdir(parents=True, exist_ok=True)
    reference = f"{args.bundle_repository}:{args.sha}"
    result = _run(["oras", "pull", reference, "-o", str(cache)], check=False)
    if result.returncode != 0:
        raise ReleaseError(
            "release manifest is unavailable; log in to GHCR/install oras or pass --manifest"
        )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ReleaseError(
        "release bundle does not contain release-index.json or release.json"
    )


def _load_v2_track(
    path: Path,
    *,
    sha: str,
    track: str,
    modules: Iterable[str],
    select_all_when_empty: bool = True,
) -> dict[str, Any]:
    try:
        release = load_release_index(path, expected_sha=sha)
        requested = list(modules)
        selected = (
            select_artifacts(release, track, requested)
            if requested or select_all_when_empty
            else {}
        )
    except ManifestV2Error as exc:
        raise ReleaseError(str(exc)) from exc
    runpod_profile_pins: dict[str, str] = {}
    gpu_manifest = release.manifests.get("gpu-execution", {})
    gpu_artifacts = gpu_manifest.get("artifacts", {})
    if isinstance(gpu_artifacts, Mapping):
        for profile, image_env in PROFILE_IMAGE_ENV.items():
            artifact = gpu_artifacts.get(profile)
            if not isinstance(artifact, Mapping):
                continue
            image_ref = artifact.get("ref")
            if not isinstance(image_ref, str) or not DIGEST_IMAGE_RE.fullmatch(
                image_ref
            ):
                raise ReleaseError(
                    f"GPU release artifact is not digest-pinned: {profile}"
                )
            existing = runpod_profile_pins.get(image_env)
            if existing is not None and existing != image_ref:
                raise ReleaseError(
                    f"GPU release artifacts conflict for RunPod image pin: {image_env}"
                )
            runpod_profile_pins[image_env] = image_ref
    document = {
        "schema_version": 2,
        "source_sha": sha,
        "git_sha": sha,
        "ci_run": release.index["ci_run"],
        "release_channel": release.index["release_channel"],
        "source_ref": release.index["source_ref"],
        "validation": dict(
            release.index.get("validation", {"mode": "full", "tests": "passed"})
        ),
        "track": track,
        "artifacts": release.manifests[track]["artifacts"],
        "selected_artifacts": list(selected),
        "release_index": str(path),
        "runpod_profile_pins": runpod_profile_pins,
    }
    promotion = release.index.get("promotion")
    approval = release.index.get("promotion_approval")
    if isinstance(promotion, Mapping):
        document["promotion"] = dict(promotion)
    if isinstance(approval, Mapping):
        document["promotion_approval"] = dict(approval)
    return document


def _read_current_state(
    args: argparse.Namespace, *, track_scoped: bool = False
) -> dict[str, Any] | None:
    if args.state_file:
        return _read_json(Path(args.state_file))
    track_segment = f"/{args.track}" if track_scoped else ""
    state_path = f"/var/lib/allbot/deployments/{args.env}{track_segment}/current.json"
    local_state = Path(state_path)
    if local_state.exists():
        return _read_json(local_state)
    host = args.remote_host or ENVIRONMENT[args.env]["host"]
    result = _run(
        ["ssh", "-o", "BatchMode=yes", host, f"cat {state_path}"],
        check=False,
    )
    if result.returncode == 0:
        try:
            state = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ReleaseError("remote deployment state is invalid") from exc
        if not isinstance(state, dict):
            raise ReleaseError("remote deployment state is invalid")
        return state
    return None


def _read_artifact_state_history(args: argparse.Namespace) -> list[dict[str, Any]]:
    track = str(args.track)
    history_root = Path(f"/var/lib/allbot/deployments/{args.env}/{track}/history")
    entries: list[tuple[float, str]] = []
    local = history_root
    if local.is_dir():
        entries = [
            (path.stat().st_mtime, str(path))
            for path in local.iterdir()
            if path.is_file() and re.fullmatch(r"[0-9a-f]{40}\.json", path.name)
        ]

        def read_state(path: str) -> dict[str, Any]:
            return _read_json(Path(path))
    else:
        host = args.remote_host or ENVIRONMENT[args.env]["host"]
        listing = _run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                host,
                (
                    f"find {shlex.quote(str(history_root))} -maxdepth 1 -type f "
                    "-regextype posix-extended "
                    "-regex '.*/[0-9a-f]{40}\\.json' -printf '%T@|%p\\n'"
                ),
            ],
            check=False,
        )
        if listing.returncode != 0:
            return []
        for raw_line in listing.stdout.splitlines():
            try:
                raw_mtime, path = raw_line.split("|", 1)
                mtime = float(raw_mtime)
            except (ValueError, TypeError):
                raise ReleaseError("deployment artifact history listing is invalid")
            candidate = Path(path)
            if candidate.parent != history_root or not re.fullmatch(
                r"[0-9a-f]{40}\.json", candidate.name
            ):
                raise ReleaseError("deployment artifact history path is invalid")
            entries.append((mtime, path))

        def read_state(path: str) -> dict[str, Any]:
            result = _run(
                [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    host,
                    f"cat {shlex.quote(path)}",
                ],
                check=False,
            )
            if result.returncode != 0:
                raise ReleaseError("deployment artifact history is unavailable")
            try:
                value = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise ReleaseError("deployment artifact history is invalid") from exc
            if not isinstance(value, dict):
                raise ReleaseError("deployment artifact history is invalid")
            return value

    return [read_state(path) for _, path in sorted(entries)]


def _resolve_previous_sha(
    args: argparse.Namespace, *, track_scoped: bool = False
) -> str | None:
    state = _read_current_state(args, track_scoped=track_scoped)
    args.previous_state = state
    if args.from_sha:
        return validate_full_sha(args.from_sha)
    if state:
        return validate_full_sha(str(state.get("git_sha", "")))
    return None


def runtime_drift_artifacts(
    target_artifacts: Mapping[str, Any],
    previous_state: Mapping[str, Any] | None,
    *,
    excluded: set[str],
) -> set[str]:
    """Select target artifacts whose recorded runtime identity is not current."""

    current_artifacts = (
        previous_state.get("artifacts") if isinstance(previous_state, Mapping) else None
    )
    selected: set[str] = set()
    for name, raw_target in target_artifacts.items():
        if name in excluded or not isinstance(raw_target, Mapping):
            continue
        target_identity = raw_target.get("digest") or raw_target.get("sha256")
        raw_current = (
            current_artifacts.get(name)
            if isinstance(current_artifacts, Mapping)
            else None
        )
        current_identity = (
            raw_current.get("digest") or raw_current.get("sha256")
            if isinstance(raw_current, Mapping)
            else None
        )
        if not target_identity or current_identity != target_identity:
            selected.add(str(name))
    return selected


def build_plan(args: argparse.Namespace) -> tuple[ReleaseImpact, dict[str, Any], str]:
    sha = validate_full_sha(args.sha)
    manifest_path = _resolve_manifest_path(
        args, allow_fetch=args.command in {"plan", "deploy-module", "promote"}
    )
    manifest_document = _read_json(manifest_path)
    policy = (
        load_promote_policy(Path(args.policy), sha)
        if getattr(args, "command", None) == "promote"
        else load_structured_file(Path(args.policy))
    )
    validate_release_policy_environment(policy, args.env)
    if manifest_document.get("schema_version") == 2:
        requested_modules = _split_services(args.modules)
        requested_services = _split_services(args.services)
        test_data_repair = bool(getattr(args, "repair_test_data_services", False))
        if test_data_repair:
            if args.env != "test" or args.track != "control-plane":
                raise ReleaseError(
                    "test data service repair is only available for the test control-plane"
                )
            if args.command not in {"plan", "preflight", "deploy"}:
                raise ReleaseError(
                    "test data service repair is only available for plan, preflight, or deploy"
                )
            if requested_modules or requested_services != {"postgres", "redis"}:
                raise ReleaseError(
                    "test data service repair requires exactly postgres and redis services"
                )
        dashboard_fast_track = bool(getattr(args, "dashboard_fast_track", False))
        repair_fast_track = bool(
            getattr(args, "control_plane_repair_fast_track", False)
        )
        if dashboard_fast_track:
            if args.env != "prod" or args.track != "control-plane":
                raise ReleaseError(
                    "dashboard fast-track is only available for the production control-plane"
                )
            if args.command not in {"plan", "preflight", "deploy", "rollback"}:
                raise ReleaseError(
                    "dashboard fast-track is only available for plan, preflight, deploy, or rollback"
                )
            if requested_modules or requested_services or args.from_sha:
                raise ReleaseError(
                    "dashboard fast-track does not accept module, service, or from-SHA overrides"
                )
        if repair_fast_track:
            if args.env != "prod" or args.track != "control-plane":
                raise ReleaseError(
                    "control-plane repair fast-track is only available for the production control-plane"
                )
            if args.command not in {"plan", "preflight", "deploy"}:
                raise ReleaseError(
                    "control-plane repair fast-track is only available for plan, preflight, or deploy"
                )
            if (
                requested_modules
                or requested_services
                or args.from_sha
                or getattr(args, "dashboard_fast_track", False)
            ):
                raise ReleaseError(
                    "control-plane repair fast-track does not accept module, service, from-SHA, or other fast-track overrides"
                )
        if requested_services and args.track != "control-plane":
            raise ReleaseError("--services is only an alias for control-plane modules")
        service_to_artifact = {
            service: artifact for artifact, service in CONTROL_ARTIFACT_SERVICE.items()
        }
        service_to_artifact.update(
            {
                name: name
                for name in CONTROL_ARTIFACT_ENV
                if name not in {"imgproxy", "postgres", "redis"}
            }
        )
        requested_modules.update(
            service_to_artifact.get(name, name) for name in requested_services
        )
        previous_sha = _resolve_previous_sha(args, track_scoped=True)
        expanded_independent = expand_independent_module_request(
            policy, requested_modules
        )
        if expanded_independent and isinstance(args.previous_state, Mapping):
            required_artifacts = expanded_independent[1]
            current_artifacts = args.previous_state.get("artifacts")
            missing_baselines = (
                required_artifacts
                if not isinstance(current_artifacts, Mapping)
                else required_artifacts - set(current_artifacts)
            )
            if missing_baselines and not args.state_file:
                args.previous_state = recover_artifact_current_state(
                    args.previous_state,
                    _read_artifact_state_history(args),
                )
        previous_state = getattr(args, "previous_state", None)
        repair_current_test_bundle = (
            expanded_independent is not None
            and expanded_independent[0] == "dashboard"
            and args.command == "recover"
            and bool(getattr(args, "repair_rollback_materials", False))
            and args.env == "test"
            and args.track == "control-plane"
            and isinstance(previous_state, Mapping)
            and previous_state.get("schema_version") == 2
            and previous_state.get("track") == "control-plane"
            and validate_full_sha(str(previous_state.get("git_sha", ""))) == sha
        )
        if repair_current_test_bundle:
            independent_release = IndependentModuleRelease(
                name=expanded_independent[0],
                artifacts=expanded_independent[1],
                previous_sha=sha,
                source_shas={sha},
            )
        else:
            independent_release = resolve_independent_module_release(
                policy,
                requested_modules,
                previous_state,
            )
        if independent_release:
            if args.track != "control-plane":
                raise ReleaseError(
                    "independent modules are only available on the control-plane track"
                )
            requested_modules = set(independent_release.artifacts)
            if args.from_sha:
                previous_sha = validate_full_sha(args.from_sha)
            else:
                previous_sha = independent_release.previous_sha
        planned_impact = ReleaseImpact(level="rolling")
        if not previous_sha and args.track == "test-execution":
            planned_impact.matched_rules.append("initial-release")
        changed_paths: list[str] = []
        comparison_shas = (
            {previous_sha}
            if independent_release and args.from_sha and previous_sha
            else independent_release.source_shas
            if independent_release
            else {previous_sha}
            if previous_sha
            else set()
        )
        if any(baseline != sha for baseline in comparison_shas):
            changed_paths = sorted(
                {
                    path
                    for baseline in comparison_shas
                    if baseline != sha
                    for path in git_changed_paths(baseline, sha)
                }
            )
            if independent_release:
                validate_independent_release_paths(
                    policy,
                    independent_release,
                    changed_paths,
                    target_sha=sha,
                )
                planned_impact = ReleaseImpact(
                    level="rolling",
                    matched_rules=[
                        f"independent-artifact-scope:{independent_release.name}"
                    ],
                )
                non_target_migrations = reviewed_non_target_migration_paths(
                    policy,
                    independent_release,
                    changed_paths,
                    target_sha=sha,
                )
                if non_target_migrations:
                    planned_impact.matched_rules.append(
                        "reviewed-non-target-migration"
                    )
                reviewed_migrations = reviewed_additive_migration_paths(
                    policy,
                    independent_release,
                    changed_paths,
                    target_sha=sha,
                )
                if reviewed_migrations:
                    planned_impact.requires_db_upgrade = True
                    planned_impact.matched_rules.append(
                        "reviewed-additive-migration"
                    )
            else:
                planned_impact = plan_changed_paths(policy, changed_paths)
        if dashboard_fast_track:
            if not previous_sha:
                raise ReleaseError(
                    "dashboard fast-track requires an existing production release"
                )
            target_parent_sha = _target_first_parent_sha(sha)
            planned_impact = plan_dashboard_fast_track(
                git_changed_paths(target_parent_sha, sha)
            )
        computed_modules: set[str] = set()
        if args.track == "control-plane":
            computed_modules = {
                service_to_artifact[service]
                for service in planned_impact.services
                if service in service_to_artifact
            }
        elif args.track == "test-execution" and "worker" in planned_impact.services:
            computed_modules = {"worker-agent", "worker-relay"}
        try:
            release_bundle = load_release_index(manifest_path, expected_sha=sha)
        except ManifestV2Error as exc:
            raise ReleaseError(str(exc)) from exc
        if not dashboard_fast_track and not independent_release:
            track_artifacts = release_bundle.manifests[args.track]["artifacts"]
            target_source_modules = {
                name
                for name, artifact in track_artifacts.items()
                if artifact.get("source_sha") == sha
                and name not in RUNTIME_BASE_ARTIFACTS
            }
            runtime_drift_modules = runtime_drift_artifacts(
                track_artifacts,
                getattr(args, "previous_state", None),
                excluded=NON_DEPLOYABLE_ARTIFACTS
                | (
                    {
                        name
                        for name in track_artifacts
                        if CONTROL_ARTIFACT_SERVICE.get(name, name)
                        not in ENVIRONMENT[args.env]["available_services"]
                        | {"web-static"}
                    }
                    if args.track == "control-plane"
                    else set()
                ),
            )
            if previous_sha:
                computed_modules.intersection_update(target_source_modules)
            computed_modules.update(target_source_modules)
            computed_modules.update(runtime_drift_modules)
        if not independent_release:
            requested_modules.update(computed_modules)
        manifest = _load_v2_track(
            manifest_path,
            sha=sha,
            track=args.track,
            modules=requested_modules,
            select_all_when_empty=not bool(previous_sha),
        )
        if args.command in {"deploy-module", "promote"}:
            validate_deploy_module_approval(manifest)
        validate_release_channel(
            manifest,
            environment=args.env,
            purpose=args.command,
            dashboard_fast_track=bool(getattr(args, "dashboard_fast_track", False)),
        )
        if not args.skip_git_checks:
            verify_git_release(
                sha,
                release_channel=manifest["release_channel"],
                source_ref=manifest["source_ref"],
            )
        if "gpu-runtime-release-required" in planned_impact.blockers:
            if args.track != "gpu-execution":
                planned_impact.blockers.remove("gpu-runtime-release-required")
            else:
                artifact_catalog = load_catalog(
                    ROOT / "deploy/release-artifacts-v2.json"
                )
                artifact_plan = plan_artifact_builds(
                    artifact_catalog, changed_paths, has_previous=True
                )
                required_gpu = {
                    name
                    for name in artifact_plan.build
                    if artifact_catalog[name]["track"] == "gpu-execution"
                }
                gpu_artifacts = release_bundle.manifests["gpu-execution"]["artifacts"]
                if required_gpu and all(
                    gpu_artifacts.get(name, {}).get("source_sha") == sha
                    for name in required_gpu
                ):
                    planned_impact.blockers.remove("gpu-runtime-release-required")
        artifact_names = set(manifest["selected_artifacts"])
        if args.track == "control-plane":
            services = {
                CONTROL_ARTIFACT_SERVICE.get(name, name)
                for name in artifact_names
                if name not in NON_DEPLOYABLE_ARTIFACTS
            }
        elif args.track == "test-execution":
            services = (
                {"worker"}
                if artifact_names & {"worker-agent", "worker-relay"}
                else set()
            )
        else:
            services = artifact_names
        if test_data_repair:
            services.update({"postgres", "redis"})
            planned_impact.level = "maintenance"
            for rule in ("initial-release", "test-data-service-repair"):
                if rule not in planned_impact.matched_rules:
                    planned_impact.matched_rules.append(rule)
        planned_impact.services = services
        apply_generation_maintenance(args.env, artifact_names, planned_impact)
        if repair_fast_track:
            test_state = _read_test_release_state(args, manifest)
            tested_sha = validate_full_sha(str(test_state.get("git_sha", "")))
            repair_impact = plan_control_plane_repair_fast_track(
                git_changed_paths(tested_sha, sha)
            )
            planned_impact.level = repair_impact.level
            planned_impact.blockers = repair_impact.blockers
            planned_impact.unknown_paths = repair_impact.unknown_paths
            planned_impact.matched_rules = repair_impact.matched_rules
        if f"track:{args.track}" not in planned_impact.matched_rules:
            planned_impact.matched_rules.append(f"track:{args.track}")
        if independent_release:
            args.promote_initial_artifacts = set(
                independent_release.initial_artifacts
            )
            planned_impact.matched_rules.append(
                f"independent-module:{independent_release.name}"
            )
            if independent_release.initial_artifacts:
                planned_impact.matched_rules.append("initial-artifact")
        args.changed_paths = list(changed_paths)
        if (
            "dashboard-backend" in planned_impact.services
            and dashboard_lan_runner_paths_changed(changed_paths)
            and "dashboard-lan-runner-change" not in planned_impact.matched_rules
        ):
            planned_impact.matched_rules.append("dashboard-lan-runner-change")
        scope_release_impact(args.env, planned_impact, requested=requested_services)
        structural_profile = resolve_execution_profile(
            planned_impact, manifest, {"drift": False}
        )
        if not args.skip_ci_checks and not (
            args.command == "promote" and structural_profile.name == "streamlined"
        ):
            verify_release_ci(manifest, sha)
        return planned_impact, manifest, previous_sha or ""

    if getattr(args, "control_plane_repair_fast_track", False):
        raise ReleaseError(
            "control-plane repair fast-track requires a schema v2 release bundle"
        )
    if args.track != "control-plane" or _split_services(args.modules):
        raise ReleaseError("release schema v1 supports only the control-plane track")
    manifest = manifest_document
    validate_release_manifest(manifest, sha)
    if not args.skip_git_checks:
        verify_git_release(sha)
    if args.command == "plan" and not args.skip_ci_checks:
        verify_release_ci(manifest, sha)
    previous_sha = _resolve_previous_sha(args)
    changed_paths: list[str] = []
    if previous_sha:
        changed_paths = git_changed_paths(previous_sha, sha)
        impact = plan_changed_paths(policy, changed_paths)
    else:
        impact = ReleaseImpact(
            services=policy["all_services"],
            level="maintenance",
            matched_rules=["initial-release"],
        )
    requested = _split_services(args.services)
    if getattr(args, "dashboard_fast_track", False):
        if args.env != "prod":
            raise ReleaseError("dashboard fast-track is only available for production")
        if args.command not in {"plan", "preflight", "deploy", "rollback"}:
            raise ReleaseError(
                "dashboard fast-track is only available for plan, preflight, deploy, or rollback"
            )
        if not previous_sha:
            raise ReleaseError(
                "dashboard fast-track requires an existing production release"
            )
        if requested:
            raise ReleaseError("dashboard fast-track does not accept --services")
        impact = plan_dashboard_fast_track(changed_paths)
    unknown_services = requested - set(policy["all_services"])
    if unknown_services:
        raise ReleaseError(
            "unknown requested services: " + ", ".join(sorted(unknown_services))
        )
    impact.services = merge_requested_services(
        computed=impact.services,
        requested=requested,
    )
    scope_release_impact(args.env, impact, requested=requested)
    return impact, manifest, previous_sha or ""


def scope_release_impact(
    environment: str,
    impact: ReleaseImpact,
    *,
    requested: set[str],
) -> None:
    if environment not in ENVIRONMENT:
        raise ReleaseError(f"unsupported release environment: {environment}")
    if environment != "prod":
        return
    if "worker" in requested:
        raise ReleaseError(
            "production GPU Worker releases must run independently on GPU hosts"
        )
    impact.services.discard("worker")


def apply_generation_maintenance(
    environment: str, artifacts: Iterable[str], impact: ReleaseImpact
) -> None:
    """Elevate one mixed transaction when any generation entry is replaced."""

    if environment != "prod" or not set(artifacts) & GENERATION_MAINTENANCE_ARTIFACTS:
        return
    impact.level = "maintenance"
    if "generation-entry-maintenance" not in impact.matched_rules:
        impact.matched_rules.append("generation-entry-maintenance")


def apply_user_authorized_no_maintenance(
    args: argparse.Namespace, impact: ReleaseImpact
) -> None:
    """Suppress planned maintenance for an explicitly selected prod module set.

    This changes only the forward rollout mode. Transaction compensation may
    still enable maintenance when a failed rollout cannot yet be proven safe.
    """

    if not getattr(args, "no_maintenance", False):
        return
    if args.command not in {"promote", "deploy"} or args.env != "prod":
        raise ReleaseError(
            "--no-maintenance is restricted to production promote/deploy"
        )
    if not _split_services(args.modules):
        raise ReleaseError("--no-maintenance requires explicit --modules")
    locked_rules = {
        "database-migrations",
        "deployment-contract",
        "initial-release",
        "test-data-service-repair",
    }
    reviewed_additive_migration = (
        "reviewed-additive-migration" in impact.matched_rules
    )
    if (
        (impact.requires_db_upgrade and not reviewed_additive_migration)
        or impact.blockers
        or impact.unknown_paths
        or locked_rules & set(impact.matched_rules)
    ):
        raise ReleaseError(
            "--no-maintenance cannot waive migration, deployment-contract, "
            "initial-release, blocker, or unknown-path safety gates"
        )
    args.maintenance_required = impact.level == "maintenance"
    args.maintenance_waived = args.maintenance_required
    if not args.maintenance_required:
        return
    impact.level = "rolling"
    if "user-authorized-no-maintenance" not in impact.matched_rules:
        impact.matched_rules.append("user-authorized-no-maintenance")


def _plan_document(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    previous_sha: str,
    environment_values: Mapping[str, str],
) -> dict[str, Any]:
    decision = getattr(args, "release_decision", None)
    if not isinstance(decision, ReleaseStrategyDecision):
        decision = resolve_release_strategy(args, impact, manifest)
    execution_profile = getattr(args, "execution_profile", None)
    if not isinstance(execution_profile, ExecutionProfile):
        execution_profile = resolve_execution_profile(
            impact,
            manifest,
            getattr(args, "runtime_env_snapshot", None),
        )
    computed_cloud_services = cloud_services_for_release(args.env, impact)
    if args.skip_env_checks:
        cloud_services = computed_cloud_services
        disabled_cloud_services: set[str] = set()
    else:
        cloud_services, disabled_cloud_services = filter_enabled_cloud_services(
            args.env,
            computed_cloud_services,
            environment_values,
        )
    document: dict[str, Any] = {
        "schema_version": manifest.get("schema_version", 1),
        "track": manifest.get("track", "control-plane"),
        "environment": args.env,
        "git_sha": manifest["git_sha"],
        "previous_sha": previous_sha or None,
        "level": impact.level,
        "services": sorted(impact.services),
        "cloud_services": sorted(cloud_services),
        "disabled_cloud_services": sorted(disabled_cloud_services),
        "config_validation": "skipped" if args.skip_env_checks else "passed",
        "config_source": (
            "skipped"
            if args.skip_env_checks
            else "target-host"
            if isinstance(getattr(args, "runtime_env_snapshot", None), Mapping)
            else "operator-local"
        ),
        "worker": "worker" in impact.services,
        "web_static": "web-static" in impact.services,
        "requires_db_upgrade": impact.requires_db_upgrade,
        "blockers": sorted(impact.blockers),
        "unknown_paths": impact.unknown_paths,
        "matched_rules": impact.matched_rules,
        "risk_class": decision.risk_class,
        "strategy": decision.strategy,
        "validation_mode": decision.validation_mode,
        "skipped_gates": list(decision.skipped_gates),
        "reason": decision.reason or None,
        "gates": dict(decision.gates),
        "test_required": release_requires_test(decision),
        "promotion_mode": (
            "control-plane-repair-fast-track"
            if getattr(args, "control_plane_repair_fast_track", False)
            else decision.strategy
        ),
        "mode": "execute" if args.execute else "dry-run",
        "release_channel": manifest.get("release_channel", "main"),
        "source_ref": manifest.get("source_ref", "refs/heads/main"),
        "maintenance_required": bool(
            getattr(args, "maintenance_required", impact.level == "maintenance")
        ),
        "maintenance_waived": bool(getattr(args, "maintenance_waived", False)),
        "execution_profile": execution_profile.name,
        "execution_profile_reasons": list(execution_profile.reasons),
    }
    runtime_snapshot = getattr(args, "runtime_env_snapshot", None)
    if isinstance(runtime_snapshot, Mapping):
        document["environment_revision"] = runtime_snapshot.get("environment_revision")
        document["config_drift"] = bool(runtime_snapshot.get("drift"))
        document["service_config_revisions"] = runtime_snapshot.get(
            "service_revisions", {}
        )
        document["credential_isolation"] = runtime_snapshot.get(
            "credential_isolation", "pending"
        )
    if manifest.get("schema_version") == 2:
        document["artifacts"] = {
            name: manifest["artifacts"][name] for name in manifest["selected_artifacts"]
        }
    else:
        document["images"] = manifest["images"]
    return document


def _promote_preview_document(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    current = getattr(args, "previous_state", None)
    current_artifacts = (
        current.get("artifacts") if isinstance(current, Mapping) else {}
    )
    runtime_artifacts = getattr(args, "promote_runtime_artifacts", {})
    decisions = resolve_promote_artifact_assurance(
        manifest.get("selected_artifacts", [])
    )
    artifacts: dict[str, dict[str, Any]] = {}
    for name in manifest.get("selected_artifacts", []):
        target = manifest.get("artifacts", {}).get(name, {})
        previous = (
            current_artifacts.get(name, {})
            if isinstance(current_artifacts, Mapping)
            else {}
        )
        live = (
            runtime_artifacts.get(name, {})
            if isinstance(runtime_artifacts, Mapping)
            else {}
        )
        artifacts[name] = {
            "current": (
                live.get("digest")
                if name != "public-web" and isinstance(live, Mapping)
                else None
            )
            or previous.get("digest")
            or previous.get("sha256"),
            "target": target.get("digest") or target.get("sha256"),
            **decisions[name],
        }
    execution_profile = getattr(args, "execution_profile", None)
    if not isinstance(execution_profile, ExecutionProfile):
        execution_profile = resolve_execution_profile(
            impact, manifest, getattr(args, "runtime_env_snapshot", None)
        )
    return {
        "status": "preview",
        "candidate_sha": manifest.get("git_sha"),
        "modules": sorted(_split_services(args.modules)),
        "artifacts": artifacts,
        "maintenance": impact.level == "maintenance",
        "maintenance_required": bool(
            getattr(args, "maintenance_required", impact.level == "maintenance")
        ),
        "maintenance_waived": bool(getattr(args, "maintenance_waived", False)),
        "preflight": preflight.get("status"),
        "blockers": list(preflight.get("blockers", [])),
        "mutation": bool(args.execute),
        "execution_profile": execution_profile.name,
        "execution_profile_reasons": list(execution_profile.reasons),
    }


def _remote_shell(host: str, script: str, *, execute: bool) -> str:
    if not execute:
        print(f"[dry-run] ssh {host} bash -s")
        print(script.rstrip())
        return ""
    result = _run_with_progress(
        ["ssh", "-o", "BatchMode=yes", host, "bash -s"],
        input_text=script,
    )
    if result.returncode:
        stderr_lines = [
            line
            for line in result.stderr.strip().splitlines()
            if not line.startswith("ALLBOT_PROGRESS:")
        ]
        detail = (
            stderr_lines[-1:]
            or result.stderr.strip().splitlines()[-1:]
            or result.stdout.strip().splitlines()[-1:]
        )
        raise ReleaseError(
            "remote release command failed: "
            + _safe_failure_detail(detail[0] if detail else "ssh")
        )
    return result.stdout


def _deploy_cloud_streamlined(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    release_env: str,
    environment_values: Mapping[str, str],
) -> Mapping[str, Any] | None:
    """Replace only selected services and roll them back from local image refs."""

    environment = ENVIRONMENT[args.env]
    host = args.remote_host or environment["host"]
    selected, _ = filter_enabled_cloud_services(
        args.env,
        cloud_services_for_release(args.env, impact),
        environment_values,
    )
    services = sorted(selected)
    if not services:
        return
    if manifest.get("schema_version") != 2 or manifest.get("track") != "control-plane":
        raise ReleaseError("streamlined cloud deployment requires control-plane schema v2")
    sha = validate_full_sha(str(manifest["git_sha"]))
    release_dir = _cloud_release_dir(sha, "control-plane")
    env_file = args.remote_env_file or environment["env_file"]
    profile_flags = compose_profile_flags(services)
    compose = (
        f"docker compose --project-name {shlex.quote(environment['project'])} "
        '--env-file "$compose_checkout/deploy/env.defaults" '
        f"--env-file {shlex.quote(env_file)} --env-file {release_dir}/release.env "
        '-f "$compose_checkout/deploy/docker-compose-cloud-base.yml" '
        f'-f "$compose_checkout/{environment["overlay"]}" {profile_flags}'
    )
    service_args = " ".join(shlex.quote(service) for service in services)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ReleaseError("streamlined release artifacts are unavailable")
    service_to_artifact = {
        service: artifact for artifact, service in PROMOTE_ARTIFACT_SERVICE.items()
    }
    target_rows: list[tuple[str, str, str, str, str]] = []
    snapshot = getattr(args, "runtime_env_snapshot", None)
    service_revisions = (
        snapshot.get("service_revisions", {}) if isinstance(snapshot, Mapping) else {}
    )
    compose_to_config = {
        compose_service: config_service
        for config_service, compose_service in CONFIG_SERVICE_TO_COMPOSE.items()
    }
    for service in services:
        artifact_name = service_to_artifact.get(service, service)
        artifact = artifacts.get(artifact_name)
        if not isinstance(artifact, Mapping) or artifact.get("kind") != "image":
            raise ReleaseError(f"streamlined target artifact is invalid: {artifact_name}")
        ref = str(artifact.get("ref", ""))
        oci = str(artifact.get("oci_revision", ""))
        variable = CONTROL_ARTIFACT_ENV.get(artifact_name, "")
        if not DIGEST_IMAGE_RE.fullmatch(ref) or not variable or not FULL_SHA_RE.fullmatch(oci):
            raise ReleaseError(f"streamlined target identity is invalid: {artifact_name}")
        config_name = compose_to_config.get(service)
        config_revision = str(service_revisions.get(config_name, "")) if config_name else ""
        if config_name and not config_revision:
            raise ReleaseError(f"streamlined target config is unavailable: {artifact_name}")
        target_rows.append((service, artifact_name, variable, oci, config_revision))

    release_payload = base64.b64encode(release_env.encode("utf-8")).decode("ascii")
    rollback_env = f"/tmp/allbot-target-rollback-{sha}.env"
    compose_identity_lines: list[str] = []
    prepare_lines: list[str] = []
    verify_lines: list[str] = []
    rollback_verify_lines: list[str] = []
    api_services = {
        "web-api",
        "payment-api",
        "dashboard-backend",
        "qqcc-config-backend",
        "bot",
        "qqcc-bot",
        "qqcc-private-bot-worker",
        "paid-group-guard-bot",
        "support-bot",
    }
    polling_services = {"bot", "qqcc-bot", "paid-group-guard-bot", "support-bot"}
    for service, artifact_name, variable, oci, config_revision in target_rows:
        quoted_service = shlex.quote(service)
        quoted_artifact = shlex.quote(artifact_name)
        quoted_variable = shlex.quote(variable)
        quoted_oci = shlex.quote(oci)
        quoted_config_revision = shlex.quote(config_revision)
        config_name = compose_to_config.get(service)
        compose_identity_lines.extend(
            [
                "target_ids=\"$(docker ps -q "
                f"--filter label=com.docker.compose.project={shlex.quote(environment['project'])} "
                f"--filter label=com.docker.compose.service={quoted_service})\"",
                'test "$(printf \'%s\\n\' "$target_ids" | sed \'/^$/d\' | wc -l)" = 1',
                'target_working_dir="$(docker inspect --format '
                "'{{index .Config.Labels \"com.docker.compose.project.working_dir\"}}' "
                '"$target_ids")"',
                'target_config_files="$(docker inspect --format '
                "'{{index .Config.Labels \"com.docker.compose.project.config_files\"}}' "
                '"$target_ids")"',
                'test "$target_working_dir" = "$compose_working_dir"',
                'test "$target_config_files" = "$compose_config_files"',
            ]
        )
        if config_name:
            projection = f"/var/lib/allbot/config/{args.env}/current/{config_name}.env"
            prepare_lines.extend(
                [
                    f"test -f {shlex.quote(projection)}",
                    f'test "$(stat -c %a {shlex.quote(projection)})" = 600',
                ]
            )
        prepare_lines.extend(
            [
                f'old_id="$({compose} ps -q {quoted_service})"',
                'test "$(printf \'%s\\n\' "$old_id" | sed \'/^$/d\' | wc -l)" = 1',
                'old_ref="$(docker inspect --format \'{{.Config.Image}}\' "$old_id")"',
                'docker image inspect "$old_ref" >/dev/null',
                f"printf '%s=%s\\n' {quoted_variable} \"$old_ref\" >> \"$rollback_env\"",
            ]
        )
        verify_lines.extend(
            [
                f'new_id="$({compose} ps -q {quoted_service})"',
                'test "$(printf \'%s\\n\' "$new_id" | sed \'/^$/d\' | wc -l)" = 1',
                'new_ref="$(docker inspect --format \'{{.Config.Image}}\' "$new_id")"',
                f'test "$new_ref" = "${{{variable}}}"',
                'new_oci="$(docker image inspect --format \'{{index .Config.Labels "org.opencontainers.image.revision"}}\' "$new_ref")"',
                f'test "$new_oci" = {quoted_oci}',
                'new_health="$(docker inspect --format \'{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}\' "$new_id")"',
                'test "$new_health" = healthy -o "$new_health" = running',
                'new_started="$(docker inspect --format \'{{.State.StartedAt}}\' "$new_id")"',
                f"printf 'ALLBOT_RUNTIME\\t%s\\t%s\\t%s\\t%s\\t%s\\t%s\\n' {quoted_artifact} {quoted_service} \"$new_id\" \"$new_ref\" \"$new_health\" \"$new_started\"",
            ]
        )
        if config_revision:
            verify_lines.extend(
                [
                    'new_config="$(docker inspect --format \'{{range .Config.Env}}{{println .}}{{end}}\' "$new_id" | sed -n \'s/^ALLBOT_CONFIG_REVISION=//p\')"',
                    f'test "$new_config" = {quoted_config_revision}',
                ]
            )
        rollback_verify_lines.extend(
            [
                f'rollback_id="$({compose} --env-file "$rollback_env" ps -q {quoted_service})"',
                'test -n "$rollback_id"',
                'rollback_health="$(docker inspect --format \'{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}\' "$rollback_id")"',
                'test "$rollback_health" = healthy -o "$rollback_health" = running',
            ]
        )
        if service in api_services:
            verify_lines.append(
                f"{compose} exec -T {quoted_service} python -c "
                "'import config,urllib.request; urllib.request.urlopen(config.API_BASE.rstrip(\"/\") + \"/health\", timeout=5).read()' </dev/null"
            )
        if service in polling_services:
            for legacy_name in legacy_cloud_containers(args.env, {service}):
                verify_lines.append(
                    "! docker ps --format '{{.Names}}' | grep -Fxq "
                    + shlex.quote(legacy_name)
                )
            verify_lines.extend(
                [
                    f'polling_id="$({compose} ps -q {quoted_service})"',
                    'test "$(printf \'%s\\n\' "$polling_id" | sed \'/^$/d\' | wc -l)" = 1',
                    'polling_started="$(docker inspect --format \'{{.State.StartedAt}}\' "$polling_id")"',
                    '! docker logs --since "$polling_started" "$polling_id" 2>&1 | grep -Eiq \'terminated by other getUpdates request|Conflict:.*getUpdates\'',
                ]
            )
    rollback_compose = f'{compose} --env-file "$rollback_env"'
    completion_marker = f"ALLBOT_CLOUD_RELEASE_VERIFIED:{sha}"
    checkout_pattern = (
        "^"
        + re.escape(args.remote_checkout_root.rstrip("/"))
        + r"/releases/[0-9a-f]{40}/deploy$"
    )
    seed_service = shlex.quote(services[0])
    script = f"""set -eEuo pipefail
config_started=$(date +%s%N)
install -d -m 755 /var/lib/allbot/deployments/{shlex.quote(args.env)}
exec 9> /var/lib/allbot/deployments/{shlex.quote(args.env)}/release.lock
flock -n 9 || {{ echo 'another release transaction is active' >&2; exit 3; }}
test -f {shlex.quote(env_file)}
test "$(stat -c %a {shlex.quote(env_file)})" = 600
seed_ids="$(docker ps -q --filter label=com.docker.compose.project={shlex.quote(environment['project'])} --filter label=com.docker.compose.service={seed_service})"
test "$(printf '%s\\n' "$seed_ids" | sed '/^$/d' | wc -l)" = 1
compose_working_dir="$(docker inspect --format '{{{{index .Config.Labels "com.docker.compose.project.working_dir"}}}}' "$seed_ids")"
compose_config_files="$(docker inspect --format '{{{{index .Config.Labels "com.docker.compose.project.config_files"}}}}' "$seed_ids")"
[[ "$compose_working_dir" =~ {checkout_pattern} ]]
compose_checkout="${{compose_working_dir%/deploy}}"
test -f "$compose_checkout/deploy/env.defaults"
test -f "$compose_checkout/deploy/docker-compose-cloud-base.yml"
test -f "$compose_checkout/{environment["overlay"]}"
expected_config_files="$compose_checkout/deploy/docker-compose-cloud-base.yml,$compose_checkout/{environment["overlay"]}"
test "$compose_config_files" = "$expected_config_files"
{chr(10).join(compose_identity_lines)}
install -d -m 755 {shlex.quote(release_dir)}
printf %s {shlex.quote(release_payload)} | base64 -d > {shlex.quote(release_dir + '/release.env.tmp')}
mv -f {shlex.quote(release_dir + '/release.env.tmp')} {shlex.quote(release_dir + '/release.env')}
. {shlex.quote(release_dir + '/release.env')}
{compose} config -q
rollback_env={shlex.quote(rollback_env)}
: > "$rollback_env"
chmod 600 "$rollback_env"
{chr(10).join(prepare_lines)}
config_finished=$(date +%s%N)
printf 'ALLBOT_TIMING:config:%s\\n' "$((config_finished-config_started))"
mutation_started=0
target_rollback() {{
  status=$?
  trap - ERR
  set +e
  if [ "$mutation_started" = 1 ]; then
    rollback_started=$(date +%s%N)
    {rollback_compose} up -d --no-deps --wait --wait-timeout 180 {service_args}
    rollback_status=$?
    if [ "$rollback_status" = 0 ]; then
      set -e
      {chr(10).join(rollback_verify_lines)}
      echo ALLBOT_TARGET_ROLLBACK_VERIFIED
      rollback_finished=$(date +%s%N)
      printf 'ALLBOT_TIMING:target-rollback:%s\\n' "$((rollback_finished-rollback_started))"
      set +e
    fi
  fi
  rm -f "$rollback_env"
  exit "$status"
}}
trap target_rollback ERR
pull_started=$(date +%s%N)
{compose} pull {service_args}
pull_finished=$(date +%s%N)
printf 'ALLBOT_TIMING:pull:%s\\n' "$((pull_finished-pull_started))"
mutation_started=1
replace_started=$(date +%s%N)
{compose} up -d --no-deps --wait --wait-timeout 180 {service_args}
replace_finished=$(date +%s%N)
printf 'ALLBOT_TIMING:replace:%s\\n' "$((replace_finished-replace_started))"
health_started=$(date +%s%N)
{chr(10).join(verify_lines)}
health_finished=$(date +%s%N)
printf 'ALLBOT_TIMING:health:%s\\n' "$((health_finished-health_started))"
trap - ERR
rm -f "$rollback_env"
printf '%s\\n' {shlex.quote(completion_marker)}
"""
    if not args.execute:
        _remote_shell(host, script, execute=False)
        return
    result = _run(
        ["ssh", "-o", "BatchMode=yes", host, "bash -s"],
        input_text=script,
        check=False,
    )
    timings: dict[str, float] = {}
    runtime: dict[str, Any] = {}
    for line in result.stdout.splitlines():
        if line.startswith("ALLBOT_TIMING:"):
            _, phase, nanoseconds = line.split(":", 2)
            if nanoseconds.isdigit():
                timings[phase] = int(nanoseconds) / 1_000_000_000
        elif line.startswith("ALLBOT_RUNTIME\t"):
            fields = line.split("\t")
            if len(fields) == 7:
                _, artifact_name, service, container_id, ref, health, started_at = fields
                runtime[artifact_name] = {
                    "service": service,
                    "container_id": container_id,
                    "ref": ref,
                    "digest": ref.rsplit("@", 1)[-1],
                    "health": health,
                    "started_at": started_at,
                }
    args.streamlined_phase_timings = timings
    args.streamlined_runtime_services = runtime
    if result.returncode:
        args.streamlined_cloud_rolled_back = (
            "ALLBOT_TARGET_ROLLBACK_VERIFIED" in result.stdout.splitlines()
        )
        raise ReleaseError(
            "streamlined target replacement failed"
            + (" and was rolled back" if args.streamlined_cloud_rolled_back else "")
        )
    if completion_marker not in result.stdout.splitlines():
        raise ReleaseError("cloud release completion marker is missing")
    return {"phase_timings_seconds": timings}


def _deploy_cloud(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    release_env: str,
    environment_values: Mapping[str, str],
) -> Mapping[str, Any] | None:
    profile = getattr(args, "execution_profile", None)
    if isinstance(profile, ExecutionProfile) and profile.name == "streamlined":
        return _deploy_cloud_streamlined(
            args, impact, manifest, release_env, environment_values
        )
    environment = ENVIRONMENT[args.env]
    host = args.remote_host or environment["host"]
    selected_cloud_services, _ = filter_enabled_cloud_services(
        args.env,
        cloud_services_for_release(args.env, impact),
        environment_values,
    )
    cloud_services = sorted(
        selected_cloud_services,
        key=lambda service: (service not in {"postgres", "redis"}, service),
    )
    if not cloud_services:
        return
    sha = manifest["git_sha"]
    track = (
        str(manifest["track"])
        if manifest.get("schema_version") == 2
        and manifest.get("track") in RELEASE_TRACKS
        else None
    )
    checkout_root = args.remote_checkout_root
    checkout = f"{checkout_root}/releases/{sha}"
    repo = f"{checkout_root}/repo"
    release_dir = _cloud_release_dir(str(sha), track)
    env_file = args.remote_env_file or environment["env_file"]
    profile_flags = compose_profile_flags(cloud_services)
    compose = (
        f"docker compose --project-name {shlex.quote(environment['project'])} "
        f"--env-file {checkout}/deploy/env.defaults "
        f"--env-file {shlex.quote(env_file)} --env-file {release_dir}/release.env "
        f"-f {checkout}/deploy/docker-compose-cloud-base.yml "
        f"-f {checkout}/{environment['overlay']} "
        f"{profile_flags}"
    )
    services = " ".join(shlex.quote(service) for service in cloud_services)
    resolved_api_base_checks = "".join(
        f"{compose} exec -T {shlex.quote(service)} python -c "
        "'import config, urllib.request; "
        "urllib.request.urlopen(config.API_BASE.rstrip(\"/\") + \"/health\", "
        "timeout=5).read()' "
        "</dev/null\n"
        for service in cloud_services
        if service
        in {
            "web-api",
            "payment-api",
            "dashboard-backend",
            "qqcc-config-backend",
            "bot",
            "qqcc-bot",
            "qqcc-private-bot-worker",
            "paid-group-guard-bot",
        }
    )
    if manifest.get("schema_version") == 2:
        service_artifacts = {
            "bot": "main-bot",
            "central-api": "central-api",
            "dashboard-backend": "dashboard-backend",
            "dashboard-frontend": "dashboard-frontend",
            "imgproxy": "imgproxy",
            "paid-group-guard-bot": "paid-group-bot",
            "support-bot": "support-bot",
            "payment-api": "payment-api",
            "postgres": "postgres",
            "qqcc-bot": "qqcc-bot",
            "qqcc-config-backend": "qqcc-config-backend",
            "qqcc-config-frontend": "qqcc-config-frontend",
            "qqcc-private-bot-worker": "private-bot-worker",
            "redis": "redis",
            "web-api": "web-api",
        }
        expected_image_variables = {
            service: CONTROL_ARTIFACT_ENV[artifact]
            for service, artifact in service_artifacts.items()
        }
        expected_revisions = {
            service: str(manifest["artifacts"][artifact].get("oci_revision", ""))
            for service, artifact in service_artifacts.items()
            if artifact in manifest["artifacts"]
            and manifest["artifacts"][artifact].get("kind") == "image"
        }
    else:
        expected_image_variables = {
            "bot": "ALLBOT_APP_IMAGE",
            "central-api": "ALLBOT_CENTRAL_IMAGE",
            "dashboard-backend": "ALLBOT_DASHBOARD_BACKEND_IMAGE",
            "dashboard-frontend": "ALLBOT_DASHBOARD_FRONTEND_IMAGE",
            "imgproxy": "ALLBOT_IMGPROXY_IMAGE",
            "paid-group-guard-bot": "ALLBOT_APP_IMAGE",
            "support-bot": "ALLBOT_APP_IMAGE",
            "payment-api": "ALLBOT_APP_IMAGE",
            "postgres": "ALLBOT_POSTGRES_IMAGE",
            "qqcc-bot": "ALLBOT_APP_IMAGE",
            "qqcc-config-backend": "ALLBOT_DASHBOARD_BACKEND_IMAGE",
            "qqcc-config-frontend": "ALLBOT_DASHBOARD_FRONTEND_IMAGE",
            "qqcc-private-bot-worker": "ALLBOT_APP_IMAGE",
            "redis": "ALLBOT_REDIS_IMAGE",
            "web-api": "ALLBOT_APP_IMAGE",
        }
        expected_revisions = {
            service: str(sha)
            for service in expected_image_variables
            if service not in {"imgproxy", "postgres", "redis"}
        }
    custom_image_services = {
        service
        for service in expected_image_variables
        if service not in {"imgproxy", "postgres", "redis"}
    }
    resolved_image_checks = ""
    for service in cloud_services:
        variable = expected_image_variables[service]
        resolved_image_checks += (
            f'container_id="$({compose} ps -q {shlex.quote(service)})"\n'
            'test -n "$container_id"\n'
            "actual_image=\"$(docker inspect --format '{{.Config.Image}}' "
            '"$container_id")"\n'
            f'test "$actual_image" = "${variable}"\n'
        )
        if service in custom_image_services:
            resolved_image_checks += (
                'actual_revision="$(docker inspect --format '
                "'{{ index .Config.Labels \"org.opencontainers.image.revision\" }}' "
                '"$container_id")"\n'
                f'test "$actual_revision" = {shlex.quote(expected_revisions[service])}\n'
            )
    polling_checks = ""
    polling_services = {"bot", "qqcc-bot", "paid-group-guard-bot", "support-bot"}
    for service in sorted(set(cloud_services) & polling_services):
        legacy = legacy_cloud_containers(args.env, {service})
        legacy_checks = "".join(
            f"! docker ps --format '{{{{.Names}}}}' | grep -Fxq {shlex.quote(name)}\n"
            for name in legacy
        )
        polling_checks += f"""{legacy_checks}polling_id="$({compose} ps -q {shlex.quote(service)})"
test "$(printf '%s\\n' "$polling_id" | sed '/^$/d' | wc -l)" = 1
started_at="$(docker inspect --format '{{{{.State.StartedAt}}}}' "$polling_id")"
! docker logs --since "$started_at" "$polling_id" 2>&1 | grep -Eiq 'terminated by other getUpdates request|Conflict:.*getUpdates'
"""
    revision_checks = ""
    for service in cloud_services:
        revision = expected_revisions.get(service)
        if not revision:
            continue
        variable = expected_image_variables[service]
        revision_checks += (
            f'ref="${variable}"\n'
            'docker image inspect "$ref" >/dev/null\n'
            'test "$(docker image inspect --format '
            "'{{ index .Config.Labels \"org.opencontainers.image.revision\" }}' "
            f'"$ref")" = {shlex.quote(revision)}\n'
        )
    completion_marker = f"ALLBOT_CLOUD_RELEASE_VERIFIED:{sha}"
    initial_cutover = (
        "initial-release" in impact.matched_rules and impact.level == "maintenance"
    )
    if (
        args.execute
        and "test-data-service-repair" in impact.matched_rules
        and not getattr(args, "confirm_empty_test_queue", False)
    ):
        raise ReleaseError(
            "test data service repair requires --confirm-empty-test-queue"
        )
    legacy_containers = legacy_cloud_containers(args.env, cloud_services)
    legacy_names = " ".join(shlex.quote(name) for name in legacy_containers)
    legacy_handoff = ""
    legacy_commit = ""
    if initial_cutover:
        if args.execute and not args.confirm_legacy_cutover:
            raise ReleaseError(
                "initial immutable cutover requires --confirm-legacy-cutover"
            )
        legacy_handoff = f"""for name in {legacy_names}; do
  docker ps --format '{{{{.Names}}}}' | grep -Fxq "$name" && printf '%s\\n' "$name" >> "$legacy_running_file"
done
legacy_running="$(tr '\\n' ' ' < "$legacy_running_file")"
if [ -n "$legacy_running" ]; then
  docker stop $legacy_running
fi
"""
        legacy_commit = "legacy_cutover_committed=1"
    maintenance_prefix = ""
    maintenance_suffix = ""
    # The transaction owner clears maintenance only after cloud, Worker, Pages,
    # state persistence and their health checks have all committed.
    hold_maintenance = impact.level == "maintenance"
    if impact.level == "maintenance":
        maintenance_paths = maintenance_files(args.env, initial_cutover=initial_cutover)
        maintenance_setup = "".join(
            f"install -d -m 755 {shlex.quote(str(Path(path).parent))}\n"
            f"touch {shlex.quote(path)}\n"
            for path in maintenance_paths
        )
        maintenance_clear = "".join(
            f"rm -f {shlex.quote(path)}\n" for path in maintenance_paths
        )
        drain_condition = f"{compose} ps -q central-api | grep -q ."
        drain_counts = (
            f"{compose} exec -T central-api python -c "
            '\'import os,redis; c=redis.Redis.from_url(os.environ.get("WORKER_REDIS_URL") or os.environ["REDIS_URL"]); '
            'print(c.zcard("comfy:queue:pending"),c.scard("comfy:queue:running"))\' '
            "</dev/null"
        )
        if "test-data-service-repair" in impact.matched_rules:
            # The operator has inspected the stopped legacy Redis directly and
            # supplied --confirm-empty-test-queue.  The current immutable
            # Central API cannot resolve Redis until this repair starts it, so
            # attempting the ordinary in-container drain would be circular.
            drain_condition = "false"
        elif initial_cutover and "central-api" in cloud_services:
            legacy_central = legacy_cloud_containers(args.env, {"central-api"})[0]
            drain_condition = (
                "docker ps --format '{{.Names}}' | "
                f"grep -Fxq {shlex.quote(legacy_central)}"
            )
            drain_counts = (
                f"docker exec {shlex.quote(legacy_central)} python -c "
                '\'import os,redis; c=redis.Redis.from_url(os.environ.get("WORKER_REDIS_URL") or os.environ["REDIS_URL"]); '
                'print(c.zcard("comfy:queue:pending"),c.scard("comfy:queue:running"))\''
            )
        legacy_setup = ""
        legacy_restore = ""
        if initial_cutover:
            legacy_setup = f"""legacy_cutover_committed=0
legacy_running_file={release_dir}/legacy-cloud-running.txt
: > "$legacy_running_file"
"""
            legacy_restore = f"""if [ "$legacy_cutover_committed" != 1 ]; then
  {compose} rm -sf {services} >/dev/null 2>&1 || true
  while read -r name; do
    [ -n "$name" ] && docker start "$name" >/dev/null 2>&1 || true
  done < "$legacy_running_file"
fi
"""
        maintenance_prefix = f"""{maintenance_setup}{legacy_setup}cleanup_maintenance() {{
  status=$?
  set +e
  {legacy_restore}
  return "$status"
}}
trap cleanup_maintenance EXIT
if {drain_condition}; then
  printf 'ALLBOT_PROGRESS:drain:started\\n' >&2
  deadline=$(( $(date +%s) + {args.drain_timeout_seconds} ))
  while true; do
    counts="$({drain_counts})"
    set -- $counts
    [ "$1" = 0 ] && [ "$2" = 0 ] && break
    printf 'ALLBOT_PROGRESS:drain:waiting pending=%s running=%s\\n' "$1" "$2" >&2
    [ "$(date +%s)" -lt "$deadline" ] || {{ echo 'queue drain timed out' >&2; exit 2; }}
    sleep {args.drain_interval_seconds}
  done
  printf 'ALLBOT_PROGRESS:drain:completed\\n' >&2
fi
"""
        if hold_maintenance:
            maintenance_suffix = (
                "trap - EXIT\necho 'generation maintenance held for worker cutover'\n"
            )
        else:
            maintenance_suffix = f"{maintenance_clear}trap - EXIT\n"
    release_branch = release_remote_branch(
        str(manifest.get("source_ref", "refs/heads/main"))
    )
    remote_release_ref = f"origin/{release_branch}"
    non_target_snapshot = (
        f"/var/lib/allbot/deployments/{args.env}/transactions/"
        f"{track + '/' if track else ''}{sha}.nontarget.tsv"
        if getattr(args, "command", "") == "promote"
        else f"/tmp/allbot-nontarget-{sha}.txt"
    )
    non_target_cleanup = (
        ""
        if getattr(args, "command", "") == "promote"
        else 'rm -f "$start_snapshot"'
    )
    script = f"""set -euo pipefail
progress_start() {{
  progress_phase="$1"
  progress_started_ns="$(date +%s%N)"
  printf 'ALLBOT_PROGRESS:%s:started\\n' "$progress_phase" >&2
}}
progress_done() {{
  progress_finished_ns="$(date +%s%N)"
  printf 'ALLBOT_TIMING:%s:%s\\n' "$1" "$((progress_finished_ns-progress_started_ns))"
  printf 'ALLBOT_PROGRESS:%s:completed\\n' "$1" >&2
}}
progress_failed() {{
  status=$?
  printf 'ALLBOT_PROGRESS:%s:failed status=%s\\n' "$progress_phase" "$status" >&2
  exit "$status"
}}
trap progress_failed ERR
progress_start candidate
test -d {shlex.quote(repo)}/.git || {{ echo 'release host is not bootstrapped; run scripts/bootstrap_release_host.sh' >&2; exit 3; }}
git -C {shlex.quote(repo)} fetch --prune origin {shlex.quote(release_branch)}
git -C {shlex.quote(repo)} merge-base --is-ancestor {sha} {shlex.quote(remote_release_ref)}
mkdir -p {shlex.quote(checkout_root)}/releases /var/lib/allbot/releases
if [ ! -d {shlex.quote(checkout)} ]; then
  git -C {shlex.quote(repo)} worktree add --detach {shlex.quote(checkout)} {sha}
fi
test "$(git -C {shlex.quote(checkout)} rev-parse HEAD)" = {sha}
progress_done candidate
progress_start config
install -d -m 755 {release_dir}
test -f {shlex.quote(env_file)}
test "$(stat -c %a {shlex.quote(env_file)})" = 600
. {release_dir}/release.env
{compose} config -q
start_snapshot={shlex.quote(non_target_snapshot)}
start_snapshot_dir="$(dirname "$start_snapshot")"
test -d "$start_snapshot_dir" || install -d -m 755 "$start_snapshot_dir"
target_names="$({compose} ps --format '{{{{.Name}}}}' {services} 2>/dev/null || true)"
for name in {legacy_names or ":"}; do
  target_names="${{target_names}}
${{name}}"
done
: > "$start_snapshot"
for name in $(docker ps --filter label=com.docker.compose.project={shlex.quote(environment['project'])} --format '{{{{.Names}}}}'); do
  printf '%s\n' "$target_names" | grep -Fxq "$name" && continue
  docker inspect --format '{{{{.Id}}}}\t{{{{.Config.Image}}}}\t{{{{.State.StartedAt}}}}' "$name" >> "$start_snapshot"
done
progress_done config
progress_start maintenance
{maintenance_prefix}progress_done maintenance
progress_start pull
{compose} pull {services}
progress_done pull
{revision_checks}
{legacy_handoff}progress_start replace
{compose} up -d --no-deps --wait --wait-timeout 180 {services}
progress_done replace
progress_start health
{compose} ps {services}
{resolved_api_base_checks}{resolved_image_checks}{polling_checks}while IFS=$'\t' read -r container_id image started_at; do
  test -n "$container_id"
  test "$(docker inspect --format '{{{{.Config.Image}}}}' "$container_id")" = "$image"
  test "$(docker inspect --format '{{{{.State.StartedAt}}}}' "$container_id")" = "$started_at"
done < "$start_snapshot"
progress_done health
{non_target_cleanup}
{legacy_commit}
{maintenance_suffix}
printf '%s\n' {shlex.quote(completion_marker)}
"""
    if impact.requires_db_upgrade:
        if not args.confirm_db_upgrade:
            raise ReleaseError("migration release requires --confirm-db-upgrade")
        backup_dir = f"{environment['state_root']}/backups"
        migration = f"""progress_start backup
install -d -m 700 {backup_dir}
backup_file={backup_dir}/pre-{sha}-$(date -u +%Y%m%dT%H%M%SZ).sql.gz
umask 077
web_container="$(docker ps -q --filter label=com.docker.compose.project={shlex.quote(environment['project'])} --filter label=com.docker.compose.service=web-api)"
test "$(printf '%s\n' "$web_container" | sed '/^$/d' | wc -l)" = 1
database_url="$(docker exec "$web_container" sh -lc 'printf %s "$DATABASE_URL"')"
docker run --rm --network "container:$web_container" -e DATABASE_URL="$database_url" {shlex.quote(PG_DUMP_IMAGE)} sh -lc 'case "$DATABASE_URL" in postgresql+asyncpg:*) url="postgresql:${{DATABASE_URL#postgresql+asyncpg:}}";; postgresql:*) url="$DATABASE_URL";; *) exit 2;; esac; url="$(printf %s "$url" | sed "s/\\([?&]\\)ssl=/\\1sslmode=/")"; exec pg_dump "$url"' | gzip -c > "$backup_file"
test -s "$backup_file"
progress_done backup
progress_start migration
heads="$({compose} run --no-deps --rm -T web-api alembic heads </dev/null | grep -c ' (head)$')"
test "$heads" = 1
{compose} run --no-deps --rm -T web-api alembic upgrade head </dev/null
progress_done migration
"""
        script = script.replace(
            "progress_done pull\n",
            "progress_done pull\n" + migration,
            1,
        )
    if args.execute:
        # Compose must never observe a partially written release contract.
        _run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                host,
                (
                    f"set -e; install -d -m 755 {shlex.quote(release_dir)}; "
                    f"umask 022; cat > {shlex.quote(release_dir + '/release.env.tmp')}; "
                    f"mv -f {shlex.quote(release_dir + '/release.env.tmp')} "
                    f"{shlex.quote(release_dir + '/release.env')}"
                ),
            ],
            input_text=release_env,
        )
    else:
        print(
            f"[dry-run] install non-secret release.env on {host}:{release_dir}/release.env"
        )
    remote_output = _remote_shell(host, script, execute=args.execute)
    if args.execute and completion_marker not in remote_output.splitlines():
        raise ReleaseError("cloud release completion marker is missing")
    timings: dict[str, float] = {}
    for line in remote_output.splitlines():
        if line.startswith("ALLBOT_TIMING:"):
            _, phase, nanoseconds = line.split(":", 2)
            if nanoseconds.isdigit():
                timings[phase] = int(nanoseconds) / 1_000_000_000
    return {"phase_timings_seconds": timings}


def _expand_disabled_test_owner_rollback_baseline(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    environment_values: Mapping[str, str],
) -> tuple[ReleaseImpact, Mapping[str, Any]]:
    """Use the complete recorded baseline when a test-only owner module is absent.

    Dashboard artifacts are deliberately not deployed to the shared test control
    plane.  A Dashboard-only candidate can still become the recorded control-plane
    baseline because its bundle carries forward every runtime artifact.  When that
    happens, repairing rollback materials must verify the actually running services
    against the complete bundle instead of looking for a Dashboard container that
    cannot exist in test.
    """

    selected = cloud_services_for_release(args.env, impact)
    if selected or args.env != "test" or manifest.get("track") != "control-plane":
        return impact, manifest
    if not set(impact.services) & {"dashboard-backend", "dashboard-frontend"}:
        return impact, manifest

    previous_state = getattr(args, "previous_state", None)
    if (
        not isinstance(previous_state, Mapping)
        or previous_state.get("git_sha") != manifest.get("git_sha")
        or not isinstance(previous_state.get("artifacts"), Mapping)
    ):
        raise ReleaseError(
            "disabled test owner rollback repair requires the exact recorded baseline"
        )

    release_index = manifest.get("release_index")
    if not isinstance(release_index, str) or not release_index:
        raise ReleaseError("rollback material repair has no complete release index")
    full_manifest = _load_v2_track(
        Path(release_index),
        sha=str(manifest["git_sha"]),
        track="control-plane",
        modules=[],
        select_all_when_empty=True,
    )

    artifact_by_service = {
        service: artifact for artifact, service in CONTROL_ARTIFACT_SERVICE.items()
    }
    full_services = {
        CONTROL_ARTIFACT_SERVICE.get(name, name)
        for name in full_manifest.get("selected_artifacts", [])
        if isinstance(full_manifest.get("artifacts", {}).get(name), Mapping)
        and full_manifest["artifacts"][name].get("kind") == "image"
    }
    enabled_services, _ = filter_enabled_cloud_services(
        args.env,
        cloud_services_for_release(
            args.env, ReleaseImpact(services=full_services, level="rolling")
        ),
        environment_values,
    )
    if not enabled_services:
        raise ReleaseError("rollback material repair has no enabled cloud services")

    current_artifacts = previous_state["artifacts"]
    for service in sorted(enabled_services):
        artifact_name = artifact_by_service.get(service, service)
        current = current_artifacts.get(artifact_name)
        bundled = full_manifest.get("artifacts", {}).get(artifact_name)
        if (
            not isinstance(current, Mapping)
            or not isinstance(bundled, Mapping)
            or not DIGEST_RE.fullmatch(str(current.get("digest", "")))
            or current.get("digest") != bundled.get("digest")
        ):
            raise ReleaseError(
                "complete rollback bundle does not match the recorded test runtime: "
                + service
            )

    expanded_impact = ReleaseImpact(
        services=enabled_services,
        level=impact.level,
        requires_db_upgrade=impact.requires_db_upgrade,
        matched_rules=list(impact.matched_rules),
        blockers=list(impact.blockers),
        unknown_paths=list(impact.unknown_paths),
    )
    return expanded_impact, full_manifest


def _materialize_cloud_rollback_materials(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    release_env: str,
    environment_values: Mapping[str, str],
) -> None:
    """Restore immutable rollback inputs without changing running services."""

    if args.env not in {"test", "prod"} or manifest.get("schema_version") != 2:
        raise ReleaseError("rollback material repair requires a schema-v2 release")
    track = str(manifest.get("track", ""))
    if track != "control-plane":
        raise ReleaseError(
            "rollback material repair currently supports only control-plane"
        )
    selected_cloud_services, disabled = filter_enabled_cloud_services(
        args.env,
        cloud_services_for_release(args.env, impact),
        environment_values,
    )
    if disabled or not selected_cloud_services:
        raise ReleaseError("rollback material repair has no enabled cloud services")

    artifact_by_service = {
        service: artifact for artifact, service in CONTROL_ARTIFACT_SERVICE.items()
    }
    expected: dict[str, str] = {}
    for service in sorted(selected_cloud_services):
        artifact_name = artifact_by_service.get(service, service)
        artifact = manifest.get("artifacts", {}).get(artifact_name or "")
        if (
            not artifact_name
            or artifact_name not in manifest.get("selected_artifacts", [])
            or not isinstance(artifact, Mapping)
            or not DIGEST_RE.fullmatch(str(artifact.get("digest", "")))
        ):
            raise ReleaseError(
                f"rollback material repair has no selected digest for {service}"
            )
        expected[service] = str(artifact["digest"])

    environment = ENVIRONMENT[args.env]
    host = args.remote_host or environment["host"]
    sha = str(manifest["git_sha"])
    checkout_root = args.remote_checkout_root
    repo = f"{checkout_root}/repo"
    checkout = f"{checkout_root}/releases/{sha}"
    release_dir = _cloud_release_dir(sha, track)
    env_file = args.remote_env_file or environment["env_file"]
    release_branch = release_remote_branch(
        str(manifest.get("source_ref", "refs/heads/main"))
    )
    profile_flags = compose_profile_flags(selected_cloud_services)
    compose = (
        f"docker compose --project-name {shlex.quote(environment['project'])} "
        f"--env-file {checkout}/deploy/env.defaults "
        f"--env-file {shlex.quote(env_file)} --env-file {release_dir}/release.env "
        f"-f {checkout}/deploy/docker-compose-cloud-base.yml "
        f"-f {checkout}/{environment['overlay']} "
        f"{profile_flags}"
    )
    running_checks = ""
    for service, digest in expected.items():
        running_checks += f"""container_ids="$(docker ps \\
  --filter label=com.docker.compose.project={shlex.quote(environment["project"])} \\
  --filter label=com.docker.compose.service={shlex.quote(service)} \\
  --format '{{{{.ID}}}}')"
test "$(printf '%s\\n' "$container_ids" | sed '/^$/d' | wc -l)" = 1
test "$(docker inspect --format '{{{{.Image}}}}' "$container_ids")" = {shlex.quote(digest)}
"""
    marker = f"ALLBOT_ROLLBACK_MATERIALS_READY:{sha}"
    _run(
        ["ssh", "-o", "BatchMode=yes", host, "bash -s"],
        input_text="set -euo pipefail\n" + running_checks,
    )
    script = f"""set -euo pipefail
test -d {shlex.quote(repo)}/.git
git -C {shlex.quote(repo)} fetch --prune origin {shlex.quote(release_branch)}
git -C {shlex.quote(repo)} merge-base --is-ancestor {shlex.quote(sha)} origin/{shlex.quote(release_branch)}
mkdir -p {shlex.quote(checkout_root)}/releases
if [ ! -d {shlex.quote(checkout)} ]; then
  git -C {shlex.quote(repo)} worktree add --detach {shlex.quote(checkout)} {shlex.quote(sha)}
fi
test "$(git -C {shlex.quote(checkout)} rev-parse HEAD)" = {shlex.quote(sha)}
test -f {shlex.quote(env_file)}
test "$(stat -c %a {shlex.quote(env_file)})" = 600
test -f {shlex.quote(release_dir + "/release.env")}
{compose} config -q
printf '%s\n' {shlex.quote(marker)}
"""
    _run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            host,
            (
                f"set -e; install -d -m 755 {shlex.quote(release_dir)}; "
                f"umask 022; cat > {shlex.quote(release_dir + '/release.env.tmp')}; "
                f"mv -f {shlex.quote(release_dir + '/release.env.tmp')} "
                f"{shlex.quote(release_dir + '/release.env')}"
            ),
        ],
        input_text=release_env,
    )
    output = _remote_shell(host, script, execute=args.execute)
    if marker not in output.splitlines():
        raise ReleaseError("rollback material repair completion marker is missing")


def _verify_web_artifact(path: Path, expected_hash: str) -> None:
    if not path.is_file():
        raise ReleaseError(f"web artifact is unavailable: {path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected_hash:
        raise ReleaseError("web artifact checksum does not match release manifest")


def _manifest_web_checksum(manifest: Mapping[str, Any]) -> str:
    if manifest.get("schema_version") == 2:
        artifact = manifest.get("artifacts", {}).get("public-web")
        if not isinstance(artifact, Mapping) or not artifact.get("sha256"):
            raise ReleaseError("control-plane track has no Public Web artifact")
        return str(artifact["sha256"])
    return str(manifest["web_artifact_sha256"])


def _resolved_web_artifact(
    args: argparse.Namespace, manifest: Mapping[str, Any]
) -> Path:
    artifact = Path(args.web_artifact).expanduser()
    if artifact.is_file() or args.web_artifact != "web-dist.tgz":
        return artifact
    cache = Path(args.bundle_cache).expanduser() / str(manifest["git_sha"])
    for candidate in (
        cache / "public-web-dist.tgz",
        cache / "release-v2" / "public-web-dist.tgz",
        cache / "release" / "public-web-dist.tgz",
        cache / "web-dist.tgz",
        cache / "release" / "web-dist.tgz",
    ):
        if candidate.is_file():
            return candidate
    return artifact


def load_web_runtime_config(
    path: Path,
    environment: str,
) -> tuple[dict[str, Any], str]:
    document = load_structured_file(path)
    if document.get("schema_version") != 1:
        raise ReleaseError("unsupported Web runtime config schema_version")
    raw_values = document.get(environment)
    if not isinstance(raw_values, dict):
        raise ReleaseError(f"Web runtime config has no {environment!r} mapping")
    unknown = sorted(set(raw_values) - PUBLIC_WEB_RUNTIME_FIELDS)
    if unknown:
        raise ReleaseError(
            "unsupported public Web runtime fields: " + ", ".join(unknown)
        )
    values: dict[str, Any] = {}
    for key, value in raw_values.items():
        if not isinstance(value, (str, bool)):
            raise ReleaseError(f"Web runtime field {key} must be a string or boolean")
        if isinstance(value, str) and not value.strip():
            raise ReleaseError(f"Web runtime field {key} cannot be empty")
        values[key] = value.strip() if isinstance(value, str) else value
    if "api_base_url" not in values:
        raise ReleaseError("Web runtime config requires api_base_url")
    canonical = json.dumps(
        values, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    revision = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return values, revision


def render_web_runtime_config_script(
    values: Mapping[str, Any],
    *,
    git_sha: str,
    config_revision: str,
) -> str:
    payload = {
        **values,
        "release_sha": git_sha,
        "runtime_config_revision": config_revision,
    }
    return (
        "window.__ALLBOT_CONFIG__ = Object.freeze("
        + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + ");\n"
    )


def _extract_web_artifact(artifact: Path, destination: Path) -> Path:
    destination_root = destination.resolve()
    with tarfile.open(artifact, "r:gz") as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if target != destination_root and destination_root not in target.parents:
                raise ReleaseError("Web artifact contains an unsafe path")
        archive.extractall(destination, filter="data")
    dist = destination / "dist"
    if not (dist / "index.html").is_file():
        raise ReleaseError("Web artifact does not contain dist/index.html")
    return dist


def _pages_deployment_url(output: str) -> str:
    matches = re.findall(r"https://[a-zA-Z0-9.-]+\.pages\.dev", output)
    return matches[-1] if matches else ""


def _pinned_wrangler_version() -> str:
    package_path = ROOT / "frontend" / "package.json"
    lock_path = ROOT / "frontend" / "package-lock.json"
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError("pinned Wrangler package metadata is unavailable") from exc

    package_version = (package.get("devDependencies") or {}).get("wrangler")
    lock_packages = lock.get("packages") or {}
    lock_root_version = (
        (lock_packages.get("") or {}).get("devDependencies") or {}
    ).get("wrangler")
    resolved_version = (lock_packages.get("node_modules/wrangler") or {}).get("version")
    if (
        not isinstance(package_version, str)
        or not re.fullmatch(r"\d+\.\d+\.\d+", package_version)
        or package_version != lock_root_version
        or package_version != resolved_version
    ):
        raise ReleaseError("Wrangler version must be exact and lockfile-matched")
    return package_version


def _pages_runtime_payload(script: str) -> Mapping[str, Any]:
    prefix = "window.__ALLBOT_CONFIG__ = Object.freeze("
    suffix = ");"
    stripped = script.strip()
    if not stripped.startswith(prefix) or not stripped.endswith(suffix):
        raise ReleaseError("canonical runtime config is not the expected JavaScript")
    try:
        payload = json.loads(stripped[len(prefix) : -len(suffix)])
    except json.JSONDecodeError as exc:
        raise ReleaseError("canonical runtime config JavaScript is invalid") from exc
    if not isinstance(payload, Mapping):
        raise ReleaseError("canonical runtime config payload is invalid")
    return payload


def _verify_canonical_pages_runtime(
    args: argparse.Namespace, sha: str, runtime_revision: str
) -> None:
    target = WEB_PAGES_TARGETS[args.env]
    runtime_url = (
        f"{target['canonical_url'].rstrip('/')}/allbot-runtime-config.js"
        f"?release_sha={urllib.parse.quote(sha)}"
    )
    request = urllib.request.Request(
        runtime_url,
        headers={
            "Accept": "application/javascript",
            "Cache-Control": "no-cache",
            "User-Agent": "AllBotReleaseVerifier/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            content_type = str(response.headers.get("Content-Type", ""))
            body = response.read().decode("utf-8")
    except (OSError, urllib.error.HTTPError, UnicodeDecodeError) as exc:
        raise ReleaseError("canonical Pages runtime config request failed") from exc
    if "javascript" not in content_type.lower():
        raise ReleaseError("canonical Pages runtime config is not JavaScript")
    payload = _pages_runtime_payload(body)
    if payload.get("release_sha") != sha:
        raise ReleaseError("canonical Pages runtime release SHA does not match")
    if payload.get("runtime_config_revision") != runtime_revision:
        raise ReleaseError("canonical Pages runtime config revision does not match")


def verify_pages_canonical_deployment(
    args: argparse.Namespace,
    sha: str,
    runtime_revision: str,
) -> dict[str, Any]:
    """Verify the API identity and public canonical content of a Pages release."""

    target = WEB_PAGES_TARGETS[args.env]
    project_path = f"pages/projects/{target['project']}"
    deployments = _pages_api_request(
        args, "GET", project_path + "/deployments?env=production"
    ).get("result")
    if not isinstance(deployments, list):
        raise ReleaseError("Pages production deployment list is invalid")
    deployment: Mapping[str, Any] | None = None
    for candidate in deployments:
        if not isinstance(candidate, Mapping):
            continue
        trigger = candidate.get("deployment_trigger")
        metadata = trigger.get("metadata") if isinstance(trigger, Mapping) else None
        stage = candidate.get("latest_stage")
        if (
            candidate.get("environment") == "production"
            and isinstance(metadata, Mapping)
            and metadata.get("branch") == target["branch"]
            and metadata.get("commit_hash") == sha
            and isinstance(stage, Mapping)
            and stage.get("status") == "success"
        ):
            deployment = candidate
            break
    if deployment is None or not deployment.get("id"):
        raise ReleaseError("matching successful Pages production deployment is missing")
    deployment_id = str(deployment["id"])
    project = _pages_api_request(args, "GET", project_path).get("result")
    canonical = (
        project.get("canonical_deployment") if isinstance(project, Mapping) else None
    )
    if not isinstance(canonical, Mapping) or str(canonical.get("id")) != deployment_id:
        raise ReleaseError("Pages canonical deployment does not match the new release")

    _verify_canonical_pages_runtime(args, sha, runtime_revision)
    return {
        "deployment_id": deployment_id,
        "environment": "production",
        "canonical_url": target["canonical_url"],
        "canonical_verified": True,
    }


def _current_pages_deployment_id(args: argparse.Namespace) -> str:
    target = WEB_PAGES_TARGETS[args.env]
    project = _pages_api_request(
        args, "GET", f"pages/projects/{target['project']}"
    ).get("result")
    canonical = (
        project.get("canonical_deployment") if isinstance(project, Mapping) else None
    )
    if not isinstance(canonical, Mapping) or not canonical.get("id"):
        raise ReleaseError("Pages canonical deployment is unavailable")
    return str(canonical["id"])


def _rollback_pages(args: argparse.Namespace, transaction: Mapping[str, Any]) -> None:
    previous = transaction.get("previous")
    deployment_id = (
        previous.get("pages_deployment_id") if isinstance(previous, Mapping) else None
    )
    if not deployment_id:
        raise ReleaseError("previous Pages production deployment is unavailable")
    target = WEB_PAGES_TARGETS[args.env]
    project_path = f"pages/projects/{target['project']}"
    current = _current_pages_deployment_id(args)
    if current == str(deployment_id):
        return
    _pages_api_request(
        args,
        "POST",
        f"{project_path}/deployments/{deployment_id}/rollback",
        payload={},
    )
    deadline = time.monotonic() + getattr(args, "pages_verify_timeout_seconds", 180)
    while True:
        project = _pages_api_request(args, "GET", project_path).get("result")
        canonical = (
            project.get("canonical_deployment")
            if isinstance(project, Mapping)
            else None
        )
        if isinstance(canonical, Mapping) and str(canonical.get("id")) == str(
            deployment_id
        ):
            break
        if time.monotonic() >= deadline:
            raise ReleaseError(
                "Pages rollback did not restore the previous canonical deployment"
            )
        time.sleep(getattr(args, "pages_verify_interval_seconds", 5))


def _deploy_web(
    args: argparse.Namespace,
    manifest: Mapping[str, Any],
) -> dict[str, Any] | None:
    if args.skip_web:
        return None
    artifact = _resolved_web_artifact(args, manifest)
    _verify_web_artifact(artifact, _manifest_web_checksum(manifest))
    sha = str(manifest["git_sha"])
    target = WEB_PAGES_TARGETS[args.env]
    runtime_values, runtime_revision = load_web_runtime_config(
        Path(args.web_runtime_config),
        args.env,
    )
    token_file = _token_file(args.cloudflare_token_file)
    if not args.execute:
        print(
            "[dry-run] extract verified Web artifact and deploy it to Pages project "
            f"{target['project']} ({target['branch']})"
        )
        return {
            "project": target["project"],
            "branch": target["branch"],
            "runtime_config_revision": runtime_revision,
            "deployment_url": "",
        }
    with tempfile.TemporaryDirectory(prefix="allbot-web-release-") as temp_dir:
        dist = _extract_web_artifact(artifact, Path(temp_dir))
        (dist / "allbot-runtime-config.js").write_text(
            render_web_runtime_config_script(
                runtime_values,
                git_sha=sha,
                config_revision=runtime_revision,
            ),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["CLOUDFLARE_API_TOKEN"] = token_file.read_text(encoding="utf-8").strip()
        if not env["CLOUDFLARE_API_TOKEN"]:
            raise ReleaseError("Cloudflare Pages token file is empty")
        env["CLOUDFLARE_ACCOUNT_ID"] = args.cloudflare_account_id
        result = subprocess.run(
            [
                "npx",
                "--yes",
                f"--package=wrangler@{_pinned_wrangler_version()}",
                "wrangler",
                "pages",
                "deploy",
                str(dist),
                "--project-name",
                target["project"],
                "--branch",
                target["branch"],
                "--commit-hash",
                sha,
            ],
            cwd=ROOT / "frontend",
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise ReleaseError("Cloudflare Pages deployment failed")
        deadline = time.monotonic() + getattr(args, "pages_verify_timeout_seconds", 180)
        while True:
            try:
                verified = verify_pages_canonical_deployment(
                    args, sha, runtime_revision
                )
                break
            except ReleaseError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(getattr(args, "pages_verify_interval_seconds", 5))
        return {
            "project": target["project"],
            "branch": target["branch"],
            "runtime_config_revision": runtime_revision,
            **verified,
        }


def _deploy_worker(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    release_env: str,
    environment_values: Mapping[str, str],
) -> None:
    if args.env != "test":
        raise ReleaseError(
            "production GPU Worker releases must run independently on GPU hosts"
        )
    selected = _split_services([environment_values.get("ALLBOT_WORKER_SERVICES", "")])
    if not selected:
        raise ReleaseError(
            "worker release requires ALLBOT_WORKER_SERVICES in the target env"
        )
    invalid = sorted(
        service for service in selected if not re.fullmatch(r"worker-(0[1-8])", service)
    )
    if invalid:
        raise ReleaseError(
            "invalid ALLBOT_WORKER_SERVICES entries: " + ", ".join(invalid)
        )

    sha = str(manifest["git_sha"])
    root = Path(args.worker_checkout_root)
    repo = root / "repo"
    checkout = root / "releases" / sha
    release_dir = (
        root / "release-env" / str(manifest["track"]) / sha
        if manifest.get("schema_version") == 2
        else root / "release-env" / sha
    )
    release_path = release_dir / "release.env"
    env_file = local_env_file(args)
    project = f"allbot-worker-{args.env}"
    service_args = ["worker-relay", *sorted(selected)]
    compose = [
        "docker",
        "compose",
        "--project-name",
        project,
        "--env-file",
        str(checkout / "deploy/env.defaults"),
        "--env-file",
        str(env_file),
        "--env-file",
        str(release_path),
        "-f",
        str(checkout / "deploy/docker-compose-worker-base.yml"),
    ]
    compose_env = {"ALLBOT_ENV_FILE": str(env_file)}
    if not args.execute:
        print(
            "[dry-run] worker drain/recreate from digest-pinned image: "
            + " ".join(service_args)
        )
        if "initial-release" in impact.matched_rules:
            print(
                f"[dry-run] record and stop matching legacy {args.env} worker containers: "
                + " ".join(legacy_worker_containers(args.env, selected))
            )
        if hold_maintenance_for_worker_cutover(args.env, impact):
            print("[dry-run] hold generation maintenance for transaction commit")
        return
    if not (repo / ".git").is_dir():
        raise ReleaseError(
            "worker release checkout is not bootstrapped; run scripts/bootstrap_release_host.sh"
        )
    release_branch = release_remote_branch(
        str(manifest.get("source_ref", "refs/heads/main"))
    )
    remote_release_ref = f"origin/{release_branch}"
    _run(["git", "-C", str(repo), "fetch", "--prune", "origin", release_branch])
    _run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", sha, remote_release_ref]
    )
    checkout.parent.mkdir(parents=True, exist_ok=True)
    if not checkout.exists():
        _run(
            ["git", "-C", str(repo), "worktree", "add", "--detach", str(checkout), sha]
        )
    if _run(["git", "-C", str(checkout), "rev-parse", "HEAD"]).stdout.strip() != sha:
        raise ReleaseError("worker release checkout SHA mismatch")
    release_dir.mkdir(parents=True, exist_ok=True)
    temp_path = release_path.with_suffix(".tmp")
    temp_path.write_text(release_env, encoding="utf-8")
    temp_path.chmod(0o644)
    temp_path.replace(release_path)
    _run([*compose, "config", "-q"], env=compose_env)
    _run([*compose, "pull", *service_args], env=compose_env)
    if manifest.get("schema_version") == 2:
        worker_refs = [
            (
                str(manifest["artifacts"][name]["ref"]),
                str(manifest["artifacts"][name]["oci_revision"]),
            )
            for name in ("worker-agent", "worker-relay")
            if name in manifest.get("selected_artifacts", [])
        ]
    else:
        worker_refs = [(str(manifest["images"]["worker"]), sha)]
    for worker_ref, expected_revision in worker_refs:
        revision = _run(
            [
                "docker",
                "image",
                "inspect",
                "--format",
                '{{ index .Config.Labels "org.opencontainers.image.revision" }}',
                worker_ref,
            ]
        ).stdout.strip()
        if revision != expected_revision:
            raise ReleaseError("worker OCI revision does not match artifact source SHA")
    if "initial-release" in impact.matched_rules:
        existing = [
            name
            for name in legacy_worker_containers(args.env, selected)
            if _run(
                ["docker", "inspect", "--format", "{{.State.Running}}", name],
                check=False,
            ).stdout.strip()
            == "true"
        ]
        snapshot = release_dir / "legacy-worker-running.txt"
        snapshot_temp = snapshot.with_suffix(".tmp")
        snapshot_temp.write_text(
            "".join(f"{name}\n" for name in existing), encoding="utf-8"
        )
        snapshot_temp.replace(snapshot)
        if existing:
            _run(["docker", "stop", *existing])
    # The impact planner has already elevated worker changes to drain level.
    # Recreate only the explicit slot allowlist; dormant canary slots stay off.
    _run([*compose, "stop", *sorted(selected)], env=compose_env)
    _run(
        [
            *compose,
            "up",
            "-d",
            "--no-deps",
            "--wait",
            "--wait-timeout",
            "180",
            *service_args,
        ],
        env=compose_env,
    )
    _run([*compose, "ps", *service_args], env=compose_env)


def _worker_compose_command(
    args: argparse.Namespace,
    sha: str,
    *,
    track: str | None = None,
) -> tuple[list[str], dict[str, str]]:
    root = Path(args.worker_checkout_root).expanduser()
    checkout = root / "releases" / sha
    release_root = root / "release-env"
    if track in RELEASE_TRACKS:
        release_root /= track
    release_path = release_root / sha / "release.env"
    env_file = local_env_file(args)
    return (
        [
            "docker",
            "compose",
            "--project-name",
            f"allbot-worker-{args.env}",
            "--env-file",
            str(checkout / "deploy/env.defaults"),
            "--env-file",
            str(env_file),
            "--env-file",
            str(release_path),
            "-f",
            str(checkout / "deploy/docker-compose-worker-base.yml"),
        ],
        {"ALLBOT_ENV_FILE": str(env_file)},
    )


def _rollback_worker_stack(
    args: argparse.Namespace,
    transaction: Mapping[str, Any],
    environment_values: Mapping[str, str],
) -> None:
    if args.env != "test":
        raise ReleaseError(
            "production GPU Worker recovery must run independently on GPU hosts"
        )
    selected = _split_services([environment_values.get("ALLBOT_WORKER_SERVICES", "")])
    if not selected:
        return
    service_args = ["worker-relay", *sorted(selected)]
    previous = transaction.get("previous")
    if not isinstance(previous, Mapping):
        raise ReleaseError("transaction previous stack is invalid")
    previous_kind = previous.get("kind")
    target_sha = str(transaction["target_sha"])
    if previous_kind == "legacy":
        project = f"allbot-worker-{args.env}"
        for service in service_args:
            result = _run(
                [
                    "docker",
                    "ps",
                    "-aq",
                    "--filter",
                    f"label=com.docker.compose.project={project}",
                    "--filter",
                    f"label=com.docker.compose.service={service}",
                ],
                check=False,
            )
            ids = result.stdout.split()
            if ids:
                _run(["docker", "rm", "-f", *ids], check=False)
        release_root = Path(args.worker_checkout_root).expanduser() / "release-env"
        track = transaction.get("track")
        if track in RELEASE_TRACKS:
            release_root /= str(track)
        snapshot = release_root / target_sha / "legacy-worker-running.txt"
        expected = legacy_worker_containers(args.env, selected)
        names = (
            [line.strip() for line in snapshot.read_text().splitlines() if line.strip()]
            if snapshot.is_file()
            else [
                name
                for name in expected
                if _run(
                    ["docker", "inspect", "--format", "{{.State.Running}}", name],
                    check=False,
                ).stdout.strip()
                == "true"
            ]
        )
        if not names:
            raise ReleaseError("legacy Worker recovery snapshot is unavailable")
        _run(["docker", "start", *names])
        for name in names:
            running = _run(
                ["docker", "inspect", "--format", "{{.State.Running}}", name]
            ).stdout.strip()
            if running != "true":
                raise ReleaseError("legacy Worker container recovery failed")
    elif previous_kind == "immutable":
        previous_sha = validate_full_sha(str(previous.get("git_sha", "")))
        compose, compose_env = _worker_compose_command(
            args,
            previous_sha,
            track=(
                str(transaction["track"])
                if transaction.get("track") in RELEASE_TRACKS
                else None
            ),
        )
        _run([*compose, "config", "-q"], env=compose_env)
        _run(
            [
                *compose,
                "up",
                "-d",
                "--no-deps",
                "--wait",
                "--wait-timeout",
                "180",
                *service_args,
            ],
            env=compose_env,
        )
    else:
        raise ReleaseError("transaction previous Worker kind is invalid")
    port = environment_values.get("ALLBOT_WORKER_RELAY_PORT", "").strip()
    if (
        not port.isdigit()
        or _run(
            ["curl", "-fsS", "--max-time", "10", f"http://127.0.0.1:{port}/health"],
            check=False,
        ).returncode
    ):
        raise ReleaseError("recovered Worker relay health check failed")


def _cloud_release_dir(sha: str, track: str | None = None) -> str:
    root = "/var/lib/allbot/releases"
    if track in RELEASE_TRACKS:
        root += f"/{track}"
    return f"{root}/{sha}"


def _cloud_release_env_candidates(sha: str, track: str | None) -> tuple[str, ...]:
    primary = _cloud_release_dir(sha, track) + "/release.env"
    if track not in RELEASE_TRACKS:
        return (primary,)
    legacy = _cloud_release_dir(sha) + "/release.env"
    return (primary, legacy)


def _cloud_release_env_selection_script(
    sha: str,
    track: str | None,
    *,
    variable: str,
) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", variable):
        raise ReleaseError("invalid release environment variable")
    candidates = _cloud_release_env_candidates(sha, track)
    lines = [f"{variable}={shlex.quote(candidates[0])}"]
    lines.extend(
        f'[ -f "${variable}" ] || {variable}={shlex.quote(candidate)}'
        for candidate in candidates[1:]
    )
    lines.append(f'test -f "${variable}"')
    return "\n".join(lines)


def _cloud_compose_command(
    args: argparse.Namespace,
    sha: str,
    *,
    track: str | None = None,
    release_env_variable: str | None = None,
    services: Iterable[str] = (),
) -> str:
    environment = ENVIRONMENT[args.env]
    checkout = f"{args.remote_checkout_root}/releases/{sha}"
    env_file = args.remote_env_file or environment["env_file"]
    if release_env_variable is None:
        release_env = shlex.quote(_cloud_release_dir(sha, track) + "/release.env")
    else:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", release_env_variable):
            raise ReleaseError("invalid release environment variable")
        release_env = f'"${release_env_variable}"'
    return (
        f"docker compose --project-name {shlex.quote(environment['project'])} "
        f"--env-file {shlex.quote(checkout + '/deploy/env.defaults')} "
        f"--env-file {shlex.quote(env_file)} "
        f"--env-file {release_env} "
        f"-f {shlex.quote(checkout + '/deploy/docker-compose-cloud-base.yml')} "
        f"-f {shlex.quote(checkout + '/' + environment['overlay'])} "
        f"{compose_profile_flags(services)}"
    )


def _rollback_cloud_stack(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    transaction: Mapping[str, Any],
    environment_values: Mapping[str, str],
) -> None:
    if transaction.get("execution_profile") == "streamlined":
        if bool(getattr(args, "streamlined_cloud_rolled_back", False)):
            return
        raise ReleaseError("streamlined target rollback was not verified")
    environment = ENVIRONMENT[args.env]
    host = args.remote_host or environment["host"]
    selected, _ = filter_enabled_cloud_services(
        args.env,
        cloud_services_for_release(args.env, impact),
        environment_values,
    )
    services = sorted(selected)
    if not services:
        return
    service_words = " ".join(shlex.quote(service) for service in services)
    previous = transaction.get("previous")
    if not isinstance(previous, Mapping):
        raise ReleaseError("transaction previous stack is invalid")
    previous_kind = previous.get("kind")
    track = (
        str(transaction["track"])
        if transaction.get("track") in RELEASE_TRACKS
        else None
    )
    previous_artifacts = previous.get("artifacts")
    rollback_env_path = previous.get("rollback_release_env_path")
    if (
        transaction.get("schema_version") == 2
        and isinstance(previous_artifacts, Mapping)
        and isinstance(rollback_env_path, str)
    ):
        target_sha = validate_full_sha(str(transaction.get("target_sha", "")))
        compose = _cloud_compose_command(
            args,
            target_sha,
            track=track,
            release_env_variable="rollback_release_env",
            services=services,
        )
        checks = ""
        removals = ""
        restore_services: list[str] = []
        artifact_by_service = {
            service: artifact for artifact, service in PROMOTE_ARTIFACT_SERVICE.items()
        }
        for service in services:
            artifact_name = artifact_by_service.get(service)
            artifact = previous_artifacts.get(artifact_name or "")
            if isinstance(artifact, Mapping) and artifact.get("absent") is True:
                removals += f"""ids="$({compose} ps -aq {shlex.quote(service)})"
for id in $ids; do docker rm -f "$id" >/dev/null; done
test -z "$({compose} ps -aq {shlex.quote(service)})"
"""
                continue
            if not isinstance(artifact, Mapping) or not artifact.get("ref"):
                raise ReleaseError(f"rollback identity is unavailable for {service}")
            restore_services.append(service)
            ref = str(artifact["ref"])
            revision = str(
                _active_service_config_revision(args, artifact_name or "")
                or artifact.get("config_revision")
                or ""
            )
            revision_check = (
                "test \"$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \"$id\" | "
                "sed -n 's/^ALLBOT_CONFIG_REVISION=//p')\" = "
                f"{shlex.quote(revision)}\n"
                if revision
                else ""
            )
            checks += f"""id="$({compose} ps -q {shlex.quote(service)})"
test -n "$id"
test "$(docker inspect --format '{{{{.Config.Image}}}}' "$id")" = {shlex.quote(ref)}
health="$(docker inspect --format '{{{{if .State.Health}}}}{{{{.State.Health.Status}}}}{{{{else}}}}{{{{.State.Status}}}}{{{{end}}}}' "$id")"
[ "$health" = healthy ] || [ "$health" = running ]
{revision_check}"""
        restore_words = " ".join(
            shlex.quote(service) for service in restore_services
        )
        restore_command = (
            f"{compose} up -d --no-deps --wait --wait-timeout 180 {restore_words}\n"
            if restore_services
            else ""
        )
        script = f"""set -euo pipefail
rollback_release_env={shlex.quote(rollback_env_path)}
test -f "$rollback_release_env"
{compose} config -q
{removals}{restore_command}
{checks}"""
    elif previous_kind == "legacy":
        target_sha = str(transaction["target_sha"])
        snapshot = _cloud_release_dir(target_sha, track) + "/legacy-cloud-running.txt"
        project = environment["project"]
        removal = ""
        for service in services:
            removal += (
                'ids="$(docker ps -aq '
                f"--filter label=com.docker.compose.project={shlex.quote(project)} "
                f'--filter label=com.docker.compose.service={shlex.quote(service)})"\n'
                '[ -z "$ids" ] || docker rm -f $ids\n'
            )
        expected_legacy = " ".join(
            shlex.quote(name) for name in legacy_cloud_containers(args.env, services)
        )
        script = f"""set -euo pipefail
{removal}if [ -s {shlex.quote(snapshot)} ]; then
  while read -r name; do [ -z "$name" ] || docker start "$name" >/dev/null; done < {shlex.quote(snapshot)}
else
  for name in {expected_legacy}; do
    test "$(docker inspect --format '{{{{.State.Running}}}}' "$name" 2>/dev/null)" = true && printf '%s\\n' "$name"
  done > {shlex.quote(snapshot + ".recovered")}
  test -s {shlex.quote(snapshot + ".recovered")}
fi
source_file={shlex.quote(snapshot)}
[ -s "$source_file" ] || source_file={shlex.quote(snapshot + ".recovered")}
while read -r name; do
  [ -z "$name" ] && continue
  test "$(docker inspect --format '{{{{.State.Running}}}}' "$name")" = true
  deadline=$(( $(date +%s) + 180 ))
  while true; do
    health="$(docker inspect --format '{{{{if .State.Health}}}}{{{{.State.Health.Status}}}}{{{{else}}}}none{{{{end}}}}' "$name")"
    [ "$health" = healthy ] || [ "$health" = none ] && break
    [ "$(date +%s)" -lt "$deadline" ] || exit 1
    sleep 2
  done
done < "$source_file"
"""
    elif previous_kind == "immutable":
        previous_sha = validate_full_sha(str(previous.get("git_sha", "")))
        release_env_selection = _cloud_release_env_selection_script(
            previous_sha,
            track,
            variable="previous_release_env",
        )
        compose = _cloud_compose_command(
            args,
            previous_sha,
            track=track,
            release_env_variable="previous_release_env",
            services=services,
        )
        script = f"""set -euo pipefail
test -d {shlex.quote(args.remote_checkout_root + "/releases/" + previous_sha)}
{release_env_selection}
{compose} config -q
{compose} up -d --no-deps --wait --wait-timeout 180 {service_words}
{compose} ps {service_words}
"""
    else:
        raise ReleaseError("transaction previous cloud kind is invalid")
    _remote_shell(host, script, execute=True)


def _clear_transaction_maintenance(
    args: argparse.Namespace, transaction: Mapping[str, Any]
) -> None:
    previous = transaction.get("previous")
    initial = isinstance(previous, Mapping) and previous.get("kind") == "legacy"
    paths = maintenance_files(args.env, initial_cutover=initial)
    track = transaction.get("track")
    transaction_id = str(transaction["transaction_id"])
    staged = _transaction_state_path(
        args.env,
        transaction_id,
        str(track) if track in RELEASE_TRACKS else None,
    )
    track_segment = f"/{track}" if track in RELEASE_TRACKS else ""
    state_root = f"/var/lib/allbot/deployments/{args.env}{track_segment}"
    current = f"{state_root}/current.json"
    history = f"{state_root}/history/{transaction_id}.json"
    forward_commit = transaction.get("phase") == "state_completed"
    state_action = f"rm -f {shlex.quote(staged)}\n"
    if forward_commit:
        prepared_history = history + ".prepared"
        history_source = staged
        current_source = staged
        if args.execute and track in RELEASE_TRACKS:
            host = args.remote_host or ENVIRONMENT[args.env]["host"]
            staged_result = _run(
                ["ssh", "-o", "BatchMode=yes", host, f"cat {shlex.quote(staged)}"]
            )
            try:
                staged_state = json.loads(staged_result.stdout)
            except json.JSONDecodeError as exc:
                raise ReleaseError("staged artifact state is invalid") from exc
            history_result = _run(
                ["ssh", "-o", "BatchMode=yes", host, f"cat {shlex.quote(history)}"],
                check=False,
            )
            existing_history: Mapping[str, Any] | None = None
            if history_result.returncode == 0:
                try:
                    loaded_history = json.loads(history_result.stdout)
                except json.JSONDecodeError as exc:
                    raise ReleaseError("artifact history is invalid") from exc
                if isinstance(loaded_history, Mapping):
                    existing_history = loaded_history
            merged_payload = (
                json.dumps(
                    merge_artifact_history_state(existing_history, staged_state),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
            _run(
                [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    host,
                    f"set -e; cat > {shlex.quote(prepared_history)}",
                ],
                input_text=merged_payload,
            )
            history_source = prepared_history
            current_result = _run(
                ["ssh", "-o", "BatchMode=yes", host, f"cat {shlex.quote(current)}"],
                check=False,
            )
            existing_current: Mapping[str, Any] | None = None
            if current_result.returncode == 0:
                try:
                    loaded_current = json.loads(current_result.stdout)
                except json.JSONDecodeError as exc:
                    raise ReleaseError("artifact current state is invalid") from exc
                if isinstance(loaded_current, Mapping):
                    existing_current = loaded_current
            prepared_current = current + ".prepared"
            current_payload = (
                json.dumps(
                    merge_artifact_current_state(existing_current, staged_state),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
            _run(
                [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    host,
                    f"set -e; cat > {shlex.quote(prepared_current)}",
                ],
                input_text=current_payload,
            )
            current_source = prepared_current
        state_action = (
            f"test -s {shlex.quote(staged)}\n"
            f"install -d -m 755 {shlex.quote(str(Path(history).parent))}\n"
            f"cp {shlex.quote(history_source)} {shlex.quote(history + '.tmp')}\n"
            f"mv -f {shlex.quote(history + '.tmp')} {shlex.quote(history)}\n"
            f"rm -f {shlex.quote(prepared_history)}\n"
            f"mv -f {shlex.quote(current_source)} {shlex.quote(current)}\n"
            f"rm -f {shlex.quote(staged)}\n"
        )
    elif args.execute:
        previous_state = (
            previous.get("state") if isinstance(previous, Mapping) else None
        )
        host = args.remote_host or ENVIRONMENT[args.env]["host"]
        if isinstance(previous_state, Mapping):
            payload = (
                json.dumps(previous_state, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n"
            )
            restore = (
                f"set -e; cat > {shlex.quote(current + '.restore')}; "
                f"mv -f {shlex.quote(current + '.restore')} {shlex.quote(current)}"
            )
            _run(
                ["ssh", "-o", "BatchMode=yes", host, restore],
                input_text=payload,
            )
        else:
            remove_target = (
                f"if test -f {shlex.quote(current)} && "
                f"grep -Fq {shlex.quote(str(transaction['target_sha']))} "
                f"{shlex.quote(current)}; then rm -f {shlex.quote(current)}; fi"
            )
            _remote_shell(host, remove_target, execute=True)
    script = (
        "set -euo pipefail\n"
        + state_action
        + "".join(f"rm -f {shlex.quote(path)}\n" for path in paths)
    )
    host = args.remote_host or ENVIRONMENT[args.env]["host"]
    _remote_shell(host, script, execute=args.execute)


def verify_deploy_module_no_change(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    environment_values: Mapping[str, str],
    config_revision: str,
    service_config_revisions: Mapping[str, str] | None = None,
) -> dict[str, Any] | None:
    """Return verified runtime identity only when a module is already exact.

    The remote script emits image references only. It compares release/config
    identity inside the container without returning the rest of Config.Env.
    """

    if manifest.get("schema_version") != 2 or "web-static" in impact.services:
        return None
    selected_services, _ = filter_enabled_cloud_services(
        args.env,
        cloud_services_for_release(args.env, impact),
        environment_values,
    )
    if not selected_services:
        return None
    service_to_artifact = {
        service: artifact for artifact, service in CONTROL_ARTIFACT_SERVICE.items()
    }
    service_to_artifact.update(
        {
            name: name
            for name in CONTROL_ARTIFACT_ENV
            if name not in {"imgproxy", "postgres", "redis"}
        }
    )
    expected: dict[str, tuple[str, str, str, str]] = {}
    for service in sorted(selected_services):
        artifact_name = service_to_artifact.get(service)
        artifact = manifest.get("artifacts", {}).get(artifact_name)
        if (
            not artifact_name
            or not isinstance(artifact, Mapping)
            or not isinstance(artifact.get("ref"), str)
            or not DIGEST_IMAGE_RE.fullmatch(str(artifact["ref"]))
            or not FULL_SHA_RE.fullmatch(str(artifact.get("oci_revision", "")))
        ):
            return None
        expected_revision = (
            str(
                service_config_revisions.get(service)
                or service_config_revisions.get(artifact_name, "")
            )
            if isinstance(service_config_revisions, Mapping)
            else config_revision
        )
        if not expected_revision:
            return None
        expected[service] = (
            artifact_name,
            str(artifact["ref"]),
            expected_revision,
            str(artifact["oci_revision"]),
        )
    project = ENVIRONMENT[args.env]["project"]
    lines = ["set -eu"]
    for service, (
        _artifact_name,
        ref,
        expected_revision,
        expected_oci_revision,
    ) in expected.items():
        lines.extend(
            [
                (
                    'container_ids="$(docker ps -q '
                    f"--filter label=com.docker.compose.project={shlex.quote(project)} "
                    f'--filter label=com.docker.compose.service={shlex.quote(service)})"'
                ),
                "set -- $container_ids",
                'test "$#" -eq 1',
                'container_id="$1"',
                (
                    "actual_image=\"$(docker inspect --format '{{.Config.Image}}' "
                    '"$container_id")"'
                ),
                f'test "$actual_image" = {shlex.quote(ref)}',
                (
                    "docker image inspect --format '{{json .RepoDigests}}' "
                    '"$actual_image" | grep -F '
                    + shlex.quote('"' + ref + '"')
                    + " >/dev/null"
                ),
                (
                    "test \"$(docker inspect --format '{{.State.Status}}' "
                    '"$container_id")" = running'
                ),
                (
                    "test \"$(docker inspect --format "
                    "'{{ index .Config.Labels \"org.opencontainers.image.revision\" }}' "
                    '"$container_id")" = '
                    + shlex.quote(expected_oci_revision)
                ),
                (
                    'health="$(docker inspect --format '
                    "'{{if .State.Health}}{{.State.Health.Status}}{{end}}' "
                    '"$container_id")"; '
                    'test -z "$health" -o "$health" = healthy'
                ),
                (
                    "test \"$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "
                    '"$container_id" | sed -n \'s/^ALLBOT_CONFIG_REVISION=//p\')" = '
                    + shlex.quote(expected_revision)
                ),
                f"printf '%s\\t%s\\n' {shlex.quote(service)} \"$actual_image\"",
            ]
        )
    host = args.remote_host or ENVIRONMENT[args.env]["host"]
    result = _run(
        ["ssh", "-o", "BatchMode=yes", host, "bash -s"],
        input_text="\n".join(lines) + "\n",
        check=False,
    )
    if result.returncode != 0:
        return None
    actual: dict[str, dict[str, str]] = {}
    for line in result.stdout.splitlines():
        service, separator, ref = line.partition("\t")
        if not separator or service not in expected or ref != expected[service][1]:
            return None
        artifact_name = expected[service][0]
        actual[artifact_name] = {
            "service": service,
            "ref": ref,
            "digest": ref.rsplit("@", 1)[1],
        }
    if len(actual) != len(expected):
        return None
    return {
        "status": "no-change",
        "environment": args.env,
        "git_sha": manifest["git_sha"],
        "config_revision": config_revision,
        "service_config_revisions": {
            artifact: revision
            for _service, (artifact, _ref, revision, _oci_revision) in expected.items()
        },
        "artifacts": actual,
        "health": "verified",
    }


def _recorded_target_digests_match(
    manifest: Mapping[str, Any],
    previous_state: Mapping[str, Any] | None,
) -> bool:
    """Use state only to avoid an unnecessary runtime no-op probe for known changes."""

    current_artifacts = (
        previous_state.get("artifacts")
        if isinstance(previous_state, Mapping)
        else None
    )
    if not isinstance(current_artifacts, Mapping):
        return False
    selected = manifest.get("selected_artifacts")
    if not isinstance(selected, list) or not selected:
        return False
    compared = 0
    for name in selected:
        target = manifest.get("artifacts", {}).get(name)
        if not isinstance(target, Mapping) or target.get("kind") != "image":
            continue
        current = current_artifacts.get(name)
        if not isinstance(current, Mapping):
            return False
        target_digest = target.get("digest") or (
            str(target.get("ref", "")).rsplit("@", 1)[-1]
        )
        current_digest = current.get("digest") or current.get("sha256")
        if not DIGEST_RE.fullmatch(str(target_digest)) or current_digest != target_digest:
            return False
        compared += 1
    return compared > 0


def _enable_transaction_maintenance(
    args: argparse.Namespace, transaction: Mapping[str, Any]
) -> None:
    previous = transaction.get("previous")
    initial = isinstance(previous, Mapping) and previous.get("kind") == "legacy"
    script = "set -euo pipefail\n" + "".join(
        f"install -d -m 755 {shlex.quote(str(Path(path).parent))}\n"
        f"touch {shlex.quote(path)}\n"
        for path in maintenance_files(args.env, initial_cutover=initial)
    )
    host = args.remote_host or ENVIRONMENT[args.env]["host"]
    _remote_shell(host, script, execute=args.execute)


def _validate_recovered_stack(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    transaction: Mapping[str, Any],
    environment_values: Mapping[str, str],
) -> None:
    previous = transaction.get("previous")
    if not isinstance(previous, Mapping):
        raise ReleaseError("transaction previous stack is invalid")
    attempted_value = transaction.get("attempted_stages")
    if not isinstance(attempted_value, list) or any(
        stage not in {"cloud", "worker", "pages", "state"} for stage in attempted_value
    ):
        raise ReleaseError("transaction attempted_stages is invalid")
    attempted = set(attempted_value)
    selected_cloud, _ = filter_enabled_cloud_services(
        args.env,
        cloud_services_for_release(args.env, impact),
        environment_values,
    )
    if "cloud" in attempted and selected_cloud:
        environment = ENVIRONMENT[args.env]
        host = args.remote_host or environment["host"]
        previous_artifacts = previous.get("artifacts")
        script: str | None = None
        if transaction.get("schema_version") == 2 and isinstance(
            previous_artifacts, Mapping
        ):
            runtime = inspect_promote_runtime_artifacts(args)
            service_to_artifact = {
                service: artifact
                for artifact, service in PROMOTE_ARTIFACT_SERVICE.items()
            }
            for service in selected_cloud:
                artifact_name = service_to_artifact.get(service)
                expected = previous_artifacts.get(artifact_name or "")
                actual = runtime.get(artifact_name or "")
                expected_revision = _active_service_config_revision(
                    args, artifact_name or ""
                ) or (
                    expected.get("config_revision")
                    if isinstance(expected, Mapping)
                    else None
                )
                if (
                    isinstance(expected, Mapping)
                    and expected.get("absent") is True
                ):
                    if isinstance(actual, Mapping) and actual.get("ref"):
                        raise ReleaseError(
                            f"recovered artifact identity is incorrect: {artifact_name}"
                        )
                    continue
                if (
                    not isinstance(expected, Mapping)
                    or not isinstance(actual, Mapping)
                    or actual.get("ref") != expected.get("ref")
                    or actual.get("health") not in {"healthy", "running"}
                    or (
                        expected_revision
                        and actual.get("config_revision")
                        != expected_revision
                    )
                ):
                    raise ReleaseError(
                        f"recovered artifact identity is incorrect: {artifact_name}"
                    )
        elif previous.get("kind") == "legacy":
            track = (
                str(transaction["track"])
                if transaction.get("track") in RELEASE_TRACKS
                else None
            )
            snapshot = (
                _cloud_release_dir(str(transaction["target_sha"]), track)
                + "/legacy-cloud-running.txt"
            )
            script = f"""set -euo pipefail
source_file={shlex.quote(snapshot)}
[ -s "$source_file" ] || source_file={shlex.quote(snapshot + ".recovered")}
test -s "$source_file"
while read -r name; do
  [ -z "$name" ] && continue
  test "$(docker inspect --format '{{{{.State.Running}}}}' "$name")" = true
  health="$(docker inspect --format '{{{{if .State.Health}}}}{{{{.State.Health.Status}}}}{{{{else}}}}none{{{{end}}}}' "$name")"
  [ "$health" = healthy ] || [ "$health" = none ]
done < "$source_file"
"""
        else:
            previous_sha = validate_full_sha(str(previous.get("git_sha", "")))
            track = (
                str(transaction["track"])
                if transaction.get("track") in RELEASE_TRACKS
                else None
            )
            release_env_selection = _cloud_release_env_selection_script(
                previous_sha,
                track,
                variable="previous_release_env",
            )
            compose = _cloud_compose_command(
                args,
                previous_sha,
                track=track,
                release_env_variable="previous_release_env",
                services=selected_cloud,
            )
            services = " ".join(shlex.quote(item) for item in sorted(selected_cloud))
            script = f"""set -euo pipefail
{release_env_selection}
for service in {services}; do
  container_id="$({compose} ps -q "$service")"
  test -n "$container_id"
  test "$(docker inspect --format '{{{{.State.Running}}}}' "$container_id")" = true
  health="$(docker inspect --format '{{{{if .State.Health}}}}{{{{.State.Health.Status}}}}{{{{else}}}}none{{{{end}}}}' "$container_id")"
  [ "$health" = healthy ] || [ "$health" = none ]
done
"""
        if script is not None:
            _remote_shell(host, script, execute=True)
        non_target_snapshot = previous.get("non_target_snapshot_path")
        if isinstance(non_target_snapshot, str):
            non_target_script = f"""set -euo pipefail
test -f {shlex.quote(non_target_snapshot)}
while IFS=$'\t' read -r container_id image started_at; do
  test -n "$container_id"
  test "$(docker inspect --format '{{{{.Config.Image}}}}' "$container_id")" = "$image"
  test "$(docker inspect --format '{{{{.State.StartedAt}}}}' "$container_id")" = "$started_at"
done < {shlex.quote(non_target_snapshot)}
"""
            _remote_shell(host, non_target_script, execute=True)
    if args.env == "test" and "worker" in attempted and "worker" in impact.services:
        port = environment_values.get("ALLBOT_WORKER_RELAY_PORT", "").strip()
        if (
            not port.isdigit()
            or _run(
                [
                    "curl",
                    "-fsS",
                    "--max-time",
                    "10",
                    f"http://127.0.0.1:{port}/health",
                ],
                check=False,
            ).returncode
        ):
            raise ReleaseError("recovered Worker relay is unhealthy")
        selected = _split_services(
            [environment_values.get("ALLBOT_WORKER_SERVICES", "")]
        )
        expected_agents = {
            environment_values.get(
                f"ALLBOT_WORKER_{service.removeprefix('worker-')}_AGENT_ID", ""
            ).strip()
            for service in selected
        }
        expected_agents.discard("")
        central = environment_values.get("ALLBOT_WORKER_CENTRAL_API_URL", "").rstrip(
            "/"
        )
        deadline = time.monotonic() + 180
        while True:
            response = _run(
                ["curl", "-fsS", "--max-time", "10", f"{central}/system/workers"],
                check=False,
            )
            observed: set[str] = set()
            if response.returncode == 0:
                try:
                    document = json.loads(response.stdout)
                except json.JSONDecodeError:
                    document = {}
                workers = (
                    document.get("workers") if isinstance(document, Mapping) else None
                )
                if isinstance(workers, list):
                    observed = {
                        str(item.get("agent_id"))
                        for item in workers
                        if isinstance(item, Mapping)
                        and item.get("agent_id")
                        and item.get("status") not in {"error", "quarantined"}
                    }
            if expected_agents and expected_agents <= observed:
                break
            if time.monotonic() >= deadline:
                raise ReleaseError("recovered Worker heartbeat verification failed")
            time.sleep(5)
    if "pages" in attempted and "web-static" in impact.services:
        expected = previous.get("pages_deployment_id")
        if not expected or _current_pages_deployment_id(args) != str(expected):
            raise ReleaseError("recovered Pages canonical deployment is incorrect")
        previous_state = previous.get("state")
        web = (
            previous_state.get("web_deployment")
            if isinstance(previous_state, Mapping)
            else None
        )
        if isinstance(web, Mapping) and web.get("runtime_config_revision"):
            previous_sha = validate_full_sha(str(previous_state.get("git_sha", "")))
            _verify_canonical_pages_runtime(
                args, previous_sha, str(web["runtime_config_revision"])
            )


def _transaction_dependencies(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    release_env: str,
    environment_values: Mapping[str, str],
    config_revision: str,
    transaction: dict[str, Any],
) -> ReleaseTransactionDependencies:
    web_result: dict[str, Mapping[str, Any] | None] = {"value": None}

    def deploy_pages() -> Mapping[str, Any] | None:
        if "web-static" not in impact.services:
            return None
        value = _deploy_web(args, manifest)
        web_result["value"] = value
        return value

    def stage_state() -> None:
        state_transaction = dict(transaction)
        state_transaction["completed_stages"] = [
            *transaction.get("completed_stages", []),
            "state",
        ]
        _write_state(
            args,
            impact,
            manifest,
            config_revision,
            web_deployment=web_result["value"],
            transaction=state_transaction,
            stage_only=True,
        )

    def persist(value: Mapping[str, Any]) -> None:
        if args.execute:
            _write_transaction_journal(args, value)
        else:
            print(
                "[dry-run] persist transaction journal "
                f"{value.get('transaction_id')} phase={value.get('phase')}"
            )

    def validate_recovery() -> None:
        if (
            transaction.get("execution_profile") == "streamlined"
            and bool(getattr(args, "streamlined_cloud_rolled_back", False))
        ):
            return
        _validate_recovered_stack(args, impact, transaction, environment_values)

    def clear_maintenance() -> None:
        if (
            transaction.get("execution_profile") == "streamlined"
            and transaction.get("phase") != "state_completed"
        ):
            return
        _clear_transaction_maintenance(args, transaction)

    return ReleaseTransactionDependencies(
        cloud=lambda: _deploy_cloud(
            args, impact, manifest, release_env, environment_values
        ),
        worker=(
            (
                lambda: _deploy_worker(
                    args, impact, manifest, release_env, environment_values
                )
            )
            if args.env == "test" and "worker" in impact.services
            else (lambda: None)
        ),
        pages=deploy_pages,
        state=stage_state,
        rollback_pages=(
            (lambda: _rollback_pages(args, transaction))
            if "web-static" in impact.services and not args.skip_web
            else (lambda: None)
        ),
        rollback_worker=(
            (lambda: _rollback_worker_stack(args, transaction, environment_values))
            if args.env == "test" and "worker" in impact.services
            else (lambda: None)
        ),
        rollback_cloud=lambda: _rollback_cloud_stack(
            args, impact, transaction, environment_values
        ),
        validate_recovery=validate_recovery,
        clear_maintenance=clear_maintenance,
        journal=persist,
        enable_maintenance=lambda: _enable_transaction_maintenance(args, transaction),
    )


def _recovery_dependencies(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    transaction: dict[str, Any],
    environment_values: Mapping[str, str],
) -> ReleaseTransactionDependencies:
    return ReleaseTransactionDependencies(
        cloud=lambda: None,
        worker=lambda: None,
        pages=lambda: None,
        state=lambda: None,
        rollback_pages=(
            (lambda: _rollback_pages(args, transaction))
            if "web-static" in impact.services
            else (lambda: None)
        ),
        rollback_worker=(
            (lambda: _rollback_worker_stack(args, transaction, environment_values))
            if args.env == "test" and "worker" in impact.services
            else (lambda: None)
        ),
        rollback_cloud=lambda: _rollback_cloud_stack(
            args, impact, transaction, environment_values
        ),
        validate_recovery=lambda: _validate_recovered_stack(
            args, impact, transaction, environment_values
        ),
        clear_maintenance=lambda: _clear_transaction_maintenance(args, transaction),
        journal=lambda value: _write_transaction_journal(args, value),
        enable_maintenance=lambda: _enable_transaction_maintenance(args, transaction),
    )


def _read_test_release_state(
    args: argparse.Namespace,
    manifest: Mapping[str, Any],
    *,
    artifact_history: bool = False,
) -> dict[str, Any]:
    host = args.test_state_host
    state_root = (
        f"/var/lib/allbot/deployments/test/{manifest['track']}"
        if manifest.get("schema_version") == 2
        else "/var/lib/allbot/deployments/test"
    )
    state_path = (
        f"{state_root}/history/{manifest['git_sha']}.json"
        if args.command == "rollback"
        or (artifact_history and manifest.get("schema_version") == 2)
        else f"{state_root}/current.json"
    )
    result = _run(
        ["ssh", "-o", "BatchMode=yes", host, f"cat {state_path}"],
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseError("production promotion requires a cloud-test release state")
    try:
        state = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ReleaseError("cloud-test release state is invalid") from exc
    if not isinstance(state, dict):
        raise ReleaseError("cloud-test release state is invalid")
    return state


def _read_test_artifact_evidence(
    args: argparse.Namespace, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Resolve verified v2 evidence by track, artifact name, and exact digest."""

    track = str(manifest["track"])
    host = args.test_state_host
    history_root = f"/var/lib/allbot/deployments/test/{track}/history"
    selected = {
        name: manifest["artifacts"][name].get("digest")
        or manifest["artifacts"][name].get("sha256")
        for name in manifest.get("selected_artifacts", [])
    }
    evidence: dict[str, dict[str, Any]] = {}
    sources: dict[str, str] = {}
    non_main_evidence_seen = False

    def collect(state: Mapping[str, Any]) -> None:
        nonlocal non_main_evidence_seen
        if state.get("track") != track:
            return
        artifacts = state.get("artifacts")
        if not isinstance(artifacts, Mapping):
            return
        if state.get("release_channel", "main") != "main":
            non_main_evidence_seen = non_main_evidence_seen or any(
                isinstance(artifacts.get(name), Mapping)
                and artifacts[name].get("status") == "verified"
                and artifacts[name].get("digest") == expected_digest
                for name, expected_digest in selected.items()
            )
            return
        source_sha = str(state.get("git_sha", ""))
        for name, expected_digest in selected.items():
            candidate = artifacts.get(name)
            if (
                name not in evidence
                and isinstance(candidate, Mapping)
                and candidate.get("status") == "verified"
                and candidate.get("digest") == expected_digest
            ):
                evidence[name] = dict(candidate)
                sources[name] = source_sha

    try:
        collect(_read_test_release_state(args, manifest, artifact_history=True))
    except ReleaseError:
        pass
    if set(evidence) != set(selected):
        find_command = (
            f"find {shlex.quote(history_root)} -maxdepth 1 -type f "
            "-regextype posix-extended "
            "-regex '.*/[0-9a-f]{40}\\.json' -print0 "
            "| sort -z -r | while IFS= read -r -d '' path; do "
            "printf '%s\\t' \"$path\"; cat \"$path\"; printf '\\0'; done"
        )
        listing = _run(
            ["ssh", "-o", "BatchMode=yes", host, find_command],
            check=False,
        )
        if listing.returncode == 0:
            for record in listing.stdout.split("\0"):
                if set(evidence) == set(selected):
                    break
                if not record:
                    continue
                path, separator, payload = record.partition("\t")
                if not separator:
                    continue
                if not path.startswith(history_root + "/"):
                    continue
                basename = Path(path).name
                if not re.fullmatch(r"[0-9a-f]{40}\.json", basename):
                    continue
                try:
                    state = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if isinstance(state, Mapping):
                    collect(state)
    missing = sorted(set(selected) - set(evidence))
    if missing:
        if non_main_evidence_seen:
            raise ReleaseError(
                "production promotion requires a verified main-channel test state"
            )
        raise ReleaseError(
            "production promotion has no verified artifact digest evidence: "
            + ", ".join(missing)
        )
    return {
        "schema_version": 2,
        "environment": "test",
        "track": track,
        "git_sha": manifest["git_sha"],
        "release_channel": "main",
        "status": "verified",
        "artifacts": evidence,
        "evidence_sources": sources,
    }


def _git_file_at_sha(sha: str, path: str) -> str:
    sha = validate_full_sha(sha)
    return _run(["git", "show", f"{sha}:{path}"]).stdout


def _artifact_catalog_at_sha(sha: str) -> Mapping[str, Mapping[str, Any]]:
    try:
        document = json.loads(_git_file_at_sha(sha, "deploy/release-artifacts-v2.json"))
    except json.JSONDecodeError as exc:
        raise ReleaseError("release artifact catalog is invalid") from exc
    artifacts = document.get("artifacts") if isinstance(document, Mapping) else None
    if not isinstance(artifacts, Mapping):
        raise ReleaseError("release artifact catalog is invalid")
    return artifacts


def _smoke_private_worker_image(ref: str) -> None:
    result = _run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "python",
            ref,
            "-c",
            (
                "import qqcc_bot.main; import qqcc_private_bot.worker; "
                "print('private-worker-import-smoke=passed')"
            ),
        ],
        check=False,
    )
    if (
        result.returncode != 0
        or "private-worker-import-smoke=passed" not in result.stdout
    ):
        raise ReleaseError("private-bot-worker digest import smoke failed")


def _promotion_check(args: argparse.Namespace, manifest: Mapping[str, Any]) -> None:
    if args.env != "prod":
        return
    if getattr(args, "command", "") == "promote" and manifest.get("schema_version") == 2:
        decisions = resolve_promote_artifact_assurance(
            manifest.get("selected_artifacts", [])
        )
        args.promote_artifact_assurance = decisions
        standard = {
            name
            for name, decision in decisions.items()
            if decision["strategy"] == "standard"
        }
        if not standard:
            return
        evidence_manifest = dict(manifest)
        evidence_manifest["selected_artifacts"] = sorted(standard)
        state = _read_test_artifact_evidence(args, evidence_manifest)
        try:
            validate_v2_promotion(
                str(manifest["track"]),
                {name: manifest["artifacts"][name] for name in standard},
                state,
            )
        except ManifestV2Error as exc:
            raise ReleaseError(str(exc)) from exc
        return
    repair_fast_track = getattr(args, "control_plane_repair_fast_track", False)
    promoted_approval = manifest.get("promotion_approval")
    if manifest.get("schema_version") == 2 and isinstance(promoted_approval, Mapping):
        approval_artifacts = promoted_approval.get("artifacts")
        if not isinstance(approval_artifacts, Mapping):
            raise ReleaseError("promoted main bundle has no artifact approval set")
        state = {
            "schema_version": 2,
            "environment": "test",
            "track": manifest["track"],
            "git_sha": manifest["git_sha"],
            "release_channel": "main",
            "status": "verified",
            "artifacts": {
                name: approval_artifacts[name]
                for name in manifest.get("selected_artifacts", [])
                if name in approval_artifacts
            },
        }
    else:
        state = (
            _read_test_release_state(args, manifest)
            if repair_fast_track
            else _read_test_artifact_evidence(args, manifest)
            if manifest.get("schema_version") == 2
            else _read_test_release_state(args, manifest, artifact_history=True)
        )
    if repair_fast_track:
        tested_sha = validate_full_sha(str(state.get("git_sha", "")))
        target_sha = validate_full_sha(str(manifest.get("git_sha", "")))
        changed_paths = git_changed_paths(tested_sha, target_sha)
        dockerfile_path = "deploy/docker/Dockerfile.control-plane"
        evidence = validate_control_plane_repair_equivalence(
            test_state=state,
            manifest=manifest,
            tested_artifact_catalog=_artifact_catalog_at_sha(tested_sha),
            target_artifact_catalog=_artifact_catalog_at_sha(target_sha),
            changed_paths=changed_paths,
            tested_dockerfile=_git_file_at_sha(tested_sha, dockerfile_path),
            target_dockerfile=_git_file_at_sha(target_sha, dockerfile_path),
            smoke_private_image=_smoke_private_worker_image,
        )
        args.control_plane_repair_acceptance = evidence
        return
    if manifest.get("schema_version") != 2 and state.get("git_sha") != manifest.get(
        "git_sha"
    ):
        raise ReleaseError("production SHA does not match the tested SHA")
    if manifest.get("schema_version") == 2:
        if state.get("release_channel", "main") != "main":
            raise ReleaseError(
                "production promotion requires a verified main-channel test state"
            )
        try:
            validate_v2_promotion(
                str(manifest["track"]),
                {
                    name: manifest["artifacts"][name]
                    for name in manifest.get("selected_artifacts", [])
                },
                state,
            )
        except ManifestV2Error as exc:
            raise ReleaseError(str(exc)) from exc
        return
    if state.get("images") != manifest.get("images"):
        raise ReleaseError("production image digests do not match cloud-test")
    if state.get("vendor_images") != manifest.get("vendor_images"):
        raise ReleaseError("production vendor image digests do not match cloud-test")
    if state.get("web_artifact_sha256") != manifest.get("web_artifact_sha256"):
        raise ReleaseError("production Web artifact does not match cloud-test")
    if state.get("status") != "verified":
        raise ReleaseError("cloud-test release has not been marked verified")


def validate_deploy_module_approval(manifest: Mapping[str, Any]) -> None:
    """Accept either a fully tested main build or a legacy promoted approval.

    Main-first release batches are built once after the batch PR merges.  Their
    standard artifacts obtain exact-digest approval from the cloud-test history
    during production preflight; direct artifacts keep the strategy-specific
    approval path.  Older promoted bundles remain deployable for rollback and
    compatibility.
    """

    validation = manifest.get("validation")
    if (
        manifest.get("release_channel") == "main"
        and manifest.get("source_ref") == "refs/heads/main"
        and isinstance(validation, Mapping)
        and validation.get("mode") == "full"
        and validation.get("tests") == "passed"
    ):
        return
    approval = manifest.get("promotion_approval")
    artifacts = approval.get("artifacts") if isinstance(approval, Mapping) else None
    if (
        not isinstance(validation, Mapping)
        or validation.get("mode") != "promoted"
        or not isinstance(artifacts, Mapping)
    ):
        raise ReleaseError(
            "deploy-module requires a full main build or promoted main approval record"
        )
    for name in manifest.get("selected_artifacts", []):
        artifact = manifest.get("artifacts", {}).get(name)
        evidence = artifacts.get(name)
        expected = (
            artifact.get("digest") or artifact.get("sha256")
            if isinstance(artifact, Mapping)
            else None
        )
        if (
            not isinstance(evidence, Mapping)
            or evidence.get("status") not in {"verified", "approved-direct"}
            or evidence.get("digest") != expected
        ):
            raise ReleaseError(f"{name} has no exact promoted-main approval")


def validate_credential_isolation_evidence(
    evidence: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate a value-free, recent secret-isolation completion attestation."""

    if (
        set(evidence)
        != {
            "schema_version",
            "generated_at",
            "isolation",
            "health",
            "old_credentials_revoked",
        }
        or evidence.get("schema_version") != 1
    ):
        raise ReleaseError("credential isolation evidence schema is invalid")
    try:
        generated_at = datetime.fromisoformat(
            str(evidence["generated_at"]).replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ReleaseError("credential isolation evidence time is invalid") from exc
    if generated_at.tzinfo is None:
        raise ReleaseError("credential isolation evidence time must include timezone")
    current = now or datetime.now(timezone.utc)
    age = (current - generated_at.astimezone(timezone.utc)).total_seconds()
    if age < -300 or age > 3600:
        raise ReleaseError("credential isolation evidence is stale or from the future")
    isolation = evidence.get("isolation")
    if not isinstance(isolation, Mapping) or set(isolation) != {
        "checked_keys",
        "reused_keys",
    }:
        raise ReleaseError("credential isolation challenge evidence is invalid")
    checked = isolation.get("checked_keys")
    reused = isolation.get("reused_keys")
    if (
        not isinstance(checked, list)
        or not all(isinstance(key, str) for key in checked)
        or not REQUIRED_ISOLATED_SECRET_KEYS.issubset(set(checked))
        or not isinstance(reused, list)
        or reused
    ):
        raise ReleaseError("credential isolation challenge is incomplete or reused")
    health = evidence.get("health")
    required_health = {"test_worker", "prod_control_plane", "prod_workers"}
    if (
        not isinstance(health, Mapping)
        or set(health) != required_health
        or any(health.get(name) is not True for name in required_health)
    ):
        raise ReleaseError("credential isolation health evidence is incomplete")
    if evidence.get("old_credentials_revoked") is not True:
        raise ReleaseError("old credentials have not been confirmed revoked")
    return {
        "schema_version": 1,
        "generated_at": generated_at.astimezone(timezone.utc).isoformat(),
        "isolation": {
            "checked_keys": sorted(set(checked)),
            "reused_keys": [],
        },
        "health": {name: True for name in sorted(required_health)},
        "old_credentials_revoked": True,
    }


def _write_remote_credential_isolation_status(
    host: str,
    environment: str,
    status: str,
    audit: Mapping[str, Any],
) -> None:
    if status not in {"pending", "credential-isolation-complete"}:
        raise ReleaseError("invalid credential isolation status")
    root = f"/var/lib/allbot/config/{environment}"
    program = r"""import hashlib,json,os,sys,tempfile
root,status,environment=sys.argv[1:]
payload=sys.stdin.read()
audit=json.loads(payload)
current_path=os.path.join(root,'current.json')
if not os.path.isfile(current_path):
    raise SystemExit('active service environment state is missing')
current=json.load(open(current_path,encoding='utf-8'))
if current.get('environment') != environment:
    raise SystemExit('active service environment identity mismatch')
os.makedirs(os.path.join(root,'credential-isolation-audit'),mode=0o700,exist_ok=True)
if status == 'credential-isolation-complete':
    digest=hashlib.sha256(payload.encode()).hexdigest()
    audit_path=os.path.join(root,'credential-isolation-audit',digest+'.json')
    if os.path.exists(audit_path) and open(audit_path,encoding='utf-8').read() != payload:
        raise SystemExit('credential isolation audit is immutable')
    if not os.path.exists(audit_path):
        fd,tmp=tempfile.mkstemp(prefix='.audit-',dir=os.path.dirname(audit_path))
        with os.fdopen(fd,'w',encoding='utf-8') as handle:
            handle.write(payload)
        os.chmod(tmp,0o600); os.replace(tmp,audit_path)
current['credential_isolation']=status
for path,text in (
    (current_path,json.dumps(current,sort_keys=True,indent=2)+'\n'),
    (os.path.join(root,'credential-isolation-status'),status+'\n'),
):
    fd,tmp=tempfile.mkstemp(prefix='.status-',dir=root)
    with os.fdopen(fd,'w',encoding='utf-8') as handle:
        handle.write(text)
    os.chmod(tmp,0o600); os.replace(tmp,path)
"""
    encoded = base64.b64encode(program.encode()).decode("ascii")
    remote_command = " ".join(
        shlex.quote(value)
        for value in (
            "python3",
            "-c",
            f"exec(__import__('base64').b64decode('{encoded}').decode())",
            root,
            status,
            environment,
        )
    )
    result = _run(
        ["ssh", "-o", "BatchMode=yes", host, remote_command],
        input_text=json.dumps(audit, sort_keys=True, indent=2) + "\n",
        check=False,
    )
    if result.returncode:
        raise ReleaseError(
            f"failed to write credential isolation status for {environment}"
        )


def complete_credential_isolation(
    args: argparse.Namespace, evidence: Mapping[str, Any]
) -> dict[str, Any]:
    completed_at = datetime.now(timezone.utc).isoformat()
    audit = {
        "schema_version": 1,
        "status": "credential-isolation-complete",
        "completed_at": completed_at,
        "evidence": dict(evidence),
    }
    audit_sha256 = hashlib.sha256(
        json.dumps(audit, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    audit["audit_sha256"] = audit_sha256
    targets = [
        (args.test_host or ENVIRONMENT["test"]["host"], "test"),
        (args.prod_host or ENVIRONMENT["prod"]["host"], "prod"),
    ]
    completed: list[tuple[str, str]] = []
    try:
        for host, environment in targets:
            _write_remote_credential_isolation_status(
                host, environment, "credential-isolation-complete", audit
            )
            completed.append((host, environment))
    except ReleaseError as exc:
        recovery_errors = []
        for host, environment in reversed(completed):
            try:
                _write_remote_credential_isolation_status(
                    host, environment, "pending", audit
                )
            except ReleaseError as recovery_error:
                recovery_errors.append(str(recovery_error))
        if recovery_errors:
            raise ReleaseError(
                "credential isolation completion failed and rollback is incomplete"
            ) from exc
        raise
    return {"audit_sha256": audit_sha256, "completed_at": completed_at}


def _test_rollback_check(args: argparse.Namespace, manifest: Mapping[str, Any]) -> None:
    if args.command != "rollback" or args.env != "test":
        return
    host = args.remote_host or ENVIRONMENT["test"]["host"]
    root = (
        f"/var/lib/allbot/deployments/test/{manifest['track']}"
        if manifest.get("schema_version") == 2
        else "/var/lib/allbot/deployments/test"
    )
    path = f"{root}/history/{manifest['git_sha']}.json"
    result = _run(["ssh", "-o", "BatchMode=yes", host, f"cat {path}"], check=False)
    if result.returncode != 0:
        raise ReleaseError("rollback target has no retained successful test release")
    try:
        state = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ReleaseError("rollback target test history is invalid") from exc
    if manifest.get("schema_version") == 2:
        expected = {
            name: artifact.get("digest") or artifact.get("sha256")
            for name, artifact in manifest["artifacts"].items()
            if name in manifest.get("selected_artifacts", [])
        }
        recorded = state.get("artifacts")
        valid = isinstance(recorded, Mapping) and all(
            isinstance(recorded.get(name), Mapping)
            and recorded[name].get("digest") == digest
            and recorded[name].get("status") == "verified"
            for name, digest in expected.items()
        )
        if not valid:
            raise ReleaseError(
                "rollback target is not the previously verified track digest set"
            )
        return
    if (
        state.get("status") != "verified"
        or state.get("images") != manifest.get("images")
        or state.get("vendor_images") != manifest.get("vendor_images")
        or state.get("web_artifact_sha256") != manifest.get("web_artifact_sha256")
    ):
        raise ReleaseError("rollback target is not the previously verified digest set")


def _parse_utc_timestamp(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReleaseError(f"test acceptance {field} is invalid") from exc
    if parsed.tzinfo is None:
        raise ReleaseError(f"test acceptance {field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def required_acceptance_checks(manifest: Mapping[str, Any]) -> set[str]:
    if manifest.get("schema_version") != 2:
        return set(REQUIRED_ACCEPTANCE_CHECKS)
    track = str(manifest.get("track", "control-plane"))
    if track == "test-execution":
        return set(WORKER_ACCEPTANCE_CHECKS)
    selected = set(manifest.get("selected_artifacts", []))
    required: set[str] = set()
    runtime = selected - NON_DEPLOYABLE_ARTIFACTS
    if not runtime:
        return set()
    if runtime & {"public-web"}:
        required.update(WEB_ACCEPTANCE_CHECKS)
    if runtime - {
        "public-web",
        "dashboard-backend",
        "dashboard-frontend",
        "qqcc-config-backend",
        "qqcc-config-frontend",
    }:
        required.update(CORE_ACCEPTANCE_CHECKS)
    if runtime & {
        "main-bot",
        "qqcc-bot",
        "private-bot-worker",
        "paid-group-bot",
    }:
        required.update(BOT_ACCEPTANCE_CHECKS)
    return required or {"health", "rollback_drill"}


def validate_test_acceptance(
    evidence: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    if evidence.get("git_sha") != manifest.get("git_sha"):
        raise ReleaseError("test acceptance SHA does not match the release")
    if manifest.get("schema_version") == 2:
        if evidence.get("track") != manifest.get("track"):
            raise ReleaseError("test acceptance track does not match the release")
        expected = {
            name: artifact.get("digest") or artifact.get("sha256")
            for name, artifact in manifest["artifacts"].items()
            if name in manifest.get("selected_artifacts", [])
        }
        if evidence.get("artifacts") != expected:
            raise ReleaseError(
                "test acceptance artifact digests do not match the release"
            )
    else:
        if evidence.get("images") != manifest.get("images"):
            raise ReleaseError("test acceptance image digests do not match the release")
        if evidence.get("vendor_images") != manifest.get("vendor_images"):
            raise ReleaseError(
                "test acceptance vendor digests do not match the release"
            )
    started = _parse_utc_timestamp(
        evidence.get("observation_started_at"), "observation_started_at"
    )
    completed = _parse_utc_timestamp(evidence.get("completed_at"), "completed_at")
    if completed <= started:
        raise ReleaseError(
            "test acceptance completed_at must be after observation_started_at"
        )
    if completed > datetime.now(timezone.utc):
        raise ReleaseError("test acceptance completed_at cannot be in the future")
    observation_duration_seconds = int((completed - started).total_seconds())
    checks = evidence.get("checks")
    required_checks = required_acceptance_checks(manifest)
    missing = sorted(
        key
        for key in required_checks
        if not isinstance(checks, Mapping) or checks.get(key) is not True
    )
    if missing:
        raise ReleaseError(
            "test acceptance checks are incomplete: " + ", ".join(missing)
        )
    return {
        "completed_at": evidence["completed_at"],
        "observation_started_at": evidence["observation_started_at"],
        "observation_duration_seconds": observation_duration_seconds,
    }


def validate_test_runtime_for_acceptance(state: Mapping[str, Any]) -> None:
    health = state.get("health")
    if not isinstance(health, Mapping):
        raise ReleaseError("cloud-test deployment health is unavailable")
    if health.get("web") not in {
        "artifact-checksum-passed",  # schema v1 compatibility
        "canonical-runtime-verified",
    }:
        raise ReleaseError(
            "cloud-test Web artifact has not passed deployment verification"
        )


def validate_v2_test_runtime_for_acceptance(
    state: Mapping[str, Any], manifest: Mapping[str, Any]
) -> None:
    """Validate only the artifacts selected by one partial track release."""

    expected_artifacts = {
        name: manifest["artifacts"][name].get("digest")
        or manifest["artifacts"][name].get("sha256")
        for name in manifest["selected_artifacts"]
    }
    state_artifacts = state.get("artifacts")
    artifacts_match = isinstance(state_artifacts, Mapping) and all(
        isinstance(state_artifacts.get(name), Mapping)
        and state_artifacts[name].get("digest") == digest
        and state_artifacts[name].get("source_sha", manifest["source_sha"])
        == manifest["artifacts"][name].get("source_sha", manifest["source_sha"])
        and state_artifacts[name].get("status") in {"deployed", "verified"}
        for name, digest in expected_artifacts.items()
    )
    if state.get("track") != manifest.get("track") or not artifacts_match:
        raise ReleaseError(
            "cloud-test runtime state does not match acceptance evidence"
        )
    health = state.get("health")
    required_health = "worker" if manifest["track"] == "test-execution" else "cloud"
    if not isinstance(health, Mapping) or health.get(required_health) not in {
        "compose-ps-passed",
        "not-targeted",
    }:
        raise ReleaseError("cloud-test track health has not passed verification")


def _mark_test_verified(args: argparse.Namespace) -> None:
    sha = validate_full_sha(args.sha)
    manifest_path = Path(args.manifest)
    raw_manifest = _read_json(manifest_path)
    if raw_manifest.get("schema_version") == 2:
        requested_modules = _split_services(args.modules)
        independent = expand_independent_module_request(
            load_structured_file(Path(getattr(args, "policy", DEFAULT_POLICY))),
            requested_modules,
        )
        if independent:
            requested_modules = independent[1]
        manifest = _load_v2_track(
            manifest_path,
            sha=sha,
            track=args.track,
            modules=requested_modules,
        )
        validate_release_channel(manifest, environment="test", purpose="verify-test")
    else:
        if getattr(
            args, "track", "control-plane"
        ) != "control-plane" or _split_services(getattr(args, "modules", [])):
            raise ReleaseError(
                "release schema v1 supports only the control-plane track"
            )
        manifest = raw_manifest
        validate_release_manifest(manifest, sha)
    host = args.remote_host or ENVIRONMENT["test"]["host"]
    track_segment = (
        f"/{manifest['track']}" if manifest.get("schema_version") == 2 else ""
    )
    state_root = f"/var/lib/allbot/deployments/test{track_segment}"
    state_path = f"{state_root}/current.json"
    result = _run(
        ["ssh", "-o", "BatchMode=yes", host, f"cat {state_path}"],
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseError("cloud-test deployment state is unavailable")
    try:
        state = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ReleaseError("cloud-test deployment state is invalid") from exc
    if state.get("git_sha") != sha:
        raise ReleaseError(
            "cloud-test runtime state does not match acceptance evidence"
        )
    if manifest.get("schema_version") == 2:
        inactive = state.get("inactive_artifacts", [])
        if not isinstance(inactive, list) or not all(
            isinstance(name, str) and name for name in inactive
        ):
            raise ReleaseError("cloud-test inactive artifact state is invalid")
        manifest = dict(manifest)
        manifest["selected_artifacts"] = [
            name
            for name in manifest.get("selected_artifacts", [])
            if name not in set(inactive)
        ]
    evidence = _read_json(Path(args.evidence))
    acceptance = validate_test_acceptance(evidence, manifest)
    if manifest.get("schema_version") == 2:
        validate_v2_test_runtime_for_acceptance(state, manifest)
    else:
        if (
            state.get("images") != manifest.get("images")
            or state.get("vendor_images") != manifest.get("vendor_images")
            or state.get("web_artifact_sha256") != manifest.get("web_artifact_sha256")
        ):
            raise ReleaseError(
                "cloud-test runtime state does not match acceptance evidence"
            )
        validate_test_runtime_for_acceptance(state)
    if manifest.get("schema_version") == 2:
        for name in manifest["selected_artifacts"]:
            artifact = state["artifacts"][name]
            artifact["status"] = "verified"
            artifact["assurance"] = "tested"
            artifact["acceptance"] = dict(acceptance)
        state["status"] = (
            "verified"
            if all(
                isinstance(artifact, Mapping) and artifact.get("status") == "verified"
                for artifact in state["artifacts"].values()
            )
            else "partial"
        )
    else:
        state["status"] = "verified"
    state["acceptance"] = acceptance
    if not args.execute:
        print(f"[dry-run] mark cloud-test {sha} verified on {host}")
        return
    payload = json.dumps(state, sort_keys=True, indent=2) + "\n"
    evidence_payload = json.dumps(evidence, sort_keys=True, indent=2) + "\n"
    acceptance_path = f"{state_root}/acceptance/{sha}.json"
    history_path = f"{state_root}/history/{sha}.json"
    history_payload = payload
    if manifest.get("schema_version") == 2:
        history_result = _run(
            ["ssh", "-o", "BatchMode=yes", host, f"cat {history_path}"],
            check=False,
        )
        history_state: Mapping[str, Any] | None = None
        if history_result.returncode == 0:
            try:
                loaded_history = json.loads(history_result.stdout)
            except json.JSONDecodeError as exc:
                raise ReleaseError("cloud-test artifact history is invalid") from exc
            if isinstance(loaded_history, Mapping):
                history_state = loaded_history
        history_payload = (
            json.dumps(
                merge_artifact_history_state(history_state, state),
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )
    _run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            host,
            (
                f"set -e; install -d -m 755 {state_root}/acceptance; "
                f"cat > {acceptance_path}.tmp; mv -f {acceptance_path}.tmp {acceptance_path}"
            ),
        ],
        input_text=evidence_payload,
    )
    _run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            host,
            f"set -e; cat > {state_path}.tmp; mv -f {state_path}.tmp {state_path}",
        ],
        input_text=payload,
    )
    _run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            host,
            f"set -e; cat > {history_path}.tmp; mv -f {history_path}.tmp {history_path}",
        ],
        input_text=history_payload,
    )


def merge_artifact_history_state(
    existing: Mapping[str, Any] | None,
    incoming: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge track/SHA history without erasing evidence for other artifacts."""

    merged = dict(incoming)
    if not existing or incoming.get("schema_version") != 2:
        return merged
    for field in ("git_sha", "track", "environment"):
        if existing.get(field) != incoming.get(field):
            raise ReleaseError(f"artifact history {field} identity mismatch")
    previous_artifacts = existing.get("artifacts")
    incoming_artifacts = incoming.get("artifacts")
    if not isinstance(previous_artifacts, Mapping) or not isinstance(
        incoming_artifacts, Mapping
    ):
        raise ReleaseError("artifact history payload is invalid")
    artifacts = {
        str(name): dict(value)
        for name, value in previous_artifacts.items()
        if isinstance(value, Mapping)
    }
    artifacts.update(
        {
            str(name): dict(value)
            for name, value in incoming_artifacts.items()
            if isinstance(value, Mapping)
        }
    )
    merged["artifacts"] = artifacts
    statuses = {str(value.get("status", "")) for value in artifacts.values()}
    merged["status"] = (
        "verified"
        if statuses == {"verified"}
        else "partial"
        if "verified" in statuses
        else str(incoming.get("status", "deployed"))
    )
    return merged


def merge_artifact_current_state(
    existing: Mapping[str, Any] | None,
    incoming: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge a partial track deployment while preserving non-target artifacts."""

    merged = dict(incoming)
    if not existing or incoming.get("schema_version") != 2:
        return merged
    for field in ("track", "environment"):
        if existing.get(field) != incoming.get(field):
            raise ReleaseError(f"artifact current state {field} identity mismatch")
    previous_artifacts = existing.get("artifacts")
    incoming_artifacts = incoming.get("artifacts")
    if not isinstance(previous_artifacts, Mapping) or not isinstance(
        incoming_artifacts, Mapping
    ):
        raise ReleaseError("artifact current state payload is invalid")
    existing_sha = str(existing.get("git_sha", ""))
    artifacts: dict[str, dict[str, Any]] = {}
    for name, value in previous_artifacts.items():
        if not isinstance(value, Mapping):
            continue
        artifact = dict(value)
        if "source_sha" not in artifact and FULL_SHA_RE.fullmatch(existing_sha):
            artifact["source_sha"] = existing_sha
        artifacts[str(name)] = artifact
    artifacts.update(
        {
            str(name): dict(value)
            for name, value in incoming_artifacts.items()
            if isinstance(value, Mapping)
        }
    )
    inactive = incoming.get("inactive_artifacts", [])
    if not isinstance(inactive, list) or not all(
        isinstance(name, str) and name for name in inactive
    ):
        raise ReleaseError("artifact current state inactive_artifacts is invalid")
    for name in inactive:
        artifacts.pop(name, None)
    merged["artifacts"] = artifacts
    return merged


def recover_artifact_current_state(
    current: Mapping[str, Any],
    history: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Recover legacy partial current state from retained successful history."""

    recovered: dict[str, Any] | None = None
    for state in (*history, current):
        normalized = dict(state)
        state_sha = str(state.get("git_sha", ""))
        state_artifacts = state.get("artifacts")
        if not isinstance(state_artifacts, Mapping):
            continue
        artifacts: dict[str, dict[str, Any]] = {}
        for name, value in state_artifacts.items():
            if not isinstance(value, Mapping):
                continue
            artifact = dict(value)
            if "source_sha" not in artifact and FULL_SHA_RE.fullmatch(state_sha):
                artifact["source_sha"] = state_sha
            artifacts[str(name)] = artifact
        normalized["artifacts"] = artifacts
        recovered = merge_artifact_current_state(recovered, normalized)
    return recovered or dict(current)


def _collect_module_runtime_state(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify and record the exact post-deploy runtime without exposing env values."""

    streamlined = getattr(args, "streamlined_runtime_services", None)
    if isinstance(streamlined, Mapping):
        artifacts = manifest.get("artifacts")
        snapshot = getattr(args, "runtime_env_snapshot", None)
        service_revisions = (
            snapshot.get("service_revisions", {})
            if isinstance(snapshot, Mapping)
            else {}
        )
        recorded: dict[str, Any] = {}
        for name in manifest.get("selected_artifacts", []):
            artifact = artifacts.get(name) if isinstance(artifacts, Mapping) else None
            observed = streamlined.get(name)
            if name == "public-web":
                continue
            if not isinstance(artifact, Mapping) or not isinstance(observed, Mapping):
                raise ReleaseError("streamlined runtime identity is incomplete")
            ref = str(artifact.get("ref", ""))
            if observed.get("ref") != ref:
                raise ReleaseError("streamlined runtime identity is not exact")
            config_name = next(
                (
                    key
                    for key, compose_service in CONFIG_SERVICE_TO_COMPOSE.items()
                    if compose_service == observed.get("service")
                ),
                name,
            )
            recorded[name] = {
                **dict(observed),
                "source_sha": artifact.get("source_sha") or manifest.get("source_sha"),
                "config_revision": service_revisions.get(config_name),
            }
        return recorded

    service_artifacts = {
        "bot": "main-bot",
        "central-api": "central-api",
        "dashboard-backend": "dashboard-backend",
        "dashboard-frontend": "dashboard-frontend",
        "paid-group-guard-bot": "paid-group-bot",
        "payment-api": "payment-api",
        "qqcc-bot": "qqcc-bot",
        "qqcc-config-backend": "qqcc-config-backend",
        "qqcc-config-frontend": "qqcc-config-frontend",
        "qqcc-private-bot-worker": "private-bot-worker",
        "support-bot": "support-bot",
        "web-api": "web-api",
    }
    environment_values: dict[str, str] = {}
    snapshot = getattr(args, "runtime_env_snapshot", None)
    if isinstance(snapshot, Mapping):
        environment_values.update(
            {str(key): "present" for key in snapshot.get("present_keys", [])}
        )
        public = snapshot.get("public_values")
        if isinstance(public, Mapping):
            environment_values.update(
                {str(key): str(value) for key, value in public.items()}
            )
    services, _ = filter_enabled_cloud_services(
        args.env, cloud_services_for_release(args.env, impact), environment_values
    )
    expected: dict[str, tuple[str, str, str, str]] = {}
    service_revisions = (
        snapshot.get("service_revisions", {}) if isinstance(snapshot, Mapping) else {}
    )
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ReleaseError("release artifacts are unavailable for runtime recording")
    for service in sorted(services):
        artifact_name = service_artifacts.get(service)
        artifact = artifacts.get(artifact_name) if artifact_name else None
        if not artifact_name or not isinstance(artifact, Mapping):
            continue
        ref = str(artifact.get("ref", ""))
        source_sha = str(artifact.get("source_sha") or manifest.get("source_sha", ""))
        revision = str(service_revisions.get(artifact_name, ""))
        if (
            not DIGEST_IMAGE_RE.fullmatch(ref)
            or not FULL_SHA_RE.fullmatch(source_sha)
            or not revision
        ):
            raise ReleaseError("runtime recording identity is incomplete")
        expected[service] = (artifact_name, ref, source_sha, revision)
    lines = ["set -euo pipefail"]
    project = ENVIRONMENT[args.env]["project"]
    for service, (_artifact, ref, source_sha, config_rev) in expected.items():
        lines.extend(
            [
                f"id=$(docker ps -q --filter label=com.docker.compose.project={shlex.quote(project)} --filter label=com.docker.compose.service={shlex.quote(service)})",
                "test \"$(printf '%s\\n' \"$id\" | sed '/^$/d' | wc -l)\" = 1",
                f'test "$(docker inspect --format \'{{{{.Config.Image}}}}\' "$id")" = {shlex.quote(ref)}',
                f"docker image inspect --format '{{{{json .RepoDigests}}}}' {shlex.quote(ref)} | grep -F {shlex.quote(ref)} >/dev/null",
                f'test "$(docker image inspect --format \'{{{{index .Config.Labels "org.opencontainers.image.revision"}}}}\' {shlex.quote(ref)})" = {shlex.quote(source_sha)}',
                f"test \"$(docker inspect --format '{{{{range .Config.Env}}}}{{{{println .}}}}{{{{end}}}}' \"$id\" | sed -n 's/^ALLBOT_CONFIG_REVISION=//p')\" = {shlex.quote(config_rev)}",
                "health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}running{{end}}' \"$id\")",
                'test "$health" = healthy -o "$health" = running',
                f'printf \'%s\\t%s\\t%s\\t%s\\t%s\\n\' {shlex.quote(service)} "$id" {shlex.quote(ref)} "$(docker inspect --format \'{{{{.State.StartedAt}}}}\' "$id")" "$health"',
            ]
        )
    host = args.remote_host or ENVIRONMENT[args.env]["host"]
    result = _run(
        ["ssh", "-o", "BatchMode=yes", host, "bash -s"],
        input_text="\n".join(lines) + "\n",
        check=False,
    )
    if result.returncode:
        raise ReleaseError("post-deploy runtime identity recording failed")
    recorded: dict[str, Any] = {}
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) != 5 or fields[0] not in expected:
            raise ReleaseError("post-deploy runtime identity output is invalid")
        service, container_id, ref, started_at, health = fields
        artifact_name, _expected_ref, source_sha, config_rev = expected[service]
        recorded[artifact_name] = {
            "service": service,
            "container_id": container_id,
            "ref": ref,
            "digest": ref.rsplit("@", 1)[1],
            "source_sha": source_sha,
            "config_revision": config_rev,
            "health": health,
            "started_at": started_at,
        }
    if len(recorded) != len(expected):
        raise ReleaseError("post-deploy runtime identity is incomplete")
    return recorded


def _write_state(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    config_revision: str,
    web_deployment: Mapping[str, Any] | None = None,
    transaction: Mapping[str, Any] | None = None,
    stage_only: bool = False,
) -> None:
    environment = ENVIRONMENT[args.env]
    host = args.remote_host or environment["host"]
    decision = getattr(args, "release_decision", None)
    if not isinstance(decision, ReleaseStrategyDecision):
        decision = resolve_release_strategy(args, impact, manifest)
    profile = getattr(args, "execution_profile", None)
    automated_test_acceptance = (
        args.env == "test"
        and args.execute
        and isinstance(profile, ExecutionProfile)
        and profile.name == "streamlined"
        and args.command == "deploy"
    )
    artifact_assurance = (
        "verified"
        if automated_test_acceptance
        else "pending"
        if args.env == "test"
        else "tested"
        if decision.strategy == "standard"
        else "attested"
        if decision.risk_class == "execution"
        else "waived"
    )
    state = {
        "schema_version": 2,
        "environment": args.env,
        "track": manifest.get("track", "control-plane"),
        "release_channel": manifest.get("release_channel", "main"),
        "source_ref": manifest.get("source_ref", "refs/heads/main"),
        "git_sha": manifest["git_sha"],
        "config_revision": config_revision,
        "services": sorted(impact.services),
        "disabled_services": sorted(getattr(args, "disabled_cloud_services", set())),
        "inactive_artifacts": sorted(getattr(args, "inactive_artifacts", set())),
        "status": (
            "verified"
            if (args.command == "rollback" and args.env == "test")
            or automated_test_acceptance
            else "deployed"
        ),
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "risk_class": decision.risk_class,
        "strategy": decision.strategy,
        "validation_mode": decision.validation_mode,
        "skipped_gates": list(decision.skipped_gates),
        "reason": decision.reason or None,
        "gates": dict(decision.gates),
        "promotion_mode": (
            "control-plane-repair-fast-track"
            if getattr(args, "control_plane_repair_fast_track", False)
            else decision.strategy
        ),
        "credential_isolation": (
            args.runtime_env_snapshot.get("credential_isolation", "pending")
            if isinstance(getattr(args, "runtime_env_snapshot", None), Mapping)
            else "not-applicable"
        ),
        "health": {
            "cloud": "compose-ps-passed",
            "worker": "compose-ps-passed"
            if "worker" in impact.services
            else "not-targeted",
            "web": (
                "skipped"
                if args.skip_web and "web-static" in impact.services
                else "artifact-checksum-passed"
                if "web-static" in impact.services
                else "not-targeted"
            ),
        },
    }
    if automated_test_acceptance:
        started = getattr(args, "automated_acceptance_started_at", None)
        if not isinstance(started, datetime):
            started = datetime.now(timezone.utc)
        completed = datetime.now(timezone.utc)
        state["acceptance"] = {
            "source": "release.py-streamlined-smoke",
            "automated": True,
            "started_at": started.isoformat(),
            "completed_at": completed.isoformat(),
            "duration_seconds": max(0.0, (completed - started).total_seconds()),
            "checks": {
                "target_health": True,
                "api_base": True,
                "single_polling": True,
            },
        }
    if (
        args.command in {"deploy-module", "promote"}
        and args.execute
        and manifest.get("schema_version") == 2
    ):
        state["runtime_services"] = _collect_module_runtime_state(
            args, impact, manifest
        )
    if getattr(args, "control_plane_repair_fast_track", False):
        acceptance = getattr(args, "control_plane_repair_acceptance", None)
        if not isinstance(acceptance, Mapping):
            raise ReleaseError(
                "control-plane repair fast-track acceptance is unavailable"
            )
        state["repair_acceptance"] = dict(acceptance)
    if manifest.get("schema_version") == 2:
        promote_assurance = getattr(args, "promote_artifact_assurance", {})
        state["artifacts"] = {
            name: {
                "digest": manifest["artifacts"][name].get("digest")
                or manifest["artifacts"][name].get("sha256"),
                "source_sha": manifest["artifacts"][name].get("source_sha")
                or manifest["source_sha"],
                "status": state["status"],
                "assurance": (
                    promote_assurance.get(name, {}).get("assurance")
                    if args.command == "promote"
                    else artifact_assurance
                ),
            }
            for name in manifest["selected_artifacts"]
        }
    else:
        state.update(
            {
                "images": manifest["images"],
                "vendor_images": manifest["vendor_images"],
                "web_artifact_sha256": manifest["web_artifact_sha256"],
            }
        )
    if web_deployment:
        state["web_deployment"] = dict(web_deployment)
        if web_deployment.get("canonical_verified") is True:
            state["health"]["web"] = "canonical-runtime-verified"
    if transaction:
        state["transaction"] = {
            "id": transaction.get("transaction_id"),
            "status": "committed",
            "completed_stages": list(transaction.get("completed_stages", [])),
        }
    payload = json.dumps(state, sort_keys=True, indent=2) + "\n"
    track_segment = (
        f"/{manifest['track']}" if manifest.get("schema_version") == 2 else ""
    )
    path = f"/var/lib/allbot/deployments/{args.env}{track_segment}/current.json"
    if stage_only:
        if not transaction:
            raise ReleaseError("staged deployment state requires a transaction")
        path = _transaction_state_path(
            args.env,
            str(transaction["transaction_id"]),
            str(manifest.get("track"))
            if manifest.get("track") in RELEASE_TRACKS
            else None,
        )
    if not args.execute:
        print(f"[dry-run] write deployment state {host}:{path}")
        return
    if stage_only:
        command = (
            f"set -e; install -d -m 755 {shlex.quote(str(Path(path).parent))}; "
            f"cat > {shlex.quote(path + '.tmp')}; "
            f"mv -f {shlex.quote(path + '.tmp')} {shlex.quote(path)}"
        )
        _run(["ssh", "-o", "BatchMode=yes", host, command], input_text=payload)
        return
    history = (
        f"/var/lib/allbot/deployments/{args.env}{track_segment}/history/"
        f"{manifest['git_sha']}.json"
    )
    command = (
        f"set -e; install -d -m 755 {shlex.quote(str(Path(path).parent))} "
        f"{shlex.quote(str(Path(history).parent))}; "
        f"cat > {shlex.quote(path + '.tmp')}; "
        f"cp {shlex.quote(path + '.tmp')} {shlex.quote(history)}; "
        f"mv -f {shlex.quote(path + '.tmp')} {shlex.quote(path)}"
    )
    _run(["ssh", "-o", "BatchMode=yes", host, command], input_text=payload)


def _validate_local_env(args: argparse.Namespace) -> tuple[dict[str, str], str]:
    path = local_env_file(args)
    values = parse_env_file(path)
    schema = load_structured_file(Path(args.schema))
    revision = validate_environment(schema, args.env, values)
    return values, revision


INDEPENDENT_MODULE_ENV_SERVICES = {
    "central-api": ("central-api",),
    "web-api": ("web-api",),
    "payment-api": ("payment-api",),
    "imgproxy": (),
    "dashboard": ("dashboard-backend", "dashboard-frontend"),
    "main-bot": ("main-bot",),
    "qqcc-bot": ("qqcc-bot",),
    "qqcc-config": ("qqcc-config-backend", "qqcc-config-frontend"),
    "private-bot-worker": ("private-bot-worker",),
    "paid-group-bot": ("paid-group-bot",),
    "support-bot": ("support-bot",),
    "support-platform": (
        "dashboard-backend",
        "dashboard-frontend",
        "support-bot",
    ),
}

SCOPED_PROJECTION_REVIEWED_LEGACY_KEYS = frozenset(
    {
        "ALLBOT_ENV_FILE",
        "FILE_BOT_TOKEN",
        "LEGACY_MINIO_ACCESS_KEY",
        "LEGACY_MINIO_BUCKET",
        "LEGACY_MINIO_ENDPOINT",
        "LEGACY_MINIO_PUBLIC_URL",
        "LEGACY_MINIO_RESULT_BUCKET",
        "LEGACY_MINIO_SECRET_KEY",
        "LEGACY_MINIO_SECURE",
        "REQUIRED_CHANNEL_ID",
        "TZ",
    }
)

# Compatibility name retained for existing audit tooling and historical tests.
DASHBOARD_INITIAL_PROJECTION_LEGACY_KEYS = (
    SCOPED_PROJECTION_REVIEWED_LEGACY_KEYS
)


def _release_target_env_services(
    environment: str, impact: ReleaseImpact
) -> set[str]:
    """Map only services that actually exist in the target environment."""

    compose_to_config = {
        compose_service: config_service
        for config_service, compose_service in CONFIG_SERVICE_TO_COMPOSE.items()
    }
    return {
        compose_to_config[service]
        for service in cloud_services_for_release(environment, impact)
        if service in compose_to_config
    }


def _runtime_env_service_options(args: argparse.Namespace) -> str:
    """Limit module operations to their machine-owned config closure."""

    modules = _split_services(list(getattr(args, "modules", None) or ()))
    command = getattr(args, "command", "")
    if command in {"deploy-module", "promote"} and modules:
        selected_modules = modules
    elif command in {"config-plan", "config-apply"}:
        selected_modules = {str(getattr(args, "config_module", "") or "")}
    else:
        selected_modules = set()
    services = {
        service
        for module in selected_modules
        for service in INDEPENDENT_MODULE_ENV_SERVICES.get(module, ())
    }
    target_services = getattr(args, "target_env_services", None)
    if isinstance(target_services, (set, list, tuple)):
        services.update(str(service) for service in target_services)
    return "".join(
        f" --service {shlex.quote(service)}" for service in sorted(services)
    )


def _remote_runtime_env_snapshot(
    args: argparse.Namespace, *, command: str = "inspect"
) -> tuple[dict[str, str], str, dict[str, Any]]:
    """Validate the authoritative host env without returning secret values."""

    if command not in {"inspect", "activate"}:
        raise ReleaseError("unsupported runtime environment operation")
    environment = ENVIRONMENT[args.env]
    host = args.remote_host or environment["host"]
    env_file = args.remote_env_file or environment["env_file"]
    root = f"/var/lib/allbot/config/{args.env}"
    try:
        helper = base64.b64encode(RUNTIME_ENV_HELPER.read_bytes()).decode("ascii")
        contract = base64.b64encode(DEFAULT_SERVICE_ENV_CONTRACT.read_bytes()).decode(
            "ascii"
        )
        defaults = base64.b64encode(DEFAULT_ENV_DEFAULTS.read_bytes()).decode("ascii")
    except OSError as exc:
        raise ReleaseError("runtime environment helper is unavailable") from exc
    service_options = _runtime_env_service_options(args)
    remote_operation = command
    target_services = getattr(args, "target_env_services", None)
    if command == "inspect" and isinstance(target_services, (set, list, tuple)):
        remote_operation = "inspect-target"
    remote_command = (
        f'python3 -c "$(printf %s {helper} | base64 -d)" {remote_operation} '
        f"--environment {shlex.quote(args.env)} "
        f"--env-file {shlex.quote(env_file)} "
        f"--contract <(printf %s {contract} | base64 -d) "
        f"--defaults <(printf %s {defaults} | base64 -d) "
        f"--root {shlex.quote(root)}"
        f"{service_options}"
    )
    script = "set -euo pipefail\n" + remote_command + "\n"
    result = _run(
        ["ssh", "-o", "BatchMode=yes", host, "bash -s"],
        input_text=script,
        check=False,
    )
    if result.returncode:
        message = result.stderr.strip().splitlines()
        detail = message[-1] if message else "remote environment validation failed"
        raise ReleaseError(detail)
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ReleaseError("remote environment summary is invalid") from exc
    if (
        not isinstance(document, dict)
        or document.get("environment") != args.env
        or not re.fullmatch(
            r"[0-9a-f]{64}", str(document.get("environment_revision", ""))
        )
    ):
        raise ReleaseError("remote environment summary is invalid")
    present = document.get("present_keys")
    public = document.get("public_values")
    if not isinstance(present, list) or not isinstance(public, Mapping):
        raise ReleaseError("remote environment summary is incomplete")
    values = {str(key): "present" for key in present if isinstance(key, str)}
    values.update({str(key): str(value) for key, value in public.items()})
    effective_revision = document.get(
        "effective_environment_revision", document["environment_revision"]
    )
    if not re.fullmatch(r"[0-9a-f]{64}", str(effective_revision)):
        raise ReleaseError("remote environment summary is invalid")
    return values, str(effective_revision), document


CONFIG_SERVICE_TO_COMPOSE = {
    "central-api": "central-api",
    "web-api": "web-api",
    "payment-api": "payment-api",
    "dashboard-backend": "dashboard-backend",
    "dashboard-frontend": "dashboard-frontend",
    "main-bot": "bot",
    "qqcc-bot": "qqcc-bot",
    "qqcc-config-backend": "qqcc-config-backend",
    "qqcc-config-frontend": "qqcc-config-frontend",
    "private-bot-worker": "qqcc-private-bot-worker",
    "paid-group-bot": "paid-group-guard-bot",
    "support-bot": "support-bot",
    "postgres": "postgres",
    "redis": "redis",
}


def _remote_runtime_env_rollback(
    args: argparse.Namespace, expected_revision: str
) -> None:
    environment = ENVIRONMENT[args.env]
    host = args.remote_host or environment["host"]
    env_file = args.remote_env_file or environment["env_file"]
    root = f"/var/lib/allbot/config/{args.env}"
    helper = base64.b64encode(RUNTIME_ENV_HELPER.read_bytes()).decode("ascii")
    contract = base64.b64encode(DEFAULT_SERVICE_ENV_CONTRACT.read_bytes()).decode(
        "ascii"
    )
    defaults = base64.b64encode(DEFAULT_ENV_DEFAULTS.read_bytes()).decode("ascii")
    command = (
        f'python3 -c "$(printf %s {helper} | base64 -d)" rollback '
        f"--environment {shlex.quote(args.env)} "
        f"--env-file {shlex.quote(env_file)} "
        f"--contract <(printf %s {contract} | base64 -d) "
        f"--defaults <(printf %s {defaults} | base64 -d) "
        f"--root {shlex.quote(root)} "
        f"--expected-revision {shlex.quote(expected_revision)}"
    )
    result = _run(
        ["ssh", "-o", "BatchMode=yes", host, "bash -s"],
        input_text="set -euo pipefail\n" + command + "\n",
        check=False,
    )
    if result.returncode:
        raise ReleaseError("service environment activation rollback failed")


def _prepare_config_backup(args: argparse.Namespace, *, initial_cutover: bool) -> None:
    """Back up the currently running database before activating new projections."""

    environment = ENVIRONMENT[args.env]
    host = args.remote_host or environment["host"]
    env_file = args.remote_env_file or environment["env_file"]
    backup_env = (
        f"install -m 600 {shlex.quote(env_file)} "
        f'"$backup_dir/{args.env}.env-pre-service-projection-$(date -u +%Y%m%dT%H%M%SZ)"\n'
        if initial_cutover
        else ""
    )
    script = f"""set -euo pipefail
backup_dir={environment["state_root"]}/backups
install -d -m 700 "$backup_dir"
{backup_env}container_id=$(docker ps -q --filter label=com.docker.compose.project={shlex.quote(environment["project"])} --filter label=com.docker.compose.service=web-api)
test "$(printf '%s\n' "$container_id" | sed '/^$/d' | wc -l)" = 1
backup_file="$backup_dir/config-pre-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
umask 077
database_url="$(docker exec "$container_id" sh -lc 'printf %s "$DATABASE_URL"')"
docker run --rm -e DATABASE_URL="$database_url" {shlex.quote(PG_DUMP_IMAGE)} sh -lc 'case "$DATABASE_URL" in postgresql+asyncpg:*) url="postgresql:${{DATABASE_URL#postgresql+asyncpg:}}";; postgresql:*) url="$DATABASE_URL";; *) exit 2;; esac; url="$(printf %s "$url" | sed "s/\\([?&]\\)ssl=/\\1sslmode=/")"; exec pg_dump "$url"' | gzip -c > "$backup_file"
test -s "$backup_file"
heads="$(docker exec "$container_id" alembic heads | grep -c ' (head)$')"
test "$heads" = 1
"""
    result = _run(
        ["ssh", "-o", "BatchMode=yes", host, "bash -s"],
        input_text=script,
        check=False,
    )
    if result.returncode:
        raise ReleaseError("pre-activation database backup failed")


def _config_apply_cloud(
    args: argparse.Namespace,
    snapshot: Mapping[str, Any],
    services: set[str],
) -> None:
    environment = ENVIRONMENT[args.env]
    host = args.remote_host or environment["host"]
    env_file = args.remote_env_file or environment["env_file"]
    state_path = f"/var/lib/allbot/deployments/{args.env}/control-plane/current.json"
    project = environment["project"]
    overlay = environment["overlay"]
    checkout_root = "/home/deploy/APP/All_bot-release"
    compose_services = {
        CONFIG_SERVICE_TO_COMPOSE[name]
        for name in services
        if name in CONFIG_SERVICE_TO_COMPOSE
        and CONFIG_SERVICE_TO_COMPOSE[name] in environment["available_services"]
    }
    if not compose_services:
        return
    service_args = " ".join(shlex.quote(name) for name in sorted(compose_services))
    profile_flags = compose_profile_flags(compose_services)
    selected_case = "|".join(sorted(compose_services))
    revisions = snapshot.get("service_revisions")
    if not isinstance(revisions, Mapping):
        raise ReleaseError("service environment revisions are unavailable")
    revision_json = json.dumps(revisions, sort_keys=True, separators=(",", ":"))
    environment_revision = str(snapshot["environment_revision"])
    script = f"""set -euo pipefail
state={shlex.quote(state_path)}
test -f "$state"
sha=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["git_sha"])' "$state")
case "$sha" in {"?" * 40}) ;; *) echo invalid-current-sha >&2; exit 2;; esac
checkout={checkout_root}/releases/$sha
release_env=/var/lib/allbot/releases/control-plane/$sha/release.env
test -d "$checkout"
test -f "$release_env"
cp "$release_env" "$release_env.config-backup"
python3 - "$release_env" {shlex.quote(environment_revision)} <<'PY'
from pathlib import Path
import os,sys
path=Path(sys.argv[1]); revision=sys.argv[2]
values={{}}
for raw in path.read_text().splitlines():
    if '=' in raw:
        key,value=raw.split('=',1); values[key]=value
values['ALLBOT_CONFIG_REVISION']=revision
values['ALLBOT_SERVICE_ENV_ROOT']={json.dumps(f"/var/lib/allbot/config/{args.env}/current")}
tmp=path.with_suffix('.env.next')
tmp.write_text(''.join(f'{{key}}={{values[key]}}\\n' for key in sorted(values)))
os.replace(tmp,path)
PY
compose="docker compose --project-name {project} --env-file $checkout/deploy/env.defaults --env-file {shlex.quote(env_file)} --env-file $release_env -f $checkout/deploy/docker-compose-cloud-base.yml -f $checkout/{overlay} {profile_flags}"
$compose config -q
available_services="$($compose config --services)"
compose_service_args=()
for service in {service_args}; do
  if grep -Fxq "$service" <<<"$available_services"; then
    compose_service_args+=("$service")
  fi
done
test "${{#compose_service_args[@]}}" -gt 0
non_target_snapshot="$(mktemp)"
trap 'rm -f "$non_target_snapshot"' EXIT
for container_id in $(docker ps -aq --filter label=com.docker.compose.project={shlex.quote(project)}); do
  service="$(docker inspect --format '{{{{index .Config.Labels "com.docker.compose.service"}}}}' "$container_id")"
  case "$service" in {selected_case}) continue ;; esac
  docker inspect --format '{{{{.Id}}}}\t{{{{.Config.Image}}}}\t{{{{.State.StartedAt}}}}' "$container_id" >> "$non_target_snapshot"
done
$compose up -d --no-deps --wait --wait-timeout 180 "${{compose_service_args[@]}}"
while IFS=$'\t' read -r container_id image started_at; do
  test -n "$container_id"
  test "$(docker inspect --format '{{{{.Config.Image}}}}' "$container_id")" = "$image"
  test "$(docker inspect --format '{{{{.State.StartedAt}}}}' "$container_id")" = "$started_at"
done < "$non_target_snapshot"
python3 - "$state" {shlex.quote(environment_revision)} {shlex.quote(revision_json)} <<'PY'
import json,os,sys
path=sys.argv[1]; revision=sys.argv[2]; service_revisions=json.loads(sys.argv[3])
data=json.load(open(path)); data['config_revision']=revision
current=data.setdefault('service_config_revisions', {{}})
current.update(service_revisions)
tmp=path+'.tmp'; open(tmp,'w').write(json.dumps(data,sort_keys=True,indent=2)+'\\n'); os.replace(tmp,path)
PY
rm -f "$release_env.config-backup"
"""
    result = _run(
        ["ssh", "-o", "BatchMode=yes", host, "bash -s"],
        input_text=script,
        check=False,
    )
    if result.returncode:
        raise ReleaseError("config activation failed")


def _restore_config_cloud(args: argparse.Namespace, services: set[str]) -> None:
    environment = ENVIRONMENT[args.env]
    host = args.remote_host or environment["host"]
    env_file = args.remote_env_file or environment["env_file"]
    state_path = f"/var/lib/allbot/deployments/{args.env}/control-plane/current.json"
    compose_services = {
        CONFIG_SERVICE_TO_COMPOSE[name]
        for name in services
        if name in CONFIG_SERVICE_TO_COMPOSE
        and CONFIG_SERVICE_TO_COMPOSE[name] in environment["available_services"]
    }
    service_args = " ".join(shlex.quote(name) for name in sorted(compose_services))
    profile_flags = compose_profile_flags(compose_services)
    script = f"""set -euo pipefail
state={shlex.quote(state_path)}
sha=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["git_sha"])' "$state")
checkout=/home/deploy/APP/All_bot-release/releases/$sha
release_env=/var/lib/allbot/releases/control-plane/$sha/release.env
test -f "$release_env.config-backup"
mv -f "$release_env.config-backup" "$release_env"
compose="docker compose --project-name {environment["project"]} --env-file $checkout/deploy/env.defaults --env-file {shlex.quote(env_file)} --env-file $release_env -f $checkout/deploy/docker-compose-cloud-base.yml -f $checkout/{environment["overlay"]} {profile_flags}"
$compose config -q
$compose up -d --no-deps --wait --wait-timeout 180 {service_args}
"""
    result = _run(
        ["ssh", "-o", "BatchMode=yes", host, "bash -s"],
        input_text=script,
        check=False,
    )
    if result.returncode:
        raise ReleaseError("previous config projection restore failed")


def _set_config_maintenance(args: argparse.Namespace, *, enabled: bool) -> None:
    host = args.remote_host or ENVIRONMENT[args.env]["host"]
    paths = maintenance_files(args.env, initial_cutover=False)
    if enabled:
        script = "set -euo pipefail\n" + "".join(
            f"install -d -m 755 {shlex.quote(str(Path(path).parent))}\n"
            f"touch {shlex.quote(path)}\n"
            for path in paths
        )
    else:
        script = "set -euo pipefail\n" + "".join(
            f"rm -f {shlex.quote(path)}\n" for path in paths
        )
    _run(
        ["ssh", "-o", "BatchMode=yes", host, "bash -s"],
        input_text=script,
    )


def run_config_command(args: argparse.Namespace) -> int:
    if args.command == "config-apply":
        if not args.execute:
            raise ReleaseError("config-apply requires --execute")
        if args.env == "prod" and not args.confirm_prod:
            raise ReleaseError("production config-apply requires --confirm-prod")
    _, _, inspected = _remote_runtime_env_snapshot(args)
    plan_document = {
        key: inspected[key]
        for key in (
            "environment",
            "environment_revision",
            "active_revision",
            "effective_environment_revision",
            "contract_revision",
            "drift",
            "changed_keys",
            "affected_services",
            "unknown_keys",
            "retired_services",
            "service_revisions",
        )
        if key in inspected
    }
    print(json.dumps(plan_document, ensure_ascii=False, indent=2, sort_keys=True))
    if args.command == "config-plan" or not inspected.get("drift"):
        return 0
    config_module = str(getattr(args, "config_module", "") or "")
    affected = {
        str(name)
        for name in inspected.get("affected_services", [])
        if isinstance(name, str)
    }
    if config_module:
        retired_services = inspected.get("retired_services")
        if isinstance(retired_services, list) and retired_services:
            raise ReleaseError(
                "scoped config activation requires full retired-service cleanup"
            )
        allowed = set(INDEPENDENT_MODULE_ENV_SERVICES[config_module])
        if not affected or not affected <= allowed:
            raise ReleaseError(
                f"{config_module} config scope escaped its service closure"
            )
        raw_unknown_keys = inspected.get("unknown_keys")
        unknown_keys = (
            {str(key) for key in raw_unknown_keys if isinstance(key, str)}
            if isinstance(raw_unknown_keys, list)
            else set()
        )
        reviewed_legacy_keys = (
            SCOPED_PROJECTION_REVIEWED_LEGACY_KEYS
            if args.env == "prod"
            else frozenset()
        )
        unreviewed_unknown_keys = unknown_keys - reviewed_legacy_keys
        if unreviewed_unknown_keys:
            raise ReleaseError(
                "scoped config activation rejects unreviewed unknown keys: "
                + ", ".join(sorted(unreviewed_unknown_keys))
            )
        _, revision, _activated = _remote_runtime_env_snapshot(args, command="activate")
        print(
            json.dumps(
                {
                    "environment": args.env,
                    "environment_revision": revision,
                    "ignored_legacy_keys": sorted(unknown_keys),
                    "services": sorted(affected),
                    "status": "config-staged",
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    generation = affected & GENERATION_MAINTENANCE_ARTIFACTS
    unknown_keys = inspected.get("unknown_keys")
    full_maintenance = (
        isinstance(unknown_keys, list) and bool(unknown_keys)
    ) or not inspected.get("active_revision")
    maintenance_enabled = False
    try:
        if args.env == "prod" and (generation or full_maintenance):
            _set_config_maintenance(args, enabled=True)
            maintenance_enabled = True
        if full_maintenance:
            _prepare_config_backup(
                args,
                initial_cutover=not inspected.get("active_revision"),
            )
        _, revision, activated = _remote_runtime_env_snapshot(args, command="activate")
        try:
            _config_apply_cloud(args, activated, affected)
        except ReleaseError as activation_error:
            recovery_errors: list[str] = []
            try:
                _remote_runtime_env_rollback(args, revision)
            except ReleaseError as exc:
                recovery_errors.append(str(exc))
            try:
                _restore_config_cloud(args, affected)
            except ReleaseError as exc:
                recovery_errors.append(str(exc))
            if recovery_errors:
                raise ReleaseError(
                    "config activation failed and recovery is incomplete; maintenance remains enabled"
                ) from activation_error
            if maintenance_enabled:
                _set_config_maintenance(args, enabled=False)
            raise activation_error
        if maintenance_enabled:
            _set_config_maintenance(args, enabled=False)
        print(
            json.dumps(
                {
                    "environment": args.env,
                    "environment_revision": revision,
                    "services": sorted(affected),
                    "status": "config-applied",
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except Exception:
        # Maintenance intentionally remains when rollback or recovery is incomplete.
        raise


def _add_release_arguments(
    parser: argparse.ArgumentParser,
    *,
    env_required: bool = True,
    allow_no_maintenance: bool = False,
) -> None:
    parser.add_argument(
        "--env",
        choices=("test", "prod"),
        required=env_required,
        default=None if env_required else "prod",
    )
    parser.add_argument("--sha")
    parser.add_argument("--to", help="rollback target SHA (alias for --sha)")
    parser.add_argument("--transaction", help="persisted release transaction SHA")
    parser.add_argument(
        "--repair-rollback-materials",
        action="store_true",
        help=(
            "recover a deployed schema-v2 module's missing immutable "
            "checkout and release.env without pulling images or restarting services"
        ),
    )
    parser.add_argument("--from-sha")
    parser.add_argument("--manifest")
    parser.add_argument(
        "--bundle-repository",
        default="ghcr.io/giraffu/allbot-release",
    )
    parser.add_argument(
        "--bundle-cache",
        default="~/.cache/allbot/releases",
    )
    parser.add_argument("--web-artifact", default="web-dist.tgz")
    parser.add_argument(
        "--web-runtime-config",
        default=str(DEFAULT_WEB_RUNTIME_CONFIG),
    )
    parser.add_argument("--services", action="append", default=[])
    parser.add_argument("--track", choices=RELEASE_TRACKS, default="control-plane")
    parser.add_argument("--modules", "--module", action="append", default=[])
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--env-file")
    parser.add_argument("--state-file")
    parser.add_argument(
        "--plan-token",
        help=(
            "reuse one short-lived, release-bound plan/preflight result; "
            "plan and preflight emit a token automatically"
        ),
    )
    parser.add_argument("--skip-git-checks", action="store_true")
    parser.add_argument("--skip-ci-checks", action="store_true")
    parser.add_argument("--skip-env-checks", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-prod", action="store_true")
    parser.add_argument(
        "--strategy",
        choices=RELEASE_STRATEGIES,
        default="auto",
        help="risk-based release strategy; auto uses the selected artifact policy",
    )
    parser.add_argument(
        "--skip-gate",
        action="append",
        default=[],
        help="explicitly waive an allowlisted release gate",
    )
    parser.add_argument("--reason", default="")
    parser.add_argument(
        "--dashboard-fast-track",
        action="store_true",
        help=(
            "deprecated compatibility alias for Dashboard --strategy direct; "
            "CI artifacts and production confirmation remain required"
        ),
    )
    parser.add_argument(
        "--control-plane-repair-fast-track",
        action="store_true",
        help=(
            "reuse a verified control-plane test release only when unchanged "
            "artifact inputs/targets are equivalent and the repaired private "
            "worker digest passes an isolated import smoke"
        ),
    )
    parser.add_argument("--confirm-db-upgrade", action="store_true")
    if allow_no_maintenance:
        parser.add_argument(
            "--no-maintenance",
            action="store_true",
            help=(
                "for an explicit production module set, record the user's "
                "decision and use a rolling forward update"
            ),
        )
    parser.add_argument("--confirm-legacy-cutover", action="store_true")
    parser.add_argument(
        "--repair-test-data-services",
        action="store_true",
        help=(
            "repair a missing test PostgreSQL/Redis immutable handoff; requires "
            "exact --services postgres and --services redis"
        ),
    )
    parser.add_argument(
        "--confirm-empty-test-queue",
        action="store_true",
        help="confirm external evidence that test pending/running queues are empty",
    )
    parser.add_argument("--drain-timeout-seconds", type=int, default=7200)
    parser.add_argument("--drain-interval-seconds", type=int, default=15)
    parser.add_argument("--pages-verify-timeout-seconds", type=int, default=180)
    parser.add_argument("--pages-verify-interval-seconds", type=int, default=5)
    parser.add_argument("--skip-web", action="store_true")
    parser.add_argument("--remote-host")
    parser.add_argument("--remote-env-file")
    parser.add_argument(
        "--remote-checkout-root",
        default="/home/deploy/APP/All_bot-release",
    )
    parser.add_argument(
        "--test-state-host",
        default="allbot-do-sgp1-test-control",
    )
    parser.add_argument(
        "--worker-checkout-root",
        default=str(Path.home() / "APP" / "All_bot-release"),
    )
    parser.add_argument(
        "--cloudflare-token-file",
        default=str(Path.home() / ".config" / "allbot" / "cloudflare-pages.token"),
    )
    parser.add_argument(
        "--cloudflare-account-id",
        default="c7220eb751acc6f7ab8255b4a0394ef3",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("plan", "preflight", "deploy", "rollback", "recover"):
        child = subparsers.add_parser(command)
        _add_release_arguments(child, allow_no_maintenance=command == "deploy")
    deploy_module = subparsers.add_parser(
        "deploy-module",
        help="deploy approved artifacts from one exact protected-main bundle",
    )
    _add_release_arguments(deploy_module, env_required=False)
    deploy_module.set_defaults(
        env="prod", bundle_repository=DEFAULT_BUNDLE_REPOSITORY
    )
    promote = subparsers.add_parser(
        "promote",
        help="preview or execute one safe daily production promotion",
    )
    promote.add_argument("--modules", action="append", default=[])
    promote.add_argument("--sha")
    promote.add_argument("--confirm-prod", action="store_true")
    promote.add_argument("--confirm-db-upgrade", action="store_true")
    promote.add_argument(
        "--no-maintenance",
        action="store_true",
        help=(
            "for an explicit module set, record the user's decision and use a "
            "rolling forward update; rollback failure safety may still enable maintenance"
        ),
    )
    promote.set_defaults(
        env="prod",
        track="control-plane",
        execute=False,
        strategy="auto",
        services=[],
        to=None,
        transaction=None,
        repair_rollback_materials=False,
        from_sha=None,
        manifest=None,
        bundle_repository=DEFAULT_BUNDLE_REPOSITORY,
        bundle_cache="~/.cache/allbot/releases",
        web_artifact="web-dist.tgz",
        web_runtime_config=str(DEFAULT_WEB_RUNTIME_CONFIG),
        policy=str(DEFAULT_POLICY),
        schema=str(DEFAULT_SCHEMA),
        env_file=None,
        state_file=None,
        plan_token=None,
        skip_git_checks=False,
        skip_ci_checks=False,
        skip_env_checks=False,
        skip_gate=[],
        reason="",
        dashboard_fast_track=False,
        control_plane_repair_fast_track=False,
        confirm_db_upgrade=False,
        confirm_legacy_cutover=False,
        repair_test_data_services=False,
        confirm_empty_test_queue=False,
        drain_timeout_seconds=7200,
        drain_interval_seconds=15,
        pages_verify_timeout_seconds=180,
        pages_verify_interval_seconds=5,
        skip_web=False,
        remote_host=None,
        remote_env_file=None,
        remote_checkout_root="/home/deploy/APP/All_bot-release",
        test_state_host="allbot-do-sgp1-test-control",
        worker_checkout_root=str(Path.home() / "APP" / "All_bot-release"),
        cloudflare_token_file=str(
            Path.home() / ".config" / "allbot" / "cloudflare-pages.token"
        ),
        cloudflare_account_id="c7220eb751acc6f7ab8255b4a0394ef3",
    )
    for command in ("config-plan", "config-apply"):
        config = subparsers.add_parser(command)
        config.add_argument("--env", choices=("test", "prod"), required=True)
        config.add_argument(
            "--module",
            dest="config_module",
            choices=tuple(sorted(INDEPENDENT_MODULE_ENV_SERVICES)),
            help=(
                "stage only one independent module's service projections "
                "without restarting containers"
            ),
        )
        config.add_argument("--remote-host")
        config.add_argument("--remote-env-file")
        config.add_argument("--execute", action="store_true")
        config.add_argument("--confirm-prod", action="store_true")
    validate = subparsers.add_parser("validate-env")
    validate.add_argument("--env", choices=("test", "prod"), required=True)
    validate.add_argument("--env-file", required=True)
    validate.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    verify = subparsers.add_parser("verify-test")
    verify.add_argument("--sha", required=True)
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--evidence", required=True)
    verify.add_argument("--track", choices=RELEASE_TRACKS, default="control-plane")
    verify.add_argument("--modules", action="append", default=[])
    verify.add_argument("--policy", default=str(DEFAULT_POLICY))
    verify.add_argument("--remote-host")
    verify.add_argument("--execute", action="store_true")
    isolation = subparsers.add_parser("credential-isolation-complete")
    isolation.add_argument("--evidence", required=True)
    isolation.add_argument("--test-host")
    isolation.add_argument("--prod-host")
    isolation.add_argument("--confirm-prod", action="store_true")
    isolation.add_argument("--execute", action="store_true")
    return parser


def _main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command_started = time.monotonic()
    args.pre_transaction_timings = {}
    transaction: dict[str, Any] | None = None
    try:
        if args.command in {"config-plan", "config-apply"}:
            return run_config_command(args)
        if args.command == "validate-env":
            values = parse_env_file(Path(args.env_file))
            revision = validate_environment(
                load_structured_file(Path(args.schema)),
                args.env,
                values,
            )
            print(f"environment contract ok; config_revision={revision}")
            return 0
        if args.command == "verify-test":
            _mark_test_verified(args)
            return 0
        if args.command == "credential-isolation-complete":
            if not args.execute or not args.confirm_prod:
                raise ReleaseError(
                    "credential isolation completion requires --execute and --confirm-prod"
                )
            try:
                raw_evidence = json.loads(
                    Path(args.evidence).read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                raise ReleaseError("credential isolation evidence is invalid") from exc
            if not isinstance(raw_evidence, Mapping):
                raise ReleaseError("credential isolation evidence is invalid")
            evidence = validate_credential_isolation_evidence(raw_evidence)
            result = complete_credential_isolation(args, evidence)
            print(
                json.dumps(
                    {
                        "status": "credential-isolation-complete",
                        **result,
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "promote":
            requested = _split_services(args.modules)
            if not args.sha:
                args.sha = resolve_latest_promote_candidate(args.bundle_repository)
            configured = load_promote_policy(
                Path(args.policy), validate_full_sha(args.sha)
            ).get("independent_modules", {})
            allowed = set(configured) if isinstance(configured, Mapping) else set()
            unknown = sorted(requested - allowed)
            if unknown:
                raise ReleaseError(
                    "unknown promote modules: " + ", ".join(unknown)
                )
            if not requested:
                modules, runtime = resolve_automatic_promote_modules(args)
                args.modules = modules
                args.promote_runtime_artifacts = runtime
                args.promote_live_no_change = not modules
            args.execute = bool(args.confirm_prod)
        if args.command == "deploy-module":
            if args.env != "prod" or args.track != "control-plane":
                raise ReleaseError(
                    "deploy-module is restricted to the production control-plane"
                )
            if not args.modules or args.services or args.from_sha:
                raise ReleaseError(
                    "deploy-module requires --module and does not accept service or baseline overrides"
                )
            if args.dashboard_fast_track or args.control_plane_repair_fast_track:
                raise ReleaseError(
                    "deploy-module does not accept legacy fast-track modes"
                )
            if not args.sha:
                args.sha = resolve_latest_protected_main_sha()
        if args.command == "recover":
            if args.repair_rollback_materials:
                if args.transaction:
                    raise ReleaseError(
                        "rollback material repair cannot be combined with transaction recovery"
                    )
                if not args.sha:
                    raise ReleaseError("rollback material repair requires --sha")
                if not args.execute or (args.env == "prod" and not args.confirm_prod):
                    raise ReleaseError(
                        "rollback material repair requires --execute; production also "
                        "requires --confirm-prod"
                    )
                if (
                    args.skip_git_checks
                    or args.skip_ci_checks
                    or args.skip_env_checks
                    or args.skip_gate
                ):
                    raise ReleaseError(
                        "rollback material repair does not allow skipped verification gates"
                    )
                if not args.modules or args.services:
                    raise ReleaseError(
                        "rollback material repair requires one independent --modules group"
                    )
                impact, manifest, previous_sha = build_plan(args)
                if previous_sha != manifest.get("git_sha"):
                    raise ReleaseError(
                        "rollback material repair SHA is not the deployed module baseline"
                    )
                if (
                    impact.requires_db_upgrade
                    or impact.blockers
                    or impact.unknown_paths
                ):
                    raise ReleaseError(
                        "rollback material repair requires a clean independent module boundary"
                    )
                verify_operator_worktree_clean(
                    source_ref=str(manifest.get("source_ref", "refs/heads/main")),
                    environment=args.env,
                    command=args.command,
                )
                if args.track == "control-plane":
                    environment_values, config_revision, _ = (
                        _remote_runtime_env_snapshot(args)
                    )
                else:
                    environment_values, config_revision = _validate_local_env(args)
                impact, manifest = _expand_disabled_test_owner_rollback_baseline(
                    args, impact, manifest, environment_values
                )
                verify_release_ci(manifest, str(manifest["git_sha"]))
                release_env = render_track_release_env(
                    manifest,
                    config_revision,
                    service_env_root=f"/var/lib/allbot/config/{args.env}/current",
                    allow_legacy_missing_dashboard_profile_pins=True,
                )
                _materialize_cloud_rollback_materials(
                    args,
                    impact,
                    manifest,
                    release_env,
                    environment_values,
                )
                print(
                    json.dumps(
                        {
                            "environment": args.env,
                            "git_sha": manifest["git_sha"],
                            "services": sorted(impact.services),
                            "status": "rollback-materials-ready",
                            "running_services_changed": False,
                        },
                        sort_keys=True,
                    )
                )
                return 0
            if not args.transaction:
                raise ReleaseError("recover requires --transaction")
            transaction_id = validate_full_sha(args.transaction)
            if not args.execute:
                raise ReleaseError("recover requires --execute")
            if args.env == "prod" and not args.confirm_prod:
                raise ReleaseError("production recover requires --confirm-prod")
            if args.track == "control-plane":
                environment_values, _, runtime_snapshot = (
                    _remote_runtime_env_snapshot(args)
                )
                args.runtime_env_snapshot = runtime_snapshot
            else:
                environment_values, _ = _validate_local_env(args)
            transaction = _read_transaction_journal(args, transaction_id)
            services = transaction.get("services")
            if not isinstance(services, list):
                raise ReleaseError("transaction services are invalid")
            impact = ReleaseImpact(
                services=services,
                level=str(transaction.get("level", "maintenance")),
                matched_rules=["transaction-recovery"],
            )
            dependencies = _recovery_dependencies(
                args, impact, transaction, environment_values
            )
            recover_release_transaction(transaction, dependencies)
            print(
                json.dumps(
                    {
                        "transaction_id": transaction_id,
                        "status": transaction["status"],
                        "phase": transaction["phase"],
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "rollback" and args.to:
            if args.sha and args.sha != args.to:
                raise ReleaseError("rollback --sha and --to must identify the same SHA")
            args.sha = args.to
        if not args.sha:
            raise ReleaseError(f"{args.command} requires --sha")
        if args.command == "promote" and getattr(
            args, "promote_live_no_change", False
        ):
            print(
                json.dumps(
                    verify_promote_no_change(args),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.env == "prod" and args.execute and not args.confirm_prod:
            raise ReleaseError("production execute requires --confirm-prod")
        if args.command == "preflight" and args.execute:
            raise ReleaseError("preflight is read-only and does not accept --execute")
        if args.execute and args.skip_ci_checks:
            raise ReleaseError("execute mode cannot skip release CI verification")
        if args.skip_env_checks and args.command != "plan":
            raise ReleaseError("--skip-env-checks is only available for plan")
        cached_plan: dict[str, Any] | None = None
        if args.plan_token:
            if args.command not in {"preflight", "deploy", "deploy-module"}:
                raise ReleaseError(
                    "--plan-token is only accepted by preflight, deploy, and deploy-module"
                )
            cached_plan = _load_plan_token(args, args.plan_token)
            impact = _impact_from_plan_token(cached_plan)
            manifest = dict(cached_plan["manifest"])
            previous_sha = str(cached_plan.get("previous_sha") or "")
            args.previous_state = cached_plan.get("previous_state")
            args.changed_paths = list(cached_plan.get("changed_paths") or [])
            args.promote_initial_artifacts = set(
                cached_plan.get("promote_initial_artifacts") or []
            )
            args.pre_transaction_timings["candidate"] = 0.0
        else:
            impact, manifest, previous_sha = build_plan(args)
            args.pre_transaction_timings["candidate"] = max(
                0.0, time.monotonic() - command_started
            )
        if args.command == "promote":
            args.promote_target_artifacts = set(
                manifest.get("selected_artifacts", [])
            )
        apply_user_authorized_no_maintenance(args, impact)
        if args.execute:
            verify_operator_worktree_clean(
                source_ref=str(manifest.get("source_ref", "refs/heads/main")),
                environment=args.env,
                command=args.command,
            )
        args.previous_sha = previous_sha
        if args.command == "rollback" and not args.dashboard_fast_track:
            impact.level = "maintenance"
        decision = resolve_release_strategy(args, impact, manifest)
        args.streamlined_candidate = (
            resolve_execution_profile(impact, manifest, {"drift": False}).name
            == "streamlined"
        )
        args.target_env_services = _release_target_env_services(args.env, impact)
        if (
            args.env == "test"
            and decision.risk_class == "owner-tools"
            and args.command != "plan"
            and not cloud_services_for_release(args.env, impact)
        ):
            raise ReleaseError(
                "owner-only admin services are removed from the test environment"
            )
        config_started = time.monotonic()
        if args.skip_env_checks:
            environment_values, config_revision = {}, ""
            args.runtime_env_snapshot = None
        elif args.track == "control-plane":
            environment_values, config_revision, runtime_snapshot = (
                _remote_runtime_env_snapshot(args)
            )
            args.runtime_env_snapshot = runtime_snapshot
        else:
            try:
                environment_values, config_revision = _validate_local_env(args)
                args.local_env_error = False
                args.runtime_env_snapshot = None
            except ReleaseError:
                environment_values, config_revision = {}, ""
                args.local_env_error = True
                args.runtime_env_snapshot = None
        args.pre_transaction_timings["config"] = max(
            0.0, time.monotonic() - config_started
        )
        if cached_plan is not None:
            cached_runtime = cached_plan.get("runtime_snapshot")
            current_environment_revision = (
                args.runtime_env_snapshot.get("environment_revision")
                if isinstance(args.runtime_env_snapshot, Mapping)
                else None
            )
            cached_environment_revision = (
                cached_runtime.get("environment_revision")
                if isinstance(cached_runtime, Mapping)
                else None
            )
            if (
                config_revision != cached_plan.get("config_revision")
                or current_environment_revision != cached_environment_revision
            ):
                raise ReleaseError(
                    "plan token target configuration changed; run plan again"
                )
        args.execution_profile = resolve_execution_profile(
            impact,
            manifest,
            (
                args.runtime_env_snapshot
                if isinstance(getattr(args, "runtime_env_snapshot", None), Mapping)
                else None
            ),
        )
        args.disabled_cloud_services = set()
        args.inactive_artifacts = set()
        if (
            not args.skip_env_checks
            and manifest.get("schema_version") == 2
            and manifest.get("track") == "control-plane"
        ):
            disabled_cloud_services = disabled_optional_cloud_services(
                args.env, environment_values
            )
            manifest, inactive_artifacts = filter_inactive_control_artifacts(
                args.env,
                manifest,
                disabled_cloud_services,
            )
            args.disabled_cloud_services = disabled_cloud_services
            args.inactive_artifacts = inactive_artifacts
        document = _plan_document(
            args,
            impact,
            manifest,
            previous_sha,
            environment_values,
        )
        if (
            cached_plan is None
            and args.command in {"plan", "preflight"}
            and not args.skip_env_checks
        ):
            args.plan_token, expires_at = _create_plan_token(
                args,
                impact=impact,
                manifest=manifest,
                previous_sha=previous_sha,
                config_revision=config_revision,
                runtime_snapshot=(
                    args.runtime_env_snapshot
                    if isinstance(args.runtime_env_snapshot, Mapping)
                    else None
                ),
            )
            document["plan_token"] = args.plan_token
            document["plan_token_expires_at"] = expires_at.isoformat()
        elif cached_plan is not None:
            document["plan_token"] = args.plan_token
            document["plan_token_expires_at"] = cached_plan["expires_at"]
        if args.command != "promote":
            print(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True))
        if args.command == "plan":
            return 0
        if isinstance(
            getattr(args, "runtime_env_snapshot", None), Mapping
        ) and args.runtime_env_snapshot.get("drift"):
            raise ReleaseError(
                "target host environment has unapplied drift; run config-plan and config-apply"
            )
        if args.command in {"deploy", "deploy-module", "promote"} and (
            args.command != "deploy"
            or _recorded_target_digests_match(
                manifest,
                (
                    args.previous_state
                    if isinstance(getattr(args, "previous_state", None), Mapping)
                    else None
                ),
            )
        ):
            no_change = (
                verify_promote_selected_no_change(
                    args,
                    manifest,
                    args.runtime_env_snapshot,
                    config_revision,
                )
                if args.command == "promote"
                else verify_deploy_module_no_change(
                    args,
                    impact,
                    manifest,
                    environment_values,
                    config_revision,
                    (
                        args.runtime_env_snapshot.get("service_revisions", {})
                        if isinstance(
                            getattr(args, "runtime_env_snapshot", None), Mapping
                        )
                        else None
                    ),
                )
            )
            if no_change is not None:
                if args.command == "promote":
                    no_change = {
                        **no_change,
                        "candidate_sha": manifest["git_sha"],
                        "modules": sorted(_split_services(args.modules)),
                        "mutation": False,
                    }
                print(json.dumps(no_change, ensure_ascii=False, indent=2, sort_keys=True))
                return 0
        cached_preflight = (
            cached_plan.get("preflight") if cached_plan is not None else None
        )
        if (
            isinstance(cached_preflight, Mapping)
            and cached_preflight.get("status") == "passed"
        ):
            preflight = dict(cached_preflight)
            args.pre_transaction_timings["evidence"] = 0.0
        else:
            evidence_started = time.monotonic()
            preflight = preflight_release(args, impact, manifest, environment_values)
            args.pre_transaction_timings["evidence"] = max(
                0.0, time.monotonic() - evidence_started
            )
        if args.command == "promote":
            print(
                json.dumps(
                    _promote_preview_document(args, impact, manifest, preflight),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(
                json.dumps(
                    {"preflight": preflight},
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
        require_preflight(preflight)
        if args.command == "preflight":
            if args.plan_token:
                _cache_plan_preflight(args, args.plan_token, preflight)
            return 0
        if args.command == "promote" and not args.execute:
            return 0
        if manifest.get("schema_version") == 2 and args.track == "gpu-execution":
            raise ReleaseError(
                "GPU track mutations must use the profile canary operator; "
                "release.py records plans, verification, and rollback metadata only"
            )
        release_env = (
            render_track_release_env(
                manifest,
                config_revision,
                service_env_root=f"/var/lib/allbot/config/{args.env}/current",
            )
            if manifest.get("schema_version") == 2
            else render_release_env(manifest, config_revision)
        )
        previous_pages_id = None
        if "web-static" in impact.services and not args.skip_web:
            previous_pages_id = _current_pages_deployment_id(args)
        transaction = new_release_transaction(
            environment=args.env,
            target_sha=str(manifest["git_sha"]),
            previous_sha=previous_sha or None,
            previous_kind="immutable" if previous_sha else "legacy",
            previous_pages_deployment_id=previous_pages_id,
        )
        transaction["release_channel"] = manifest.get("release_channel", "main")
        transaction["source_ref"] = manifest.get("source_ref", "refs/heads/main")
        if manifest.get("schema_version") == 2:
            transaction["track"] = manifest["track"]
        if isinstance(getattr(args, "previous_state", None), Mapping):
            transaction["previous"]["state"] = dict(args.previous_state)
        rollback_release_env = ""
        if args.command == "promote":
            transaction["schema_version"] = 2
            previous_artifacts = build_promote_previous_artifacts(args, manifest)
            transaction["previous"]["artifacts"] = previous_artifacts
            if args.execution_profile.name == "strict":
                transaction["previous"]["rollback_release_env_path"] = (
                    "/var/lib/allbot/deployments/prod/transactions/control-plane/"
                    + str(manifest["git_sha"])
                    + ".rollback.env"
                )
                transaction["previous"]["non_target_snapshot_path"] = (
                    "/var/lib/allbot/deployments/prod/transactions/control-plane/"
                    + str(manifest["git_sha"])
                    + ".nontarget.tsv"
                )
                rollback_release_env = render_promote_rollback_release_env(
                    release_env, previous_artifacts
                )
        transaction["services"] = sorted(impact.services)
        transaction["level"] = impact.level
        transaction["maintenance_required"] = bool(
            getattr(args, "maintenance_required", impact.level == "maintenance")
        )
        transaction["maintenance_waived"] = bool(
            getattr(args, "maintenance_waived", False)
        )
        transaction["execution_profile"] = args.execution_profile.name
        transaction["execution_profile_reasons"] = list(
            args.execution_profile.reasons
        )
        transaction["phase_timings_seconds"] = {
            "candidate": 0.0,
            "evidence": 0.0,
            "config": 0.0,
            "pull": 0.0,
            "replace": 0.0,
            "health": 0.0,
            "state": 0.0,
            "target-rollback": 0.0,
        }
        transaction["phase_timings_seconds"].update(args.pre_transaction_timings)
        transaction.update(
            {
                "risk_class": decision.risk_class,
                "strategy": decision.strategy,
                "validation_mode": decision.validation_mode,
                "skipped_gates": list(decision.skipped_gates),
                "reason": decision.reason or None,
            }
        )
        transaction["snapshots"] = {
            "cloud_legacy_running": (
                _cloud_release_dir(
                    str(manifest["git_sha"]),
                    str(manifest["track"])
                    if manifest.get("schema_version") == 2
                    else None,
                )
                + "/legacy-cloud-running.txt"
            ),
            "worker_legacy_running": str(
                Path(args.worker_checkout_root).expanduser()
                / "release-env"
                / (
                    str(manifest["track"])
                    if manifest.get("schema_version") == 2
                    else ""
                )
                / str(manifest["git_sha"])
                / "legacy-worker-running.txt"
            ),
        }
        dependencies = _transaction_dependencies(
            args,
            impact,
            manifest,
            release_env,
            environment_values,
            config_revision,
            transaction,
        )
        if args.command == "promote" and args.execution_profile.name == "strict":
            _prepare_promote_rollback_materials(
                args, transaction, rollback_release_env
            )
        if args.env == "test" and args.execution_profile.name == "streamlined":
            args.automated_acceptance_started_at = datetime.now(timezone.utc)
        execute_release_transaction(transaction, dependencies)
        if args.command == "promote":
            print(
                json.dumps(
                    {
                        "status": "committed",
                        "candidate_sha": manifest["git_sha"],
                        "modules": sorted(_split_services(args.modules)),
                        "transaction_id": transaction["transaction_id"],
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
        return 0
    except ReleaseError as exc:
        if args.command == "promote":
            status = "blocked"
            transaction_id = None
            if isinstance(transaction, Mapping):
                transaction_id = transaction.get("transaction_id")
                if transaction.get("status") == "rolled_back":
                    status = "rolled-back"
                elif transaction.get("status") == "rollback_failed":
                    status = "rollback-incomplete"
            print(
                json.dumps(
                    {
                        "status": status,
                        "candidate_sha": getattr(args, "sha", None),
                        "transaction_id": transaction_id,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 2
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


def main(argv: Sequence[str] | None = None) -> int:
    """Run one release command with process-scoped SSH connection reuse."""

    global _SSH_CONTROL_PATH
    global _SSH_CONTROL_HOSTS
    with tempfile.TemporaryDirectory(prefix="allbot-release-ssh-") as directory:
        _SSH_CONTROL_PATH = str(Path(directory) / "control-%C")
        _SSH_CONTROL_HOSTS = set()
        try:
            return _main(argv)
        finally:
            control_path = _SSH_CONTROL_PATH
            hosts = set(_SSH_CONTROL_HOSTS)
            _SSH_CONTROL_PATH = None
            _SSH_CONTROL_HOSTS = set()
            if control_path:
                for host in hosts:
                    subprocess.run(
                        [
                            "ssh",
                            "-o",
                            f"ControlPath={control_path}",
                            "-O",
                            "exit",
                            host,
                        ],
                        text=True,
                        capture_output=True,
                        check=False,
                    )


if __name__ == "__main__":
    raise SystemExit(main())
