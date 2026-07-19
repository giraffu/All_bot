from __future__ import annotations

import os
from dataclasses import dataclass


def _required_env(name: str) -> str:
    raw = os.getenv(name, "").strip()
    if not raw:
        raise RuntimeError(f"{name} is required")
    return raw


def _env_bool(name: str) -> bool:
    raw = _required_env(name)
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str) -> int:
    return int(_required_env(name))


def _with_bot_suffix(base_url: str | None) -> str | None:
    if not base_url:
        return None
    normalized = base_url.rstrip("/")
    if normalized.endswith("/bot"):
        return normalized
    return f"{normalized}/bot"


@dataclass(frozen=True)
class PaidGroupBotSettings:
    token: str
    target_chat_id: int
    decline_unqualified: bool = False
    dry_run: bool = False
    base_url: str | None = None
    base_file_url: str | None = None
    connect_timeout: float = 60.0
    read_timeout: float = 60.0
    write_timeout: float = 60.0
    pool_size: int = 20
    poll_interval: float = 2.0
    poll_timeout: int = 30
    log_file: str = "logs/paid_group_guard_bot.log"
    moderation_config_file: str = "/app/runtime/paid-group-guard/config.json"
    moderation_log_file: str = "/app/logs/paid_group_moderation.jsonl"

    @classmethod
    def from_env(cls) -> "PaidGroupBotSettings":
        token = _required_env("PAID_GROUP_BOT_TOKEN")
        target_chat_id = _env_int("PAID_GROUP_CHAT_ID")
        base_url = os.getenv("PAID_GROUP_BOT_BASE_URL") or _required_env(
            "TELEGRAM_API_BASE_URL"
        )
        base_file_url = os.getenv("PAID_GROUP_BOT_BASE_FILE_URL") or _required_env(
            "TELEGRAM_FILE_BASE_URL"
        )

        return cls(
            token=token,
            target_chat_id=target_chat_id,
            decline_unqualified=_env_bool("PAID_GROUP_DECLINE_UNQUALIFIED"),
            dry_run=_env_bool("PAID_GROUP_DRY_RUN"),
            base_url=_with_bot_suffix(base_url),
            base_file_url=base_file_url,
            connect_timeout=float(_required_env("PAID_GROUP_BOT_CONNECT_TIMEOUT")),
            read_timeout=float(_required_env("PAID_GROUP_BOT_READ_TIMEOUT")),
            write_timeout=float(_required_env("PAID_GROUP_BOT_WRITE_TIMEOUT")),
            pool_size=_env_int("PAID_GROUP_BOT_POOL_SIZE"),
            poll_interval=float(_required_env("PAID_GROUP_BOT_POLL_INTERVAL")),
            poll_timeout=_env_int("PAID_GROUP_BOT_POLL_TIMEOUT"),
            log_file=_required_env("PAID_GROUP_BOT_LOG_FILE"),
            moderation_config_file=_required_env("PAID_GROUP_MODERATION_CONFIG_FILE"),
            moderation_log_file=_required_env("PAID_GROUP_MODERATION_LOG_FILE"),
        )
