from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.task_core_types import CoreDomainError
from src.web_api.schemas.prompt_optimization_schema import PromptOptimizationTaskRequest
from src.web_api.services.prompt_optimization_service import (
    PROMPT_MEDIA_MAX_BYTES,
    build_prompt_capability_payload,
    submit_prompt_optimization,
)


def _request(**overrides):
    payload = {
        "client_request_id": "761206f6-50ed-437c-855a-af14544352f9",
        "target_task_type": "ltx_video_v2",
        "template": {"id": "ltx_scene_script_cinematic", "version": 3},
        "prompt": "A performer turns toward the camera",
        "context": {"duration_seconds": 5},
        "media": [
            {"role": "start_image", "object_key": "web_uploads/7/start.webp"}
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


@pytest.mark.asyncio
async def test_submit_uses_deterministic_idempotency_and_immutable_refs():
    submit = AsyncMock(return_value={"task_id": "central-1", "cost": 1})
    result = await submit_prompt_optimization(
        request=_request(),
        current_user=SimpleNamespace(id=7, username="alice"),
        get_balance=AsyncMock(return_value=19),
        object_size=AsyncMock(return_value=1024),
        submit_task_func=submit,
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
    assert kwargs["allow_contribute_override"] is False
    assert "761206f6-50ed-437c-855a-af14544352f9" in kwargs[
        "submission_idempotency_key"
    ]


@pytest.mark.asyncio
async def test_submit_rejects_media_owned_by_another_user_before_storage_lookup():
    object_size = AsyncMock(return_value=1)
    with pytest.raises(CoreDomainError, match="当前用户"):
        await submit_prompt_optimization(
            request=_request(
                media=[
                    {
                        "role": "start_image",
                        "object_key": "web_uploads/8/start.png",
                    }
                ]
            ),
            current_user=SimpleNamespace(id=7, username="alice"),
            get_balance=AsyncMock(),
            object_size=object_size,
            submit_task_func=AsyncMock(),
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
            submit_task_func=AsyncMock(),
        )
