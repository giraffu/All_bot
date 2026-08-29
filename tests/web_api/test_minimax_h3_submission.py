from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.task_core_types import CoreDomainError
from src.web_api.schemas.task_schema import TaskGenerateRequest
from src.web_api.services import task_submission_service as service
from src.web_api.services.web_submission_preparation import (
    prepare_web_submission_request,
)
from tests.task_application_test_support import LegacyTaskApplicationAdapter


@pytest.mark.asyncio
async def test_minimax_h3_backend_flag_defaults_closed(monkeypatch):
    monkeypatch.delenv("MINIMAX_H3_BACKEND_ENABLED", raising=False)
    with pytest.raises(CoreDomainError, match="当前未开放") as exc_info:
        await service.submit_generation_task(
            req=TaskGenerateRequest(
                task_type="minimax_h3_t2v", prompt="scene", inputs={"duration": 5}
            ),
            current_user=SimpleNamespace(id=7, username="tester"),
            get_balance=AsyncMock(return_value=100),
        )
    assert "MiniMax" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_minimax_h3_operator_canary_uses_existing_submission_saga(monkeypatch):
    monkeypatch.setenv("MINIMAX_H3_BACKEND_ENABLED", "false")
    submit = AsyncMock(return_value={"task_id": "h3-canary", "cost": 10})
    monkeypatch.setattr(
        service,
        "get_task_application",
        lambda: LegacyTaskApplicationAdapter(submit),
    )
    response = await service.submit_generation_task(
        req=TaskGenerateRequest(
            task_type="minimax_h3_i2v",
            prompt="scene",
            inputs={"images": ["web_uploads/7/start.png"], "duration": 5},
        ),
        current_user=SimpleNamespace(id=7, username="tester"),
        get_balance=AsyncMock(return_value=90),
        operator_canary_authorized=True,
        advanced_video_profile_loader=AsyncMock(
            return_value={"main_model": "10eros", "addon_items": []}
        ),
    )
    assert response.task_id == "h3-canary"
    submit.assert_awaited_once()


@pytest.mark.asyncio
async def test_minimax_h3_direct_web_submission_uses_admin_model_profile():
    req = TaskGenerateRequest(
        task_type="minimax_h3_i2v",
        prompt="scene",
        inputs={
            "images": ["web_uploads/7/start.png"],
            "duration": 5,
            "main_model": "10eros",
            "lora_items": [{"name": "naughty_times", "strength": 2.0}],
        },
    )

    prepared = await prepare_web_submission_request(
        req,
        internal_user_id=7,
        operator_canary_authorized=True,
        env_enabled=lambda _name: True,
        advanced_video_profile_loader=AsyncMock(
            return_value={
                "main_model": "official",
                "addon_items": [
                    {"name": "motion_booster", "strength": 0.7},
                ],
            }
        ),
    )

    assert prepared.inputs["main_model"] == "official"
    assert prepared.inputs["lora_items"] == [
        {"name": "motion_booster", "strength": 0.7},
    ]


@pytest.mark.asyncio
async def test_minimax_h3_extension_uses_server_tail_and_inherits_contribution():
    prepare_extension = AsyncMock(
        return_value=SimpleNamespace(
            images=("task-results/parent/last.png",),
            metadata={
                "minimax_h3_prev_task_id": "parent",
                "minimax_h3_chain_task_ids": ["root", "parent"],
            },
            allow_contribute=False,
        )
    )
    req = TaskGenerateRequest(
        task_type="minimax_h3_i2v",
        prompt="continue walking",
        inputs={"minimax_h3_prev_task_id": "parent", "duration": 10},
    )

    prepared = await prepare_web_submission_request(
        req,
        internal_user_id=7,
        operator_canary_authorized=True,
        env_enabled=lambda _name: True,
        advanced_video_profile_loader=AsyncMock(
            return_value={"main_model": "official", "addon_items": []}
        ),
        prepare_h3_extension_func=prepare_extension,
    )

    assert prepared.images == ["task-results/parent/last.png"]
    assert prepared.registry_metadata == {
        "minimax_h3_prev_task_id": "parent",
        "minimax_h3_chain_task_ids": ["root", "parent"],
    }
    assert prepared.allow_contribute_override is False
    prepare_extension.assert_awaited_once_with(
        prev_task_id="parent",
        internal_user_id=7,
        target_task_type="minimax_h3_i2v",
        client_images=[],
    )


