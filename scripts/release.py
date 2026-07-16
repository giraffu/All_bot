#!/usr/bin/env python3
"""Plan and execute AllBot immutable releases.

The public seam is intentionally small: ``plan``, ``preflight``, ``deploy``,
``rollback``, ``recover`` and ``validate-env``. Application code is delivered
only through digest-pinned images from a CI-produced release manifest. Git
checkouts on runtime hosts are used solely for the matching deployment contract
(compose, policy and helpers).
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
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


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "deploy" / "release-policy.yml"
DEFAULT_SCHEMA = ROOT / "deploy" / "env.schema.yml"
DEFAULT_WEB_RUNTIME_CONFIG = ROOT / "frontend" / "runtime-config.yml"
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_IMAGE_RE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
REQUIRED_IMAGES = {
    "app",
    "central",
    "dashboard_backend",
    "dashboard_frontend",
    "worker",
}
REQUIRED_VENDOR_IMAGES = {"imgproxy", "postgres", "redis"}
CONTROL_ARTIFACT_ENV = {
    "central-api": "ALLBOT_CENTRAL_IMAGE",
    "web-api": "ALLBOT_WEB_API_IMAGE",
    "payment-api": "ALLBOT_PAYMENT_API_IMAGE",
    "main-bot": "ALLBOT_MAIN_BOT_IMAGE",
    "qqcc-bot": "ALLBOT_QQCC_BOT_IMAGE",
    "private-bot-worker": "ALLBOT_PRIVATE_BOT_WORKER_IMAGE",
    "paid-group-bot": "ALLBOT_PAID_GROUP_BOT_IMAGE",
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
    "public-web": "web-static",
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
            "dashboard-backend",
            "dashboard-frontend",
            "qqcc-config-backend",
            "qqcc-config-frontend",
            "bot",
            "qqcc-bot",
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
            "imgproxy",
        },
    },
}

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
            value = action()
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
        rollback_failures: list[str] = []
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
            transaction["rollback_failures"] = rollback_failures
            _journal_transition(
                transaction,
                dependencies.journal,
                phase="rollback_failed",
                status="rollback_failed",
            )
            raise ReleaseError(
                "release failed and rollback incomplete; maintenance remains enabled"
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
            transaction["rollback_failures"] = ["recovery_validation"]
            _journal_transition(
                transaction,
                dependencies.journal,
                phase="rollback_failed",
                status="rollback_failed",
            )
            raise ReleaseError(
                "release failed and rollback incomplete; maintenance remains enabled"
            ) from recovery_exc
        _journal_transition(
            transaction,
            dependencies.journal,
            phase="recovery_verified",
            status="rolled_back",
        )
        raise ReleaseError("release failed and was recovered to the previous stack") from exc


def recover_release_transaction(
    transaction: dict[str, Any],
    dependencies: ReleaseTransactionDependencies,
) -> None:
    """Idempotently compensate a persisted transaction; never resume it forward."""

    if transaction.get("status") == "committed":
        raise ReleaseError("a committed transaction cannot be recovered forward or backward")
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


def _assert_secret_free_transaction(value: Any, *, path: str = "transaction") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower()
            if any(marker in normalized for marker in ("token", "secret", "password", "env_values")):
                raise ReleaseError(f"transaction journal contains forbidden field: {path}.{key}")
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
    payload = json.dumps(transaction, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
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
        or transaction.get("schema_version") != 1
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
    next_stage = re.compile(r"^FROM\s+", re.MULTILINE).search(
        dockerfile, marker.end()
    )
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
            or spec.get("dockerfile")
            != "deploy/docker/Dockerfile.control-plane"
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
            raise ReleaseError(
                f"{name} target changed after the verified test release"
            )
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
            raise ReleaseError(
                "test-candidate bundles cannot use Dashboard fast-track"
            )
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


def parse_env_file(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ReleaseError(f"environment file is unavailable: {path}") from exc
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
    manifest: Mapping[str, Any], config_revision: str
) -> str:
    """Render only image variables owned by one schema-v2 track."""

    track = str(manifest.get("track", ""))
    artifacts = manifest.get("artifacts", {})
    lines = [
        f"ALLBOT_RELEASE_SHA={manifest['source_sha']}",
        f"ALLBOT_CONFIG_REVISION={config_revision}",
        f"ALLBOT_RELEASE_TRACK={track}",
    ]
    if track == "control-plane":
        for name, variable in CONTROL_ARTIFACT_ENV.items():
            artifact = artifacts.get(name)
            if isinstance(artifact, Mapping) and artifact.get("kind") in {
                "image",
                "external-image",
            }:
                lines.append(f"{variable}={artifact['ref']}")
    elif track == "test-execution":
        for name, variable in {
            "worker-agent": "ALLBOT_WORKER_AGENT_IMAGE",
            "worker-relay": "ALLBOT_WORKER_RELAY_IMAGE",
        }.items():
            artifact = artifacts.get(name)
            if isinstance(artifact, Mapping):
                lines.append(f"{variable}={artifact['ref']}")
    return "\n".join((*lines, ""))


def _run(
    args: Sequence[str],
    *,
    cwd: Path = ROOT,
    input_text: str | None = None,
    env: Mapping[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    process_env = None
    if env is not None:
        process_env = os.environ.copy()
        process_env.update(env)
    result = subprocess.run(
        list(args),
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
    if manifest.get("release_channel") == "test-candidate" and status.get(
        "headBranch"
    ) != "codex/test-train":
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


def _split_services(values: Sequence[str]) -> set[str]:
    selected: set[str] = set()
    for value in values:
        selected.update(item for item in re.split(r"[\s,]+", value) if item)
    return selected


def legacy_worker_containers(
    environment: str, selected: Iterable[str]
) -> list[str]:
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
        "qqcc-bot": bool(
            values.get(
                "QQCC_BOT_TOKEN_TEST" if environment == "test" else "QQCC_BOT_TOKEN",
                "",
            ).strip()
        ),
        "qqcc-private-bot-worker": values.get("PRIVATE_QQCC_BOT_ENABLED", "false")
        .strip()
        .lower()
        in {"1", "true", "yes", "on"},
        "paid-group-guard-bot": bool(values.get("PAID_GROUP_BOT_TOKEN", "").strip()),
    }
    disabled = {
        service
        for service, enabled in optional_enabled.items()
        if service in chosen and not enabled
    }
    return chosen - disabled, disabled


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
    paths = [
        f"{ENVIRONMENT[environment]['state_root']}/runtime/GENERATION_MAINTENANCE"
    ]
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


def _operator_preflight(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    _environment_values: Mapping[str, str],
) -> list[str]:
    blockers: list[str] = []
    env_path = local_env_file(args)
    if not env_path.is_file():
        blockers.append("operator-env-file-unavailable")
    elif env_path.stat().st_mode & 0o077:
        blockers.append("operator-env-file-permissions-not-600")
    if getattr(args, "local_env_error", False):
        blockers.append("operator-env-contract-invalid")
    if not args.skip_ci_checks:
        try:
            verify_release_ci(manifest, str(manifest["git_sha"]))
        except ReleaseError:
            blockers.append("operator-release-ci-unavailable")
    try:
        if args.env == "prod":
            if not getattr(args, "dashboard_fast_track", False):
                _promotion_check(args, manifest)
        else:
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
    _environment_values: Mapping[str, str],
) -> list[str]:
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
    if args.env == "prod" and initial:
        script += (
            f"compgen -G {shlex.quote(root + '/legacy-prod-*')} >/dev/null "
            "|| echo cloud-legacy-archive-unavailable\n"
        )
    previous_sha = str(getattr(args, "previous_sha", "") or "")
    if not initial and FULL_SHA_RE.fullmatch(previous_sha):
        previous_release_env = (
            _cloud_release_dir(
                previous_sha,
                str(manifest.get("track"))
                if manifest.get("track") in RELEASE_TRACKS
                else None,
            )
            + "/release.env"
        )
        script += (
            f"test -d {shlex.quote(root + '/releases/' + previous_sha)} "
            "|| echo cloud-rollback-checkout-unavailable\n"
            f"test -f {shlex.quote(previous_release_env)} "
            "|| echo cloud-rollback-release-env-unavailable\n"
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
    _manifest: Mapping[str, Any],
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
    selected = _split_services(
        [environment_values.get("ALLBOT_WORKER_SERVICES", "")]
    )
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
            if not (root / "release-env" / previous_sha / "release.env").is_file():
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
    previous_sha = str(getattr(args, "previous_sha", "") or "")
    if "initial-release" in impact.matched_rules:
        return []
    if not FULL_SHA_RE.fullmatch(previous_sha):
        return ["rollback-previous-release-state-unavailable"]
    cache = Path(args.bundle_cache).expanduser() / previous_sha
    manifest_available = any(
        path.is_file()
        for path in (cache / "release.json", cache / "release" / "release.json")
    )
    web_available = any(
        path.is_file()
        for path in (cache / "web-dist.tgz", cache / "release" / "web-dist.tgz")
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
    impact_blockers = sorted(set(impact.blockers))
    checks: dict[str, dict[str, Any]] = {
        "impact": {
            "status": "blocked" if impact_blockers else "passed",
            "blockers": impact_blockers,
        }
    }
    blockers: list[str] = list(impact_blockers)
    for name in ("operator", "cloud", "worker", "pages", "rollback"):
        if name == "worker" and args.env == "prod":
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
    return {
        "schema_version": 1,
        "environment": args.env,
        "git_sha": manifest["git_sha"],
        "status": "blocked" if blockers else "passed",
        "mutation_allowed": not blockers,
        "checks": checks,
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
    raise ReleaseError("release bundle does not contain release-index.json or release.json")


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
    return {
        "schema_version": 2,
        "source_sha": sha,
        "git_sha": sha,
        "ci_run": release.index["ci_run"],
        "release_channel": release.index["release_channel"],
        "source_ref": release.index["source_ref"],
        "track": track,
        "artifacts": release.manifests[track]["artifacts"],
        "selected_artifacts": list(selected),
        "release_index": str(path),
    }


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


def build_plan(args: argparse.Namespace) -> tuple[ReleaseImpact, dict[str, Any], str]:
    sha = validate_full_sha(args.sha)
    manifest_path = _resolve_manifest_path(args, allow_fetch=args.command == "plan")
    manifest_document = _read_json(manifest_path)
    if manifest_document.get("schema_version") == 2:
        requested_modules = _split_services(args.modules)
        requested_services = _split_services(args.services)
        test_data_repair = bool(
            getattr(args, "repair_test_data_services", False)
        )
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
        repair_fast_track = bool(
            getattr(args, "control_plane_repair_fast_track", False)
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
        planned_impact = ReleaseImpact(level="rolling")
        if not previous_sha and args.track == "test-execution":
            planned_impact.matched_rules.append("initial-release")
        changed_paths: list[str] = []
        if previous_sha and previous_sha != sha:
            changed_paths = git_changed_paths(previous_sha, sha)
            planned_impact = plan_changed_paths(
                load_structured_file(Path(args.policy)), changed_paths
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
        computed_modules.update(
            name
            for name, artifact in release_bundle.manifests[args.track]["artifacts"].items()
            if artifact.get("source_sha") == sha
            and name not in {"python-runtime-base", "python-worker-base"}
        )
        requested_modules.update(computed_modules)
        manifest = _load_v2_track(
            manifest_path,
            sha=sha,
            track=args.track,
            modules=requested_modules,
            select_all_when_empty=not bool(previous_sha),
        )
        validate_release_channel(
            manifest,
            environment=args.env,
            purpose=args.command,
            dashboard_fast_track=bool(
                getattr(args, "dashboard_fast_track", False)
            ),
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
        if not args.skip_ci_checks:
            verify_release_ci(manifest, sha)
        artifact_names = set(manifest["selected_artifacts"])
        if args.track == "control-plane":
            services = {
                CONTROL_ARTIFACT_SERVICE.get(name, name)
                for name in artifact_names
                if name not in {"python-runtime-base", "imgproxy", "postgres", "redis"}
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
        scope_release_impact(args.env, planned_impact, requested=requested_services)
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
    policy = load_structured_file(Path(args.policy))
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
            raise ReleaseError("dashboard fast-track requires an existing production release")
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


def _plan_document(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    previous_sha: str,
    environment_values: Mapping[str, str],
) -> dict[str, Any]:
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
        "worker": "worker" in impact.services,
        "web_static": "web-static" in impact.services,
        "requires_db_upgrade": impact.requires_db_upgrade,
        "blockers": sorted(impact.blockers),
        "unknown_paths": impact.unknown_paths,
        "matched_rules": impact.matched_rules,
        "promotion_mode": (
            "control-plane-repair-fast-track"
            if getattr(args, "control_plane_repair_fast_track", False)
            else "dashboard-fast-track"
            if getattr(args, "dashboard_fast_track", False)
            else "verified-test-promotion"
            if args.env == "prod"
            else "test-release"
        ),
        "mode": "execute" if args.execute else "dry-run",
        "release_channel": manifest.get("release_channel", "main"),
        "source_ref": manifest.get("source_ref", "refs/heads/main"),
    }
    if manifest.get("schema_version") == 2:
        document["artifacts"] = {
            name: manifest["artifacts"][name]
            for name in manifest["selected_artifacts"]
        }
    else:
        document["images"] = manifest["images"]
    return document


def _remote_shell(host: str, script: str, *, execute: bool) -> str:
    if not execute:
        print(f"[dry-run] ssh {host} bash -s")
        print(script.rstrip())
        return ""
    return _run(
        ["ssh", "-o", "BatchMode=yes", host, "bash -s"],
        input_text=script,
    ).stdout


def _deploy_cloud(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    release_env: str,
    environment_values: Mapping[str, str],
) -> None:
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
    compose = (
        f"docker compose --project-name {shlex.quote(environment['project'])} "
        f"--env-file {checkout}/deploy/env.defaults "
        f"--env-file {shlex.quote(env_file)} --env-file {release_dir}/release.env "
        f"-f {checkout}/deploy/docker-compose-cloud-base.yml "
        f"-f {checkout}/{environment['overlay']} "
        "--profile bot --profile qqcc-bot --profile qqcc-private-bots"
    )
    services = " ".join(shlex.quote(service) for service in cloud_services)
    resolved_api_base_checks = "".join(
        f"{compose} exec -T {shlex.quote(service)} python -c "
        "'import config; assert config.API_BASE == \"http://central-api:8003\"' "
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
    revision_checks = ""
    for service in cloud_services:
        revision = expected_revisions.get(service)
        if not revision:
            continue
        variable = expected_image_variables[service]
        revision_checks += (
            f'ref="${variable}"\n'
            'docker pull "$ref" >/dev/null\n'
            'docker image inspect "$ref" >/dev/null\n'
            "test \"$(docker image inspect --format "
            "'{{ index .Config.Labels \"org.opencontainers.image.revision\" }}' "
            f'\"$ref\")\" = {shlex.quote(revision)}\n'
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
        maintenance_paths = maintenance_files(
            args.env, initial_cutover=initial_cutover
        )
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
  deadline=$(( $(date +%s) + {args.drain_timeout_seconds} ))
  while true; do
    counts="$({drain_counts})"
    set -- $counts
    [ "$1" = 0 ] && [ "$2" = 0 ] && break
    [ "$(date +%s)" -lt "$deadline" ] || {{ echo 'queue drain timed out' >&2; exit 2; }}
    sleep {args.drain_interval_seconds}
  done
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
    script = f"""set -euo pipefail
