#!/usr/bin/env python3
"""Plan and execute AllBot immutable releases.

The public seam is intentionally small: ``plan``, ``deploy``, ``rollback`` and
``validate-env``.  Application code is delivered only through digest-pinned
images from a CI-produced release manifest.  Git checkouts on runtime hosts are
used solely for the matching deployment contract (compose, policy and helpers).
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
import tempfile
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "deploy" / "release-policy.yml"
DEFAULT_SCHEMA = ROOT / "deploy" / "env.schema.yml"
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


def plan_changed_paths(policy: Mapping[str, Any], paths: Iterable[str]) -> ReleaseImpact:
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
        services.update(all_services if fallback_services == "all" else fallback_services)
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


def validate_release_manifest(manifest: Mapping[str, Any], expected_sha: str) -> None:
    expected_sha = validate_full_sha(expected_sha)
    if manifest.get("schema_version") != 1:
        raise ReleaseError("release manifest schema_version must be 1")
    if manifest.get("git_sha") != expected_sha:
        raise ReleaseError("release manifest git_sha does not match requested SHA")
    images = manifest.get("images")
    if not isinstance(images, Mapping) or not REQUIRED_IMAGES <= set(images):
        missing = sorted(REQUIRED_IMAGES - set(images or {}))
        raise ReleaseError("release manifest is missing image entries: " + ", ".join(missing))
    mutable = sorted(
        name for name in REQUIRED_IMAGES if not DIGEST_IMAGE_RE.fullmatch(str(images[name]))
    )
    if mutable:
        raise ReleaseError(
            "release images must be digest-pinned (digest-pinned): " + ", ".join(mutable)
        )
    vendor_images = manifest.get("vendor_images")
    if not isinstance(vendor_images, Mapping) or not REQUIRED_VENDOR_IMAGES <= set(vendor_images):
        missing = sorted(REQUIRED_VENDOR_IMAGES - set(vendor_images or {}))
        raise ReleaseError("release manifest is missing vendor image entries: " + ", ".join(missing))
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
        raise ReleaseError("release manifest ci_run must identify the successful CI run")


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
    forbidden_values = {str(item).lower() for item in common.get("forbidden_values", [])}
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


def _run(
    args: Sequence[str],
    *,
    cwd: Path = ROOT,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(args),
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1:] or result.stdout.strip().splitlines()[-1:]
        raise ReleaseError("command failed: " + (detail[0] if detail else args[0]))
    return result


def verify_git_release(sha: str) -> None:
    _run(["git", "cat-file", "-e", f"{sha}^{{commit}}"])
    result = _run(
        ["git", "merge-base", "--is-ancestor", sha, "origin/main"],
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseError("release SHA is not reachable from origin/main")
    remote_refs = _run(["git", "branch", "-r", "--contains", sha]).stdout
    if not any(line.strip().startswith("origin/") for line in remote_refs.splitlines()):
        raise ReleaseError("release SHA has not been pushed to origin")


def verify_operator_worktree_clean() -> None:
    if _run(["git", "status", "--porcelain"]).stdout.strip():
        raise ReleaseError("execute mode refuses an uncommitted operator worktree")
    head = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
    if _run(["git", "merge-base", "--is-ancestor", head, "origin/main"], check=False).returncode:
        raise ReleaseError("operator checkout must be a clean origin/main release checkout")


def verify_release_ci(manifest: Mapping[str, Any], sha: str) -> None:
    match = re.fullmatch(
        r"https://github\.com/giraffu/All_bot/actions/runs/([0-9]+)",
        str(manifest.get("ci_run", "")),
    )
    if not match:
        raise ReleaseError("release manifest CI run URL is not trusted")
    result = _run(
        [
            "gh", "run", "view", match.group(1), "--repo", "giraffu/All_bot",
            "--json", "conclusion,headSha,status",
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


def git_changed_paths(from_sha: str | None, target_sha: str) -> list[str]:
    if from_sha:
        validate_full_sha(from_sha)
        output = _run(
            ["git", "diff", "--name-only", "--diff-filter=ACDMRT", from_sha, target_sha]
        ).stdout
        return [line for line in output.splitlines() if line]
    return []


def _split_services(values: Sequence[str]) -> set[str]:
    selected: set[str] = set()
    for value in values:
        selected.update(item for item in re.split(r"[\s,]+", value) if item)
    return selected


def legacy_worker_containers(selected: Iterable[str]) -> list[str]:
    slots = sorted(
        int(match.group(1))
        for service in selected
        if (match := re.fullmatch(r"worker-(0[1-8])", service))
    )
    return [
        *(f"cloud-comfy-agent-test-{slot}" for slot in slots),
        "cloud-worker-relay-test",
    ]


def cloud_services_for_release(
    environment: str, impact: ReleaseImpact
) -> set[str]:
    selected = set(impact.services) & set(
        ENVIRONMENT[environment]["available_services"]
    )
    if environment == "test" and "initial-release" in impact.matched_rules:
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
        "qqcc-private-bot-worker": values.get(
            "PRIVATE_QQCC_BOT_ENABLED", "false"
        ).strip().lower()
        in {"1", "true", "yes", "on"},
        "paid-group-guard-bot": bool(
            values.get("PAID_GROUP_BOT_TOKEN", "").strip()
        ),
    }
    disabled = {
        service
        for service, enabled in optional_enabled.items()
        if service in chosen and not enabled
    }
    return chosen - disabled, disabled


def legacy_cloud_containers(
    environment: str, selected: Iterable[str]
) -> list[str]:
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


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"invalid JSON file: {path}") from exc
    if not isinstance(value, dict):
        raise ReleaseError(f"JSON file must contain an object: {path}")
    return value


def _resolve_manifest_path(args: argparse.Namespace) -> Path:
    if args.manifest:
        return Path(args.manifest)
    cache = Path(args.bundle_cache).expanduser() / args.sha
    candidates = (cache / "release.json", cache / "release/release.json")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
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
    raise ReleaseError("release bundle does not contain release.json")


def _resolve_previous_sha(args: argparse.Namespace) -> str | None:
    if args.from_sha:
        return validate_full_sha(args.from_sha)
    if args.state_file:
        value = _read_json(Path(args.state_file)).get("git_sha")
        return validate_full_sha(str(value))
    state_path = f"/var/lib/allbot/deployments/{args.env}/current.json"
    local_state = Path(state_path)
    if local_state.exists():
        return validate_full_sha(str(_read_json(local_state).get("git_sha")))
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
        return validate_full_sha(str(state.get("git_sha", "")))
    return None


def build_plan(args: argparse.Namespace) -> tuple[ReleaseImpact, dict[str, Any], str]:
    sha = validate_full_sha(args.sha)
    if not args.skip_git_checks:
        verify_git_release(sha)
    manifest = _read_json(_resolve_manifest_path(args))
    validate_release_manifest(manifest, sha)
    if not args.skip_ci_checks:
        verify_release_ci(manifest, sha)
    policy = load_structured_file(Path(args.policy))
    previous_sha = _resolve_previous_sha(args)
    if previous_sha:
        impact = plan_changed_paths(policy, git_changed_paths(previous_sha, sha))
    else:
        impact = ReleaseImpact(
            services=policy["all_services"],
            level="maintenance",
            matched_rules=["initial-release"],
        )
    requested = _split_services(args.services)
    unknown_services = requested - set(policy["all_services"])
    if unknown_services:
        raise ReleaseError("unknown requested services: " + ", ".join(sorted(unknown_services)))
    impact.services = merge_requested_services(
        computed=impact.services,
        requested=requested,
    )
    return impact, manifest, previous_sha or ""


def _plan_document(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    previous_sha: str,
    environment_values: Mapping[str, str],
) -> dict[str, Any]:
    cloud_services, disabled_cloud_services = filter_enabled_cloud_services(
        args.env,
        cloud_services_for_release(args.env, impact),
        environment_values,
    )
    return {
        "environment": args.env,
        "git_sha": manifest["git_sha"],
        "previous_sha": previous_sha or None,
        "level": impact.level,
        "services": sorted(impact.services),
        "cloud_services": sorted(cloud_services),
        "disabled_cloud_services": sorted(disabled_cloud_services),
        "worker": "worker" in impact.services,
        "web_static": "web-static" in impact.services,
        "requires_db_upgrade": impact.requires_db_upgrade,
        "blockers": sorted(impact.blockers),
        "unknown_paths": impact.unknown_paths,
        "matched_rules": impact.matched_rules,
        "images": manifest["images"],
        "mode": "execute" if args.execute else "dry-run",
    }


def _remote_shell(host: str, script: str, *, execute: bool) -> None:
    if not execute:
        print(f"[dry-run] ssh {host} bash -s")
        print(script.rstrip())
        return
    _run(["ssh", "-o", "BatchMode=yes", host, "bash -s"], input_text=script)


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
    checkout_root = args.remote_checkout_root
    checkout = f"{checkout_root}/releases/{sha}"
    repo = f"{checkout_root}/repo"
    release_dir = f"/var/lib/allbot/releases/{sha}"
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
    initial_cutover = (
        "initial-release" in impact.matched_rules and impact.level == "maintenance"
    )
    legacy_containers = legacy_cloud_containers(args.env, cloud_services)
    legacy_names = " ".join(shlex.quote(name) for name in legacy_containers)
    legacy_handoff = ""
    legacy_commit = ""
    if initial_cutover:
        if args.execute and not args.confirm_legacy_cutover:
            raise ReleaseError("initial immutable cutover requires --confirm-legacy-cutover")
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
    hold_maintenance = hold_maintenance_for_worker_cutover(args.env, impact)
    if impact.level == "maintenance":
        maintenance_file = f"{environment['state_root']}/runtime/GENERATION_MAINTENANCE"
        drain_condition = f"{compose} ps -q central-api | grep -q ."
        drain_counts = (
            f"{compose} exec -T central-api python -c "
            "'import os,redis; c=redis.Redis.from_url(os.environ.get(\"WORKER_REDIS_URL\") or os.environ[\"REDIS_URL\"]); "
            "print(c.zcard(\"comfy:queue:pending\"),c.scard(\"comfy:queue:running\"))'"
        )
        if initial_cutover and "central-api" in cloud_services:
            legacy_central = legacy_cloud_containers(args.env, {"central-api"})[0]
            drain_condition = (
                "docker ps --format '{{.Names}}' | "
                f"grep -Fxq {shlex.quote(legacy_central)}"
            )
            drain_counts = (
                f"docker exec {shlex.quote(legacy_central)} python -c "
                "'import os,redis; c=redis.Redis.from_url(os.environ.get(\"WORKER_REDIS_URL\") or os.environ[\"REDIS_URL\"]); "
                "print(c.zcard(\"comfy:queue:pending\"),c.scard(\"comfy:queue:running\"))'"
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
        maintenance_prefix = f"""install -d -m 755 {environment['state_root']}/runtime
