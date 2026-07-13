#!/usr/bin/env python3
"""Validate QQCC private Bot deployment secrets and public URL boundaries."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit


ENABLE_KEY = "PRIVATE_QQCC_BOT_ENABLED"
ACTIVATION_REQUIRED_KEYS = (
    "PRIVATE_QQCC_BOT_TOKEN_KEYRING",
    "PRIVATE_QQCC_BOT_TOKEN_ACTIVE_KEY_VERSION",
    "PRIVATE_QQCC_BOT_TOKEN_FINGERPRINT_KEY",
    "PRIVATE_QQCC_BOT_FORBIDDEN_BOT_IDS",
    "PRIVATE_QQCC_BOT_TELEGRAM_API_BASE_URL",
    "PRIVATE_QQCC_BOT_TELEGRAM_FILE_BASE_URL",
    "PRIVATE_QQCC_BOT_OWNER_JWT_SECRET",
    "PRIVATE_QQCC_BOT_WEBHOOK_BASE_URL",
    "PRIVATE_QQCC_BOT_OWNER_WEBAPP_URL",
    "PRIVATE_QQCC_BOT_OWNER_HOST",
    "QQCC_CONFIG_ADMIN_HOST",
    "R2_ENDPOINT",
    "R2_ACCESS_KEY",
    "R2_SECRET_KEY",
    "R2_BUCKET",
)
OPTIONAL_KEYS = ("PRIVATE_QQCC_BOT_TELEGRAM_TRUSTED_HOSTS",)
COMPARISON_SECRET_KEYS = (
    "QQCC_CONFIG_SECRET_KEY",
    "JWT_SECRET_KEY",
    "DASHBOARD_SECRET_KEY",
)
HOST_PATTERN = re.compile(r"^[A-Za-z0-9.-]+$")


class ContractError(ValueError):
    pass


def _unquote(value: str) -> str:
    normalized = value.strip()
    if (
        len(normalized) >= 2
        and normalized[0] == normalized[-1]
        and normalized[0] in {"'", '"'}
    ):
        return normalized[1:-1]
    return normalized


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        values[key.strip()] = _unquote(raw_value)
    for key in (
        ENABLE_KEY,
        *ACTIVATION_REQUIRED_KEYS,
        *OPTIONAL_KEYS,
        *COMPARISON_SECRET_KEYS,
    ):
        if key in os.environ:
            values[key] = os.environ[key].strip()
    return values


def _hostname(value: str, *, label: str) -> str:
    normalized = value.strip().lower()
    if (
        not normalized
        or not HOST_PATTERN.fullmatch(normalized)
        or ".." in normalized
        or normalized.startswith((".", "-"))
        or normalized.endswith((".", "-"))
    ):
        raise ContractError(f"{label} must contain one valid hostname")
    return normalized


def _https_url(
    value: str,
    *,
    label: str,
    trusted_hosts: set[str] | None = None,
    exact_path: str | None = None,
) -> tuple[str, str]:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    try:
        parsed.port
    except ValueError as exc:
        raise ContractError(f"{label} contains an invalid port") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ContractError(
            f"{label} must be a credential-free HTTPS URL without query or fragment"
        )
    host = _hostname(parsed.hostname, label=f"{label} host")
    if trusted_hosts is not None and host not in trusted_hosts:
        raise ContractError(f"{label} host is not explicitly trusted")
    if exact_path is not None and parsed.path != exact_path:
        raise ContractError(f"{label} must use path {exact_path}")
    return normalized, host


def _decode_32_byte_key(value: object, *, label: str) -> bytes:
    try:
        encoded = str(value).encode("ascii")
        encoded += b"=" * (-len(encoded) % 4)
        decoded = base64.b64decode(encoded, altchars=b"-_", validate=True)
    except Exception as exc:
        raise ContractError(f"{label} must be URL-safe Base64") from exc
    if len(decoded) != 32:
        raise ContractError(f"{label} must decode to exactly 32 bytes")
    return decoded


def validate(values: dict[str, str], *, allow_disabled: bool = False) -> None:
    raw_enabled = values.get(ENABLE_KEY, "").strip().lower()
    enabled_values = {"1", "true", "yes", "on"}
    disabled_values = {"0", "false", "no", "off"}
    if not raw_enabled:
        if allow_disabled:
            return
        raise ContractError(f"missing required private Bot env key: {ENABLE_KEY}")
    if raw_enabled not in enabled_values | disabled_values:
        raise ContractError(f"{ENABLE_KEY} must be a boolean")
    if raw_enabled in disabled_values:
        if allow_disabled:
            return
        raise ContractError(
            "PRIVATE_QQCC_BOT_ENABLED must be true before activation"
        )

    missing = [
        key for key in ACTIVATION_REQUIRED_KEYS if not values.get(key, "").strip()
    ]
    bot_type = values.get("BOT_TYPE", "TEST").strip().upper()
    official_qqcc_token_key = (
        "QQCC_BOT_TOKEN" if bot_type == "PROD" else "QQCC_BOT_TOKEN_TEST"
    )
    if not values.get(official_qqcc_token_key, "").strip():
        missing.append(official_qqcc_token_key)
    if missing:
        raise ContractError(
            "missing required private Bot env keys: " + ", ".join(sorted(missing))
        )

    try:
        keyring_payload = json.loads(values["PRIVATE_QQCC_BOT_TOKEN_KEYRING"])
        active_version = int(values["PRIVATE_QQCC_BOT_TOKEN_ACTIVE_KEY_VERSION"])
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ContractError("private Bot AES keyring/version contract is invalid") from exc
    if not isinstance(keyring_payload, dict) or not keyring_payload or active_version <= 0:
        raise ContractError("private Bot AES keyring/version contract is invalid")
    normalized_keyring: dict[int, object] = {}
    try:
        for raw_version, raw_key in keyring_payload.items():
            version = int(raw_version)
            if version <= 0 or version in normalized_keyring:
                raise ValueError
            normalized_keyring[version] = raw_key
    except (TypeError, ValueError) as exc:
        raise ContractError("private Bot AES key versions must be unique positive integers") from exc
    if active_version not in normalized_keyring:
        raise ContractError("active private Bot AES key version is unavailable")
    decoded_aes_keys = {
        version: _decode_32_byte_key(
            raw_key,
            label=f"private Bot AES key version {version}",
        )
        for version, raw_key in normalized_keyring.items()
    }
    fingerprint_key = _decode_32_byte_key(
        values["PRIVATE_QQCC_BOT_TOKEN_FINGERPRINT_KEY"],
        label="private Bot fingerprint key",
    )
    owner_jwt_key = _decode_32_byte_key(
        values["PRIVATE_QQCC_BOT_OWNER_JWT_SECRET"],
        label="private Bot owner JWT key",
    )
    cryptographic_keys = [*decoded_aes_keys.values(), fingerprint_key, owner_jwt_key]
    if len(set(cryptographic_keys)) != len(cryptographic_keys):
        raise ContractError("private Bot AES, fingerprint and owner JWT keys must be independent")
    owner_jwt_secret = values["PRIVATE_QQCC_BOT_OWNER_JWT_SECRET"].strip()
    for key in COMPARISON_SECRET_KEYS:
        candidate = values.get(key, "").strip()
        if not candidate:
            continue
        reused = owner_jwt_secret == candidate
        if not reused:
            try:
                reused = (
                    _decode_32_byte_key(candidate, label=key) == owner_jwt_key
                )
            except ContractError:
                # Existing service JWT/admin secrets are not required to be Base64URL.
                reused = False
        if reused:
            raise ContractError(
                "PRIVATE_QQCC_BOT_OWNER_JWT_SECRET must not reuse another service key"
            )

    forbidden_ids = [
        item
        for item in re.split(
            r"[,\s]+", values["PRIVATE_QQCC_BOT_FORBIDDEN_BOT_IDS"].strip()
        )
        if item
    ]
    if not forbidden_ids or any(not item.isdigit() or int(item) <= 0 for item in forbidden_ids):
        raise ContractError("PRIVATE_QQCC_BOT_FORBIDDEN_BOT_IDS is invalid")

    owner_host = _hostname(
        values["PRIVATE_QQCC_BOT_OWNER_HOST"],
        label="PRIVATE_QQCC_BOT_OWNER_HOST",
    )
    admin_host = _hostname(
        values["QQCC_CONFIG_ADMIN_HOST"],
        label="QQCC_CONFIG_ADMIN_HOST",
    )
    if owner_host == admin_host:
        raise ContractError("private Bot owner and QQCC admin hosts must be different")

    configured_trusted_hosts = {
        _hostname(item, label="PRIVATE_QQCC_BOT_TELEGRAM_TRUSTED_HOSTS entry")
        for item in values.get("PRIVATE_QQCC_BOT_TELEGRAM_TRUSTED_HOSTS", "").split(",")
        if item.strip()
    }
    trusted_hosts = {"api.telegram.org", *configured_trusted_hosts}
    _https_url(
        values["PRIVATE_QQCC_BOT_TELEGRAM_API_BASE_URL"],
        label="PRIVATE_QQCC_BOT_TELEGRAM_API_BASE_URL",
        trusted_hosts=trusted_hosts,
    )
    _https_url(
        values["PRIVATE_QQCC_BOT_TELEGRAM_FILE_BASE_URL"],
        label="PRIVATE_QQCC_BOT_TELEGRAM_FILE_BASE_URL",
        trusted_hosts=trusted_hosts,
    )
    _https_url(
        values["PRIVATE_QQCC_BOT_WEBHOOK_BASE_URL"],
        label="PRIVATE_QQCC_BOT_WEBHOOK_BASE_URL",
        exact_path="/api/private-bots/webhook",
    )
    _https_url(values["R2_ENDPOINT"], label="R2_ENDPOINT")
    _, owner_webapp_host = _https_url(
        values["PRIVATE_QQCC_BOT_OWNER_WEBAPP_URL"],
        label="PRIVATE_QQCC_BOT_OWNER_WEBAPP_URL",
    )
    if owner_webapp_host != owner_host:
        raise ContractError(
            "PRIVATE_QQCC_BOT_OWNER_WEBAPP_URL host must match PRIVATE_QQCC_BOT_OWNER_HOST"
        )

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument(
        "--bot-type",
        choices=("PROD", "TEST"),
        help="validate the official QQCC token for the target deployment environment",
    )
    parser.add_argument(
        "--allow-disabled",
        action="store_true",
        help="accept a missing/false rollout gate without requiring activation secrets",
    )
    args = parser.parse_args()
    try:
        values = _read_env(args.env_file)
        if args.bot_type:
            values["BOT_TYPE"] = args.bot_type
        validate(values, allow_disabled=args.allow_disabled)
    except (ContractError, OSError) as exc:
        parser.error(str(exc))
    print("Private QQCC Bot deployment env contract ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
