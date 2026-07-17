import pytest
import base64
from unittest.mock import AsyncMock

from dashboard.backend.routers import qqcc as router_module
from dashboard.backend.schemas import QqccBotConfigRequest
from src.database.models import PrivateQqccBot, RuntimeCheckpoint
from src.lora_catalog import LTX_VIDEO_LORA_MODELS
from src.qqcc_ltx_lora_catalog import QQCC_LTX23_LIBRARY_MODELS
from src.services import qqcc_config_service as config_service_module
from src.services.qqcc_config_service import (
    AI_VIDEO_SCENE_ENGINE_LTX_VIDEO,
    DEFAULT_QQCC_LAZY_BOT_CONFIG,
    QQCC_LAZY_BOT_CONFIG_KEY,
    QQCC_SCENE_PRESET_PROMPTS,
    SCENE_PRESET_VERSION,
    DRAW_SCENE_ENGINE_FREE_EDIT,
    DRAW_SCENE_ENGINE_FREE_EDIT_V2,
    DRAW_SCENE_ENGINE_FREE_EDIT_V3,
    VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
    VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2,
    get_enabled_qqcc_draw_scenes,
    get_enabled_qqcc_filter_scenes,
    get_enabled_qqcc_video_scenes,
    get_enabled_qqcc_ai_video_scenes,
    cache_qqcc_demo_telegram_file_ids,
    get_qqcc_copywriting_override,
    load_qqcc_config_payload,
    normalize_qqcc_config,
    render_qqcc_copywriting,
    resolve_qqcc_prompt,
    save_qqcc_config_payload,
)
from src.services.qqcc_draw_chain_service import resolve_qqcc_draw_scene_prompt


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
    assert config["scene_preset_version"] == SCENE_PRESET_VERSION
    assert config["main_buttons"]["quick_undress"] is False
    assert config["main_buttons"]["quick_faceswap"] is True
    assert config["main_buttons"]["photo_edit"] is False
    assert config["main_buttons"]["ai_draw"] is True
    assert config["main_buttons"]["ai_filter"] is True
    assert config["main_buttons"]["ai_video"] is True
    assert config["ai_video_scenes"] == []
    assert config["main_buttons"]["private_bot"] is True
    assert config["filter_scenes"] == []
    assert config["main_menu_layout"] == {
        "buttons_per_row": None,
        "button_order": [
            "quick_faceswap",
            "ai_draw",
            "ai_filter",
            "video_edit",
            "ai_video",
            "market",
            "private_bot",
            "main_bot_link",
        ],
    }
    assert config["draw_scenes"] == [
        {
            "id": "quick_masturbation",
            "name": "快速自慰",
            "prompt": QQCC_SCENE_PRESET_PROMPTS["masturbation"],
            "negative_prompt": "",
            "engine": DRAW_SCENE_ENGINE_FREE_EDIT,
            "lora_name": "",
            "postprocess_draw_scene_id": "",
            "postprocess_filter_scene_id": "",
            "original_face_swap_enabled": False,
        },
        {
            "id": "quick_undress",
            "name": "快速脱衣",
            "prompt": QQCC_SCENE_PRESET_PROMPTS["undress"],
            "negative_prompt": "",
            "engine": DRAW_SCENE_ENGINE_FREE_EDIT,
            "lora_name": "",
            "postprocess_draw_scene_id": "",
            "postprocess_filter_scene_id": "",
            "original_face_swap_enabled": False,
        },
    ]


def test_normalize_qqcc_main_menu_layout_sanitizes_columns_and_order():
    config = normalize_qqcc_config(
        {
            "main_menu_layout": {
                "buttons_per_row": 3,
                "button_order": [
                    "market",
                    "unknown",
                    "market",
                    "quick_undress",
                    "quick_faceswap",
                ],
            }
        }
    )

    assert config["main_menu_layout"] == {
        "buttons_per_row": 3,
        "button_order": [
            "market",
            "quick_faceswap",
            "ai_draw",
            "ai_filter",
            "video_edit",
            "ai_video",
            "private_bot",
            "main_bot_link",
        ],
    }


@pytest.mark.parametrize("invalid_columns", [True, False, 0, 5, "2", 2.5])
def test_normalize_qqcc_main_menu_layout_falls_back_for_invalid_columns(
    invalid_columns,
):
    config = normalize_qqcc_config(
        {"main_menu_layout": {"buttons_per_row": invalid_columns}}
    )

    assert config["main_menu_layout"]["buttons_per_row"] is None
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
    assert config["video_scenes"][0]["negative_prompt"] == ""