@pytest.mark.asyncio
async def test_minimax_h3_ref2v_resolves_single_audio_ref_without_rewriting_prompt(
    monkeypatch,
):
    from src.web_api.services import reference_asset_service

    resolve = AsyncMock(return_value="web_uploads/7/voice.m4a")
    monkeypatch.setattr(
        reference_asset_service, "resolve_h3_reference_audio_ref", resolve
    )
    req = TaskGenerateRequest(
        task_type="minimax_h3_ref2v",
        prompt="the character speaks softly",
        inputs={
            "images": ["web_uploads/7/subject.png"],
            "reference_audio_ref": {
                "source": "upload",
                "object_key": "web_uploads/7/voice.m4a",
            },
        },
    )

    prepared = await prepare_web_submission_request(
        req,
        internal_user_id=7,
        operator_canary_authorized=True,
        env_enabled=lambda _name: True,
        advanced_video_profile_loader=AsyncMock(
            return_value={"main_model": "10eros", "addon_items": []}
        ),
    )

    assert prepared.inputs["prompt"] == "the character speaks softly"
    assert prepared.inputs["reference_audio"] == "web_uploads/7/voice.m4a"
    assert "reference_audio_ref" not in prepared.inputs
    resolve.assert_awaited_once_with(
        user_id=7,
        reference_audio_ref={
            "source": "upload",
            "object_key": "web_uploads/7/voice.m4a",
        },
        source_post_id=None,
        is_template=False,
    )


@pytest.mark.asyncio
async def test_minimax_h3_template_can_reuse_gallery_reference_audio(monkeypatch):
    from src.web_api.services import reference_asset_service

    resolve = AsyncMock(return_value="task-inputs/source-task/3.m4a")
    monkeypatch.setattr(
        reference_asset_service, "resolve_h3_reference_audio_ref", resolve
    )
    req = TaskGenerateRequest(
        task_type="minimax_h3_ref2v",
        prompt="the character speaks softly",
        inputs={
            "images": ["web_uploads/7/new-subject.png"],
            "reference_audio_ref": {
                "source": "gallery_post",
                "post_id": 29,
            },
        },
        is_template=True,
        source_post_id=29,
    )

    prepared = await prepare_web_submission_request(
        req,
        internal_user_id=7,
        operator_canary_authorized=True,
        env_enabled=lambda _name: True,
        advanced_video_profile_loader=AsyncMock(
            return_value={"main_model": "10eros", "addon_items": []}
        ),
    )

    assert prepared.inputs["reference_audio"] == "task-inputs/source-task/3.m4a"
    resolve.assert_awaited_once_with(
        user_id=7,
        reference_audio_ref={"source": "gallery_post", "post_id": 29},
        source_post_id=29,
        is_template=True,
    )


@pytest.mark.asyncio
async def test_minimax_h3_rejects_audio_ref_outside_ref2v():
    req = TaskGenerateRequest(
        task_type="minimax_h3_t2v",
        prompt="scene",
        inputs={
            "reference_audio_ref": {
                "source": "upload",
                "object_key": "web_uploads/7/voice.m4a",
            }
        },
    )

    with pytest.raises(CoreDomainError, match="参考图生视频"):
        await prepare_web_submission_request(
            req,
            internal_user_id=7,
            operator_canary_authorized=True,
            env_enabled=lambda _name: True,
            advanced_video_profile_loader=AsyncMock(
                return_value={"main_model": "10eros", "addon_items": []}
            ),
        )
