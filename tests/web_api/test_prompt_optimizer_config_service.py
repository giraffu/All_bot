from types import SimpleNamespace

import pytest

from src.prompt_optimizer.minimax_h3_prompt import (
    MINIMAX_H3_HMNSFW_TRANSLATION_ZH,
)
from src.web_api.services.prompt_optimizer_config_service import (
    get_default_config,
    save_config,
)


class FakeConfigDb:
    def __init__(self):
        self.row = None
        self.commits = 0

    async def get(self, _model, scene_key):
        return self.row if self.row and self.row.scene_key == scene_key else None

    def add(self, row):
        self.row = row

    async def commit(self):
        self.commits += 1


def test_h3_admin_default_is_one_shared_english_runtime_config():
    config = get_default_config("minimax_h3")

    assert config["display_name"] == "高级图生视频pro"
    assert config["revision"] == 0
    assert "{duration_seconds}" in config["system_template"]
    assert "{addon_rules}" not in config["user_template"]
    assert "fixed MiniMax H3 RedMix stack" in config["system_template"]
    assert MINIMAX_H3_HMNSFW_TRANSLATION_ZH not in config["system_template"]


@pytest.mark.asyncio
async def test_h3_admin_save_increments_revision_for_new_task_snapshots_only():
    db = FakeConfigDb()
    default = get_default_config("minimax_h3")
    payload = SimpleNamespace(
        display_name=default["display_name"],
        description=default["description"],
        system_template=default["system_template"],
        user_template=default["user_template"],
    )

    first = await save_config(
        db, scene_key="minimax_h3", payload=payload, updated_by="a"
    )
    second = await save_config(
        db, scene_key="minimax_h3", payload=payload, updated_by="b"
    )

    assert first["revision"] == 1
    assert second["revision"] == 2
    assert first["content_hash"] == second["content_hash"]
    assert db.commits == 2