test -d {shlex.quote(repo)}/.git || {{ echo 'release host is not bootstrapped; run scripts/bootstrap_release_host.sh' >&2; exit 3; }}
git -C {shlex.quote(repo)} fetch --prune origin {shlex.quote(release_branch)}
git -C {shlex.quote(repo)} merge-base --is-ancestor {sha} {shlex.quote(remote_release_ref)}
mkdir -p {shlex.quote(checkout_root)}/releases /var/lib/allbot/releases
if [ ! -d {shlex.quote(checkout)} ]; then
  git -C {shlex.quote(repo)} worktree add --detach {shlex.quote(checkout)} {sha}
fi
test "$(git -C {shlex.quote(checkout)} rev-parse HEAD)" = {sha}
install -d -m 755 {release_dir}
test -f {shlex.quote(env_file)}
test "$(stat -c %a {shlex.quote(env_file)})" = 600
. {release_dir}/release.env
{compose} config -q
start_snapshot=/tmp/allbot-nontarget-{sha}.txt
target_names="$({compose} ps --format '{{{{.Name}}}}' {services} 2>/dev/null || true)"
for name in {legacy_names or ":"}; do
  target_names="${{target_names}}
${{name}}"
done
: > "$start_snapshot"
for name in $(docker ps --format '{{{{.Names}}}}'); do
  printf '%s\n' "$target_names" | grep -Fxq "$name" && continue
  docker inspect --format '{{{{.Name}}}} {{{{.State.StartedAt}}}}' "$name" >> "$start_snapshot"