def test_normalize_qqcc_config_keeps_valid_ai_video_scenes_and_ltx_options():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "tail_pose",
                    "name": "Tail",
                    "prompt": "make a tail frame",
                    "engine": "free_edit_v2",
                }
            ],
            "video_scenes": [],
            "ai_video_scenes": [
                {
                    "id": "cinematic",
                    "name": " Cinematic ",
                    "prompt": " move slowly ",
                    "negative_prompt": " blur, jitter ",
                    "duration": 10,
                    "engine": "ltx_video",
                    "end_frame_draw_scene_id": "tail_pose",
                    "lora_items": [
                        {
                            "path": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
                            "strength": 99,
                        },
                        {
                            "path": "ltx2.3/SynthPussy_01_rank32.safetensors",
                            "strength": 0.04,
                        },
                        {
                            "path": "ltx2.3/SynthPussy_01_rank32.safetensors",
                            "strength": 1.5,
                        },
                        {
                            "path": "ltx2.3/ltxdeepthroat_v01.safetensors",
                        },
                        {
                            "path": "ltx2.3/sfbehind_LTX2_3_v0_1.safetensors",
                            "strength": 1,
                        },
                    ],
                },
                {
                    "id": "fallbacks",
                    "name": "Fallbacks",
                    "prompt": "prompt",
                    "negative_prompt": "   ",
                    "duration": "99s",
                    "engine": "unknown",
                    "end_frame_draw_scene_id": "missing",
                    "lora_items": [{"path": "missing.safetensors", "strength": 1}],
                },
            ],
        }
    )

    assert get_enabled_qqcc_ai_video_scenes(config) == [
        {
            "id": "cinematic",
            "name": "Cinematic",
            "prompt": "move slowly",
            "negative_prompt": "blur, jitter",
            "duration": 10,
            "engine": AI_VIDEO_SCENE_ENGINE_LTX_VIDEO,
            "lora_items": [
                {
                    "path": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
                    "strength": 2.0,
                },
                {
                    "path": "ltx2.3/SynthPussy_01_rank32.safetensors",
                    "strength": 0.1,
                },
                {
                    "path": "ltx2.3/ltxdeepthroat_v01.safetensors",
                    "strength": 1.0,
                },
            ],
            "end_frame_draw_scene_id": "tail_pose",
        },
        {
            "id": "fallbacks",
            "name": "Fallbacks",
            "prompt": "prompt",
            "negative_prompt": "",
            "duration": 5,
            "engine": AI_VIDEO_SCENE_ENGINE_LTX_VIDEO,
            "lora_items": [],
            "end_frame_draw_scene_id": "",
        },
    ]

    options = config_service_module.build_qqcc_config_options()
    assert options["default_ai_video_engine"] == AI_VIDEO_SCENE_ENGINE_LTX_VIDEO
    assert options["ai_video_engines"] == [
        {"value": AI_VIDEO_SCENE_ENGINE_LTX_VIDEO, "supports_lora": True}
    ]
    assert any(
        item["value"] == "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors"
        and item["default_strength"] == 0.8
        for item in options["ltx_video_lora_models"]
    )


def test_qqcc_admin_only_ltx_lora_is_configurable_without_public_exposure():
    admin_only_path = "ltx2.3/SexGod_Nudity_LTX23_v2_0.safetensors"

    assert len(QQCC_LTX23_LIBRARY_MODELS) == 32
    assert len(set(QQCC_LTX23_LIBRARY_MODELS) - set(LTX_VIDEO_LORA_MODELS)) == 26
    assert admin_only_path not in LTX_VIDEO_LORA_MODELS

    options = config_service_module.build_qqcc_config_options()
    assert any(
        item == {
            "value": admin_only_path,
            "label": "自然裸体与写真姿势",
            "default_strength": 0.8,
        }
        for item in options["ltx_video_lora_models"]
    )

    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "video_scenes": [],
            "ai_video_scenes": [
                {
                    "id": "admin_nudity",
                    "name": "后台写真",
                    "prompt": "LTXNUDES, natural full-body posing",
                    "duration": 5,
                    "lora_items": [
                        {"path": admin_only_path, "strength": 0.8},
                    ],
                }
            ],
        }
    )

    assert config["ai_video_scenes"][0]["lora_items"] == [
        {"path": admin_only_path, "strength": 0.8}
    ]


def test_normalize_config_keeps_generated_output_draft_only_after_save_payload():
    config = normalize_qqcc_config({
        "scene_preset_version": 1,
        "video_scenes": [],
        "filter_scenes": [],
        "draw_scenes": [{
            "id": "portrait",
            "name": "Portrait",
            "prompt": "portrait prompt",
            "engine": "free_edit_v2",
            "demo_output_media": {
                "object_key": "qqcc/demo/draw/portrait/generated/qqcc-demo-task-1/output",
                "media_type": "image",
                "mime_type": "image/png",
                "file_name": "generated.png",
            },
        }],
    })

    assert config["draw_scenes"][0]["demo_output_media"]["object_key"].endswith(
        "/generated/qqcc-demo-task-1/output"
    )


def test_demo_media_upload_route_supports_put_and_legacy_post():
    methods = {
        method
        for route in router_module.router.routes
        if route.path == "/api/qqcc/demo-media/{scene_kind}/{scene_id}/{slot}"
        for method in route.methods
    }

    assert methods == {"POST", "PUT"}


@pytest.mark.asyncio
async def test_demo_generation_routes_submit_and_poll_without_saving_config(monkeypatch):
    submit = AsyncMock(return_value={"generation_id": "task-1", "status": "pending"})
    poll = AsyncMock(return_value={"generation_id": "task-1", "status": "done", "media": {}})
    monkeypatch.setattr(router_module, "submit_qqcc_demo_generation", submit)
    monkeypatch.setattr(router_module, "get_qqcc_demo_generation", poll)
    scene = {
        "id": "portrait",
        "prompt": "portrait prompt",
        "engine": "free_edit_v2",
        "demo_input_media": {
            "object_key": "qqcc/demo/draw/portrait/input",
            "mime_type": "image/png",
        },
    }

    submitted = await router_module.submit_qqcc_scene_demo_generation(
        "draw", router_module.QqccDemoGenerationRequest(scene=scene)
    )
    completed = await router_module.get_qqcc_scene_demo_generation(
        "draw", "portrait", "task-1"
    )

    assert submitted["status"] == "pending"
    assert completed["status"] == "done"
    submit.assert_awaited_once_with(scene_kind="draw", scene=scene)
    poll.assert_awaited_once_with(
        scene_kind="draw", scene_id="portrait", generation_id="task-1"
    )


