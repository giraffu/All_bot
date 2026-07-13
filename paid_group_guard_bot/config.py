from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from config import TELEGRAM_API_BASE_URL

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int | None = None) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


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
        token = os.getenv("PAID_GROUP_BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("PAID_GROUP_BOT_TOKEN is required")

        target_chat_id = _env_int("PAID_GROUP_CHAT_ID")
        if target_chat_id is None:
            raise RuntimeError("PAID_GROUP_CHAT_ID is required")

        base_url = os.getenv("PAID_GROUP_BOT_BASE_URL")
        if not base_url:
            base_url = _with_bot_suffix(TELEGRAM_API_BASE_URL)

        return cls(
            token=token,
            target_chat_id=target_chat_id,
            decline_unqualified=_env_bool(
                "PAID_GROUP_DECLINE_UNQUALIFIED",
                default=False,
            ),
            dry_run=_env_bool("PAID_GROUP_DRY_RUN", default=False),
            base_url=_with_bot_suffix(base_url),
            base_file_url=os.getenv("PAID_GROUP_BOT_BASE_FILE_URL")
            or os.getenv("TELEGRAM_FILE_BASE_URL")
            or "http://69.63.220.115:8082",
            connect_timeout=float(
                os.getenv("PAID_GROUP_BOT_CONNECT_TIMEOUT", "60")
            ),
            read_timeout=float(os.getenv("PAID_GROUP_BOT_READ_TIMEOUT", "60")),
            write_timeout=float(os.getenv("PAID_GROUP_BOT_WRITE_TIMEOUT", "60")),
            pool_size=int(os.getenv("PAID_GROUP_BOT_POOL_SIZE", "20")),
            poll_interval=float(os.getenv("PAID_GROUP_BOT_POLL_INTERVAL", "2")),
            poll_timeout=int(os.getenv("PAID_GROUP_BOT_POLL_TIMEOUT", "30")),
            log_file=os.getenv(
                "PAID_GROUP_BOT_LOG_FILE",
                "logs/paid_group_guard_bot.log",
            ),
            moderation_config_file=os.getenv(
                "PAID_GROUP_MODERATION_CONFIG_FILE",
                "/app/runtime/paid-group-guard/config.json",
            ),
            moderation_log_file=os.getenv(
                "PAID_GROUP_MODERATION_LOG_FILE",
                "/app/logs/paid_group_moderation.jsonl",
            ),
        )
