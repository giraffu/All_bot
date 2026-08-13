from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default or "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _bot_base_url(value: str) -> str:
    value = value.rstrip("/")
    return value if value.endswith("/bot") else f"{value}/bot"


@dataclass(frozen=True)
class GroupManageBotSettings:
    token: str
    target_chat_id: int
    base_url: str | None = None
    base_file_url: str | None = None
    connect_timeout: float = 60.0
    read_timeout: float = 60.0
    write_timeout: float = 60.0
    pool_size: int = 20
    poll_interval: float = 2.0
    poll_timeout: int = 30
    log_file: str = "/app/logs/group_manage_bot.log"
    moderation_config_file: str = "/app/runtime/group-manage/config.json"
    moderation_log_file: str = "/app/logs/group_manage_moderation.jsonl"

    @classmethod
    def from_env(cls) -> "GroupManageBotSettings":
        return cls(
            token=_env("GROUP_MANAGE_BOT_TOKEN"),
            target_chat_id=int(_env("GROUP_MANAGE_CHAT_ID")),
            base_url=_bot_base_url(
                os.getenv("GROUP_MANAGE_BOT_BASE_URL")
                or _env("TELEGRAM_API_BASE_URL")
            ),
            base_file_url=os.getenv("GROUP_MANAGE_BOT_BASE_FILE_URL")
            or _env("TELEGRAM_FILE_BASE_URL"),
            connect_timeout=float(_env("GROUP_MANAGE_BOT_CONNECT_TIMEOUT", "60")),
            read_timeout=float(_env("GROUP_MANAGE_BOT_READ_TIMEOUT", "60")),
            write_timeout=float(_env("GROUP_MANAGE_BOT_WRITE_TIMEOUT", "60")),
            pool_size=int(_env("GROUP_MANAGE_BOT_POOL_SIZE", "20")),
            poll_interval=float(_env("GROUP_MANAGE_BOT_POLL_INTERVAL", "2")),
            poll_timeout=int(_env("GROUP_MANAGE_BOT_POLL_TIMEOUT", "30")),
            log_file=_env("GROUP_MANAGE_BOT_LOG_FILE", "/app/logs/group_manage_bot.log"),
            moderation_config_file=_env(
                "GROUP_MANAGE_MODERATION_CONFIG_FILE",
                "/app/runtime/group-manage/config.json",
            ),
            moderation_log_file=_env(
                "GROUP_MANAGE_MODERATION_LOG_FILE",
                "/app/logs/group_manage_moderation.jsonl",
            ),
        )