@pytest.mark.asyncio
async def test_json_demo_media_upload_decodes_file_and_uses_existing_validation(monkeypatch):
    uploaded = {
        "object_key": "qqcc/demo/draw/portrait/input",
        "media_type": "image",
        "mime_type": "image/png",
        "file_name": "before.png",
        "telegram_file_ids": {},
    }
    upload_media = AsyncMock(return_value=uploaded)
    monkeypatch.setattr(router_module, "upload_qqcc_demo_media", upload_media)
    monkeypatch.setattr(
        router_module,
        "build_qqcc_demo_preview_url",
        lambda media: f"https://preview.example/{media['object_key']}",
    )

    response = await router_module.put_qqcc_scene_demo_media_json(
        scene_kind="draw",
        scene_id="portrait",
        slot="input",
        payload=router_module.QqccDemoMediaJsonRequest(
            file_name="before.png",
            mime_type="image/png",
            content_base64=base64.b64encode(b"\x89PNG\r\n\x1a\nbody").decode(),
        ),
    )

    upload = upload_media.await_args.kwargs["upload"]
    assert upload.content_type == "image/png"
    assert upload.filename == "before.png"
    assert await upload.read() == b"\x89PNG\r\n\x1a\nbody"
    assert response["media"] == uploaded


def test_normalize_qqcc_config_migrates_legacy_config_with_scene_presets():
    config = normalize_qqcc_config(
        {
            "draw_scenes": [
                {
                    "id": "little_hip",
                    "name": "小屁股",
                    "prompt": "图中女人衣服脱光，屁股变小露出来",
                    "engine": DRAW_SCENE_ENGINE_FREE_EDIT_V2,
                }
            ]
        }
    )

    assert [scene["id"] for scene in config["draw_scenes"]] == [
        "quick_masturbation",
        "quick_undress",
        "little_hip",
    ]
    assert config["draw_scenes"][0]["name"] == "快速自慰"
    assert config["draw_scenes"][0]["prompt"] == QQCC_SCENE_PRESET_PROMPTS["masturbation"]
    assert config["draw_scenes"][1]["name"] == "快速脱衣"
    assert config["draw_scenes"][1]["prompt"] == QQCC_SCENE_PRESET_PROMPTS["undress"]
    assert config["draw_scenes"][2]["name"] == "小屁股"
    assert config["scene_preset_version"] == SCENE_PRESET_VERSION


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
        "quick_faceswap": True,
        "photo_edit": False,
        "ai_draw": True,
        "ai_filter": True,
        "video_edit": True,
        "ai_video": True,
        "market": True,
        "main_bot_link": True,
        "private_bot": True,
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


def test_normalize_qqcc_config_keeps_supported_copywriting_and_renders_scene_button():
    config = normalize_qqcc_config(
        {
            "copywriting": {
                "ai_draw_menu": "  请选择绘图模式  ",
                "ai_draw_scene_start": "已切换到【{butten}】模式，请发送图片。",
                "unknown": "drop me",
            }
        }
    )

    assert config["copywriting"]["ai_draw_menu"] == "请选择绘图模式"
    assert config["copywriting"]["ai_draw_scene_start"] == (
        "已切换到【{butten}】模式，请发送图片。"
    )
    assert "unknown" not in config["copywriting"]
    assert get_qqcc_copywriting_override(config, "ai_filter_menu") is None
    assert render_qqcc_copywriting(
        get_qqcc_copywriting_override(config, "ai_draw_scene_start"),
        "柔光写真",
    ) == "已切换到【柔光写真】模式，请发送图片。"


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
    assert scenes[0]["negative_prompt"] == ""
    assert scenes[0]["engine"] == VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO
    assert scenes[0]["lora_name"] == ""
    assert scenes[-1]["prompt"] == "custom closeup prompt"
    assert scenes[-1]["duration"] == "5s"


def test_normalize_qqcc_config_keeps_only_valid_dynamic_video_scenes():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "video_scenes": [
                {
                    "id": "kiss",
                    "name": "亲吻",
                    "prompt": "  kissing prompt  ",
                    "negative_prompt": "  blur, low quality  ",
                    "duration": "8s",
                },
                {
                    "id": "kiss",
                    "name": "重复 id",
                    "prompt": "duplicate prompt",
                    "negative_prompt": 123,
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
            "negative_prompt": "blur, low quality",
            "duration": "8s",
                "engine": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
                "lora_name": "",
                "lora_strength": 1.0,
                "lora_items": [],
                "end_frame_draw_scene_id": "",
        },
        {
            "id": "scene_2",
            "name": "重复 id",
            "prompt": "duplicate prompt",
            "negative_prompt": "",
            "duration": "10s",
                "engine": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
                "lora_name": "",
                "lora_strength": 1.0,
                "lora_items": [],
                "end_frame_draw_scene_id": "",
        },
        {
            "id": "scene_3",
            "name": "安全 id",
            "prompt": "safe id prompt",
            "negative_prompt": "",
            "duration": "5s",
                "engine": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
                "lora_name": "",
                "lora_strength": 1.0,
                "lora_items": [],
                "end_frame_draw_scene_id": "",
        },
    ]


def test_normalize_qqcc_config_validates_scene_engines_and_loras():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
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
    assert video_scenes[0]["lora_strength"] == 1.0
    assert video_scenes[0]["lora_items"] == [
        {"name": "BreastGrow", "strength": 1.0}
    ]
    assert video_scenes[0]["negative_prompt"] == ""
    assert video_scenes[1]["engine"] == VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2
    assert video_scenes[1]["lora_name"] == "BreastGrow"
    assert video_scenes[1]["lora_strength"] == 1.0
    assert video_scenes[1]["lora_items"] == [
        {"name": "BreastGrow", "strength": 1.0}
    ]
    assert video_scenes[1]["negative_prompt"] == ""
    assert video_scenes[2]["engine"] == VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO
    assert video_scenes[2]["lora_name"] == ""
    assert video_scenes[2]["lora_items"] == []
    assert video_scenes[2]["negative_prompt"] == ""

    draw_scenes = get_enabled_qqcc_draw_scenes(config)
    draw_scenes_by_id = {scene["id"]: scene for scene in draw_scenes}
    assert draw_scenes_by_id["old_draw"]["engine"] == DRAW_SCENE_ENGINE_FREE_EDIT
    assert draw_scenes_by_id["old_draw"]["lora_name"] == "qwen/YARN_1.0.safetensors"
    assert draw_scenes_by_id["old_draw"]["negative_prompt"] == ""
    assert draw_scenes_by_id["v2_draw"]["engine"] == DRAW_SCENE_ENGINE_FREE_EDIT_V2
    assert draw_scenes_by_id["v2_draw"]["lora_name"] == ""
    assert draw_scenes_by_id["v2_draw"]["negative_prompt"] == ""
    assert draw_scenes_by_id["bad_draw"]["engine"] == DRAW_SCENE_ENGINE_FREE_EDIT_V2
    assert draw_scenes_by_id["bad_draw"]["lora_name"] == ""
    assert draw_scenes_by_id["bad_draw"]["negative_prompt"] == ""


