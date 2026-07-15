from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.constants import (
    MODE_IMAGE_TO_VIDEO,
    MODE_LTX_VIDEO,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
    MODE_RANDOM_FACESWAP,
)
from src.services.qqcc_config_service import SCENE_PRESET_VERSION, normalize_qqcc_config
from src.services.qqcc_regeneration_service import (
    QQCCRegenerationError,
    prepare_qqcc_regeneration_submission,
)
from src.services.quick_image_submission_service import QuickImageSubmissionKind
from src.services.quick_video_submission_service import QuickVideoSubmissionKind


@pytest.mark.asyncio
async def test_prepare_qqcc_regeneration_rebuilds_random_faceswap_from_user_input(
    monkeypatch,
):
    history = SimpleNamespace(
        type="face_swap",
        input_file="template:quick_face/old.png|history/user-face.png",
        extra_outputs={
            "_qqcc_regenerate": {
                "kind": "quick_image",
                "mode": MODE_RANDOM_FACESWAP,
                "display_mode_name": "快速换脸",
            }
        },
    )
    download_input = AsyncMock(return_value="/tmp/user-face.png")
    monkeypatch.setattr(
        "src.services.qqcc_regeneration_service.download_history_input_file_to_fsm_temp",
        download_input,
    )
    monkeypatch.setattr(
        "src.services.qqcc_regeneration_service.list_quick_faceswap_template_files",
        lambda: ["quick_face/new.png"],
    )
    monkeypatch.setattr(
        "src.services.qqcc_regeneration_service.load_prompts",
        lambda: {"face_swap": "swap prompt"},
    )

    submission = await prepare_qqcc_regeneration_submission(
        task_id="task-random",
        telegram_user_id=123,
        username="tester",
        load_history_func=AsyncMock(return_value=history),
        load_config_func=AsyncMock(return_value=normalize_qqcc_config(None)),
    )

    assert submission.kind == "quick_image"
    assert submission.display_mode_name == "快速换脸"
    assert submission.image_path == "/tmp/user-face.png"
    assert submission.plan.kind == QuickImageSubmissionKind.RANDOM_FACESWAP
    assert submission.plan.allow_contribute is False
    assert submission.plan.result_meta == history.extra_outputs
    download_input.assert_awaited_once_with(
        history=history,
        index=1,
        name_hint="qqcc_regenerate_image",
    )


@pytest.mark.asyncio
async def test_prepare_qqcc_regeneration_rebuilds_quick_video_scene(monkeypatch):
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "video_scenes": [
                {
                    "id": "lora_scene",
                    "name": "模型动图",
                    "prompt": "video prompt",
                    "negative_prompt": "video blur",
                    "duration": "5s",
                    "engine": "image_to_video",
                    "lora_name": "BreastGrow",
                }
            ],
        }
    )
    history = SimpleNamespace(
        type=MODE_IMAGE_TO_VIDEO,
        input_file="history/start.png",
        billing_resolution="720p",
        requested_duration=5,
        duration=5,
        extra_outputs={
            "_qqcc_regenerate": {
                "kind": "quick_video",
                "mode": MODE_IMAGE_TO_VIDEO,
                "scene_id": "lora_scene",
                "display_mode_name": "模型动图",
            }
        },
    )
    download_input = AsyncMock(return_value="/tmp/start.png")
    monkeypatch.setattr(
        "src.services.qqcc_regeneration_service.download_history_input_file_to_fsm_temp",
        download_input,
    )
    monkeypatch.setattr(
        "src.services.qqcc_regeneration_service.resolve_allowed_quick_video_resolutions",
        AsyncMock(return_value=["512p", "720p"]),
    )

    submission = await prepare_qqcc_regeneration_submission(
        task_id="task-video",
        telegram_user_id=123,
        username="tester",
        load_history_func=AsyncMock(return_value=history),
        load_config_func=AsyncMock(return_value=config),
    )

    assert submission.kind == "quick_video"
    assert submission.display_mode_name == "模型动图"
    assert submission.plan.kind == QuickVideoSubmissionKind.LEGACY_VIDEO
    assert submission.plan.mode == MODE_IMAGE_TO_VIDEO
    assert submission.plan.default_prompt_text == "video prompt"
    assert submission.plan.allow_contribute is False
    assert submission.plan.result_meta == history.extra_outputs
    download_input.assert_awaited_once_with(
        history=history,
        index=0,
        name_hint="qqcc_regenerate_video",
    )


