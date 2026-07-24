from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from config import MINIO_BUCKET
from src.web_api.schemas.character_schema import CharacterBuildRequest
from src.web_api.services import character_reference_service as service


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value


class _Session:
    def __init__(self, results):
        self.results = iter(results)
        self.added = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def execute(self, _statement):
        return _ScalarResult(next(self.results))

    def in_transaction(self):
        return True

    def add(self, value):
        self.added.append(value)


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return None


def _user():
    return SimpleNamespace(id=123, username="tester")


def test_character_name_rejects_whitespace_only_values():
    with pytest.raises(ValidationError):
        CharacterBuildRequest(
            name="   ", source_object_key="web_uploads/123/source.webp"
        )


@pytest.mark.asyncio
async def test_character_build_is_private_and_costs_eighteen(monkeypatch):
    db = _Session([0])
    submit = AsyncMock(return_value={"task_id": "task-1", "cost": 18})
    monkeypatch.setattr(
        service.storage, "async_object_exists", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        service.storage,
        "async_object_size",
        AsyncMock(return_value=20 * 1024 * 1024),
    )
    monkeypatch.setattr(service, "process_and_submit_task", submit)
    monkeypatch.setattr(
        service,
        "QuotaManager",
        lambda: SimpleNamespace(get_credits=AsyncMock(return_value=82)),
    )

    result = await service.build_character(
        db=db,
        current_user=_user(),
        payload=CharacterBuildRequest(
            name="Alice",
            source_object_key="web_uploads/123/source.webp",
        ),
    )

    assert result["cost"] == 18
    assert result["balance_remaining"] == 82
    assert db.added[0].status == "pending"
    assert submit.await_args.kwargs["allow_contribute_override"] is False
    assert submit.await_args.kwargs["inputs"]["images"] == [
        f"{MINIO_BUCKET}/web_uploads/123/source.webp"
    ]


@pytest.mark.asyncio
async def test_character_build_rejects_foreign_or_oversized_upload(monkeypatch):
    payload = CharacterBuildRequest(
        name="Alice",
        source_object_key="web_uploads/999/source.png",
    )
    with pytest.raises(HTTPException, match="当前用户"):
        await service.build_character(
            db=_Session([]), current_user=_user(), payload=payload
        )

    monkeypatch.setattr(
        service.storage, "async_object_exists", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        service.storage,
        "async_object_size",
        AsyncMock(return_value=20 * 1024 * 1024 + 1),
    )
    with pytest.raises(HTTPException) as exc_info:
        await service.build_character(
            db=_Session([]),
            current_user=_user(),
            payload=CharacterBuildRequest(
                name="Alice",
                source_object_key="web_uploads/123/source.png",
            ),
        )
    assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_ready_character_resolution_rejects_non_ready_and_returns_owned_sheet():
    with pytest.raises(HTTPException, match="未就绪"):
        await service.resolve_ready_character_sheet(
            db=_Session([SimpleNamespace(status="failed", sheet_object_key=None)]),
            user_id=123,
            character_id="character-1",
        )

    db = _Session(
        [SimpleNamespace(status="ready", sheet_object_key="bot-data/private/sheet.png")]
    )
    assert (
        await service.resolve_ready_character_sheet(
            db=db,
            user_id=123,
            character_id="character-1",
        )
        == "bot-data/private/sheet.png"
    )
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_character_finalizer_is_idempotent(monkeypatch):
    from src.database import core as database_core

    row = SimpleNamespace(status="pending", sheet_object_key=None, updated_at=None)
    db = _Session([row, row])
    monkeypatch.setattr(database_core, "AsyncSessionLocal", lambda: _SessionContext(db))

    await service.finalize_character_reference(
        task_id="task-1", status="done", result_path="bot-data/private/sheet.png"
    )
    await service.finalize_character_reference(
        task_id="task-1", status="done", result_path="other.png"
    )

    assert row.status == "ready"
    assert row.sheet_object_key == "bot-data/private/sheet.png"
    assert db.commit.await_count == 1