done
{maintenance_prefix}{compose} pull {services}
{revision_checks}
{legacy_handoff}{compose} up -d --no-deps --wait --wait-timeout 180 {services}
{compose} ps {services}
{resolved_api_base_checks}{resolved_image_checks}while read -r name started_at; do
  name="${{name#/}}"
  test "$(docker inspect --format '{{{{.State.StartedAt}}}}' "$name")" = "$started_at"
done < "$start_snapshot"
rm -f "$start_snapshot"
{legacy_commit}
{maintenance_suffix}
printf '%s\n' {shlex.quote(completion_marker)}
"""
    if impact.requires_db_upgrade:
        if not args.confirm_db_upgrade:
            raise ReleaseError("migration release requires --confirm-db-upgrade")
        backup_dir = f"{environment['state_root']}/backups"
        migration = f"""install -d -m 700 {backup_dir}
backup_file={backup_dir}/pre-{sha}-$(date -u +%Y%m%dT%H%M%SZ).sql.gz
umask 077
{compose} run --rm -T web-api sh -lc 'url="${{DATABASE_URL/postgresql+asyncpg:/postgresql:}}"; exec pg_dump "$url"' </dev/null | gzip -c > "$backup_file"
test -s "$backup_file"
heads="$({compose} run --rm -T web-api alembic heads </dev/null | grep -c ' (head)$')"
test "$heads" = 1
{compose} run --rm -T web-api alembic upgrade head </dev/null
"""
        script = script.replace(
            f"{compose} pull {services}\n",
            f"{compose} pull {services}\n" + migration,
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
    resolved_version = (lock_packages.get("node_modules/wrangler") or {}).get(
        "version"
    )
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
    canonical = project.get("canonical_deployment") if isinstance(project, Mapping) else None
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
    canonical = project.get("canonical_deployment") if isinstance(project, Mapping) else None
    if not isinstance(canonical, Mapping) or not canonical.get("id"):
        raise ReleaseError("Pages canonical deployment is unavailable")
    return str(canonical["id"])


def _rollback_pages(
    args: argparse.Namespace, transaction: Mapping[str, Any]
) -> None:
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
            project.get("canonical_deployment") if isinstance(project, Mapping) else None
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
    _run(
        ["git", "-C", str(repo), "fetch", "--prune", "origin", release_branch]
    )
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
    selected = _split_services(
        [environment_values.get("ALLBOT_WORKER_SERVICES", "")]
    )
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
    if not port.isdigit() or _run(
        ["curl", "-fsS", "--max-time", "10", f"http://127.0.0.1:{port}/health"],
        check=False,
    ).returncode:
        raise ReleaseError("recovered Worker relay health check failed")


def _cloud_release_dir(sha: str, track: str | None = None) -> str:
    root = "/var/lib/allbot/releases"
    if track in RELEASE_TRACKS:
        root += f"/{track}"
    return f"{root}/{sha}"


def _cloud_compose_command(
    args: argparse.Namespace,
    sha: str,
    *,
    track: str | None = None,
) -> str:
    environment = ENVIRONMENT[args.env]
    checkout = f"{args.remote_checkout_root}/releases/{sha}"
    env_file = args.remote_env_file or environment["env_file"]
    release_dir = _cloud_release_dir(sha, track)
    return (
        f"docker compose --project-name {shlex.quote(environment['project'])} "
        f"--env-file {shlex.quote(checkout + '/deploy/env.defaults')} "
        f"--env-file {shlex.quote(env_file)} "
        f"--env-file {shlex.quote(release_dir + '/release.env')} "
        f"-f {shlex.quote(checkout + '/deploy/docker-compose-cloud-base.yml')} "
        f"-f {shlex.quote(checkout + '/' + environment['overlay'])} "
        "--profile bot --profile qqcc-bot --profile qqcc-private-bots"
    )


def _rollback_cloud_stack(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    transaction: Mapping[str, Any],
    environment_values: Mapping[str, str],
) -> None:
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
    if previous_kind == "legacy":
        target_sha = str(transaction["target_sha"])
        snapshot = (
            _cloud_release_dir(target_sha, track) + "/legacy-cloud-running.txt"
        )
        project = environment["project"]
        removal = ""
        for service in services:
            removal += (
                "ids=\"$(docker ps -aq "
                f"--filter label=com.docker.compose.project={shlex.quote(project)} "
                f"--filter label=com.docker.compose.service={shlex.quote(service)})\"\n"
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
  done > {shlex.quote(snapshot + '.recovered')}
  test -s {shlex.quote(snapshot + '.recovered')}
fi
source_file={shlex.quote(snapshot)}
[ -s "$source_file" ] || source_file={shlex.quote(snapshot + '.recovered')}
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
        compose = _cloud_compose_command(args, previous_sha, track=track)
        previous_release_env = _cloud_release_dir(previous_sha, track) + "/release.env"
        script = f"""set -euo pipefail
