from __future__ import annotations

import os

from dashboard.backend.schemas import GroupManageConfigResponse
from dashboard.backend.services.paid_group_guard_admin_service import (
    get_paid_group_guard_logs_payload,
)
from paid_group_guard_bot.moderation import (
    moderation_config_to_dict,
    normalize_moderation_config,
    write_moderation_config,
)
from standalone_group_manage_bot.moderation import load_group_manage_config

DEFAULT_CONFIG_PATH = "/app/runtime/group-manage/config.json"
DEFAULT_LOG_PATH = "/app/logs/group_manage_moderation.jsonl"


def _config_path() -> str:
    return os.getenv("GROUP_MANAGE_MODERATION_CONFIG_FILE", DEFAULT_CONFIG_PATH)


def _log_path() -> str:
    return os.getenv("GROUP_MANAGE_MODERATION_LOG_FILE", DEFAULT_LOG_PATH)


def _response(config) -> GroupManageConfigResponse:
    return GroupManageConfigResponse(
        **moderation_config_to_dict(config),
        config_path=_config_path(),
        log_path=_log_path(),
    )


async def get_group_manage_config_payload() -> GroupManageConfigResponse:
    return _response(load_group_manage_config(_config_path()))


async def update_group_manage_config_payload(payload) -> GroupManageConfigResponse:
    config = normalize_moderation_config(payload.model_dump())
    write_moderation_config(_config_path(), config)
    return _response(config)


async def get_group_manage_logs_payload(**kwargs):
    return await get_paid_group_guard_logs_payload(log_path=_log_path(), **kwargs)
