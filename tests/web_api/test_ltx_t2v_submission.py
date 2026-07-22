from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.core.task_core_types import CoreDomainError
from src.web_api.schemas.task_schema import TaskGenerateRequest
from src.web_api.services import task_submission_service as service


def _user():
    return SimpleNamespace(id=123, username="tester")


@pytest.mark.asyncio
async def test_ltx_t2v_backend_flag_defaults_closed(monkeypatch):
    monkeypatch.delenv("LTX_T2V_BACKEND_ENABLED", raising=False)

    with pytest.raises(CoreDomainError, match="当前未开放"):
        await service.submit_generation_task(
            req=TaskGenerateRequest(
                task_type="ltx_t2v",
                prompt="a cinematic scene",
                inputs={"duration": 5, "resolution": "1280x704"},
            ),
            current_user=_user(),
            get_balance=AsyncMock(return_value=100),
        )


@pytest.mark.asyncio
async def test_ltx_t2v_ic_resolves_character_server_side(monkeypatch):
    monkeypatch.setenv("LTX_T2V_BACKEND_ENABLED", "true")
    submit = AsyncMock(return_value={"task_id": "task-1", "cost": 12})
    monkeypatch.setattr(service, "process_and_submit_task", submit)

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    from src.database import core as db_core
    from src.web_api.services import character_reference_service

    monkeypatch.setattr(db_core, "AsyncSessionLocal", _Session)
    resolve = AsyncMock(return_value="bot-data/private/owned-sheet.png")
    monkeypatch.setattr(
        character_reference_service, "resolve_ready_character_sheet", resolve
    )

    response = await service.submit_generation_task(
        req=TaskGenerateRequest(
            task_type="ltx_t2v_ic",
            prompt="the same adult character walks through a room",
            inputs={
                "duration": 5,
                "resolution": "768x448",
                "character_id": "character-1",
            },
        ),
        current_user=_user(),
        get_balance=AsyncMock(return_value=88),
    )

    assert response.cost == 12
    assert submit.await_args.kwargs["inputs"]["character_sheet"] == (
        "bot-data/private/owned-sheet.png"
    )
    resolve.assert_awaited_once()
    assert resolve.await_args.kwargs["user_id"] == 123
    assert resolve.await_args.kwargs["character_id"] == "character-1"


@pytest.mark.asyncio
async def test_ltx_t2v_ic_rejects_client_storage_path(monkeypatch):
    monkeypatch.setenv("LTX_T2V_BACKEND_ENABLED", "true")

    with pytest.raises(CoreDomainError, match="不得直接指定"):
        await service.submit_generation_task(
            req=TaskGenerateRequest(
                task_type="ltx_t2v_ic",
                prompt="scene",
                inputs={
                    "duration": 5,
                    "resolution": "768x448",
                    "character_id": "character-1",
                    "character_sheet": "bot-data/another-user/sheet.png",
                },
            ),
            current_user=_user(),
            get_balance=AsyncMock(return_value=100),
        )


@pytest.mark.asyncio
async def test_ltx_t2v_ic_maps_non_ready_character_to_domain_error(monkeypatch):
    monkeypatch.setenv("LTX_T2V_BACKEND_ENABLED", "true")

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    from src.database import core as db_core
    from src.web_api.services import character_reference_service

    monkeypatch.setattr(db_core, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(
        character_reference_service,
        "resolve_ready_character_sheet",
        AsyncMock(side_effect=HTTPException(status_code=400, detail="人物未就绪。")),
    )

    with pytest.raises(CoreDomainError, match="人物未就绪"):
        await service.submit_generation_task(
            req=TaskGenerateRequest(
                task_type="ltx_t2v_ic",
                prompt="scene",
                inputs={
                    "duration": 5,
                    "resolution": "768x448",
                    "character_id": "character-1",
                },
            ),
            current_user=_user(),
            get_balance=AsyncMock(return_value=100),
        )
