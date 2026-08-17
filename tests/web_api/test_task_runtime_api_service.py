from unittest.mock import AsyncMock

import pytest

from src.web_api.services import task_runtime_api_service


@pytest.mark.asyncio
async def test_get_queue_status_payload_returns_runtime_fallback_when_backend_unavailable():
    result = await task_runtime_api_service.get_queue_status_payload(
        get_queue_info_func=AsyncMock(return_value=None)
    )

    assert result == {"comfy_online": False, "queue_size": 0, "queue_by_type": {}}


@pytest.mark.asyncio
async def test_get_queue_status_payload_returns_backend_status_when_available():
    payload = {"comfy_online": True, "queue_size": 5, "queue_by_type": {"video": 2}}

    result = await task_runtime_api_service.get_queue_status_payload(
        get_queue_info_func=AsyncMock(return_value=payload)
    )

    assert result == payload


@pytest.mark.asyncio
async def test_prompt_text_result_remains_visible_to_status_after_active_registry_cleanup():
    payload = await task_runtime_api_service.get_task_status_payload_for_user(
        task_id="prompt-task",
        user_id=77,
        get_owned_active_task_func=AsyncMock(return_value=None),
        get_user_history_record_func=AsyncMock(return_value=None),
        get_owned_prompt_result_func=AsyncMock(
            return_value={
                "task_id": "prompt-task",
                "task_type": "prompt_optimize",
                "result_kind": "text",
                "result_text": "optimized prompt",
            }
        ),
    )

    assert payload == {
        "status": "success",
        "task_id": "prompt-task",
        "task_type": "prompt_optimize",
        "media_type": None,
    }
