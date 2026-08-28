from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


def _required(values: Mapping[str, str], key: str) -> str:
    value = str(values.get(key, "")).strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _ids(values: Mapping[str, str], key: str, *, required: bool = False) -> frozenset[int]:
    raw = str(values.get(key, "")).strip()
    if not raw:
        if required:
            raise ValueError(f"{key} must contain at least one Telegram chat ID")
        return frozenset()
    try:
        return frozenset(int(part.strip()) for part in raw.split(",") if part.strip())
    except ValueError as exc:
        raise ValueError(f"{key} must be a comma-separated list of integers") from exc


def _integer(values: Mapping[str, str], key: str, default: int, *, minimum: int = 1) -> int:
    raw = str(values.get(key, default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{key} must be >= {minimum}")
    return value


@dataclass(frozen=True)
class ObserverSettings:
    token: str
    database_url: str
    admin_chat_ids: frozenset[int]
    authorized_group_ids: frozenset[int]
    lm_studio_base_url: str
    central_api_url: str = "http://central-api:8003"
    lm_studio_api_key: str = ""
    lm_studio_model: str = ""
    timezone: str = "Asia/Shanghai"
    queue_poll_seconds: int = 60
    queue_size_threshold: int = 20
    queue_wait_threshold_seconds: int = 900
    queue_alert_cooldown_seconds: int = 1800
    queue_failure_threshold: int = 3
    report_tick_seconds: int = 300
    report_hour: int = 9
    report_max_input_chars: int = 60_000
    report_chunk_chars: int = 12_000
    message_retention_days: int = 120
    lm_studio_timeout_seconds: int = 180
    telegram_connect_timeout: int = 30
    telegram_read_timeout: int = 60
    telegram_write_timeout: int = 60
    telegram_pool_size: int = 20
    telegram_poll_interval: int = 2
    telegram_poll_timeout: int = 30
    telegram_base_url: str = ""
    telegram_file_base_url: str = ""

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "ObserverSettings":
        report_hour = _integer(values, "OBSERVER_REPORT_HOUR", 9, minimum=0)
        if report_hour > 23:
            raise ValueError("OBSERVER_REPORT_HOUR must be between 0 and 23")
        return cls(
            token=_required(values, "OBSERVER_BOT_TOKEN"),
            database_url=_required(values, "OBSERVER_DATABASE_URL"),
            admin_chat_ids=_ids(values, "OBSERVER_ADMIN_CHAT_IDS", required=True),
            authorized_group_ids=_ids(values, "OBSERVER_AUTHORIZED_GROUP_IDS"),
            lm_studio_base_url=_required(values, "OBSERVER_LM_STUDIO_BASE_URL").rstrip("/"),
            central_api_url=str(
                values.get("OBSERVER_CENTRAL_API_URL", "http://central-api:8003")
            ).strip().rstrip("/"),
            lm_studio_api_key=str(values.get("OBSERVER_LM_STUDIO_API_KEY", "")).strip(),
            lm_studio_model=str(values.get("OBSERVER_LM_STUDIO_MODEL", "")).strip(),
            timezone=str(values.get("OBSERVER_TIMEZONE", "Asia/Shanghai")).strip(),
            queue_poll_seconds=_integer(values, "OBSERVER_QUEUE_POLL_SECONDS", 60),
            queue_size_threshold=_integer(values, "OBSERVER_QUEUE_SIZE_THRESHOLD", 20),
            queue_wait_threshold_seconds=_integer(
                values, "OBSERVER_QUEUE_WAIT_THRESHOLD_SECONDS", 900
            ),
            queue_alert_cooldown_seconds=_integer(
                values, "OBSERVER_QUEUE_ALERT_COOLDOWN_SECONDS", 1800
            ),
            queue_failure_threshold=_integer(
                values, "OBSERVER_QUEUE_FAILURE_THRESHOLD", 3
            ),
            report_tick_seconds=_integer(values, "OBSERVER_REPORT_TICK_SECONDS", 300),
            report_hour=report_hour,
            report_max_input_chars=_integer(
                values, "OBSERVER_REPORT_MAX_INPUT_CHARS", 60_000
            ),
            report_chunk_chars=_integer(values, "OBSERVER_REPORT_CHUNK_CHARS", 12_000),
            message_retention_days=_integer(
                values, "OBSERVER_MESSAGE_RETENTION_DAYS", 120
            ),
            lm_studio_timeout_seconds=_integer(
                values, "OBSERVER_LM_STUDIO_TIMEOUT_SECONDS", 180
            ),
            telegram_connect_timeout=_integer(
                values, "OBSERVER_BOT_CONNECT_TIMEOUT", 30
            ),
            telegram_read_timeout=_integer(values, "OBSERVER_BOT_READ_TIMEOUT", 60),
            telegram_write_timeout=_integer(values, "OBSERVER_BOT_WRITE_TIMEOUT", 60),
            telegram_pool_size=_integer(values, "OBSERVER_BOT_POOL_SIZE", 20),
            telegram_poll_interval=_integer(values, "OBSERVER_BOT_POLL_INTERVAL", 2),
            telegram_poll_timeout=_integer(values, "OBSERVER_BOT_POLL_TIMEOUT", 30),
            telegram_base_url=str(values.get("TELEGRAM_API_BASE_URL", "")).strip(),
            telegram_file_base_url=str(values.get("TELEGRAM_FILE_BASE_URL", "")).strip(),
        )

    @classmethod
    def from_env(cls) -> "ObserverSettings":
        return cls.from_mapping(os.environ)
