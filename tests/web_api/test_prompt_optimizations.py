from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from config import MINIO_BUCKET
from src.core.task_core_types import CoreDomainError, SubmissionReconciliationPending
from src.web_api.routers.prompt_optimizations import _require_enabled
from src.web_api.schemas.prompt_optimization_schema import PromptOptimizationTaskRequest
from src.web_api.services.prompt_optimization_service import (
    PROMPT_MEDIA_MAX_BYTES,
    build_prompt_capability_payload,
    submit_prompt_optimization,
)
from src.web_api.services.prompt_optimizer_config_service import get_default_config
from tests.task_application_test_support import LegacyTaskApplicationAdapter


async def _load_config(scene_key: str):
    return get_default_config(scene_key)


def _request(**overrides):
    payload = {
        "client_request_id": "761206f6-50ed-437c-855a-af14544352f9",
        "target_task_type": "ltx_video_v2",
        "template": {"id": "ltx_scene_script_cinematic", "version": 3},
        "prompt": "A performer turns toward the camera",
        "context": {"duration_seconds": 5},
        "media": [
            {
                "role": "start_image",
                "object_key": "staging/user-uploads/7/start.webp",
            }
        ],
    }
    payload.update(overrides)
    return PromptOptimizationTaskRequest.model_validate(payload)


def test_capability_does_not_expose_template_bodies():
    payload = build_prompt_capability_payload("ltx_video_v2")
    assert payload["cost"] == 1
    assert payload["templates"][0]["is_default"] is True
    assert "system_template" not in str(payload)
    assert "user_template" not in str(payload)
    assert payload["text_stream"] == {
        "enabled": True,
        "schema_version": "allbot.text_stream.v1",
        "events": ["text_snapshot", "text_delta"],
        "fields": ["positive_prompt"],
    }


def test_h3_optimizer_uses_its_own_environment_gate(monkeypatch):
    monkeypatch.setenv("MINIMAX_H3_BACKEND_ENABLED", "true")
    monkeypatch.setenv("MINIMAX_H3_PROMPT_OPTIMIZER_ENABLED", "false")
    with pytest.raises(HTTPException) as exc_info:
        _require_enabled("minimax_h3_t2v")
    assert exc_info.value.status_code == 404

    monkeypatch.setenv("MINIMAX_H3_PROMPT_OPTIMIZER_ENABLED", "true")
    _require_enabled("minimax_h3_t2v")


@pytest.mark.asyncio
async def test_submit_uses_deterministic_idempotency_and_immutable_refs():
    submit = AsyncMock(return_value={"task_id": "central-1", "cost": 1})
    result = await submit_prompt_optimization(
        request=_request(),
        current_user=SimpleNamespace(id=7, username="alice"),
        get_balance=AsyncMock(return_value=19),
        object_size=AsyncMock(return_value=1024),
        task_application=LegacyTaskApplicationAdapter(submit),
        load_config_func=_load_config,
    )

    assert result == {
        "task_id": "central-1",
        "status": "pending",
        "cost": 1,
        "balance_remaining": 19,
    }
    kwargs = submit.await_args.kwargs
    assert kwargs["task_type"] == "prompt_optimize"
    assert kwargs["cost_override"] == 1
    assert kwargs["inputs"]["profile_ref"] == "ltx_eros_v14_i2v@1"
    assert kwargs["inputs"]["template_ref"] == "ltx_scene_script_cinematic@3"
    assert len(kwargs["inputs"]["template_hash"]) == 64
    assert kwargs["inputs"]["text_stream_contract"] == {
        "schema_version": "allbot.text_stream.v1",
        "fields": ["positive_prompt"],
        "max_chars": 2000,
    }
    assert kwargs["registry_metadata"]["record_history"] is False
    assert kwargs["submission_before_dispatch_func"] is not None
    assert kwargs["submission_should_compensate_func"] is not None
    assert kwargs["allow_contribute_override"] is False
    assert (
        "761206f6-50ed-437c-855a-af14544352f9"
        in kwargs["submission_idempotency_key"]
    )


@pytest.mark.asyncio
async def test_submit_returns_pending_when_dispatch_is_reconciling():
    result = await submit_prompt_optimization(
        request=_request(),
        current_user=SimpleNamespace(id=7, username="alice"),
        get_balance=AsyncMock(return_value=19),
        object_size=AsyncMock(return_value=1024),
        task_application=LegacyTaskApplicationAdapter(
            AsyncMock(
                side_effect=SubmissionReconciliationPending(
                    registry_task_id="prompt-task",
                    cost=1,
                )
            )
        ),
        load_config_func=_load_config,
    )

    assert result["task_id"] == "prompt-task"
    assert result["status"] == "pending"
    assert result["cost"] == 1


