from unittest.mock import AsyncMock

import pytest

from src.services import telegram_gallery_history_service


class _Session:
    def __init__(self):
        self.execute = AsyncMock()
        self.commit = AsyncMock()


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_mark_history_public_by_task_id_commits(monkeypatch):
    session = _Session()
    monkeypatch.setattr(
        telegram_gallery_history_service,
        "AsyncSessionLocal",
        lambda: _SessionContext(session),
    )

    await telegram_gallery_history_service.mark_history_public_by_task_id("task-1")

    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_history_rating_by_task_id_commits(monkeypatch):
    session = _Session()
    monkeypatch.setattr(
        telegram_gallery_history_service,
        "AsyncSessionLocal",
        lambda: _SessionContext(session),
    )

    await telegram_gallery_history_service.update_history_rating_by_task_id(
        "task-1",
        1,
    )

    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()