test -d {shlex.quote(args.remote_checkout_root + '/releases/' + previous_sha)}
test -f {shlex.quote(previous_release_env)}
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
    history = (
        f"{state_root}/history/{transaction_id}.json"
    )
    forward_commit = transaction.get("phase") == "state_completed"
    state_action = f"rm -f {shlex.quote(staged)}\n"
    if forward_commit:
        state_action = (
            f"test -s {shlex.quote(staged)}\n"
            f"install -d -m 755 {shlex.quote(str(Path(history).parent))}\n"
            f"cp {shlex.quote(staged)} {shlex.quote(history + '.tmp')}\n"
            f"mv -f {shlex.quote(history + '.tmp')} {shlex.quote(history)}\n"
            f"mv -f {shlex.quote(staged)} {shlex.quote(current)}\n"
        )
    elif args.execute:
        previous_state = previous.get("state") if isinstance(previous, Mapping) else None
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
    script = "set -euo pipefail\n" + state_action + "".join(
        f"rm -f {shlex.quote(path)}\n" for path in paths
    )
    host = args.remote_host or ENVIRONMENT[args.env]["host"]
    _remote_shell(host, script, execute=args.execute)


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
        stage not in {"cloud", "worker", "pages", "state"}
        for stage in attempted_value
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
        if previous.get("kind") == "legacy":
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
[ -s "$source_file" ] || source_file={shlex.quote(snapshot + '.recovered')}
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
            compose = _cloud_compose_command(args, previous_sha, track=track)
            services = " ".join(shlex.quote(item) for item in sorted(selected_cloud))
            script = f"""set -euo pipefail
for service in {services}; do
  container_id="$({compose} ps -q "$service")"
  test -n "$container_id"
  test "$(docker inspect --format '{{{{.State.Running}}}}' "$container_id")" = true
  health="$(docker inspect --format '{{{{if .State.Health}}}}{{{{.State.Health.Status}}}}{{{{else}}}}none{{{{end}}}}' "$container_id")"
  [ "$health" = healthy ] || [ "$health" = none ]
done
"""
        _remote_shell(host, script, execute=True)
    if args.env == "test" and "worker" in attempted and "worker" in impact.services:
        port = environment_values.get("ALLBOT_WORKER_RELAY_PORT", "").strip()
        if not port.isdigit() or _run(
            [
                "curl",
                "-fsS",
                "--max-time",
                "10",
                f"http://127.0.0.1:{port}/health",
            ],
            check=False,
        ).returncode:
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
                workers = document.get("workers") if isinstance(document, Mapping) else None
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

    return ReleaseTransactionDependencies(
        cloud=lambda: _deploy_cloud(
            args, impact, manifest, release_env, environment_values
        ),
        worker=(
            (lambda: _deploy_worker(
                args, impact, manifest, release_env, environment_values
            ))
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
        validate_recovery=lambda: _validate_recovered_stack(
            args, impact, transaction, environment_values
        ),
        clear_maintenance=lambda: _clear_transaction_maintenance(args, transaction),
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
    args: argparse.Namespace, manifest: Mapping[str, Any]
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


def _git_file_at_sha(sha: str, path: str) -> str:
    sha = validate_full_sha(sha)
    return _run(["git", "show", f"{sha}:{path}"]).stdout


def _artifact_catalog_at_sha(sha: str) -> Mapping[str, Mapping[str, Any]]:
    try:
        document = json.loads(
            _git_file_at_sha(sha, "deploy/release-artifacts-v2.json")
        )
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
    if result.returncode != 0 or "private-worker-import-smoke=passed" not in result.stdout:
        raise ReleaseError("private-bot-worker digest import smoke failed")


def _promotion_check(args: argparse.Namespace, manifest: Mapping[str, Any]) -> None:
    if args.env != "prod":
        return
    state = _read_test_release_state(args, manifest)
    if getattr(args, "control_plane_repair_fast_track", False):
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
    if state.get("git_sha") != manifest.get("git_sha"):
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
        if state.get("status") != "verified":
            raise ReleaseError("cloud-test release has not been marked verified")
        return
    if state.get("images") != manifest.get("images"):
        raise ReleaseError("production image digests do not match cloud-test")
    if state.get("vendor_images") != manifest.get("vendor_images"):
        raise ReleaseError("production vendor image digests do not match cloud-test")
    if state.get("web_artifact_sha256") != manifest.get("web_artifact_sha256"):
        raise ReleaseError("production Web artifact does not match cloud-test")
    if state.get("status") != "verified":
        raise ReleaseError("cloud-test release has not been marked verified")


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
            name: {
                "digest": artifact.get("digest") or artifact.get("sha256"),
                "status": "verified",
            }
            for name, artifact in manifest["artifacts"].items()
            if name in manifest.get("selected_artifacts", [])
        }
        if state.get("status") != "verified" or state.get("artifacts") != expected:
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


def validate_test_acceptance(
    evidence: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    confirm_short_observation: bool = False,
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
            raise ReleaseError("test acceptance vendor digests do not match the release")
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
    short_observation = observation_duration_seconds < 24 * 60 * 60
    override_reason: str | None = None
    if short_observation:
        if not confirm_short_observation:
            if evidence.get("short_observation_override") is True:
                raise ReleaseError(
                    "short observation override requires explicit CLI confirmation"
                )
            raise ReleaseError(
                "test acceptance requires at least 24 hours of observation"
            )
        if evidence.get("short_observation_override") is not True:
            raise ReleaseError(
                "short observation override requires evidence flag "
                "short_observation_override=true"
            )
        override_reason = str(evidence.get("override_reason", "")).strip()
        if not override_reason:
            raise ReleaseError(
                "short observation override requires non-empty override_reason"
            )
    checks = evidence.get("checks")
    missing = sorted(
        key
        for key in REQUIRED_ACCEPTANCE_CHECKS
        if not isinstance(checks, Mapping) or checks.get(key) is not True
    )
    if missing:
        raise ReleaseError(
            "test acceptance checks are incomplete: " + ", ".join(missing)
        )
    if not str(evidence.get("approved_by", "")).strip():
        raise ReleaseError("test acceptance approved_by is required")
    return {
        "approved_by": str(evidence["approved_by"]).strip(),
        "completed_at": evidence["completed_at"],
        "observation_started_at": evidence["observation_started_at"],
        "observation_duration_seconds": observation_duration_seconds,
        "short_observation_override": short_observation,
        "override_reason": override_reason,
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


def _mark_test_verified(args: argparse.Namespace) -> None:
    sha = validate_full_sha(args.sha)
    manifest_path = Path(args.manifest)
    raw_manifest = _read_json(manifest_path)
    if raw_manifest.get("schema_version") == 2:
        manifest = _load_v2_track(
            manifest_path,
            sha=sha,
            track=args.track,
            modules=_split_services(args.modules),
        )
        validate_release_channel(
            manifest, environment="test", purpose="verify-test"
        )
    else:
        if getattr(args, "track", "control-plane") != "control-plane" or _split_services(
            getattr(args, "modules", [])
        ):
            raise ReleaseError(
                "release schema v1 supports only the control-plane track"
            )
        manifest = raw_manifest
        validate_release_manifest(manifest, sha)
    evidence = _read_json(Path(args.evidence))
    acceptance = validate_test_acceptance(
        evidence,
        manifest,
        confirm_short_observation=getattr(
            args, "confirm_short_observation", False
        ),
    )
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
        expected_artifacts = {
            name: {
                "digest": manifest["artifacts"][name].get("digest")
                or manifest["artifacts"][name].get("sha256"),
                "status": "deployed",
            }
            for name in manifest["selected_artifacts"]
        }
        if state.get("track") != manifest.get("track") or state.get(
            "artifacts"
        ) != expected_artifacts:
            raise ReleaseError(
                "cloud-test runtime state does not match acceptance evidence"
            )
        health = state.get("health")
        required_health = (
            "worker" if manifest["track"] == "test-execution" else "cloud"
        )
        if not isinstance(health, Mapping) or health.get(required_health) not in {
            "compose-ps-passed",
            "not-targeted",
        }:
            raise ReleaseError("cloud-test track health has not passed verification")
    else:
        if (
            state.get("images") != manifest.get("images")
            or state.get("vendor_images") != manifest.get("vendor_images")
            or state.get("web_artifact_sha256")
            != manifest.get("web_artifact_sha256")
        ):
            raise ReleaseError(
                "cloud-test runtime state does not match acceptance evidence"
            )
        validate_test_runtime_for_acceptance(state)
    state["status"] = "verified"
    if manifest.get("schema_version") == 2:
        for artifact in state["artifacts"].values():
            artifact["status"] = "verified"
    state["acceptance"] = acceptance
    if not args.execute:
        if acceptance["short_observation_override"]:
            print(
                "[dry-run] short observation override confirmed; "
                f"duration={acceptance['observation_duration_seconds']}s"
            )
        print(f"[dry-run] mark cloud-test {sha} verified on {host}")
        return
    payload = json.dumps(state, sort_keys=True, indent=2) + "\n"
    evidence_payload = json.dumps(evidence, sort_keys=True, indent=2) + "\n"
    acceptance_path = f"{state_root}/acceptance/{sha}.json"
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
    history_path = f"{state_root}/history/{sha}.json"
    _run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            host,
            f"set -e; cat > {history_path}.tmp; mv -f {history_path}.tmp {history_path}",
        ],
        input_text=payload,
    )


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
    state = {
        "schema_version": 2,
        "environment": args.env,
        "track": manifest.get("track", "control-plane"),
        "release_channel": manifest.get("release_channel", "main"),
        "source_ref": manifest.get("source_ref", "refs/heads/main"),
        "git_sha": manifest["git_sha"],
        "config_revision": config_revision,
        "services": sorted(impact.services),
        "status": (
            "verified"
            if args.command == "rollback" and args.env == "test"
            else "deployed"
        ),
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "promotion_mode": (
            "control-plane-repair-fast-track"
            if getattr(args, "control_plane_repair_fast_track", False)
            else "dashboard-fast-track"
            if getattr(args, "dashboard_fast_track", False)
            else "verified-test-promotion"
            if args.env == "prod"
            else "test-release"
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
    if getattr(args, "control_plane_repair_fast_track", False):
        acceptance = getattr(args, "control_plane_repair_acceptance", None)
        if not isinstance(acceptance, Mapping):
            raise ReleaseError(
                "control-plane repair fast-track acceptance is unavailable"
            )
        state["repair_acceptance"] = dict(acceptance)
    if manifest.get("schema_version") == 2:
        state["artifacts"] = {
            name: {
                "digest": manifest["artifacts"][name].get("digest")
                or manifest["artifacts"][name].get("sha256"),
                "status": state["status"],
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


def _add_release_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--env", choices=("test", "prod"), required=True)
    parser.add_argument("--sha")
    parser.add_argument("--to", help="rollback target SHA (alias for --sha)")
    parser.add_argument("--transaction", help="persisted release transaction SHA")
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
    parser.add_argument("--modules", action="append", default=[])
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--env-file")
    parser.add_argument("--state-file")
    parser.add_argument("--skip-git-checks", action="store_true")
    parser.add_argument("--skip-ci-checks", action="store_true")
    parser.add_argument("--skip-env-checks", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-prod", action="store_true")
    parser.add_argument(
        "--dashboard-fast-track",
        action="store_true",
        help=(
            "deploy only Dashboard services to production without cloud-test "
            "promotion; CI artifacts and production confirmation remain required"
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
        _add_release_arguments(child)
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
    verify.add_argument("--remote-host")
    verify.add_argument("--confirm-short-observation", action="store_true")
    verify.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
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
        if args.command == "recover":
            if not args.transaction:
                raise ReleaseError("recover requires --transaction")
            transaction_id = validate_full_sha(args.transaction)
            if not args.execute:
                raise ReleaseError("recover requires --execute")
            if args.env == "prod" and not args.confirm_prod:
                raise ReleaseError("production recover requires --confirm-prod")
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
        if args.env == "prod" and args.execute and not args.confirm_prod:
            raise ReleaseError("production execute requires --confirm-prod")
        if args.command == "preflight" and args.execute:
            raise ReleaseError("preflight is read-only and does not accept --execute")
        if args.execute and args.skip_ci_checks:
            raise ReleaseError("execute mode cannot skip release CI verification")
        if args.skip_env_checks and args.command != "plan":
            raise ReleaseError("--skip-env-checks is only available for plan")
        impact, manifest, previous_sha = build_plan(args)
        if args.execute:
            verify_operator_worktree_clean(
                source_ref=str(manifest.get("source_ref", "refs/heads/main")),
                environment=args.env,
                command=args.command,
            )
        args.previous_sha = previous_sha
        if args.command == "rollback" and not args.dashboard_fast_track:
            impact.level = "maintenance"
        if args.skip_env_checks:
            environment_values, config_revision = {}, ""
        elif args.command == "plan":
            environment_values, config_revision = _validate_local_env(args)
        else:
            try:
                environment_values, config_revision = _validate_local_env(args)
                args.local_env_error = False
            except ReleaseError:
                environment_values, config_revision = {}, ""
                args.local_env_error = True
        document = _plan_document(
            args,
            impact,
            manifest,
            previous_sha,
            environment_values,
        )
        print(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True))
        if args.command == "plan":
            return 0
        preflight = preflight_release(args, impact, manifest, environment_values)
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
            return 0
        if manifest.get("schema_version") == 2 and args.track == "gpu-execution":
            raise ReleaseError(
                "GPU track mutations must use the profile canary operator; "
                "release.py records plans, verification, and rollback metadata only"
            )
        release_env = (
            render_track_release_env(manifest, config_revision)
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
        transaction["services"] = sorted(impact.services)
        transaction["level"] = impact.level
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
        execute_release_transaction(transaction, dependencies)
        return 0
    except ReleaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