@pytest.mark.asyncio
async def test_submit_rejects_media_owned_by_another_user_before_storage_lookup():
    object_size = AsyncMock(return_value=1)
    with pytest.raises(CoreDomainError, match="当前用户"):
        await submit_prompt_optimization(
            request=_request(
                media=[
                    {
                        "role": "start_image",
                        "object_key": "staging/user-uploads/8/start.png",
                    }
                ]
            ),
            current_user=SimpleNamespace(id=7, username="alice"),
            get_balance=AsyncMock(),
            object_size=object_size,
            task_application=LegacyTaskApplicationAdapter(AsyncMock()),
            load_config_func=_load_config,
        )
    object_size.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_rejects_oversized_media():
    with pytest.raises(CoreDomainError, match="20 MB"):
        await submit_prompt_optimization(
            request=_request(),
            current_user=SimpleNamespace(id=7, username="alice"),
            get_balance=AsyncMock(),
            object_size=AsyncMock(return_value=PROMPT_MEDIA_MAX_BYTES + 1),
            task_application=LegacyTaskApplicationAdapter(AsyncMock()),
            load_config_func=_load_config,
        )


@pytest.mark.asyncio
async def test_submit_pure_t2v_uses_v4_and_accepts_no_media():
    submit = AsyncMock(return_value={"task_id": "central-t2v", "cost": 1})
    await submit_prompt_optimization(
        request=_request(
            target_task_type="ltx_t2v",
            template={"id": "ltx_scene_script_cinematic", "version": 4},
            media=[],
        ),
        current_user=SimpleNamespace(id=7, username="alice"),
        get_balance=AsyncMock(return_value=18),
        object_size=AsyncMock(),
        task_application=LegacyTaskApplicationAdapter(submit),
        load_config_func=_load_config,
    )

    inputs = submit.await_args.kwargs["inputs"]
    assert inputs["profile_ref"] == "ltx_eros_t2v@1"
    assert inputs["template_ref"] == "ltx_scene_script_cinematic@4"
    assert inputs["media"] == []


@pytest.mark.asyncio
async def test_submit_minimax_h3_uses_fixed_stack_and_shared_scene_config():
    submit = AsyncMock(return_value={"task_id": "central-h3", "cost": 1})
    loaded_scene_keys = []

    async def load_config(scene_key):
        loaded_scene_keys.append(scene_key)
        return get_default_config(scene_key)

    await submit_prompt_optimization(
        request=_request(
            target_task_type="minimax_h3_i2v",
            template={"id": "minimax_h3_10eros_naughtytimes", "version": 4},
            prompt='中文场景描述，女人低声说：“Keep looking at me.”',
            context={"duration_seconds": 10},
        ),
        current_user=SimpleNamespace(id=7, username="alice"),
        get_balance=AsyncMock(return_value=18),
        object_size=AsyncMock(return_value=1024),
        task_application=LegacyTaskApplicationAdapter(submit),
        load_config_func=load_config,
    )

    assert loaded_scene_keys == ["minimax_h3"]
    inputs = submit.await_args.kwargs["inputs"]
    assert inputs["trusted_context"] == {}
    assert "HMBreasts" not in inputs["prompt_config_snapshot"]["user_message"]
    assert "hmmotion" not in inputs["prompt_config_snapshot"]["user_message"]
    assert inputs["profile_ref"] == "minimax_h3_i2v_prompt@5"
    assert "integrated_multimodal_description" in inputs["prompt_config_snapshot"]["system_message"]
    assert "<Picture 1> (from [Shot 1]) is fully referenced." in inputs["prompt_config_snapshot"]["user_message"]
    assert "[English]" in inputs["prompt_config_snapshot"]["user_message"]
    assert "Keep looking at me." in inputs["prompt_config_snapshot"]["user_message"]