touch {maintenance_file}
{legacy_setup}cleanup_maintenance() {{
  status=$?
  set +e
  {legacy_restore}rm -f {maintenance_file}
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
                "trap - EXIT\n"
                "echo 'generation maintenance held for worker cutover'\n"
            )
        else:
            maintenance_suffix = f"rm -f {maintenance_file}\ntrap - EXIT\n"
    script = f"""set -euo pipefail
test -d {shlex.quote(repo)}/.git || {{ echo 'release host is not bootstrapped; run scripts/bootstrap_release_host.sh' >&2; exit 3; }}
git -C {shlex.quote(repo)} fetch --prune origin main
git -C {shlex.quote(repo)} merge-base --is-ancestor {sha} origin/main
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
for name in {legacy_names or ':'}; do
  target_names="${{target_names}}
${{name}}"
done
: > "$start_snapshot"
for name in $(docker ps --format '{{{{.Names}}}}'); do
  printf '%s\n' "$target_names" | grep -Fxq "$name" && continue
  docker inspect --format '{{{{.Name}}}} {{{{.State.StartedAt}}}}' "$name" >> "$start_snapshot"
done
{maintenance_prefix}{compose} pull {services}
for ref in "$ALLBOT_APP_IMAGE" "$ALLBOT_CENTRAL_IMAGE" "$ALLBOT_DASHBOARD_BACKEND_IMAGE" "$ALLBOT_DASHBOARD_FRONTEND_IMAGE"; do
  docker pull "$ref" >/dev/null
  docker image inspect "$ref" >/dev/null
  test "$(docker image inspect --format '{{{{ index .Config.Labels \"org.opencontainers.image.revision\" }}}}' "$ref")" = {sha}
done
{legacy_handoff}{compose} up -d --no-deps --wait --wait-timeout 180 {services}
{compose} ps {services}
while read -r name started_at; do
  name="${{name#/}}"
  test "$(docker inspect --format '{{{{.State.StartedAt}}}}' "$name")" = "$started_at"
done < "$start_snapshot"
rm -f "$start_snapshot"
{legacy_commit}
{maintenance_suffix}
"""
    if impact.requires_db_upgrade:
        if not args.confirm_db_upgrade:
            raise ReleaseError("migration release requires --confirm-db-upgrade")
        backup_dir = f"{environment['state_root']}/backups"
        migration = f"""install -d -m 700 {backup_dir}
backup_file={backup_dir}/pre-{sha}-$(date -u +%Y%m%dT%H%M%SZ).sql.gz
umask 077
{compose} run --rm -T web-api sh -lc 'url="${{DATABASE_URL/postgresql+asyncpg:/postgresql:}}"; exec pg_dump "$url"' | gzip -c > "$backup_file"
test -s "$backup_file"
heads="$({compose} run --rm web-api alembic heads | grep -c ' (head)$')"
test "$heads" = 1
{compose} run --rm web-api alembic upgrade head
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
        print(f"[dry-run] install non-secret release.env on {host}:{release_dir}/release.env")
    _remote_shell(host, script, execute=args.execute)


def _verify_web_artifact(path: Path, expected_hash: str) -> None:
    if not path.is_file():
        raise ReleaseError(f"web artifact is unavailable: {path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected_hash:
        raise ReleaseError("web artifact checksum does not match release manifest")


def _deploy_web(
    args: argparse.Namespace,
    manifest: Mapping[str, Any],
) -> None:
    if args.skip_web:
        return
    artifact = Path(args.web_artifact)
    if not artifact.is_file() and args.web_artifact == "web-dist.tgz":
        cache = Path(args.bundle_cache).expanduser() / str(manifest["git_sha"])
        for candidate in (cache / "web-dist.tgz", cache / "release/web-dist.tgz"):
            if candidate.is_file():
                artifact = candidate
                break
    _verify_web_artifact(artifact, str(manifest["web_artifact_sha256"]))
    sha = str(manifest["git_sha"])
    if args.env == "test":
        remote_dir = f"/root/allbot-web-releases/{sha}"
        if not args.execute:
            print(f"[dry-run] upload {artifact} to web edge {remote_dir} and switch /root/dist-test")
            return
        key_path = Path(args.test_web_ssh_key)
        if not key_path.is_file():
            raise ReleaseError(f"test Web SSH key is unavailable: {key_path}")
        key = str(key_path)
        target = "root@100.88.57.122"
        _run(["ssh", "-i", key, target, f"install -d -m 755 {remote_dir}"])
        _run(["scp", "-i", key, str(artifact), f"{target}:{remote_dir}/web-dist.tgz"])
        _run(
            [
                "ssh",
                "-i",
                key,
                target,
                (
                    f"set -e; tar -xzf {remote_dir}/web-dist.tgz -C {remote_dir}; "
                    f"ln -sfn {remote_dir}/dist /root/dist-test.next; "
                    "mv -Tf /root/dist-test.next /root/dist-test"
                ),
            ]
        )
        return
    token_file = Path(args.cloudflare_token_file)
    if not token_file.is_file():
        raise ReleaseError(f"Cloudflare Pages token file is unavailable: {token_file}")
    if not args.execute:
        print("[dry-run] extract verified Web artifact and deploy it to Pages project allbot-web-prod")
        return
    with tempfile.TemporaryDirectory(prefix="allbot-web-release-") as temp_dir:
        _run(["tar", "-xzf", str(artifact), "-C", temp_dir])
        env = os.environ.copy()
        env["CLOUDFLARE_API_TOKEN"] = token_file.read_text(encoding="utf-8").strip()
        env["CLOUDFLARE_ACCOUNT_ID"] = args.cloudflare_account_id
        result = subprocess.run(
            [
                "npx",
                "wrangler",
                "pages",
                "deploy",
                str(Path(temp_dir) / "dist"),
                "--project-name",
                "allbot-web-prod",
                "--branch",
                "main",
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


def _deploy_worker(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    release_env: str,
    environment_values: Mapping[str, str],
) -> None:
    selected = _split_services(
        [environment_values.get("ALLBOT_WORKER_SERVICES", "")]
    )
    if not selected:
        raise ReleaseError(
            "worker release requires ALLBOT_WORKER_SERVICES in the target env"
        )
    invalid = sorted(
        service
        for service in selected
        if not re.fullmatch(r"worker-(0[1-8])", service)
    )
    if invalid:
        raise ReleaseError("invalid ALLBOT_WORKER_SERVICES entries: " + ", ".join(invalid))

    sha = str(manifest["git_sha"])
    root = Path(args.worker_checkout_root)
    repo = root / "repo"
    checkout = root / "releases" / sha
    release_dir = root / "release-env" / sha
    release_path = release_dir / "release.env"
    env_file = Path(args.env_file or ENVIRONMENT[args.env]["env_file"])
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
    if not args.execute:
        print(
            "[dry-run] worker drain/recreate from digest-pinned image: "
            + " ".join(service_args)
        )
        if "initial-release" in impact.matched_rules:
            print(
                "[dry-run] stop matching legacy test worker containers: "
                + " ".join(legacy_worker_containers(selected))
            )
        if hold_maintenance_for_worker_cutover(args.env, impact):
            print("[dry-run] clear cloud-test generation maintenance after worker health")
        return
    if not (repo / ".git").is_dir():
        raise ReleaseError(
            "worker release checkout is not bootstrapped; run scripts/bootstrap_release_host.sh"
        )
    _run(["git", "-C", str(repo), "fetch", "--prune", "origin", "main"])
    _run(["git", "-C", str(repo), "merge-base", "--is-ancestor", sha, "origin/main"])
    checkout.parent.mkdir(parents=True, exist_ok=True)
    if not checkout.exists():
        _run(["git", "-C", str(repo), "worktree", "add", "--detach", str(checkout), sha])
    if _run(["git", "-C", str(checkout), "rev-parse", "HEAD"]).stdout.strip() != sha:
        raise ReleaseError("worker release checkout SHA mismatch")
    release_dir.mkdir(parents=True, exist_ok=True)
    temp_path = release_path.with_suffix(".tmp")
    temp_path.write_text(release_env, encoding="utf-8")
    temp_path.chmod(0o644)
    temp_path.replace(release_path)
    _run([*compose, "config", "-q"])
    _run([*compose, "pull", *service_args])
    worker_ref = str(manifest["images"]["worker"])
    revision = _run(
        [
            "docker", "image", "inspect", "--format",
            '{{ index .Config.Labels "org.opencontainers.image.revision" }}',
            worker_ref,
        ]
    ).stdout.strip()
    if revision != sha:
        raise ReleaseError("worker OCI revision does not match release SHA")
    if "initial-release" in impact.matched_rules:
        existing = [
            name
            for name in legacy_worker_containers(selected)
            if _run(["docker", "inspect", name], check=False).returncode == 0
        ]
        if existing:
            _run(["docker", "stop", *existing])
    # The impact planner has already elevated worker changes to drain level.
    # Recreate only the explicit slot allowlist; dormant canary slots stay off.
    _run([*compose, "stop", *sorted(selected)])
    _run([*compose, "up", "-d", "--no-deps", "--wait", "--wait-timeout", "180", *service_args])
    _run([*compose, "ps", *service_args])
    if hold_maintenance_for_worker_cutover(args.env, impact):
        environment = ENVIRONMENT[args.env]
        host = args.remote_host or environment["host"]
        maintenance_file = f"{environment['state_root']}/runtime/GENERATION_MAINTENANCE"
        _remote_shell(
            host,
            f"set -euo pipefail\nrm -f {shlex.quote(maintenance_file)}\n",
            execute=True,
        )


def _promotion_check(args: argparse.Namespace, manifest: Mapping[str, Any]) -> None:
    if args.env != "prod":
        return
    host = args.test_state_host
    if args.command == "rollback":
        state_path = f"/var/lib/allbot/deployments/test/history/{manifest['git_sha']}.json"
    else:
        state_path = "/var/lib/allbot/deployments/test/current.json"
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
    if state.get("git_sha") != manifest.get("git_sha"):
        raise ReleaseError("production SHA does not match the tested SHA")
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
    path = f"/var/lib/allbot/deployments/test/history/{manifest['git_sha']}.json"
    result = _run(["ssh", "-o", "BatchMode=yes", host, f"cat {path}"], check=False)
    if result.returncode != 0:
        raise ReleaseError("rollback target has no retained successful test release")
    try:
        state = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ReleaseError("rollback target test history is invalid") from exc
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
    evidence: Mapping[str, Any], manifest: Mapping[str, Any]
) -> None:
    if evidence.get("git_sha") != manifest.get("git_sha"):
        raise ReleaseError("test acceptance SHA does not match the release")
    if evidence.get("images") != manifest.get("images"):
        raise ReleaseError("test acceptance image digests do not match the release")
    if evidence.get("vendor_images") != manifest.get("vendor_images"):
        raise ReleaseError("test acceptance vendor digests do not match the release")
    started = _parse_utc_timestamp(evidence.get("observation_started_at"), "observation_started_at")
    completed = _parse_utc_timestamp(evidence.get("completed_at"), "completed_at")
    if (completed - started).total_seconds() < 24 * 60 * 60:
        raise ReleaseError("test acceptance requires at least 24 hours of observation")
    if completed > datetime.now(timezone.utc):
        raise ReleaseError("test acceptance completed_at cannot be in the future")
    checks = evidence.get("checks")
    missing = sorted(
        key
        for key in REQUIRED_ACCEPTANCE_CHECKS
        if not isinstance(checks, Mapping) or checks.get(key) is not True
    )
    if missing:
        raise ReleaseError("test acceptance checks are incomplete: " + ", ".join(missing))
    if not str(evidence.get("approved_by", "")).strip():
        raise ReleaseError("test acceptance approved_by is required")


def _mark_test_verified(args: argparse.Namespace) -> None:
    sha = validate_full_sha(args.sha)
    manifest = _read_json(Path(args.manifest))
    validate_release_manifest(manifest, sha)
    evidence = _read_json(Path(args.evidence))
    validate_test_acceptance(evidence, manifest)
    host = args.remote_host or ENVIRONMENT["test"]["host"]
    state_path = "/var/lib/allbot/deployments/test/current.json"
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
    if (
        state.get("git_sha") != sha
        or state.get("images") != manifest.get("images")
        or state.get("vendor_images") != manifest.get("vendor_images")
        or state.get("web_artifact_sha256") != manifest.get("web_artifact_sha256")
    ):
        raise ReleaseError("cloud-test runtime state does not match acceptance evidence")
    state["status"] = "verified"
    state["acceptance"] = {
        "approved_by": evidence["approved_by"],
        "completed_at": evidence["completed_at"],
    }
    if not args.execute:
        print(f"[dry-run] mark cloud-test {sha} verified on {host}")
        return
    payload = json.dumps(state, sort_keys=True, indent=2) + "\n"
    evidence_payload = json.dumps(evidence, sort_keys=True, indent=2) + "\n"
    acceptance_path = f"/var/lib/allbot/deployments/test/acceptance/{sha}.json"
    _run(
        [
            "ssh", "-o", "BatchMode=yes", host,
            (
                "set -e; install -d -m 755 /var/lib/allbot/deployments/test/acceptance; "
                f"cat > {acceptance_path}.tmp; mv -f {acceptance_path}.tmp {acceptance_path}"
            ),
        ],
        input_text=evidence_payload,
    )
    _run(
        [
            "ssh", "-o", "BatchMode=yes", host,
            f"set -e; cat > {state_path}.tmp; mv -f {state_path}.tmp {state_path}",
        ],
        input_text=payload,
    )
    history_path = f"/var/lib/allbot/deployments/test/history/{sha}.json"
    _run(
        [
            "ssh", "-o", "BatchMode=yes", host,
            f"set -e; cat > {history_path}.tmp; mv -f {history_path}.tmp {history_path}",
        ],
        input_text=payload,
    )


def _write_state(
    args: argparse.Namespace,
    impact: ReleaseImpact,
    manifest: Mapping[str, Any],
    config_revision: str,
) -> None:
    environment = ENVIRONMENT[args.env]
    host = args.remote_host or environment["host"]
    state = {
        "schema_version": 1,
        "environment": args.env,
        "git_sha": manifest["git_sha"],
        "images": manifest["images"],
        "vendor_images": manifest["vendor_images"],
        "web_artifact_sha256": manifest["web_artifact_sha256"],
        "config_revision": config_revision,
        "services": sorted(impact.services),
        "status": (
            "verified"
            if args.command == "rollback" and args.env == "test"
            else "deployed"
        ),
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "health": {
            "cloud": "compose-ps-passed",
            "worker": "compose-ps-passed" if "worker" in impact.services else "not-targeted",
            "web": "artifact-checksum-passed" if "web-static" in impact.services else "not-targeted",
        },
    }
    payload = json.dumps(state, sort_keys=True, indent=2) + "\n"
    path = f"/var/lib/allbot/deployments/{args.env}/current.json"
    if not args.execute:
        print(f"[dry-run] write deployment state {host}:{path}")
        return
    history = f"/var/lib/allbot/deployments/{args.env}/history/{manifest['git_sha']}.json"
    command = (
        f"set -e; install -d -m 755 {shlex.quote(str(Path(path).parent))} "
        f"{shlex.quote(str(Path(history).parent))}; "
        f"cat > {shlex.quote(path + '.tmp')}; "
        f"cp {shlex.quote(path + '.tmp')} {shlex.quote(history)}; "
        f"mv -f {shlex.quote(path + '.tmp')} {shlex.quote(path)}"
    )
    _run(["ssh", "-o", "BatchMode=yes", host, command], input_text=payload)


def _validate_local_env(args: argparse.Namespace) -> tuple[dict[str, str], str]:
    path = Path(args.env_file or ENVIRONMENT[args.env]["env_file"])
    values = parse_env_file(path)
    schema = load_structured_file(Path(args.schema))
    revision = validate_environment(schema, args.env, values)
    return values, revision


def _add_release_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--env", choices=("test", "prod"), required=True)
    parser.add_argument("--sha")
    parser.add_argument("--to", help="rollback target SHA (alias for --sha)")
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
    parser.add_argument("--services", action="append", default=[])
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--env-file")
    parser.add_argument("--state-file")
    parser.add_argument("--skip-git-checks", action="store_true")
    parser.add_argument("--skip-ci-checks", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-prod", action="store_true")
    parser.add_argument("--confirm-db-upgrade", action="store_true")
    parser.add_argument("--confirm-legacy-cutover", action="store_true")
    parser.add_argument("--drain-timeout-seconds", type=int, default=7200)
    parser.add_argument("--drain-interval-seconds", type=int, default=15)
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
        default="/home/deploy/APP/All_bot-release",
    )
    parser.add_argument(
        "--test-web-ssh-key",
        default="/home/deploy/.ssh/allbot_test_edge_ed25519",
    )
    parser.add_argument(
        "--cloudflare-token-file",
        default="/home/deploy/.config/allbot/cloudflare-pages.token",
    )
    parser.add_argument(
        "--cloudflare-account-id",
        default="c7220eb751acc6f7ab8255b4a0394ef3",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("plan", "deploy", "rollback"):
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
    verify.add_argument("--remote-host")
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
        if args.command == "rollback" and args.to:
            if args.sha and args.sha != args.to:
                raise ReleaseError("rollback --sha and --to must identify the same SHA")
            args.sha = args.to
        if not args.sha:
            raise ReleaseError(f"{args.command} requires --sha")
        if args.env == "prod" and args.execute and not args.confirm_prod:
            raise ReleaseError("production execute requires --confirm-prod")
        if args.execute and args.skip_ci_checks:
            raise ReleaseError("execute mode cannot skip release CI verification")
        if args.execute:
            verify_operator_worktree_clean()
        impact, manifest, previous_sha = build_plan(args)
        environment_values, config_revision = _validate_local_env(args)
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
        if impact.blockers:
            raise ReleaseError(
                "release is blocked: " + ", ".join(sorted(impact.blockers))
            )
        if args.command == "rollback":
            impact.level = "maintenance"
        release_env = render_release_env(manifest, config_revision)
        if args.env == "prod":
            _promotion_check(args, manifest)
        else:
            _test_rollback_check(args, manifest)
        _deploy_cloud(
            args,
            impact,
            manifest,
            release_env,
            environment_values,
        )
        if "web-static" in impact.services:
            _deploy_web(args, manifest)
        if "worker" in impact.services:
            _deploy_worker(args, impact, manifest, release_env, environment_values)
        _write_state(args, impact, manifest, config_revision)
        return 0
    except ReleaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
