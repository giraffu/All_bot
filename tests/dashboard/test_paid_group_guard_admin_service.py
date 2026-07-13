import json
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from dashboard.backend.routers import paid_group_guard as router_module
from dashboard.backend.schemas import PaidGroupGuardConfigRequest
from dashboard.backend.services import paid_group_guard_admin_service as service


@pytest.mark.asyncio
async def test_get_paid_group_guard_config_returns_defaults_for_missing_file(
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "moderation.jsonl"
    monkeypatch.setenv("PAID_GROUP_MODERATION_CONFIG_FILE", str(config_path))
    monkeypatch.setenv("PAID_GROUP_MODERATION_LOG_FILE", str(log_path))

    response = await service.get_paid_group_guard_config_payload()

    assert response.enabled is True
    assert response.dry_run is False
    assert response.block_links is True
    assert response.allowed_domains == []
    assert response.forbidden_words == []
    assert response.exempt_user_ids == []
    assert response.config_path == str(config_path)
    assert response.log_path == str(log_path)


@pytest.mark.asyncio
async def test_update_paid_group_guard_config_normalizes_and_writes_file(
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "config.json"
    monkeypatch.setenv("PAID_GROUP_MODERATION_CONFIG_FILE", str(config_path))

    response = await service.update_paid_group_guard_config_payload(
        PaidGroupGuardConfigRequest(
            enabled=True,
            dry_run=False,
            block_links=True,
            allowed_domains=[
                " https://www.Aivison.it.com/path ",
                "aivison.it.com",
                "",
            ],
            forbidden_words=["  spam  ", "SPAM", ""],
            exempt_user_ids=[7, 7, -1, 0, 8],
        )
    )

    assert response.allowed_domains == ["aivison.it.com"]
    assert response.forbidden_words == ["spam"]
    assert response.exempt_user_ids == [7, 8]
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    assert raw["allowed_domains"] == ["aivison.it.com"]
    assert raw["exempt_user_ids"] == [7, 8]


@pytest.mark.asyncio
async def test_get_paid_group_guard_logs_filters_and_limits_page_size(
    tmp_path,
    monkeypatch,
):
    log_path = tmp_path / "moderation.jsonl"
    monkeypatch.setenv("PAID_GROUP_MODERATION_LOG_FILE", str(log_path))
    rows = [
        {
            "timestamp": "2026-06-21T10:00:00+08:00",
            "chat_id": -100,
            "message_id": 1,
            "user_id": 7,
            "username": "alice",
            "full_name": "Alice",
            "reason": "link",
            "matched_value": "https://spam.example",
            "text_snippet": "x",
            "action": "deleted",
            "error": None,
        },
        {
            "timestamp": "2026-06-22T10:00:00+08:00",
            "chat_id": -100,
            "message_id": 2,
            "user_id": 8,
            "username": "bob",
            "full_name": "Bob",
            "reason": "forbidden_word",
            "matched_value": "bad",
            "text_snippet": "bad",
            "action": "deleted",
            "error": None,
        },
    ]
    log_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )

    response = await service.get_paid_group_guard_logs_payload(
        reason="link",
        user_id=7,
        start_date="2026-06-21",
        end_date="2026-06-21",
        page=1,
        page_size=500,
    )

    assert response.total == 1
    assert response.page_size == 100
    assert response.items[0].user_id == 7
    assert response.items[0].reason == "link"


@pytest.mark.asyncio
async def test_paid_group_guard_router_routes_to_config_service(monkeypatch):
    expected = {
        "enabled": True,
        "dry_run": False,
        "block_links": True,
        "allowed_domains": [],
        "forbidden_words": [],
        "exempt_user_ids": [],
        "config_path": "/tmp/config.json",
        "log_path": "/tmp/log.jsonl",
    }
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(
        router_module,
        "get_paid_group_guard_config_payload",
        service_mock,
    )

    response = await router_module.get_paid_group_guard_config()

    assert response == expected
    service_mock.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_paid_group_guard_router_wraps_service_exception(monkeypatch):
    service_mock = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(
        router_module,
        "get_paid_group_guard_config_payload",
        service_mock,
    )

    with pytest.raises(HTTPException) as exc_info:
        await router_module.get_paid_group_guard_config()

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "boom"