@pytest.mark.asyncio
async def test_submit_minimax_h3_rejects_any_addon_before_media_lookup():
    object_size = AsyncMock(return_value=1024)
    with pytest.raises(CoreDomainError, match="不接受附加模型"):
        await submit_prompt_optimization(
            request=_request(
                target_task_type="minimax_h3_i2v",
                template={"id": "minimax_h3_10eros_naughtytimes", "version": 4},
                lora_items=[{"name": "client_rule_injection", "strength": 1.0}],
            ),
            current_user=SimpleNamespace(id=7, username="alice"),
            get_balance=AsyncMock(),
            object_size=object_size,
            task_application=LegacyTaskApplicationAdapter(AsyncMock()),
            load_config_func=_load_config,
        )
    object_size.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_h3_ref2v_resolves_typed_character_views_in_picture_order(
    monkeypatch,
):
    class SessionFactory:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            return None

    from src.web_api.services.reference_asset_service import ResolvedH3ReferenceSet

    monkeypatch.setenv("CHARACTER_ASSETS_ENABLED", "true")
    monkeypatch.setenv("CHARACTER_EXPLICIT_VIEWS_ENABLED", "true")
    monkeypatch.setattr("src.database.core.AsyncSessionLocal", SessionFactory)
    resolve = AsyncMock(
        return_value=ResolvedH3ReferenceSet(
            images=(
                "character_references/7/alice/face.png",
                "character_references/7/alice/genitals.png",
            ),
            descriptions=(
                "Adult character Alice; front face view.",
                "Adult character Alice; front genital anatomy close-up.",
            ),
        )
    )
    monkeypatch.setattr(
        "src.web_api.services.reference_asset_service.resolve_h3_reference_refs",
        resolve,
    )
    submit = AsyncMock(return_value={"task_id": "central-h3-ref", "cost": 1})

    await submit_prompt_optimization(
        request=_request(
            target_task_type="minimax_h3_ref2v",
            template={"id": "minimax_h3_ref2v", "version": 1},
            media=[],
            reference_refs=[
                {
                    "source": "private_character_view",
                    "character_id": "alice",
                    "view_type": "face_front",
                },
                {
                    "source": "private_character_view",
                    "character_id": "alice",
                    "view_type": "genitals_front",
                },
            ],
        ),
        current_user=SimpleNamespace(id=7, username="alice"),
        get_balance=AsyncMock(return_value=18),
        object_size=AsyncMock(return_value=1024),
        task_application=LegacyTaskApplicationAdapter(submit),
        load_config_func=_load_config,
    )

    inputs = submit.await_args.kwargs["inputs"]
    assert [item["role"] for item in inputs["media"]] == [
        "reference_image_1",
        "reference_image_2",
    ]
    assert [item["object_key"] for item in inputs["media"]] == list(
        resolve.return_value.images
    )
    assert inputs["trusted_context"]["reference_descriptions"] == list(
        resolve.return_value.descriptions
    )
    assert "front genital anatomy close-up" in inputs["prompt_config_snapshot"][
        "user_message"
    ]


@pytest.mark.asyncio
async def test_submit_ic_t2v_resolves_two_owner_fenced_characters(monkeypatch):
    class SessionFactory:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            return None

    resolve = AsyncMock(
        side_effect=[
            SimpleNamespace(
                sheet_object_key=f"{MINIO_BUCKET}/character_references/7/a/v1.png",
                description="adult A",
            ),
            SimpleNamespace(
                sheet_object_key=f"{MINIO_BUCKET}/character_references/7/b/v1.png",
                description="adult B",
            ),
        ]
    )
    monkeypatch.setattr("src.database.core.AsyncSessionLocal", SessionFactory)
    monkeypatch.setattr(
        "src.web_api.services.character_reference_service.resolve_ready_character_sheet",
        resolve,
    )
    submit = AsyncMock(return_value={"task_id": "central-ic", "cost": 1})
    await submit_prompt_optimization(
        request=_request(
            target_task_type="ltx_t2v_ic",
            template={"id": "ltx_scene_script_cinematic", "version": 4},
            character_ids=["a", "b"],
            media=[
                {
                    "role": "scene_background",
                    "object_key": "staging/user-uploads/7/bedroom.webp",
                }
            ],
        ),
        current_user=SimpleNamespace(id=7, username="alice"),
        get_balance=AsyncMock(return_value=18),
        object_size=AsyncMock(return_value=1024),
        task_application=LegacyTaskApplicationAdapter(submit),
        load_config_func=_load_config,
    )

    inputs = submit.await_args.kwargs["inputs"]
    assert inputs["profile_ref"] == "ltx_eros_t2v_ic_msr@1"
    assert [item["role"] for item in inputs["media"]] == [
        "reference_character_1",
        "reference_character_2",
        "scene_background",
    ]
    assert [item["object_key"] for item in inputs["media"]] == [
        "character_references/7/a/v1.png",
        "character_references/7/b/v1.png",
        "staging/user-uploads/7/bedroom.webp",
    ]
    assert "character_ids" not in inputs
