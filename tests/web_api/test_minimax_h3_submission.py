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
