from datetime import datetime, timezone

import pytest

from dashboard.backend.services.observer_notification_admin_service import (
    ObserverNotificationAdminService,
)


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class FakeConnection:
    def __init__(self):
        self.executed = []

    def transaction(self):
        return FakeTransaction()

    async def fetchrow(self, query, *_args):
        if "COUNT(*)" in query:
            return {"total": 1}
        return {
            "queue_alerts_enabled": True,
            "group_collection_enabled": True,
            "daily_reports_enabled": False,
            "weekly_reports_enabled": False,
            "monthly_reports_enabled": False,
        }

    async def fetch(self, query, *_args):
        if "observer_admin_recipients" in query:
            return [{"telegram_user_id": 42}]
        if "observer_authorized_chats" in query:
            return [{"chat_id": -1001}]
        if "observer_report_runs" in query:
            return [{"run_key": "daily:2026-08-29", "updated_at": datetime.now(timezone.utc)}]
        return []

    async def execute(self, query, *args):
        self.executed.append((query, args))

    async def executemany(self, query, args):
        self.executed.append((query, args))

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_settings_read_runtime_flags_and_allowlists():
    connection = FakeConnection()
    service = ObserverNotificationAdminService(
        "postgresql://observer/db", connect=lambda _url: _async_value(connection)
    )

    settings = await service.get_settings()

    assert settings["admin_telegram_user_ids"] == [42]
    assert settings["authorized_group_ids"] == [-1001]
    assert settings["queue_alerts_enabled"] is True


@pytest.mark.asyncio
async def test_settings_replace_recipients_groups_and_feature_flags_atomically():
    connection = FakeConnection()
    service = ObserverNotificationAdminService(
        "postgresql://observer/db", connect=lambda _url: _async_value(connection)
    )

    await service.update_settings(
        admin_telegram_user_ids=[42, 84],
        authorized_group_ids=[-1001],
        queue_alerts_enabled=False,
        group_collection_enabled=True,
        daily_reports_enabled=False,
        weekly_reports_enabled=False,
        monthly_reports_enabled=False,
    )

    statements = "\n".join(query for query, _args in connection.executed)
    assert "DELETE FROM observer_admin_recipients" in statements
    assert "INSERT INTO observer_authorized_chats" in statements
    assert "recipients_initialized = TRUE" in statements


async def _async_value(value):
    return value