def test_normalize_qqcc_video_lora_items_preserves_order_dedupes_and_limits_five():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "video_scenes": [
                {
                    "id": "lora_five",
                    "name": "五模型",
                    "prompt": "video prompt",
                    "engine": VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2,
                    "lora_items": [
                        {"name": "Footjob", "strength": 1.37},
                        {"name": "BreastGrow", "strength": 99},
                        {"name": "Footjob", "strength": 0.2},
                        {"name": "Cum", "strength": 0.04},
                        {"name": "Cunilingus"},
                        {"name": "Insertion", "strength": "bad"},
                        {"name": "Flatchested", "strength": 0.8},
                        {"name": "missing", "strength": 1.0},
                    ],
                }
            ],
        }
    )

    scene = config["video_scenes"][0]
    assert scene["lora_items"] == [
        {"name": "Footjob", "strength": 1.35},
        {"name": "BreastGrow", "strength": 2.0},
        {"name": "Cum", "strength": 0.1},
        {"name": "Cunilingus", "strength": 1.0},
        {"name": "Insertion", "strength": 1.0},
    ]
    assert scene["lora_name"] == "Footjob"
    assert scene["lora_strength"] == 1.35

    options = config_service_module.build_qqcc_config_options()
    assert options["video_engines"] == [
        {"value": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO, "supports_lora": True},
        {"value": VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2, "supports_lora": True},
    ]
    assert any(
        item == {
            "value": "Footjob",
            "label": "足交",
            "default_strength": 1.0,
        }
        for item in options["video_lora_models"]
    )


def test_normalize_qqcc_config_validates_video_end_frame_draw_scene_reference():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
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


def test_normalize_qqcc_config_validates_draw_postprocess_reference():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "base",
                    "name": "基础绘图",
                    "prompt": "base prompt",
                    "postprocess_draw_scene_id": "polish",
                },
                {
                    "id": "polish",
                    "name": "精修",
                    "prompt": "polish prompt",
                    "postprocess_draw_scene_id": "polish",
                },
                {
                    "id": "missing",
                    "name": "缺失引用",
                    "prompt": "missing prompt",
                    "postprocess_draw_scene_id": "removed_scene",
                },
            ]
        }
    )

    scenes = get_enabled_qqcc_draw_scenes(config)
    scenes_by_id = {scene["id"]: scene for scene in scenes}

    assert scenes_by_id["base"]["postprocess_draw_scene_id"] == "polish"
    assert scenes_by_id["polish"]["postprocess_draw_scene_id"] == ""
    assert scenes_by_id["missing"]["postprocess_draw_scene_id"] == ""


def test_normalize_qqcc_config_validates_filter_scenes_and_draw_filter_reference():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "filter_scenes": [
                {
                    "id": "real_skin",
                    "name": "真实质感",
                    "prompt": "  keep identity, improve skin texture  ",
                    "negative_prompt": "  waxy skin  ",
                    "engine": DRAW_SCENE_ENGINE_FREE_EDIT,
                    "lora_name": "qwen/YARN_1.0.safetensors",
                    "original_face_swap_enabled": True,
                },
                {
                    "id": "v2_filter",
                    "name": "清晰增强",
                    "prompt": "sharp detail",
                    "engine": DRAW_SCENE_ENGINE_FREE_EDIT_V2,
                    "lora_name": "qwen/YARN_1.0.safetensors",
                },
                {"id": "empty_prompt", "name": "空提示", "prompt": ""},
            ],
            "draw_scenes": [
                {
                    "id": "base",
                    "name": "基础绘图",
                    "prompt": "base prompt",
                    "postprocess_filter_scene_id": "real_skin",
                },
                {
                    "id": "missing",
                    "name": "缺失滤镜",
                    "prompt": "missing prompt",
                    "postprocess_filter_scene_id": "removed_filter",
                },
                {
                    "id": "draw_wins",
                    "name": "绘图优先",
                    "prompt": "draw wins prompt",
                    "postprocess_draw_scene_id": "base",
                    "postprocess_filter_scene_id": "real_skin",
                },
            ],
        }
    )

    filters = get_enabled_qqcc_filter_scenes(config)
    assert filters == [
        {
            "id": "real_skin",
            "name": "真实质感",
            "prompt": "keep identity, improve skin texture",
            "negative_prompt": "waxy skin",
            "engine": DRAW_SCENE_ENGINE_FREE_EDIT,
            "lora_name": "qwen/YARN_1.0.safetensors",
            "original_face_swap_enabled": True,
        },
        {
            "id": "v2_filter",
            "name": "清晰增强",
            "prompt": "sharp detail",
            "negative_prompt": "",
            "engine": DRAW_SCENE_ENGINE_FREE_EDIT_V2,
            "lora_name": "",
            "original_face_swap_enabled": False,
        },
    ]
    scenes_by_id = {scene["id"]: scene for scene in get_enabled_qqcc_draw_scenes(config)}
    assert scenes_by_id["base"]["postprocess_filter_scene_id"] == "real_skin"
    assert scenes_by_id["missing"]["postprocess_filter_scene_id"] == ""
    assert scenes_by_id["draw_wins"]["postprocess_draw_scene_id"] == "base"
    assert scenes_by_id["draw_wins"]["postprocess_filter_scene_id"] == ""


