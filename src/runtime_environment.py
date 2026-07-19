"""Strict runtime environment identity and required-value helpers.

Production entrypoints must receive their environment through a scoped host
projection.  This module deliberately does not read dotenv files.
"""

from __future__ import annotations

import os
from collections.abc import Mapping


class RuntimeEnvironmentError(RuntimeError):
    pass


def resolve_runtime_environment(
    values: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    source = os.environ if values is None else values
    environment = str(source.get("ALLBOT_ENV", "")).strip().lower()
    if environment not in {"test", "prod"}:
        raise RuntimeEnvironmentError(
            "ALLBOT_ENV must be explicitly set to test or prod"
        )
    bot_type = "PROD" if environment == "prod" else "TEST"
    configured_bot_type = str(source.get("BOT_TYPE", "")).strip().upper()
    if configured_bot_type and configured_bot_type != bot_type:
        raise RuntimeEnvironmentError("BOT_TYPE conflicts with ALLBOT_ENV")
    return environment, bot_type


def require_env(name: str, values: Mapping[str, str] | None = None) -> str:
    source = os.environ if values is None else values
    value = str(source.get(name, "")).strip()
    if not value:
        raise RuntimeEnvironmentError(f"required runtime key is missing: {name}")
    return value
