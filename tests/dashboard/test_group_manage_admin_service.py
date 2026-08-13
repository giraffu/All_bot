import pytest

from dashboard.backend.schemas import GroupManageConfigRequest
from dashboard.backend.services import group_manage_admin_service as service


@pytest.mark.asyncio
async def test_group_manage_config_is_saved_to_its_own_path(monkeypatch, tmp_path):
    path = tmp_path / "group-manage.json"
    monkeypatch.setenv("GROUP_MANAGE_MODERATION_CONFIG_FILE", str(path))
    monkeypatch.setenv("GROUP_MANAGE_MODERATION_LOG_FILE", str(tmp_path / "events.jsonl"))

    response = await service.update_group_manage_config_payload(
        GroupManageConfigRequest(forbidden_words=["  spam ", "SPAM"], block_links=True)
    )

    assert response.forbidden_words == ["spam"]
    assert response.config_path == str(path)
    assert path.exists()
