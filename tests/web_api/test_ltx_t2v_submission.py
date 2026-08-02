from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.core.task_core_types import CoreDomainError
from src.web_api.core.security import create_access_token
from src.web_api.schemas.task_schema import TaskGenerateRequest
from src.web_api.routers import tasks as tasks_router
from src.web_api.services import task_submission_service as service


def _user():
    return SimpleNamespace(id=123, username="tester")


def test_operator_canary_requires_dedicated_jwt_channel():
    canary_token = create_access_token(
        subject="123",
        pwd_ver=1,
        channel="runpod_canary",
    )
    user_token = create_access_token(
        subject="123",
        pwd_ver=1,
        channel="web",
    )

    assert tasks_router._is_operator_canary_authorized(canary_token) is True
    assert tasks_router._is_operator_canary_authorized(user_token) is False
    assert tasks_router._is_operator_canary_authorized(None) is False


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
async def test_ltx_t2v_operator_canary_bypasses_closed_user_flag(monkeypatch):
    monkeypatch.setenv("LTX_T2V_BACKEND_ENABLED", "false")
    submit = AsyncMock(return_value={"task_id": "task-canary", "cost": 12})
    monkeypatch.setattr(service, "process_and_submit_task", submit)

    response = await service.submit_generation_task(
        req=TaskGenerateRequest(
            task_type="ltx_t2v",
            prompt="a cinematic scene",
            inputs={"duration": 5, "resolution": "1280x704"},
        ),
        current_user=_user(),
        get_balance=AsyncMock(return_value=88),
        operator_canary_authorized=True,
    )

    assert response.task_id == "task-canary"
    submit.assert_awaited_once()


@pytest.mark.asyncio
async def test_ltx_t2v_ic_operator_canary_accepts_only_isolated_fixture(monkeypatch):
    monkeypatch.setenv("LTX_T2V_BACKEND_ENABLED", "false")
    submit = AsyncMock(return_value={"task_id": "task-canary", "cost": 12})
    monkeypatch.setattr(service, "process_and_submit_task", submit)

    await service.submit_generation_task(
        req=TaskGenerateRequest(
            task_type="ltx_t2v_ic",
            prompt="the same adult character walks through a room",
            inputs={
                "duration": 5,
                "resolution": "768x448",
                "character_sheet": (
                    "runpod-canary/ltx-t2v/20260727T032529Z/character_reference.png"
                ),
                "character_description": "an adult woman with short black hair",
            },
        ),
        current_user=_user(),
        get_balance=AsyncMock(return_value=88),
        operator_canary_authorized=True,
    )

    assert submit.await_args.kwargs["inputs"]["character_sheet"].startswith(
        "runpod-canary/ltx-t2v/"
    )

    with pytest.raises(CoreDomainError, match="隔离测试前缀"):
        await service.submit_generation_task(
            req=TaskGenerateRequest(
                task_type="ltx_t2v_ic",
                prompt="scene",
                inputs={
                    "duration": 5,
                    "resolution": "768x448",
                    "character_sheet": "web_uploads/another-user/private.png",
                },
            ),
            current_user=_user(),
            get_balance=AsyncMock(return_value=88),
            operator_canary_authorized=True,
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
    resolve = AsyncMock(
        return_value=SimpleNamespace(
            sheet_object_key="bot-data/private/owned-sheet.png",
            description="an adult woman with short black hair",
        )
    )
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
    assert submit.await_args.kwargs["inputs"]["character_description"] == (
        "an adult woman with short black hair"
    )
    resolve.assert_awaited_once()
    assert resolve.await_args.kwargs["user_id"] == 123
    assert resolve.await_args.kwargs["character_id"] == "character-1"


@pytest.mark.asyncio
async def test_ltx_t2v_ic_resolves_ordered_msr_characters_server_side(monkeypatch):
    monkeypatch.setenv("LTX_T2V_BACKEND_ENABLED", "true")
    monkeypatch.setenv("LTX_T2V_MSR_ENABLED", "true")
    submit = AsyncMock(return_value={"task_id": "task-msr", "cost": 12})
    monkeypatch.setattr(service, "process_and_submit_task", submit)

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    from src.database import core as db_core
    from src.web_api.services import character_reference_service

    monkeypatch.setattr(db_core, "AsyncSessionLocal", _Session)
    resolve = AsyncMock(
        side_effect=[
            SimpleNamespace(
                sheet_object_key="bot-data/private/wang-panel.png",
                description="adult woman Wang with a short black bob",
            ),
            SimpleNamespace(
                sheet_object_key="bot-data/private/man-panel.png",
                description="adult man with short brown hair",
            ),
        ]
    )
    monkeypatch.setattr(
        character_reference_service, "resolve_ready_character_sheet", resolve
    )

    await service.submit_generation_task(
        req=TaskGenerateRequest(
            task_type="ltx_t2v_ic",
            prompt="图1与图2在客厅中交谈",
            inputs={
                "duration": 5,
                "resolution": "768x448",
                "character_ids": ["wang", "man"],
                "sulphur_strength": 0.5,
            },
        ),
        current_user=_user(),
        get_balance=AsyncMock(return_value=88),
    )

    submitted = submit.await_args.kwargs["inputs"]
    assert submitted["character_sheets"] == [
        "bot-data/private/wang-panel.png",
        "bot-data/private/man-panel.png",
    ]
    assert submitted["character_descriptions"] == [
        "adult woman Wang with a short black bob",
        "adult man with short brown hair",
    ]
    assert "character_ids" not in submitted
    assert [call.kwargs["character_id"] for call in resolve.await_args_list] == [
        "wang",
        "man",
    ]


@pytest.mark.asyncio
async def test_ltx_t2v_ic_msr_flag_defaults_closed(monkeypatch):
    monkeypatch.setenv("LTX_T2V_BACKEND_ENABLED", "true")
    monkeypatch.delenv("LTX_T2V_MSR_ENABLED", raising=False)

    with pytest.raises(CoreDomainError, match="MSR 多人物模式当前未开放"):
        await service.submit_generation_task(
            req=TaskGenerateRequest(
                task_type="ltx_t2v_ic",
                prompt="scene",
                inputs={
                    "duration": 5,
                    "resolution": "768x448",
                    "character_ids": ["wang", "man"],
                    "sulphur_strength": 0.5,
                },
            ),
            current_user=_user(),
            get_balance=AsyncMock(return_value=100),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "inputs",
    [
        {"character_id": "wang", "character_ids": ["wang", "man"]},
        {"character_ids": ["wang", "wang"]},
        {"character_ids": ["wang", "man"], "character_sheets": ["private.png"]},
        {"character_ids": ["wang", "man"], "character_descriptions": ["private"]},
    ],
)
async def test_ltx_t2v_ic_rejects_unsafe_msr_selection(monkeypatch, inputs):
    monkeypatch.setenv("LTX_T2V_BACKEND_ENABLED", "true")
    monkeypatch.setenv("LTX_T2V_MSR_ENABLED", "true")

    with pytest.raises(CoreDomainError):
        await service.submit_generation_task(
            req=TaskGenerateRequest(
                task_type="ltx_t2v_ic",
                prompt="scene",
                inputs={"duration": 5, "resolution": "768x448", **inputs},
            ),
            current_user=_user(),
            get_balance=AsyncMock(return_value=100),
        )


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