def test_normalize_qqcc_config_breaks_draw_postprocess_cycles():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "base",
                    "name": "基础绘图",
                    "prompt": "base prompt",
                    "postprocess_draw_scene_id": "polish",
                },
                {
                    "id": "polish",
                    "name": "精修",
                    "prompt": "polish prompt",
                    "postprocess_draw_scene_id": "base",
                },
                {
                    "id": "outer",
                    "name": "外层引用",
                    "prompt": "outer prompt",
                    "postprocess_draw_scene_id": "base",
                },
            ]
        }
    )

    scenes = get_enabled_qqcc_draw_scenes(config)
    scenes_by_id = {scene["id"]: scene for scene in scenes}

    assert scenes_by_id["base"]["postprocess_draw_scene_id"] == ""
    assert scenes_by_id["polish"]["postprocess_draw_scene_id"] == ""
    assert scenes_by_id["outer"]["postprocess_draw_scene_id"] == "base"


def test_normalize_qqcc_config_keeps_only_valid_dynamic_draw_scenes():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "soft_light",
                    "name": "柔光写真",
                    "prompt": "  make it cinematic  ",
                    "negative_prompt": "  low detail  ",
                },
                {
                    "id": "soft_light",
                    "name": "重复 id",
                    "prompt": "duplicate prompt",
                    "negative_prompt": ["invalid"],
                },
                {
                    "id": "bad id!",
                    "name": "安全 id",
                    "prompt": "safe id prompt",
                },
                {
                    "id": "builtin",
                    "name": "内置提示词",
                    "prompt": "",
                    "prompt_key": "undress",
                    "engine": DRAW_SCENE_ENGINE_FREE_EDIT,
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
            "negative_prompt": "low detail",
            "engine": DRAW_SCENE_ENGINE_FREE_EDIT_V2,
            "lora_name": "",
            "postprocess_draw_scene_id": "",
            "postprocess_filter_scene_id": "",
            "original_face_swap_enabled": False,
        },
        {
            "id": "scene_2",
            "name": "重复 id",
            "prompt": "duplicate prompt",
            "negative_prompt": "",
            "engine": DRAW_SCENE_ENGINE_FREE_EDIT_V2,
            "lora_name": "",
            "postprocess_draw_scene_id": "",
            "postprocess_filter_scene_id": "",
            "original_face_swap_enabled": False,
        },
        {
            "id": "scene_3",
            "name": "安全 id",
            "prompt": "safe id prompt",
            "negative_prompt": "",
            "engine": DRAW_SCENE_ENGINE_FREE_EDIT_V2,
            "lora_name": "",
            "postprocess_draw_scene_id": "",
            "postprocess_filter_scene_id": "",
            "original_face_swap_enabled": False,
        },
    ]


def test_normalize_qqcc_config_keeps_all_valid_draw_scenes_without_a_count_limit():
    raw_scenes = [
        {
            "id": f"draw_{index}",
            "name": f"绘图 {index}",
            "prompt": f"prompt {index}",
        }
        for index in range(1, 26)
    ]

    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": raw_scenes,
        }
    )

    scenes = get_enabled_qqcc_draw_scenes(config)
    assert len(scenes) == 25
    assert scenes[-1]["id"] == "draw_25"
    assert scenes[-1]["name"] == "绘图 25"


def test_normalize_qqcc_config_preserves_scene_demo_media_and_bot_file_id_cache():
    media = {
        "object_key": "qqcc/demo/draw/portrait/input",
        "media_type": "image",
        "mime_type": "image/png",
        "file_name": "before.png",
        "telegram_file_ids": {
            "123456": "telegram-photo-file-id",
            "invalid-bot": "must-be-dropped",
        },
        "preview_url": "https://expired.example/should-not-persist",
    }

    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "portrait",
                    "name": "人像",
                    "prompt": "portrait prompt",
                    "demo_input_media": media,
                    "demo_output_media": {
                        **media,
                        "object_key": "qqcc/demo/draw/portrait/output",
                        "file_name": "after.png",
                    },
                }
            ],
        }
    )

    scene = config["draw_scenes"][0]
    assert scene["demo_input_media"] == {
        "object_key": "qqcc/demo/draw/portrait/input",
        "media_type": "image",
        "mime_type": "image/png",
        "file_name": "before.png",
        "telegram_file_ids": {"123456": "telegram-photo-file-id"},
    }
    assert scene["demo_output_media"]["object_key"].endswith("/output")
    assert "preview_url" not in scene["demo_input_media"]


def test_normalize_qqcc_config_migrates_legacy_draw_prompt_keys_to_scene_prompts():
    config = normalize_qqcc_config(
        {
            "prompts": {"undress": "  config override  "},
            "draw_scenes": [
                {
                    "id": "quick_undress",
                    "name": "快速脱衣",
                    "prompt": "",
                    "prompt_key": "undress",
                    "engine": DRAW_SCENE_ENGINE_FREE_EDIT,
                },
                {
                    "id": "quick_masturbation",
                    "name": "快速自慰",
                    "prompt": "",
                    "prompt_key": "masturbation",
                    "engine": DRAW_SCENE_ENGINE_FREE_EDIT,
                },
            ],
        }
    )
    scenes = get_enabled_qqcc_draw_scenes(config)
    scenes_by_id = {scene["id"]: scene for scene in scenes}

    assert "prompt_key" not in scenes_by_id["quick_undress"]
    assert "prompt_key" not in scenes_by_id["quick_masturbation"]
    assert resolve_qqcc_draw_scene_prompt(
        config,
        scenes_by_id["quick_undress"],
        {"undress": "prompts ini undress", "masturbation": "prompts ini masturbation"},
    ) == "config override"
    assert resolve_qqcc_draw_scene_prompt(
        config,
        scenes_by_id["quick_masturbation"],
        {"masturbation": "prompts ini masturbation"},
    ) == QQCC_SCENE_PRESET_PROMPTS["masturbation"]


