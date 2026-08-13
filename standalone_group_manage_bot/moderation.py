from __future__ import annotations

import json
from pathlib import Path

from paid_group_guard_bot.moderation import (
    PaidGroupModerationConfig,
    normalize_moderation_config,
)


def load_group_manage_config(path: str | Path) -> PaidGroupModerationConfig:
    try:
        with Path(path).open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        payload = {}
    return normalize_moderation_config(
        {"enabled": True, "dry_run": False, "block_links": True, **payload}
    )


class GroupManageConfigProvider:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._mtime: float | None = None
        self._config: PaidGroupModerationConfig | None = None

    def load(self) -> PaidGroupModerationConfig:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            mtime = None
        if self._config is None or self._mtime != mtime:
            self._config = load_group_manage_config(self.path)
            self._mtime = mtime
        return self._config
