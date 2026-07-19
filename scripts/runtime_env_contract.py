#!/usr/bin/env python3
"""Validate a host environment and derive least-privilege service env files.

The module never serializes configuration values in summaries. Secret-bearing
projections are only returned to the caller or written with mode 0600 by the
activation path.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping


class ContractError(RuntimeError):
    """The host environment cannot safely configure the selected services."""


class EnvironmentSnapshot:
    def __init__(
        self,
        *,
        environment: str,
        environment_revision: str,
        contract_revision: str,
        projections: Mapping[str, Mapping[str, str]],
        service_revisions: Mapping[str, str],
        key_hashes: Mapping[str, str],
    ) -> None:
        self.environment = environment
        self.environment_revision = environment_revision
        self.contract_revision = contract_revision
        self.projections = {name: dict(values) for name, values in projections.items()}
        self.service_revisions = dict(service_revisions)
        self.key_hashes = dict(key_hashes)


def load_contract(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError("service environment contract is invalid") from exc
    if value.get("schema_version") != 1 or not isinstance(value.get("services"), dict):
        raise ContractError("unsupported service environment contract")
    _external_patterns(value)
    return value


def _external_patterns(contract: Mapping[str, Any]) -> tuple[str, ...]:
    raw_patterns = contract.get("external_patterns", [])
    if not isinstance(raw_patterns, list) or any(
        not isinstance(pattern, str) or not pattern.strip() for pattern in raw_patterns
    ):
        raise ContractError("service environment external_patterns is invalid")
    return tuple(pattern.strip() for pattern in raw_patterns)


def _is_external_key(contract: Mapping[str, Any], key: str) -> bool:
    return any(
        fnmatch.fnmatchcase(key, pattern) for pattern in _external_patterns(contract)
    )


def parse_env_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ContractError(f"invalid environment assignment at line {line_number}")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _digest(values: Mapping[str, str]) -> str:
    payload = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _projection(
    name: str,
    config: Mapping[str, Any],
    values: Mapping[str, str],
    *,
    included_keys: Iterable[str] = (),
) -> dict[str, str]:
    required = {str(key) for key in config.get("required", [])}
    missing = sorted(key for key in required if not values.get(key, "").strip())
    if missing:
        raise ContractError(
            f"{name} is missing required environment keys: " + ", ".join(missing)
        )
    patterns = [str(pattern) for pattern in config.get("patterns", [])]
    included = {str(key) for key in included_keys}
    selected = {
        key: value
        for key, value in values.items()
        if key in required
        or key in included
        or any(fnmatch.fnmatchcase(key, pattern) for pattern in patterns)
    }
    selected["ALLBOT_ENV"] = values["ALLBOT_ENV"]
    return selected


def _service_enabled(config: Mapping[str, Any], values: Mapping[str, str]) -> bool:
    condition = config.get("enabled_if")
    if not isinstance(condition, Mapping):
        return True
    key = str(condition.get("key", ""))
    value = values.get(key, "").strip()
    if condition.get("nonempty") is True:
        return bool(value)
    if "equals" in condition:
        return value.lower() == str(condition["equals"]).strip().lower()
    raise ContractError("service enabled_if contract is invalid")


def build_snapshot(
    contract: Mapping[str, Any],
    environment: str,
    values: Mapping[str, str],
    *,
    services: Iterable[str] | None = None,
) -> EnvironmentSnapshot:
    if environment not in {"test", "prod"}:
        raise ContractError("environment must be test or prod")
    if values.get("ALLBOT_ENV") != environment:
        raise ContractError(f"ALLBOT_ENV must equal {environment}")
    configured = contract.get("services")
    if not isinstance(configured, Mapping):
        raise ContractError("service environment contract has no services")
    selected = set(services or configured)
    unknown = sorted(selected - set(configured))
    if unknown:
        raise ContractError(
            "unknown service environment contract: " + ", ".join(unknown)
        )
    projections: dict[str, dict[str, str]] = {}
    revisions: dict[str, str] = {}
    shared_defaults = contract.get("shared_defaults", {})
    default_services = {
        str(name)
        for name in shared_defaults.get("services", [])
        if isinstance(name, str)
    }
    default_keys = {
        str(key) for key in shared_defaults.get("keys", []) if isinstance(key, str)
    }
    for name in sorted(selected):
        config = configured[name]
        if not isinstance(config, Mapping):
            raise ContractError(f"{name} service environment contract is invalid")
        if not _service_enabled(config, values):
            continue
        projection = _projection(
            name,
            config,
            values,
            included_keys=default_keys if name in default_services else (),
        )
        revision = _digest(projection)
        projection["ALLBOT_CONFIG_REVISION"] = revision
        projections[name] = projection
        revisions[name] = revision
    tracked_values = {
        key: value
        for key, value in values.items()
        if not _is_external_key(contract, key)
    }
    key_hashes = {
        key: hashlib.sha256(value.encode("utf-8")).hexdigest()
        for key, value in tracked_values.items()
    }
    contract_revision = hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    environment_revision = _digest(
        {**tracked_values, "ALLBOT_SERVICE_CONTRACT_REVISION": contract_revision}
    )
    return EnvironmentSnapshot(
        environment=environment,
        environment_revision=environment_revision,
        contract_revision=contract_revision,
        projections=projections,
        service_revisions=revisions,
        key_hashes=key_hashes,
    )


def affected_services(contract: Mapping[str, Any], changed_keys: set[str]) -> set[str]:
    changed_keys = {key for key in changed_keys if not _is_external_key(contract, key)}
    if not changed_keys:
        return set()
    configured = contract.get("services", {})
    affected: set[str] = set()
    matched_keys: set[str] = set()
    shared_defaults = contract.get("shared_defaults", {})
    if isinstance(shared_defaults, Mapping):
        shared_keys = {
            str(key) for key in shared_defaults.get("keys", []) if isinstance(key, str)
        }
        changed_shared = changed_keys & shared_keys
        if changed_shared:
            affected.update(
                str(name)
                for name in shared_defaults.get("services", [])
                if isinstance(name, str) and name in configured
            )
            matched_keys.update(changed_shared)
    for name, raw_config in configured.items():
        if not isinstance(raw_config, Mapping):
            continue
        required = {str(key) for key in raw_config.get("required", [])}
        patterns = [str(pattern) for pattern in raw_config.get("patterns", [])]
        matched = {
            key
            for key in changed_keys
            if key in required
            or any(fnmatch.fnmatchcase(key, pattern) for pattern in patterns)
        }
        if matched:
            affected.add(str(name))
            matched_keys.update(matched)
    if changed_keys - matched_keys:
        return {str(name) for name in configured}
    return affected


def unknown_changed_keys(
    contract: Mapping[str, Any], changed_keys: set[str]
) -> set[str]:
    changed_keys = {key for key in changed_keys if not _is_external_key(contract, key)}
    configured = contract.get("services", {})
    matched: set[str] = set()
    shared_defaults = contract.get("shared_defaults", {})
    if isinstance(shared_defaults, Mapping):
        matched.update(
            key
            for key in changed_keys
            if key
            in {
                str(value)
                for value in shared_defaults.get("keys", [])
                if isinstance(value, str)
            }
        )
    for raw_config in configured.values():
        if not isinstance(raw_config, Mapping):
            continue
        required = {str(key) for key in raw_config.get("required", [])}
        patterns = [str(pattern) for pattern in raw_config.get("patterns", [])]
        matched.update(
            key
            for key in changed_keys
            if key in required
            or any(fnmatch.fnmatchcase(key, pattern) for pattern in patterns)
        )
    return changed_keys - matched


def snapshot_summary(
    snapshot: EnvironmentSnapshot,
    *,
    changed_keys: Iterable[str] = (),
    active_revision: str | None = None,
    active_service_revisions: Mapping[str, Any] | None = None,
    credential_isolation: str = "pending",
) -> dict[str, Any]:
    changed = set(changed_keys)
    active_services = (
        active_service_revisions
        if isinstance(active_service_revisions, Mapping)
        else {}
    )
    service_drift = any(
        str(active_services.get(name, "")) != revision
        for name, revision in snapshot.service_revisions.items()
    )
    return {
        "schema_version": 1,
        "environment": snapshot.environment,
        "environment_revision": snapshot.environment_revision,
        "contract_revision": snapshot.contract_revision,
        "active_revision": active_revision,
        "drift": active_revision != snapshot.environment_revision or service_drift,
        "changed_keys": sorted(changed),
        "affected_services": sorted(
            name
            for name, projection in snapshot.projections.items()
            if not changed or any(key in projection for key in changed)
        ),
        "service_revisions": dict(sorted(snapshot.service_revisions.items())),
        "credential_isolation": credential_isolation,
    }


PUBLIC_CONFIG_KEYS = {
    "ALLBOT_ENV",
    "ALLBOT_STATE_ROOT",
    "CLOUD_TEST_BIND_IP",
    "CLOUD_TEST_CONTROL_HOST",
    "CLOUD_PROD_BIND_IP",
    "DASHBOARD_LAN_AIO_RUNNER_HOST",
    "DASHBOARD_LAN_AIO_RUNNER_KEY_DIR",
    "DASHBOARD_LAN_AIO_RUNNER_PROJECT_ROOT",
    "DASHBOARD_LAN_AIO_RUNNER_SSH_PORT",
    "DASHBOARD_RUNPOD_AUTOSCALER_ENABLED",
    "DASHBOARD_RUNPOD_AUTOSCALER_MODE",
    "PRIVATE_QQCC_BOT_ENABLED",
    "TON_PAYMENT_POLLING_ENABLED",
}


def dumps_summary(document: Mapping[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)


def _env_text(values: Mapping[str, str]) -> str:
    lines: list[str] = []
    for key in sorted(values):
        value = values[key]
        if "\n" in key or "\n" in value or "\r" in value:
            raise ContractError(f"{key} cannot be represented in a service env file")
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, text: str, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_active_state(root: Path) -> dict[str, Any] | None:
    path = root / "current.json"
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError("active service environment state is invalid") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ContractError("active service environment state is invalid")
    return value


def validate_active_projection_integrity(root: Path, active: Mapping[str, Any]) -> None:
    """Fail closed when the activated projection set was changed in place."""

    revision = str(active.get("environment_revision", ""))
    service_revisions = active.get("service_revisions")
    link = root / "current"
    state_path = root / "current.json"
    revision_path = root / revision
    if (
        not revision
        or len(revision) != 64
        or any(character not in "0123456789abcdef" for character in revision)
        or not isinstance(service_revisions, Mapping)
        or not service_revisions
        or not link.is_symlink()
        or os.readlink(link) != revision
        or root.stat().st_mode & 0o077
        or not revision_path.is_dir()
        or revision_path.stat().st_mode & 0o077
        or not state_path.is_file()
        or state_path.stat().st_mode & 0o077
    ):
        raise ContractError("active service environment integrity check failed")
    for service, raw_service_revision in service_revisions.items():
        service_name = str(service)
        service_revision = str(raw_service_revision)
        if (
            not service_name
            or any(
                character not in "abcdefghijklmnopqrstuvwxyz0123456789-"
                for character in service_name
            )
            or len(service_revision) != 64
            or any(
                character not in "0123456789abcdef" for character in service_revision
            )
        ):
            raise ContractError("active service environment integrity check failed")
        path = root / revision / f"{service_name}.env"
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
            raise ContractError("active service environment integrity check failed")
        projection = parse_env_text(path.read_text(encoding="utf-8"))
        recorded_revision = projection.pop("ALLBOT_CONFIG_REVISION", None)
        if (
            recorded_revision != service_revision
            or _digest(projection) != service_revision
        ):
            raise ContractError("active service environment integrity check failed")


def activate_snapshot(
    root: Path,
    snapshot: EnvironmentSnapshot,
    *,
    credential_isolation: str = "pending",
) -> dict[str, Any]:
    """Write one immutable projection set and atomically select it."""

    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    previous = load_active_state(root)
    previous_revision = (
        str(previous.get("environment_revision")) if previous is not None else None
    )
    revision_dir = root / snapshot.environment_revision
    if revision_dir.exists() and not revision_dir.is_dir():
        raise ContractError("service environment revision path is not a directory")
    revision_dir.mkdir(mode=0o700, exist_ok=True)
    os.chmod(revision_dir, 0o700)
    for service, projection in snapshot.projections.items():
        path = revision_dir / f"{service}.env"
        rendered = _env_text(projection)
        if path.exists() and path.read_text(encoding="utf-8") != rendered:
            raise ContractError("immutable service environment revision conflicts")
        if not path.exists():
            _atomic_write(path, rendered)
        os.chmod(path, 0o600)
    state = {
        "schema_version": 1,
        "environment": snapshot.environment,
        "environment_revision": snapshot.environment_revision,
        "contract_revision": snapshot.contract_revision,
        "previous_revision": previous_revision,
        "service_revisions": dict(sorted(snapshot.service_revisions.items())),
        "key_hashes": dict(sorted(snapshot.key_hashes.items())),
        "credential_isolation": credential_isolation,
    }
    states = root / "states"
    states.mkdir(mode=0o700, exist_ok=True)
    _atomic_write(
        states / f"{snapshot.environment_revision}.json",
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    link = root / "current"
    temporary_link = root / f".current.tmp-{os.getpid()}"
    temporary_link.unlink(missing_ok=True)
    temporary_link.symlink_to(snapshot.environment_revision)
    os.replace(temporary_link, link)
    _atomic_write(
        root / "current.json",
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return state


def rollback_activation(root: Path, expected_revision: str) -> dict[str, Any]:
    current = load_active_state(root)
    if current is None or current.get("environment_revision") != expected_revision:
        raise ContractError("service environment rollback target is not active")
    previous_revision = current.get("previous_revision")
    if not isinstance(previous_revision, str) or not previous_revision:
        raise ContractError("service environment activation has no rollback revision")
    previous_path = root / "states" / f"{previous_revision}.json"
    try:
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(
            "previous service environment state is unavailable"
        ) from exc
    if not (root / previous_revision).is_dir():
        raise ContractError("previous service environment projection is unavailable")
    temporary_link = root / f".current.rollback-{os.getpid()}"
    temporary_link.unlink(missing_ok=True)
    temporary_link.symlink_to(previous_revision)
    os.replace(temporary_link, root / "current")
    _atomic_write(
        root / "current.json",
        json.dumps(previous, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return previous


def changed_keys(
    snapshot: EnvironmentSnapshot, active: Mapping[str, Any] | None
) -> set[str]:
    previous = active.get("key_hashes") if isinstance(active, Mapping) else None
    if not isinstance(previous, Mapping):
        return set(snapshot.key_hashes)
    changed = {
        key
        for key in set(previous) | set(snapshot.key_hashes)
        if previous.get(key) != snapshot.key_hashes.get(key)
    }
    if active.get("contract_revision") != snapshot.contract_revision:
        changed.add("ALLBOT_SERVICE_CONTRACT_REVISION")
    return changed


def validate_environment_semantics(environment: str, values: Mapping[str, str]) -> None:
    if values.get("ALLBOT_ENV") != environment:
        raise ContractError(f"ALLBOT_ENV must equal {environment}")
    bot_type = values.get("BOT_TYPE")
    if bot_type and bot_type != environment.upper():
        raise ContractError("BOT_TYPE conflicts with ALLBOT_ENV")
    if environment != "prod":
        return
    test_keys = sorted(
        key for key, value in values.items() if key.endswith("_TEST") and value
    )
    if test_keys:
        raise ContractError(
            "production environment contains test-only keys: " + ", ".join(test_keys)
        )
    sentinel_keys = {
        "MINIO_BUCKET",
        "MINIO_RESULT_BUCKET",
        "MINIO_TEMPLATE_BUCKET",
        "R2_BUCKET",
        "R2_PUBLIC_DOMAIN",
        "WEBAPP_URL",
        "MINI_APP_URL",
        "QQCC_CONFIG_ADMIN_HOST",
        "PRIVATE_QQCC_BOT_OWNER_HOST",
        "BOT_USERNAME",
    }
    contaminated = sorted(
        key for key in sentinel_keys if "test" in values.get(key, "").strip().lower()
    )
    if contaminated:
        raise ContractError(
            "production environment contains test identity values: "
            + ", ".join(contaminated)
        )


def _credential_status(root: Path) -> str:
    path = root / "credential-isolation-status"
    if not path.is_file():
        return "pending"
    value = path.read_text(encoding="utf-8").strip()
    return value if value in {"pending", "credential-isolation-complete"} else "pending"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "activate", "rollback"))
    parser.add_argument("--environment", choices=("test", "prod"), required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--defaults", type=Path)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--service", action="append", default=[])
    parser.add_argument("--expected-revision")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "rollback":
            if not args.expected_revision:
                raise ContractError("rollback requires --expected-revision")
            state = rollback_activation(args.root, args.expected_revision)
            print(
                dumps_summary(
                    {
                        "status": "rolled-back",
                        "environment": args.environment,
                        "environment_revision": state["environment_revision"],
                    }
                )
            )
            return 0
        if not args.env_file.is_file() or args.env_file.stat().st_mode & 0o077:
            raise ContractError("environment file must exist with mode 0600")
        values = (
            parse_env_text(args.defaults.read_text(encoding="utf-8"))
            if args.defaults is not None
            else {}
        )
        values.update(parse_env_text(args.env_file.read_text(encoding="utf-8")))
        validate_environment_semantics(args.environment, values)
        contract = load_contract(args.contract)
        snapshot = build_snapshot(
            contract,
            args.environment,
            values,
            services=set(args.service) or None,
        )
        active = load_active_state(args.root)
        if active is not None:
            validate_active_projection_integrity(args.root, active)
        changed = changed_keys(snapshot, active)
        status = _credential_status(args.root)
        if args.command == "activate":
            active = activate_snapshot(args.root, snapshot, credential_isolation=status)
            active_revision = snapshot.environment_revision
        else:
            active_revision = (
                str(active.get("environment_revision")) if active else None
            )
        summary = snapshot_summary(
            snapshot,
            changed_keys=changed,
            active_revision=active_revision,
            active_service_revisions=(
                active.get("service_revisions") if isinstance(active, Mapping) else None
            ),
            credential_isolation=status,
        )
        active_service_revisions = (
            active.get("service_revisions")
            if isinstance(active, Mapping)
            and isinstance(active.get("service_revisions"), Mapping)
            else {}
        )
        projection_drift = {
            name
            for name, revision in snapshot.service_revisions.items()
            if str(active_service_revisions.get(name, "")) != revision
        }
        summary["affected_services"] = sorted(
            (affected_services(contract, changed) & set(snapshot.projections))
            | projection_drift
        )
        summary["unknown_keys"] = sorted(unknown_changed_keys(contract, changed))
        summary["present_keys"] = sorted(key for key, value in values.items() if value)
        summary["public_values"] = {
            key: values[key] for key in sorted(PUBLIC_CONFIG_KEYS) if key in values
        }
        summary["status"] = "activated" if args.command == "activate" else "inspected"
        print(dumps_summary(summary))
        return 0
    except ContractError as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
