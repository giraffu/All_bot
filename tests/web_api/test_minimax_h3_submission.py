from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.task_core_types import CoreDomainError
from src.web_api.schemas.task_schema import TaskGenerateRequest
from src.web_api.services import task_submission_service as service
from tests.task_application_test_support import LegacyTaskApplicationAdapter


@pytest.mark.asyncio
async def test_minimax_h3_backend_flag_defaults_closed(monkeypatch):
    monkeypatch.delenv("MINIMAX_H3_BACKEND_ENABLED", raising=False)
    with pytest.raises(CoreDomainError, match="当前未开放") as exc_info:
        await service.submit_generation_task(
            req=TaskGenerateRequest(task_type="minimax_h3_t2v", prompt="scene", inputs={"duration": 5}),
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
    )
    assert response.task_id == "h3-canary"
    submit.assert_awaited_once()
