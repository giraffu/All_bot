from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.core.task_core_types import CoreDomainError
from src.web_api.core.security import create_access_token
from src.web_api.schemas.task_schema import TaskGenerateRequest
from src.web_api.routers import tasks as tasks_router
from src.web_api.services import task_submission_service as service
from tests.task_application_test_support import LegacyTaskApplicationAdapter


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
    monkeypatch.setattr(
        service,
        "get_task_application",
        lambda: LegacyTaskApplicationAdapter(submit),
    )

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
async def test_h3_ref2v_resolves_typed_character_references_before_submission(
    monkeypatch,
):
    monkeypatch.setenv("MINIMAX_H3_BACKEND_ENABLED", "true")
    monkeypatch.setenv("MINIMAX_H3_REF2V_ENABLED", "true")
    monkeypatch.setenv("CHARACTER_ASSETS_ENABLED", "true")
    monkeypatch.setenv("CHARACTER_EXPLICIT_VIEWS_ENABLED", "true")
    submit = AsyncMock(return_value={"task_id": "task-h3-ref", "cost": 15})
    monkeypatch.setattr(
        service,
        "get_task_application",
        lambda: LegacyTaskApplicationAdapter(submit),
    )

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    from src.database import core as db_core
    from src.web_api.services.reference_asset_service import ResolvedH3ReferenceSet

    monkeypatch.setattr(db_core, "AsyncSessionLocal", _Session)
    resolve = AsyncMock(
        return_value=ResolvedH3ReferenceSet(
            images=("character_references/123/alice/views/face.png", "staging/user-uploads/123/style.png"),
            descriptions=("Adult character Alice; front face identity reference.", "User-uploaded visual reference."),
        )
    )
    monkeypatch.setattr(
        "src.web_api.services.reference_asset_service.resolve_h3_reference_refs",
        resolve,
    )

    await service.submit_generation_task(
        req=TaskGenerateRequest(
            task_type="minimax_h3_ref2v",
            prompt="Alice walks toward the camera",
            inputs={
                "duration": 5,
                "resolution_preset": "preview",
                "aspect_ratio": "16:9",
                "reference_refs": [
                    {
                        "source": "private_character_view",
                        "character_id": "alice",
                        "view_type": "face_front",
                    },
                    {
                        "source": "upload",
                        "object_key": "staging/user-uploads/123/style.png",
                    },
                ],
            },
        ),
        current_user=_user(),
        get_balance=AsyncMock(return_value=85),
        promote_staged_inputs_func=AsyncMock(
            side_effect=lambda **kwargs: list(kwargs["input_refs"])
        ),
    )

    submitted = submit.await_args.kwargs["inputs"]
    assert submitted["images"] == list(resolve.return_value.images)
    assert submitted["reference_descriptions"] == list(resolve.return_value.descriptions)
    assert submitted["prompt"].startswith("Reference-to-target binding (mandatory):")
    assert (
        "The one and only person in the target video is the person from <Picture 1>"
        in submitted["prompt"]
    )
    assert submitted["prompt"].endswith("Alice walks toward the camera")
    assert "reference_refs" not in submitted


@pytest.mark.asyncio
@pytest.mark.parametrize("task_type", ["minimax_h3_i2v", "minimax_h3_flf2v"])
async def test_h3_frame_modes_reject_character_reference_refs(monkeypatch, task_type):
    monkeypatch.setenv("MINIMAX_H3_BACKEND_ENABLED", "true")
    with pytest.raises(CoreDomainError, match="仅支持参考图生视频"):
        await service.submit_generation_task(
            req=TaskGenerateRequest(
                task_type=task_type,
                prompt="scene",
                inputs={
                    "reference_refs": [
                        {
                            "source": "private_character_view",
                            "character_id": "alice",
                            "view_type": "face_front",
                        }
                    ]
                },
            ),
            current_user=_user(),
            get_balance=AsyncMock(return_value=100),
        )


