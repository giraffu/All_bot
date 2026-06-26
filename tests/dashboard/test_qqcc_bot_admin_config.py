import pytest

from dashboard.backend.routers import qqcc as router_module
from dashboard.backend.schemas import QqccBotConfigRequest
from src.database.models import RuntimeCheckpoint
from src.services.qqcc_config_service import (
    DEFAULT_QQCC_LAZY_BOT_CONFIG,
    QQCC_LAZY_BOT_CONFIG_KEY,
    load_qqcc_config_payload,
    normalize_qqcc_config,
    resolve_qqcc_prompt,
    save_qqcc_config_payload,
)


class _Result:
    def __init__(self, checkpoint):
        self._checkpoint = checkpoint

    def scalar_one_or_none(self):
        return self._checkpoint


class _FakeSession:
    def __init__(self, checkpoint=None):
        self.checkpoint = checkpoint
        self.added = []
        self.committed = False
        self.refreshed = []

    async def execute(self, _stmt):
        return _Result(self.checkpoint)

    def add(self, checkpoint):
        self.checkpoint = checkpoint
        self.added.append(checkpoint)

    async def commit(self):
        self.committed = True

    async def refresh(self, checkpoint):
        self.refreshed.append(checkpoint)


def test_normalize_qqcc_config_returns_default_shape_for_empty_config():
    config = normalize_qqcc_config(None)

    assert config == DEFAULT_QQCC_LAZY_BOT_CONFIG
    assert config["main_buttons"]["quick_undress"] is True
    assert config["video_settings"]["resolutions"]["1024p"] is True


def test_normalize_qqcc_config_drops_unknown_keys_and_keeps_empty_prompt_for_fallback():
    config = normalize_qqcc_config(
        {
            "global_enabled": False,
            "main_buttons": {
                "quick_undress": False,
                "unknown": False,
                "video_edit": "bad",
            },
            "video_settings": {
                "resolutions": {"512p": False, "2048p": True},
                "durations": {"10s": False, "1m": True},
            },
            "prompts": {
                "undress": "  override prompt  ",
                "face_swap": "   ",
                "unknown": "drop me",
            },
            "unknown_section": {"x": True},
        }
    )

    assert config["global_enabled"] is False
    assert config["main_buttons"] == {
        "quick_undress": False,
        "photo_edit": True,
        "video_edit": True,
        "main_bot_link": True,
    }
    assert "unknown" not in config["main_buttons"]
    assert config["video_settings"]["resolutions"] == {
        "512p": False,
        "720p": True,
        "1024p": True,
    }
    assert config["video_settings"]["durations"] == {
        "5s": True,
        "8s": True,
        "10s": False,
    }
    assert config["prompts"]["undress"] == "override prompt"
    assert config["prompts"]["face_swap"] == ""
    assert "unknown" not in config["prompts"]
    assert resolve_qqcc_prompt(
        config,
        "face_swap",
        {"face_swap": "prompts ini fallback"},
        "default fallback",
    ) == "prompts ini fallback"


@pytest.mark.asyncio
async def test_load_qqcc_config_payload_returns_defaults_when_checkpoint_missing():
    db = _FakeSession()

    response = await load_qqcc_config_payload(db)

    assert response["key"] == QQCC_LAZY_BOT_CONFIG_KEY
    assert response["config"] == DEFAULT_QQCC_LAZY_BOT_CONFIG
    assert response["updated_at"] is None


@pytest.mark.asyncio
async def test_save_qqcc_config_payload_writes_runtime_checkpoint():
    db = _FakeSession()

    response = await save_qqcc_config_payload(
        db,
        {
            "global_enabled": True,
            "main_buttons": {"quick_undress": False},
            "prompts": {"undress": "custom prompt"},
        },
    )

    assert db.committed is True
    assert len(db.added) == 1
    assert isinstance(db.checkpoint, RuntimeCheckpoint)
    assert db.checkpoint.key == QQCC_LAZY_BOT_CONFIG_KEY
    assert db.checkpoint.value["main_buttons"]["quick_undress"] is False
    assert db.checkpoint.value["prompts"]["undress"] == "custom prompt"
    assert response["config"] == db.checkpoint.value


@pytest.mark.asyncio
async def test_update_qqcc_config_router_routes_to_runtime_checkpoint_service():
    db = _FakeSession()
    payload = QqccBotConfigRequest(main_buttons={"video_edit": False})

    response = await router_module.update_qqcc_config(payload, db=db)

    assert db.committed is True
    assert response["config"]["main_buttons"]["video_edit"] is False
