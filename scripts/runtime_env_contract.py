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
import re
from pathlib import Path
from typing import Any, Iterable, Mapping


SERVICE_CONTRACT_REVISION_KEY = "ALLBOT_SERVICE_CONTRACT_REVISION"
OCI_DIGEST_REF_RE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")


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
    for service, config in value["services"].items():
        if not isinstance(config, Mapping):
            raise ContractError(f"{service} service environment contract is invalid")
        _service_environments(config)
        _conditional_contract_keys(config)
        _json_digest_pin_sets(config)
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


def _service_environments(config: Mapping[str, Any]) -> frozenset[str]:
    raw = config.get("environments", ["test", "prod"])
    if (
        not isinstance(raw, list)
        or not raw
        or any(value not in {"test", "prod"} for value in raw)
        or len(set(raw)) != len(raw)
    ):
        raise ContractError("service environments contract is invalid")
    return frozenset(str(value) for value in raw)


def _service_available(config: Mapping[str, Any], environment: str) -> bool:
    return environment in _service_environments(config)


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


def _condition_matches(condition: Mapping[str, Any], values: Mapping[str, str]) -> bool:
    key = str(condition.get("key", "")).strip()
    if not key:
        raise ContractError("conditional environment contract key is invalid")
    value = values.get(key, "").strip()
    if condition.get("nonempty") is True:
        return bool(value)
    if "equals" in condition:
        return value.lower() == str(condition["equals"]).strip().lower()
    raise ContractError("conditional environment contract is invalid")


def _conditional_contract_keys(config: Mapping[str, Any]) -> set[str]:
    raw_rules = config.get("required_if", [])
    if not isinstance(raw_rules, list):
        raise ContractError("service required_if contract is invalid")
    keys: set[str] = set()
    for rule in raw_rules:
        if not isinstance(rule, Mapping):
            raise ContractError("service required_if contract is invalid")
        key = str(rule.get("key", "")).strip()
        condition = rule.get("when")
        if not key or not isinstance(condition, Mapping):
            raise ContractError("service required_if contract is invalid")
        condition_key = str(condition.get("key", "")).strip()
        if not condition_key:
            raise ContractError("service required_if contract is invalid")
        _condition_matches(condition, {})
        keys.update({key, condition_key})
    return keys


def _active_conditional_required_keys(
    config: Mapping[str, Any], values: Mapping[str, str]
) -> set[str]:
    required: set[str] = set()
    for rule in config.get("required_if", []):
        condition = rule["when"]
        if _condition_matches(condition, values):
            required.add(str(rule["key"]).strip())
    return required


def _conditional_condition_keys(config: Mapping[str, Any]) -> set[str]:
    return {
        str(rule["when"]["key"]).strip()
        for rule in config.get("required_if", [])
    }


def _json_digest_pin_sets(
    config: Mapping[str, Any],
) -> dict[str, frozenset[str]]:
    raw_sets = config.get("json_digest_pin_sets", {})
    if not isinstance(raw_sets, Mapping):
        raise ContractError("service json_digest_pin_sets contract is invalid")
    normalized: dict[str, frozenset[str]] = {}
    for raw_key, raw_expected_keys in raw_sets.items():
        key = str(raw_key).strip()
        if (
            not key
            or not isinstance(raw_expected_keys, list)
            or not raw_expected_keys
            or any(
                not isinstance(value, str) or not value.strip()
                for value in raw_expected_keys
            )
        ):
            raise ContractError("service json_digest_pin_sets contract is invalid")
        expected_keys = frozenset(value.strip() for value in raw_expected_keys)
        if len(expected_keys) != len(raw_expected_keys):
            raise ContractError("service json_digest_pin_sets contract is invalid")
        normalized[key] = expected_keys
    return normalized


