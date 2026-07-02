import pytest

from dashboard.backend.routers import qqcc as router_module
from dashboard.backend.schemas import QqccBotConfigRequest
from src.database.models import RuntimeCheckpoint
from src.services.qqcc_config_service import (
    DEFAULT_QQCC_LAZY_BOT_CONFIG,
    QQCC_LAZY_BOT_CONFIG_KEY,
    get_enabled_qqcc_video_scenes,
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
    assert [scene["id"] for scene in config["video_scenes"]] == [
        "missionary",
        "doggy",
        "blowjob",
        "undress_tongue",
        "closeup_blowjob",
    ]
    assert config["video_scenes"][0]["duration"] == "5s"


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
        "market": True,
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
    assert [scene["id"] for scene in config["video_scenes"]] == [
        "missionary",
        "doggy",
        "blowjob",
        "undress_tongue",
        "closeup_blowjob",
    ]
    assert resolve_qqcc_prompt(
        config,
        "face_swap",
        {"face_swap": "prompts ini fallback"},
        "default fallback",
    ) == "prompts ini fallback"


def test_normalize_qqcc_config_migrates_legacy_video_buttons_to_scenes():
    config = normalize_qqcc_config(
        {
            "video_buttons": {
                "missionary": True,
                "doggy": False,
                "blowjob": True,
                "undress_tongue": False,
                "closeup_blowjob": True,
            },
            "prompts": {
                "perfect_video_insert": "  custom missionary prompt  ",
                "closeup_blowjob": "  custom closeup prompt  ",
            },
            "video_settings": {
                "resolutions": {"512p": False, "720p": False, "1024p": False},
                "durations": {"5s": False, "8s": False, "10s": False},
            },
        }
    )

    scenes = get_enabled_qqcc_video_scenes(config)

    assert [scene["id"] for scene in scenes] == [
        "missionary",
        "blowjob",
        "closeup_blowjob",
    ]
    assert scenes[0]["prompt"] == "custom missionary prompt"
    assert scenes[0]["prompt_key"] == "perfect_video_insert"
    assert scenes[-1]["prompt"] == "custom closeup prompt"
    assert scenes[-1]["duration"] == "5s"


def test_normalize_qqcc_config_keeps_only_valid_dynamic_video_scenes():
    config = normalize_qqcc_config(
        {
            "video_scenes": [
                {
                    "id": "kiss",
                    "name": "亲吻",
                    "prompt": "  kissing prompt  ",
                    "duration": "8s",
                },
                {
                    "id": "kiss",
                    "name": "重复 id",
                    "prompt": "duplicate prompt",
                    "duration": "10s",
                },
                {
                    "id": "bad id!",
                    "name": "安全 id",
                    "prompt": "safe id prompt",
                    "duration": "99s",
                },
                {"id": "empty_prompt", "name": "无提示词", "prompt": ""},
                {"id": "empty_name", "name": " ", "prompt": "has prompt"},
            ]
        }
    )

    scenes = get_enabled_qqcc_video_scenes(config)

    assert scenes == [
        {
            "id": "kiss",
            "name": "亲吻",
            "prompt": "kissing prompt",
            "duration": "8s",
        },
        {
            "id": "scene_2",
            "name": "重复 id",
            "prompt": "duplicate prompt",
            "duration": "10s",
        },
        {
            "id": "scene_3",
            "name": "安全 id",
            "prompt": "safe id prompt",
            "duration": "5s",
        },
    ]


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
