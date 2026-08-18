from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from dashboard.backend.routers import reference_assets


@pytest.mark.asyncio
async def test_official_asset_submission_uses_typed_task_application(monkeypatch):
    application = SimpleNamespace(
        submit=AsyncMock(
            return_value={
                "task_id": "official-task-1",
                "registry_task_id": "official-task-1",
                "cost": 0,
            }
        )
    )
    monkeypatch.setenv("DASHBOARD_OFFICIAL_ASSET_OPERATOR_USER_ID", "42")
    monkeypatch.setattr(
        reference_assets,
        "get_task_application",
        lambda: application,
    )
    monkeypatch.setattr(reference_assets.uuid, "uuid4", lambda: "official-task-1")

    result = await reference_assets._submit_operator_task(
        task_type="free_edit_v2_5",
        inputs={"images": ["source.png"]},
        prompt="front view",
        marker={"kind": "character_view", "asset_id": "character-1"},
    )

    assert result == {"task_id": "official-task-1", "status": "pending", "cost": 0}
    command, policy = application.submit.await_args.args
    assert command.internal_user_id == 42
    assert command.registry_metadata == {
        "record_history": False,
        "_official_asset": {"kind": "character_view", "asset_id": "character-1"},
    }
    assert policy.client_type == "dashboard:official-assets"
    assert policy.deduct_quota is False
    assert policy.check_lock is False
    assert policy.side_effect_plan.attach_web_monitor is True