def test_normalize_qqcc_config_seeds_presets_once_and_respects_new_empty_scenes():
    legacy_config = normalize_qqcc_config(
        {
            "main_buttons": {"ai_draw": True},
            "draw_scenes": [],
        }
    )
    explicit_empty_config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "main_buttons": {"quick_faceswap": True, "ai_draw": True},
            "draw_scenes": [],
            "video_scenes": [],
        }
    )

    assert [scene["id"] for scene in legacy_config["draw_scenes"]] == [
        "quick_masturbation",
        "quick_undress",
    ]
    assert explicit_empty_config["draw_scenes"] == []
    assert explicit_empty_config["video_scenes"] == []


@pytest.mark.asyncio
async def test_load_qqcc_config_payload_returns_defaults_when_checkpoint_missing():
    db = _FakeSession()

    response = await load_qqcc_config_payload(db)

    assert response["key"] == QQCC_LAZY_BOT_CONFIG_KEY
    assert response["config"] == DEFAULT_QQCC_LAZY_BOT_CONFIG
    assert response["options"]["video_engines"][0]["value"] == VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO
    assert response["options"]["draw_engines"][0]["value"] == DRAW_SCENE_ENGINE_FREE_EDIT
    assert response["options"]["scene_preset_version"] == SCENE_PRESET_VERSION
    assert response["options"]["default_video_engine"] == VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO
    assert response["options"]["default_draw_engine"] == DRAW_SCENE_ENGINE_FREE_EDIT_V2
    assert response["options"]["draw_engines"][-1] == {
        "value": DRAW_SCENE_ENGINE_FREE_EDIT_V3,
        "supports_lora": False,
    }
    assert any(
        item["value"] == "BreastGrow"
        for item in response["options"]["video_lora_models"]
    )
    assert any(
        item["value"] == "qwen/YARN_1.0.safetensors"
        for item in response["options"]["image_lora_models"]
    )
    assert response["updated_at"] is None


def test_normalize_qqcc_config_preserves_free_edit_v3_for_draw_and_filter_scenes():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {"id": "draw_v3", "name": "绘图 v3", "prompt": "draw", "engine": "free_edit_v3"}
            ],
            "filter_scenes": [
                {"id": "filter_v3", "name": "滤镜 v3", "prompt": "filter", "engine": "free_edit_v3"}
            ],
        }
    )

    assert config["draw_scenes"][0]["engine"] == DRAW_SCENE_ENGINE_FREE_EDIT_V3
    assert config["filter_scenes"][0]["engine"] == DRAW_SCENE_ENGINE_FREE_EDIT_V3
    assert config["draw_scenes"][0]["lora_name"] == ""
    assert config["filter_scenes"][0]["lora_name"] == ""


@pytest.mark.asyncio
async def test_load_qqcc_config_payload_adds_fresh_demo_preview_urls(monkeypatch):
    checkpoint = RuntimeCheckpoint(
        key=QQCC_LAZY_BOT_CONFIG_KEY,
        value={
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "portrait",
                    "name": "人像",
                    "prompt": "portrait prompt",
                    "demo_input_media": {
                        "object_key": "qqcc/demo/draw/portrait/input",
                        "media_type": "image",
                        "mime_type": "image/png",
                        "file_name": "before.png",
                    },
                    "demo_output_media": {
                        "object_key": "qqcc/demo/draw/portrait/generated/qqcc-demo-task-1/output",
                        "media_type": "image",
                        "mime_type": "image/png",
                        "file_name": "generated.png",
                        "content_sha256": "a" * 64,
                    },
                }
            ],
        },
    )
    db = _FakeSession(checkpoint)
    monkeypatch.setattr(
        config_service_module,
        "build_qqcc_demo_preview_url",
        lambda media: f"https://preview.example/{media['object_key']}",
    )

    response = await load_qqcc_config_payload(db)

    media = response["config"]["draw_scenes"][0]["demo_input_media"]
    assert media["preview_url"].endswith("qqcc/demo/draw/portrait/input")
    assert "preview_url" not in checkpoint.value["draw_scenes"][0]["demo_input_media"]


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
async def test_cache_qqcc_demo_telegram_file_ids_updates_matching_media_only():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "portrait",
                    "name": "人像",
                    "prompt": "portrait prompt",
                    "demo_input_media": {
                        "object_key": "qqcc/demo/draw/portrait/input",
                        "media_type": "image",
                        "mime_type": "image/png",
                        "file_name": "before.png",
                    },
                    "demo_output_media": {
                        "object_key": "qqcc/demo/draw/portrait/generated/qqcc-demo-task-1/output",
                        "media_type": "image",
                        "mime_type": "image/png",
                        "file_name": "generated.png",
                        "content_sha256": "a" * 64,
                    },
                }
            ],
        }
    )
    checkpoint = RuntimeCheckpoint(key=QQCC_LAZY_BOT_CONFIG_KEY, value=config)
    db = _FakeSession(checkpoint)

    updated = await cache_qqcc_demo_telegram_file_ids(
        scene_kind="draw",
        scene_id="portrait",
        bot_id="123",
        updates=[
            {
                "slot": "input",
                "object_key": "qqcc/demo/draw/portrait/input",
                "file_id": "photo-file-id",
            },
            {
                "slot": "output",
                "object_key": "wrong-key",
                "file_id": "must-not-be-written",
            },
        ],
        db=db,
    )

    assert updated == 1
    assert db.committed is True
    media = checkpoint.value["draw_scenes"][0]["demo_input_media"]
    assert media["telegram_file_ids"] == {"123": "photo-file-id"}
    output = checkpoint.value["draw_scenes"][0]["demo_output_media"]
    assert output["object_key"].endswith("/generated/qqcc-demo-task-1/output")
    assert output["content_sha256"] == "a" * 64


