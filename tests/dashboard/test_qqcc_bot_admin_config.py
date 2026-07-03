import pytest

from dashboard.backend.routers import qqcc as router_module
from dashboard.backend.schemas import QqccBotConfigRequest
from src.database.models import RuntimeCheckpoint
from src.services.qqcc_config_service import (
    DEFAULT_QQCC_LAZY_BOT_CONFIG,
    QQCC_LAZY_BOT_CONFIG_KEY,
    DRAW_SCENE_ENGINE_FREE_EDIT,
    DRAW_SCENE_ENGINE_FREE_EDIT_V2,
    VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
    VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2,
    get_enabled_qqcc_draw_scenes,
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
    assert config["main_buttons"]["ai_draw"] is True
    assert config["draw_scenes"] == []
    assert config["video_settings"]["resolutions"]["1024p"] is True
    assert [scene["id"] for scene in config["video_scenes"]] == [
        "missionary",
        "doggy",
        "blowjob",
        "undress_tongue",
        "closeup_blowjob",
    ]
    assert config["video_scenes"][0]["duration"] == "5s"
    assert config["video_scenes"][0]["engine"] == VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO
    assert config["video_scenes"][0]["lora_name"] == ""
    assert config["video_scenes"][0]["end_frame_draw_scene_id"] == ""


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
        "ai_draw": True,
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
    assert scenes[0]["engine"] == VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO
    assert scenes[0]["lora_name"] == ""
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
            "engine": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
            "lora_name": "",
            "end_frame_draw_scene_id": "",
        },
        {
            "id": "scene_2",
            "name": "重复 id",
            "prompt": "duplicate prompt",
            "duration": "10s",
            "engine": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
            "lora_name": "",
            "end_frame_draw_scene_id": "",
        },
        {
            "id": "scene_3",
            "name": "安全 id",
            "prompt": "safe id prompt",
            "duration": "5s",
            "engine": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
            "lora_name": "",
            "end_frame_draw_scene_id": "",
        },
    ]


def test_normalize_qqcc_config_validates_scene_engines_and_loras():
    config = normalize_qqcc_config(
        {
            "video_scenes": [
                {
                    "id": "legacy_lora",
                    "name": "旧版模型",
                    "prompt": "legacy prompt",
                    "duration": "5s",
                    "engine": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
                    "lora_name": "BreastGrow",
                },
                {
                    "id": "v2_clears_lora",
                    "name": "新版模型",
                    "prompt": "v2 prompt",
                    "duration": "8s",
                    "engine": VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2,
                    "lora_name": "BreastGrow",
                },
                {
                    "id": "bad_lora",
                    "name": "非法模型",
                    "prompt": "bad prompt",
                    "duration": "10s",
                    "engine": "unknown",
                    "lora_name": "not-a-model",
                },
            ],
            "draw_scenes": [
                {
                    "id": "old_draw",
                    "name": "旧自由P图",
                    "prompt": "old draw prompt",
                    "engine": DRAW_SCENE_ENGINE_FREE_EDIT,
                    "lora_name": "qwen/YARN_1.0.safetensors",
                },
                {
                    "id": "v2_draw",
                    "name": "新版自由P图",
                    "prompt": "v2 draw prompt",
                    "engine": DRAW_SCENE_ENGINE_FREE_EDIT_V2,
                    "lora_name": "qwen/YARN_1.0.safetensors",
                },
                {
                    "id": "bad_draw",
                    "name": "非法绘图",
                    "prompt": "bad draw prompt",
                    "engine": "unknown",
                    "lora_name": "not-a-model",
                },
            ],
        }
    )

    video_scenes = get_enabled_qqcc_video_scenes(config)
    assert video_scenes[0]["engine"] == VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO
    assert video_scenes[0]["lora_name"] == "BreastGrow"
    assert video_scenes[1]["engine"] == VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2
    assert video_scenes[1]["lora_name"] == ""
    assert video_scenes[2]["engine"] == VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO
    assert video_scenes[2]["lora_name"] == ""

    draw_scenes = get_enabled_qqcc_draw_scenes(config)
    assert draw_scenes[0]["engine"] == DRAW_SCENE_ENGINE_FREE_EDIT
    assert draw_scenes[0]["lora_name"] == "qwen/YARN_1.0.safetensors"
    assert draw_scenes[1]["engine"] == DRAW_SCENE_ENGINE_FREE_EDIT_V2
    assert draw_scenes[1]["lora_name"] == ""
    assert draw_scenes[2]["engine"] == DRAW_SCENE_ENGINE_FREE_EDIT_V2
    assert draw_scenes[2]["lora_name"] == ""


def test_normalize_qqcc_config_validates_video_end_frame_draw_scene_reference():
    config = normalize_qqcc_config(
        {
            "draw_scenes": [
                {
                    "id": "tail_pose",
                    "name": "尾帧姿势",
                    "prompt": "tail pose prompt",
                }
            ],
            "video_scenes": [
                {
                    "id": "valid_tail",
                    "name": "有效尾帧",
                    "prompt": "video prompt",
                    "end_frame_draw_scene_id": "tail_pose",
                },
                {
                    "id": "missing_tail",
                    "name": "失效尾帧",
                    "prompt": "video prompt",
                    "end_frame_draw_scene_id": "removed_scene",
                },
            ],
        }
    )

    video_scenes = get_enabled_qqcc_video_scenes(config)

    assert video_scenes[0]["end_frame_draw_scene_id"] == "tail_pose"
    assert video_scenes[1]["end_frame_draw_scene_id"] == ""