def _validate_json_digest_pin_sets(
    name: str,
    config: Mapping[str, Any],
    values: Mapping[str, str],
) -> None:
    for key, expected_keys in _json_digest_pin_sets(config).items():
        raw_value = values.get(key, "").strip()
        try:
            pins = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ContractError(f"{name} has invalid {key}") from exc
        if not isinstance(pins, dict):
            raise ContractError(f"{name} has invalid {key}")
        actual_keys = {str(pin_key) for pin_key in pins}
        if actual_keys != expected_keys:
            missing = sorted(expected_keys - actual_keys)
            extra = sorted(actual_keys - expected_keys)
            details: list[str] = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if extra:
                details.append("extra " + ", ".join(extra))
            raise ContractError(
                f"{name} has invalid {key} profile keys: " + "; ".join(details)
            )
        if any(
            not isinstance(image_ref, str)
            or not OCI_DIGEST_REF_RE.fullmatch(image_ref)
            for image_ref in pins.values()
        ):
            raise ContractError(f"{name} has non-digest-pinned values in {key}")


def _projection(
    name: str,
    config: Mapping[str, Any],
    values: Mapping[str, str],
    *,
    included_keys: Iterable[str] = (),
) -> dict[str, str]:
    required = {str(key) for key in config.get("required", [])}
    required.update(_active_conditional_required_keys(config, values))
    missing = sorted(key for key in required if not values.get(key, "").strip())
    if missing:
        raise ContractError(
            f"{name} is missing required environment keys: " + ", ".join(missing)
        )
    _validate_json_digest_pin_sets(name, config, values)
    patterns = [str(pattern) for pattern in config.get("patterns", [])]
    included = {str(key) for key in included_keys}
    included.update(_conditional_condition_keys(config))
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
    try:
        return _condition_matches(condition, values)
    except ContractError as exc:
        raise ContractError("service enabled_if contract is invalid") from exc


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
    selected = set(services) if services is not None else {
        str(name)
        for name, config in configured.items()
        if isinstance(config, Mapping) and _service_available(config, environment)
    }
    unknown = sorted(selected - set(configured))
    if unknown:
        raise ContractError(
            "unknown service environment contract: " + ", ".join(unknown)
        )
    unavailable = sorted(
        name
        for name in selected
        if not _service_available(configured[name], environment)
    )
    if unavailable:
        raise ContractError(
            f"service environment contract is unavailable in {environment}: "
            + ", ".join(unavailable)
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
        {**tracked_values, SERVICE_CONTRACT_REVISION_KEY: contract_revision}
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
        required.update(_conditional_contract_keys(raw_config))
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
        required.update(_conditional_contract_keys(raw_config))
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
    effective_changed = changed - {SERVICE_CONTRACT_REVISION_KEY}
    active_services = (
        active_service_revisions
        if isinstance(active_service_revisions, Mapping)
        else {}
    )
    projection_drift = {
        name
        for name, revision in snapshot.service_revisions.items()
        if str(active_services.get(name, "")) != revision
    }
    return {
        "schema_version": 1,
        "environment": snapshot.environment,
        "environment_revision": snapshot.environment_revision,
        "contract_revision": snapshot.contract_revision,
        "active_revision": active_revision,
        "drift": active_revision != snapshot.environment_revision
        or bool(projection_drift),
        "changed_keys": sorted(changed),
        "affected_services": sorted(
            {
                name
                for name, projection in snapshot.projections.items()
                if not changed
                or any(key in projection for key in effective_changed)
            }
            | projection_drift
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


def preserve_active_projections(
    root: Path,
    active: Mapping[str, Any],
    snapshot: EnvironmentSnapshot,
    services: Iterable[str],
) -> EnvironmentSnapshot:
    """Carry verified non-target projections through a scoped activation."""

    active_revision = str(active["environment_revision"])
    active_service_revisions = active["service_revisions"]
    projections = dict(snapshot.projections)
    service_revisions = dict(snapshot.service_revisions)
    for service in sorted(set(services)):
        revision = str(active_service_revisions[service])
        path = root / active_revision / f"{service}.env"
        projection = parse_env_text(path.read_text(encoding="utf-8"))
        if projection.get("ALLBOT_CONFIG_REVISION") != revision:
            raise ContractError("active service environment integrity check failed")
        projections[service] = projection
        service_revisions[service] = revision
    return EnvironmentSnapshot(
        environment=snapshot.environment,
        environment_revision=snapshot.environment_revision,
        contract_revision=snapshot.contract_revision,
        projections=projections,
        service_revisions=service_revisions,
        key_hashes=snapshot.key_hashes,
    )


def validate_target_projection_integrity(
    root: Path,
    active: Mapping[str, Any],
    services: Iterable[str],
) -> None:
    """Validate only requested active projections without trusting other state names.

    This is deliberately read-only and narrower than activation integrity.  It is
    used by ordinary rolling releases where an unrelated historical service must
    not block a known target, while the target's state, permissions and bytes stay
    fail-closed.
    """

    revision = str(active.get("environment_revision", ""))
    service_revisions = active.get("service_revisions")
    link = root / "current"
    state_path = root / "current.json"
    revision_path = root / revision
    if (
        not re.fullmatch(r"[0-9a-f]{64}", revision)
        or not isinstance(service_revisions, Mapping)
        or not link.is_symlink()
        or os.readlink(link) != revision
        or root.stat().st_mode & 0o077
        or not revision_path.is_dir()
        or revision_path.stat().st_mode & 0o077
        or not state_path.is_file()
        or state_path.stat().st_mode & 0o077
    ):
        raise ContractError("target service environment integrity check failed")
    for service in sorted(set(services)):
        recorded = str(service_revisions.get(service, ""))
        path = revision_path / f"{service}.env"
        if (
            not re.fullmatch(r"[0-9a-f]{64}", recorded)
            or path.is_symlink()
            or not path.is_file()
            or path.stat().st_mode & 0o077
        ):
            raise ContractError("target service environment integrity check failed")
        projection = parse_env_text(path.read_text(encoding="utf-8"))
        embedded = projection.pop("ALLBOT_CONFIG_REVISION", None)
        if embedded != recorded or _digest(projection) != recorded:
            raise ContractError("target service environment integrity check failed")


def activate_snapshot(
    root: Path,
    snapshot: EnvironmentSnapshot,
    *,
    credential_isolation: str = "pending",
    preserve_active: bool = False,
    mutable_services: Iterable[str] = (),
) -> dict[str, Any]:
    """Write one immutable projection set and atomically select it."""

    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    previous = load_active_state(root)
    previous_service_revisions = (
        previous.get("service_revisions") if isinstance(previous, Mapping) else None
    )
    if preserve_active and isinstance(previous_service_revisions, Mapping):
        mutable = {str(service) for service in mutable_services}
        missing = set(previous_service_revisions) - set(snapshot.service_revisions)
        changed = {
            str(service)
            for service, revision in previous_service_revisions.items()
            if str(service) not in mutable
            if str(snapshot.service_revisions.get(str(service), "")) != str(revision)
        }
        if missing or changed:
            raise ContractError(
                "scoped activation would change active service projections"
            )
    if (
        preserve_active
        and previous is not None
        and previous.get("environment_revision") == snapshot.environment_revision
    ):
        previous_revision = previous.get("previous_revision")
    else:
        previous_revision = (
            str(previous.get("environment_revision"))
            if previous is not None
            else None
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
    activation_id = hashlib.sha256(
        json.dumps(
            state["service_revisions"], sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    activation_history = states / "activations"
    activation_history.mkdir(mode=0o700, exist_ok=True)
    os.chmod(activation_history, 0o700)
    activation_path = (
        activation_history / f"{snapshot.environment_revision}-{activation_id}.json"
    )
    activation_text = json.dumps(
        state, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    if (
        activation_path.exists()
        and activation_path.read_text(encoding="utf-8") != activation_text
    ):
        raise ContractError("immutable service environment activation conflicts")
    if not activation_path.exists():
        _atomic_write(activation_path, activation_text)
    os.chmod(activation_path, 0o600)
    _atomic_write(
        states / f"{snapshot.environment_revision}.json",
        activation_text,
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
        changed.add(SERVICE_CONTRACT_REVISION_KEY)
    return changed


def validate_environment_semantics(environment: str, values: Mapping[str, str]) -> None:
    if values.get("ALLBOT_ENV") != environment:
        raise ContractError(f"ALLBOT_ENV must equal {environment}")
    bot_type = values.get("BOT_TYPE")
    if bot_type and bot_type != environment.upper():
        raise ContractError("BOT_TYPE conflicts with ALLBOT_ENV")
    expected_mini_app_urls = {
        "test": "https://web-cf-test.aivison.it.com",
        "prod": "https://web.aivison.it.com",
    }
    mini_app_url = values.get("MINI_APP_URL", "").strip().rstrip("/")
    if mini_app_url and mini_app_url != expected_mini_app_urls[environment]:
        raise ContractError(
            f"MINI_APP_URL does not match the canonical {environment} Web"
        )
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
    parser.add_argument(
        "command", choices=("inspect", "inspect-target", "activate", "rollback")
    )
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
        requested_services = set(args.service)
        active = load_active_state(args.root)
        active_before = active
        if args.command != "inspect-target" and active is not None:
            validate_active_projection_integrity(args.root, active)
        selected_services = set(requested_services)
        preserved_services: set[str] = set()
        if (
            args.command != "inspect-target"
            and requested_services
            and isinstance(active, Mapping)
        ):
            active_service_revisions = active.get("service_revisions")
            if not isinstance(active_service_revisions, Mapping):
                raise ContractError("active service environment state is invalid")
            configured = contract["services"]
            active_services = {str(name) for name in active_service_revisions}
            rebuildable_services = {
                name
                for name in active_services
                if name in configured
                and _service_available(configured[name], args.environment)
            }
            selected_services.update(rebuildable_services)
            preserved_services = (
                active_services - rebuildable_services - requested_services
            )
        snapshot = build_snapshot(
            contract,
            args.environment,
            values,
            services=(
                selected_services
                if args.command == "inspect-target" or requested_services
                else None
            ),
        )
        if preserved_services and isinstance(active, Mapping):
            snapshot = preserve_active_projections(
                args.root,
                active,
                snapshot,
                preserved_services,
            )
        if args.command == "inspect-target" and snapshot.projections:
            if active is None:
                raise ContractError("target service environment is not activated")
            validate_target_projection_integrity(
                args.root, active, snapshot.projections
            )
        elif args.command == "inspect-target" and active is not None:
            validate_target_projection_integrity(args.root, active, ())
        if (
            args.command != "inspect-target"
            and requested_services
            and isinstance(active, Mapping)
        ):
            active_services = {
                str(name) for name in active.get("service_revisions", {})
            }
            if not active_services <= set(snapshot.projections):
                raise ContractError(
                    "scoped activation would remove active service projections"
                )
        changed = changed_keys(snapshot, active)
        status = _credential_status(args.root)
        if args.command == "activate":
            active = activate_snapshot(
                args.root,
                snapshot,
                credential_isolation=status,
                preserve_active=bool(requested_services),
                mutable_services=requested_services,
            )
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
        effective_changed = changed - {SERVICE_CONTRACT_REVISION_KEY}
        retired_services = (
            sorted(
                set(
                    str(name)
                    for name in active_before.get("service_revisions", {})
                )
                - set(snapshot.service_revisions)
            )
            if args.command != "inspect-target"
            and isinstance(active_before, Mapping)
            and isinstance(active_before.get("service_revisions"), Mapping)
            else []
        )
        if args.command == "inspect-target":
            # Global env and unrelated active revisions are intentionally outside
            # this read-only gate.  Only the requested projection may block the
            # rolling release.
            target_changed_keys = {
                key
                for key in effective_changed
                if affected_services(contract, {key}) & set(snapshot.projections)
            }
            summary["drift"] = bool(projection_drift or target_changed_keys)
            summary["changed_keys"] = sorted(target_changed_keys)
            effective_changed = target_changed_keys
        else:
            summary["drift"] = bool(summary["drift"] or retired_services)
        summary["affected_services"] = sorted(
            (affected_services(contract, effective_changed) & set(snapshot.projections))
            | projection_drift
        )
        summary["unknown_keys"] = sorted(
            unknown_changed_keys(contract, effective_changed)
        )
        summary["effective_environment_revision"] = (
            str(active_before.get("environment_revision"))
            if args.command == "inspect-target"
            and isinstance(active_before, Mapping)
            and active_before.get("environment_revision")
            else snapshot.environment_revision
        )
        summary["retired_services"] = retired_services
        summary["present_keys"] = sorted(key for key, value in values.items() if value)
        summary["public_values"] = {
            key: values[key] for key in sorted(PUBLIC_CONFIG_KEYS) if key in values
        }
        summary["status"] = (
            "activated"
            if args.command == "activate"
            else "target-inspected"
            if args.command == "inspect-target"
            else "inspected"
        )
        print(dumps_summary(summary))
        return 0
    except ContractError as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
