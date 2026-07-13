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