def test_normalize_qqcc_config_keeps_only_valid_dynamic_draw_scenes():
    config = normalize_qqcc_config(
        {
            "draw_scenes": [
                {
                    "id": "soft_light",
                    "name": "柔光写真",
                    "prompt": "  make it cinematic  ",
                },
                {
                    "id": "soft_light",
                    "name": "重复 id",
                    "prompt": "duplicate prompt",
                },
                {
                    "id": "bad id!",
                    "name": "安全 id",
                    "prompt": "safe id prompt",
                },
                {"id": "empty_prompt", "name": "无提示词", "prompt": ""},
                {"id": "empty_name", "name": " ", "prompt": "has prompt"},
            ]
        }
    )

    scenes = get_enabled_qqcc_draw_scenes(config)

    assert scenes == [
        {
            "id": "soft_light",
            "name": "柔光写真",
            "prompt": "make it cinematic",
            "engine": DRAW_SCENE_ENGINE_FREE_EDIT_V2,
            "lora_name": "",
        },
        {
            "id": "scene_2",
            "name": "重复 id",
            "prompt": "duplicate prompt",
            "engine": DRAW_SCENE_ENGINE_FREE_EDIT_V2,
            "lora_name": "",
        },
        {
            "id": "scene_3",
            "name": "安全 id",
            "prompt": "safe id prompt",
            "engine": DRAW_SCENE_ENGINE_FREE_EDIT_V2,
            "lora_name": "",
        },
    ]


@pytest.mark.asyncio
async def test_load_qqcc_config_payload_returns_defaults_when_checkpoint_missing():
    db = _FakeSession()

    response = await load_qqcc_config_payload(db)

    assert response["key"] == QQCC_LAZY_BOT_CONFIG_KEY
    assert response["config"] == DEFAULT_QQCC_LAZY_BOT_CONFIG
    assert response["options"]["video_engines"][0]["value"] == VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO
    assert response["options"]["draw_engines"][0]["value"] == DRAW_SCENE_ENGINE_FREE_EDIT
    assert any(
        item["value"] == "BreastGrow"
        for item in response["options"]["video_lora_models"]
    )
    assert any(
        item["value"] == "qwen/YARN_1.0.safetensors"
        for item in response["options"]["image_lora_models"]
    )
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


@pytest.mark.asyncio
async def test_update_qqcc_config_router_preserves_dynamic_video_scenes():
    db = _FakeSession()
    payload = QqccBotConfigRequest(
        draw_scenes=[
            {
                "id": "tail_pose",
                "name": "尾帧姿势",
                "prompt": "custom tail prompt",
            }
        ],
        video_scenes=[
            {
                "id": "kiss",
                "name": "贴贴",
                "prompt": "custom kiss prompt",
                "duration": "8s",
                "engine": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
                "lora_name": "BreastGrow",
                "end_frame_draw_scene_id": "tail_pose",
            },
            {
                "id": "missionary",
                "name": "自定义传教士",
                "prompt": "custom missionary prompt",
                "duration": "10s",
                "prompt_key": "perfect_video_insert",
                "engine": VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2,
                "lora_name": "BreastGrow",
                "end_frame_draw_scene_id": "removed_tail",
            },
        ]
    )

    response = await router_module.update_qqcc_config(payload, db=db)

    assert db.committed is True
    assert response["config"]["video_scenes"] == [
        {
            "id": "kiss",
            "name": "贴贴",
            "prompt": "custom kiss prompt",
            "duration": "8s",
            "engine": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
            "lora_name": "BreastGrow",
            "end_frame_draw_scene_id": "tail_pose",
        },
        {
            "id": "missionary",
            "name": "自定义传教士",
            "prompt": "custom missionary prompt",
            "duration": "10s",
            "prompt_key": "perfect_video_insert",
            "engine": VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2,
            "lora_name": "",
            "end_frame_draw_scene_id": "",
        },
    ]


@pytest.mark.asyncio
async def test_update_qqcc_config_router_preserves_dynamic_draw_scenes():
    db = _FakeSession()
    payload = QqccBotConfigRequest(
        main_buttons={"ai_draw": True},
        draw_scenes=[
            {
                "id": "soft_light",
                "name": "柔光写真",
                "prompt": "custom draw prompt",
                "engine": DRAW_SCENE_ENGINE_FREE_EDIT,
                "lora_name": "qwen/YARN_1.0.safetensors",
            },
            {
                "id": "anime",
                "name": "动漫风",
                "prompt": "anime style prompt",
                "engine": DRAW_SCENE_ENGINE_FREE_EDIT_V2,
                "lora_name": "qwen/YARN_1.0.safetensors",
            },
        ],
    )

    response = await router_module.update_qqcc_config(payload, db=db)

    assert db.committed is True
    assert response["config"]["main_buttons"]["ai_draw"] is True
    assert response["config"]["draw_scenes"] == [
        {
            "id": "soft_light",
            "name": "柔光写真",
            "prompt": "custom draw prompt",
            "engine": DRAW_SCENE_ENGINE_FREE_EDIT,
            "lora_name": "qwen/YARN_1.0.safetensors",
        },
        {
            "id": "anime",
            "name": "动漫风",
            "prompt": "anime style prompt",
            "engine": DRAW_SCENE_ENGINE_FREE_EDIT_V2,
            "lora_name": "",
        },
    ]