@pytest.mark.asyncio
async def test_prepare_qqcc_regeneration_reloads_latest_ai_video_scene(monkeypatch):
    config = normalize_qqcc_config(
        {
            "main_buttons": {"ai_video": True},
            "ai_video_scenes": [
                {
                    "id": "cinema",
                    "name": "电影运镜新版",
                    "prompt": "latest prompt",
                    "negative_prompt": "latest blur",
                    "duration": 20,
                }
            ],
        }
    )
    history = SimpleNamespace(
        type=MODE_LTX_VIDEO,
        input_file="history/start.png",
        billing_resolution="1280x704",
        requested_duration=5,
        duration=5,
        extra_outputs={
            "_qqcc_regenerate": {
                "kind": "quick_video",
                "mode": MODE_LTX_VIDEO,
                "scene_id": "cinema",
                "scene_kind": "ai_video",
                "display_mode_name": "电影运镜旧版",
            }
        },
    )
    monkeypatch.setattr(
        "src.services.qqcc_regeneration_service.download_history_input_file_to_fsm_temp",
        AsyncMock(return_value="/tmp/start.png"),
    )
    monkeypatch.setattr(
        "src.services.qqcc_regeneration_service.resolve_allowed_quick_video_resolutions",
        AsyncMock(return_value=[]),
    )

    submission = await prepare_qqcc_regeneration_submission(
        task_id="task-ltx",
        telegram_user_id=123,
        username="tester",
        load_history_func=AsyncMock(return_value=history),
        load_config_func=AsyncMock(return_value=config),
    )

    assert submission.display_mode_name == "电影运镜新版"
    assert submission.plan.kind == QuickVideoSubmissionKind.LTX_VIDEO
    assert submission.plan.default_prompt_text == "latest prompt"
    assert submission.plan.negative_prompt == "latest blur"
    assert submission.plan.duration == "20s"


@pytest.mark.asyncio
async def test_prepare_qqcc_regeneration_rebuilds_quick_image_filter_scene(monkeypatch):
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "filter_scenes": [
                {
                    "id": "real_skin",
                    "name": "真实质感",
                    "prompt": "filter prompt",
                    "negative_prompt": "plastic skin",
                }
            ],
        }
    )
    history = SimpleNamespace(
        type=MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
        input_file="history/original.png",
        extra_outputs={
            "_qqcc_regenerate": {
                "kind": "quick_image",
                "mode": MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
                "scene_id": "real_skin",
                "scene_kind": "filter",
                "display_mode_name": "真实质感",
            }
        },
    )
    download_input = AsyncMock(return_value="/tmp/original.png")
    monkeypatch.setattr(
        "src.services.qqcc_regeneration_service.download_history_input_file_to_fsm_temp",
        download_input,
    )

    submission = await prepare_qqcc_regeneration_submission(
        task_id="task-filter",
        telegram_user_id=123,
        username="tester",
        load_history_func=AsyncMock(return_value=history),
        load_config_func=AsyncMock(return_value=config),
    )

    assert submission.kind == "quick_image"
    assert submission.display_mode_name == "真实质感"
    assert submission.plan.kind == QuickImageSubmissionKind.DRAW_CHAIN
    assert submission.plan.draw_chain[0]["id"] == "real_skin"
    assert submission.plan.result_meta == history.extra_outputs


@pytest.mark.asyncio
async def test_prepare_qqcc_regeneration_cleans_download_when_plan_rejected(
    monkeypatch,
):
    history = SimpleNamespace(
        type="pornmaster_flux2_single_edit",
        input_file="history/original.png",
        extra_outputs={
            "_qqcc_regenerate": {
                "kind": "quick_image",
                "mode": "pornmaster_flux2_single_edit",
                "scene_id": "deleted_scene",
                "display_mode_name": "已删场景",
            }
        },
    )
    download_input = AsyncMock(return_value="/tmp/original.png")
    cleaned = []
    monkeypatch.setattr(
        "src.services.qqcc_regeneration_service.download_history_input_file_to_fsm_temp",
        download_input,
    )
    monkeypatch.setattr(
        "src.services.qqcc_regeneration_service.cleanup_fsm_temp_files",
        lambda paths: cleaned.extend(paths),
    )

    with pytest.raises(QQCCRegenerationError):
        await prepare_qqcc_regeneration_submission(
            task_id="task-deleted",
            telegram_user_id=123,
            username="tester",
            load_history_func=AsyncMock(return_value=history),
            load_config_func=AsyncMock(return_value=normalize_qqcc_config(None)),
        )

    assert cleaned == ["/tmp/original.png"]