@pytest.mark.asyncio
async def test_cache_private_bot_demo_file_id_updates_tenant_config():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "portrait",
                    "name": "人像",
                    "prompt": "portrait prompt",
                    "demo_input_media": {
                        "object_key": "qqcc/private/7/demo/draw/portrait/input",
                        "media_type": "image",
                        "mime_type": "image/png",
                        "file_name": "before.png",
                    },
                }
            ],
        }
    )
    private_bot = PrivateQqccBot(id=7, config=config)
    db = _FakeSession(private_bot)

    updated = await cache_qqcc_demo_telegram_file_ids(
        scene_kind="draw",
        scene_id="portrait",
        bot_id="456",
        private_bot_id=7,
        updates=[
            {
                "slot": "input",
                "object_key": "qqcc/private/7/demo/draw/portrait/input",
                "file_id": "tenant-photo-file-id",
            }
        ],
        db=db,
    )

    assert updated == 1
    media = private_bot.config["draw_scenes"][0]["demo_input_media"]
    assert media["telegram_file_ids"] == {"456": "tenant-photo-file-id"}


@pytest.mark.asyncio
async def test_private_demo_cache_never_selects_tenant_from_mutable_object_key():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "portrait",
                    "name": "人像",
                    "prompt": "portrait prompt",
                    "demo_input_media": {
                        "object_key": "qqcc/private/7/demo/draw/portrait/input",
                        "media_type": "image",
                        "mime_type": "image/png",
                        "file_name": "before.png",
                    },
                }
            ],
        }
    )
    private_bot = PrivateQqccBot(id=7, config=config)
    db = _FakeSession(private_bot)

    updated = await cache_qqcc_demo_telegram_file_ids(
        scene_kind="draw",
        scene_id="portrait",
        bot_id="456",
        updates=[
            {
                "slot": "input",
                "object_key": "qqcc/private/7/demo/draw/portrait/input",
                "file_id": "must-not-be-written",
            }
        ],
        db=db,
    )

    assert updated == 0
    assert db.committed is False


@pytest.mark.asyncio
async def test_save_qqcc_config_preserves_newer_telegram_demo_cache():
    base_scene = {
        "id": "portrait",
        "name": "人像",
        "prompt": "old prompt",
        "demo_input_media": {
            "object_key": "qqcc/demo/draw/portrait/input",
            "media_type": "image",
            "mime_type": "image/png",
            "file_name": "before.png",
            "content_sha256": "a" * 64,
            "telegram_file_ids": {"123": "cached-photo"},
        },
    }
    checkpoint = RuntimeCheckpoint(
        key=QQCC_LAZY_BOT_CONFIG_KEY,
        value=normalize_qqcc_config(
            {
                "scene_preset_version": SCENE_PRESET_VERSION,
                "draw_scenes": [base_scene],
            }
        ),
    )
    db = _FakeSession(checkpoint)
    stale_payload_scene = {
        **base_scene,
        "prompt": "updated prompt",
        "demo_input_media": {
            **base_scene["demo_input_media"],
            "telegram_file_ids": {},
        },
    }

    await save_qqcc_config_payload(
        db,
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [stale_payload_scene],
        },
    )

    scene = checkpoint.value["draw_scenes"][0]
    assert scene["prompt"] == "updated prompt"
    assert scene["demo_input_media"]["telegram_file_ids"] == {
        "123": "cached-photo"
    }


@pytest.mark.asyncio
async def test_save_qqcc_config_drops_telegram_cache_when_demo_content_changes():
    old_media = {
        "object_key": "qqcc/demo/draw/portrait/input",
        "media_type": "image",
        "mime_type": "image/png",
        "file_name": "before.png",
        "content_sha256": "a" * 64,
        "telegram_file_ids": {"123": "old-photo"},
    }
    checkpoint = RuntimeCheckpoint(
        key=QQCC_LAZY_BOT_CONFIG_KEY,
        value=normalize_qqcc_config(
            {
                "scene_preset_version": SCENE_PRESET_VERSION,
                "draw_scenes": [
                    {
                        "id": "portrait",
                        "name": "人像",
                        "prompt": "prompt",
                        "demo_input_media": old_media,
                    }
                ],
            }
        ),
    )
    db = _FakeSession(checkpoint)

    await save_qqcc_config_payload(
        db,
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "portrait",
                    "name": "人像",
                    "prompt": "prompt",
                    "demo_input_media": {
                        **old_media,
                        "content_sha256": "b" * 64,
                        "telegram_file_ids": {},
                    },
                }
            ],
        },
    )

    media = checkpoint.value["draw_scenes"][0]["demo_input_media"]
    assert media["content_sha256"] == "b" * 64
    assert media["telegram_file_ids"] == {}


@pytest.mark.asyncio
async def test_update_qqcc_config_router_routes_to_runtime_checkpoint_service():
    db = _FakeSession()
    payload = QqccBotConfigRequest(main_buttons={"video_edit": False})

    response = await router_module.update_qqcc_config(payload, db=db)

    assert db.committed is True
    assert response["config"]["main_buttons"]["video_edit"] is False