@pytest.mark.asyncio
async def test_ltx_t2v_ic_resolves_ordered_msr_characters_server_side(monkeypatch):
    monkeypatch.setenv("LTX_T2V_BACKEND_ENABLED", "true")
    monkeypatch.setenv("LTX_T2V_MSR_ENABLED", "true")
    submit = AsyncMock(return_value={"task_id": "task-msr", "cost": 12})
    monkeypatch.setattr(
        service,
        "get_task_application",
        lambda: LegacyTaskApplicationAdapter(submit),
    )

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    from src.database import core as db_core
    from src.services.storage import storage
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
    monkeypatch.setattr(storage, "async_object_size", AsyncMock(return_value=2048))

    await service.submit_generation_task(
        req=TaskGenerateRequest(
            task_type="ltx_t2v_ic",
            prompt="图1与图2在客厅中交谈",
            inputs={
                "duration": 5,
                "resolution": "768x448",
                "character_ids": ["wang", "man"],
                "background_object_key": "web_uploads/123/bedroom.png",
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
    assert submitted["background_image"] == "web_uploads/123/bedroom.png"
    assert "character_ids" not in submitted
    assert "background_object_key" not in submitted
    assert [call.kwargs["character_id"] for call in resolve.await_args_list] == [
        "wang",
        "man",
    ]


@pytest.mark.asyncio
async def test_ltx_t2v_ic_msr_flag_defaults_closed(monkeypatch):
    monkeypatch.setenv("LTX_T2V_BACKEND_ENABLED", "true")
    monkeypatch.delenv("LTX_T2V_MSR_ENABLED", raising=False)

    with pytest.raises(CoreDomainError, match="MSR 双角色模式当前未开放"):
        await service.submit_generation_task(
            req=TaskGenerateRequest(
                task_type="ltx_t2v_ic",
                prompt="scene",
                inputs={
                    "duration": 5,
                    "resolution": "768x448",
                    "character_ids": ["wang", "man"],
                    "background_object_key": "web_uploads/123/bedroom.png",
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
        {"character_ids": ["wang", "man"], "sulphur_strength": 0.5},
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
    monkeypatch.setenv("LTX_T2V_MSR_ENABLED", "true")

    with pytest.raises(CoreDomainError, match="不得直接指定"):
        await service.submit_generation_task(
            req=TaskGenerateRequest(
                task_type="ltx_t2v_ic",
                prompt="scene",
                inputs={
                    "duration": 5,
                    "resolution": "768x448",
                    "character_ids": ["character-1", "character-2"],
                    "character_sheet": "bot-data/another-user/sheet.png",
                    "background_object_key": "web_uploads/123/bedroom.png",
                },
            ),
            current_user=_user(),
            get_balance=AsyncMock(return_value=100),
        )


@pytest.mark.asyncio
async def test_ltx_t2v_ic_maps_non_ready_character_to_domain_error(monkeypatch):
    monkeypatch.setenv("LTX_T2V_BACKEND_ENABLED", "true")
    monkeypatch.setenv("LTX_T2V_MSR_ENABLED", "true")

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    from src.database import core as db_core
    from src.services.storage import storage
    from src.web_api.services import character_reference_service

    monkeypatch.setattr(db_core, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(
        character_reference_service,
        "resolve_ready_character_sheet",
        AsyncMock(side_effect=HTTPException(status_code=400, detail="人物未就绪。")),
    )
    monkeypatch.setattr(storage, "async_object_size", AsyncMock(return_value=2048))

    with pytest.raises(CoreDomainError, match="人物未就绪"):
        await service.submit_generation_task(
            req=TaskGenerateRequest(
                task_type="ltx_t2v_ic",
                prompt="scene",
                inputs={
                    "duration": 5,
                    "resolution": "768x448",
                    "character_ids": ["character-1", "character-2"],
                    "background_object_key": "web_uploads/123/bedroom.png",
                },
            ),
            current_user=_user(),
            get_balance=AsyncMock(return_value=100),
        )