@pytest.mark.asyncio
async def test_upload_qqcc_demo_media_router_returns_uploaded_descriptor(monkeypatch):
    uploaded = {
        "object_key": "qqcc/demo/video/kiss/output",
        "media_type": "video",
        "mime_type": "video/mp4",
        "file_name": "result.mp4",
        "telegram_file_ids": {},
    }
    upload = object()
    upload_media = AsyncMock(return_value=uploaded)
    monkeypatch.setattr(router_module, "upload_qqcc_demo_media", upload_media)
    monkeypatch.setattr(
        router_module,
        "build_qqcc_demo_preview_url",
        lambda media: f"https://preview.example/{media['object_key']}",
    )

    response = await router_module.upload_qqcc_scene_demo_media(
        scene_kind="video",
        scene_id="kiss",
        slot="output",
        file=upload,
    )

    upload_media.assert_awaited_once_with(
        scene_kind="video",
        scene_id="kiss",
        slot="output",
        upload=upload,
    )
    assert response["media"] == uploaded
    assert response["preview_url"].endswith("qqcc/demo/video/kiss/output")


@pytest.mark.asyncio
async def test_update_qqcc_config_router_preserves_dynamic_video_scenes():
    db = _FakeSession()
    payload = QqccBotConfigRequest(
        scene_preset_version=SCENE_PRESET_VERSION,
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
                "negative_prompt": "bad hands",
                "duration": "8s",
                "engine": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
                "lora_name": "BreastGrow",
                "lora_strength": 1.0,
                "lora_items": [{"name": "BreastGrow", "strength": 1.0}],
                "end_frame_draw_scene_id": "tail_pose",
            },
            {
                "id": "missionary",
                "name": "自定义传教士",
                "prompt": "custom missionary prompt",
                "negative_prompt": 999,
                "duration": "10s",
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
            "negative_prompt": "bad hands",
            "duration": "8s",
            "engine": VIDEO_SCENE_ENGINE_IMAGE_TO_VIDEO,
            "lora_name": "BreastGrow",
            "lora_strength": 1.0,
            "lora_items": [{"name": "BreastGrow", "strength": 1.0}],
            "end_frame_draw_scene_id": "tail_pose",
        },
        {
            "id": "missionary",
            "name": "自定义传教士",
            "prompt": "custom missionary prompt",
            "negative_prompt": "",
            "duration": "10s",
            "engine": VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2,
            "lora_name": "BreastGrow",
            "lora_strength": 1.0,
            "lora_items": [{"name": "BreastGrow", "strength": 1.0}],
            "end_frame_draw_scene_id": "",
        },
    ]


@pytest.mark.asyncio
async def test_update_qqcc_config_router_preserves_dynamic_draw_scenes():
    db = _FakeSession()
    payload = QqccBotConfigRequest(
        scene_preset_version=SCENE_PRESET_VERSION,
        main_buttons={"ai_draw": True},
        draw_scenes=[
            {
                "id": "soft_light",
                "name": "柔光写真",
                "prompt": "custom draw prompt",
                "negative_prompt": "bad anatomy",
                "engine": DRAW_SCENE_ENGINE_FREE_EDIT,
                "lora_name": "qwen/YARN_1.0.safetensors",
                "postprocess_draw_scene_id": "anime",
                "original_face_swap_enabled": True,
            },
            {
                "id": "anime",
                "name": "动漫风",
                "prompt": "anime style prompt",
                "negative_prompt": ["invalid"],
                "engine": DRAW_SCENE_ENGINE_FREE_EDIT_V2,
                "lora_name": "qwen/YARN_1.0.safetensors",
                "original_face_swap_enabled": "yes",
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
            "negative_prompt": "bad anatomy",
            "engine": DRAW_SCENE_ENGINE_FREE_EDIT,
            "lora_name": "qwen/YARN_1.0.safetensors",
            "postprocess_draw_scene_id": "anime",
            "postprocess_filter_scene_id": "",
            "original_face_swap_enabled": True,
        },
        {
            "id": "anime",
            "name": "动漫风",
            "prompt": "anime style prompt",
            "negative_prompt": "",
            "engine": DRAW_SCENE_ENGINE_FREE_EDIT_V2,
            "lora_name": "",
            "postprocess_draw_scene_id": "",
            "postprocess_filter_scene_id": "",
            "original_face_swap_enabled": False,
        },
    ]


@pytest.mark.asyncio
async def test_update_qqcc_config_router_preserves_filter_scenes_and_draw_filter_reference():
    db = _FakeSession()
    payload = QqccBotConfigRequest(
        scene_preset_version=SCENE_PRESET_VERSION,
        main_buttons={"ai_filter": True},
        filter_scenes=[
            {
                "id": "real_skin",
                "name": "真实质感",
                "prompt": "filter prompt",
                "negative_prompt": "plastic skin",
                "engine": DRAW_SCENE_ENGINE_FREE_EDIT,
                "lora_name": "qwen/YARN_1.0.safetensors",
                "original_face_swap_enabled": True,
            }
        ],
        draw_scenes=[
            {
                "id": "soft_light",
                "name": "柔光写真",
                "prompt": "custom draw prompt",
                "postprocess_filter_scene_id": "real_skin",
            }
        ],
    )

    response = await router_module.update_qqcc_config(payload, db=db)

    assert db.committed is True
    assert response["config"]["main_buttons"]["ai_filter"] is True
    assert response["config"]["filter_scenes"] == [
        {
            "id": "real_skin",
            "name": "真实质感",
            "prompt": "filter prompt",
            "negative_prompt": "plastic skin",
            "engine": DRAW_SCENE_ENGINE_FREE_EDIT,
            "lora_name": "qwen/YARN_1.0.safetensors",
            "original_face_swap_enabled": True,
        }
    ]
    assert response["config"]["draw_scenes"][0]["postprocess_filter_scene_id"] == "real_skin"
