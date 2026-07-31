from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import io

import pytest
from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError

from config import MINIO_BUCKET
from src.core.task_core import ConcurrencyLimitError
from src.web_api.schemas.character_schema import (
    CharacterBuildRequest,
    CharacterViewUploadRequest,
)
from src.web_api.services import character_reference_service as service


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
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


def test_character_view_catalog_exposes_four_official_nude_character_targets():
    assert [item["type"] for item in service.CHARACTER_VIEW_CATALOG] == [
        "face_front",
        "body_front",
        "body_side",
        "body_back",
    ]
    assert len({item["default_prompt"] for item in service.CHARACTER_VIEW_CATALOG}) == 4
    assert all(
        item["default_prompt"].strip() for item in service.CHARACTER_VIEW_CATALOG
    )
    for item in service.CHARACTER_VIEW_CATALOG:
        prompt = item["default_prompt"]
        assert "同一位成年人" in prompt
        assert "完全裸体" in prompt
        assert "纯黑背景" in prompt
        assert not any("a" <= char.lower() <= "z" for char in prompt)


@pytest.mark.asyncio
async def test_character_draft_upload_creates_editable_workspace_without_charging(
    monkeypatch,
):
    db = _Session([0])
    monkeypatch.setattr(
        service.storage, "async_object_exists", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        service.storage,
        "async_object_size",
        AsyncMock(return_value=1024),
    )

    result = await service.create_character_draft(
        db=db,
        current_user=_user(),
        payload=CharacterBuildRequest(
            name="Alice",
            source_object_key="web_uploads/123/source.webp",
        ),
    )

    assert result["status"] == "draft"
    assert result["views"] == []
    assert db.added[0].status == "draft"
    assert db.added[0].sheet_object_key is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("engine", "task_type", "cost"),
    [
        ("free_edit", "edit", 2),
        ("free_edit_v2_5", "free_edit_v2_5", 3),
        ("free_edit_v3", "pornmaster_flux2_edit_bf16", 5),
    ],
)
async def test_generate_character_view_uses_the_selected_standard_free_edit_flow(
    monkeypatch,
    engine,
    task_type,
    cost,
):
    from src.web_api.schemas.character_schema import CharacterViewGenerateRequest

    character = SimpleNamespace(
        id="character-1",
        user_id=123,
        status="draft",
        source_object_key=f"{MINIO_BUCKET}/web_uploads/123/source.webp",
    )
    db = _Session([character, None])
    submit = AsyncMock(
        return_value=SimpleNamespace(
            task_id="task-view-1",
            cost=cost,
            status="pending",
            balance_remaining=100 - cost,
        )
    )
    monkeypatch.setattr(service, "submit_generation_task", submit)

    result = await service.generate_character_view(
        db=db,
        current_user=_user(),
        character_id="character-1",
        view_type="body_side",
        payload=CharacterViewGenerateRequest(
            prompt="custom side portrait",
            engine=engine,
        ),
    )

    assert result["cost"] == cost
    assert result["status"] == "pending"
    assert db.added[0].view_type == "body_side"
    kwargs = submit.await_args.kwargs
    assert kwargs["req"].task_type == task_type
    assert kwargs["req"].inputs == {
        "images": [character.source_object_key],
        "record_history": False,
    }
    assert kwargs["req"].prompt == "custom side portrait"
    assert kwargs["task_id_override"] == db.added[0].task_id
    assert kwargs["registry_metadata_extra"] == {
        "_character_reference_view": {
            "version": 1,
            "character_id": "character-1",
            "view_type": "body_side",
        },
        "record_history": False,
    }
    assert kwargs["allow_contribute_override"] is False


@pytest.mark.asyncio
async def test_upload_character_view_persists_owned_image_as_ready_without_task(
    monkeypatch,
):
    character = SimpleNamespace(
        id="character-1",
        user_id=123,
        status="draft",
    )
    db = _Session([character, None])
    monkeypatch.setattr(
        service.storage, "async_object_exists", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        service.storage, "async_object_size", AsyncMock(return_value=2048)
    )
    monkeypatch.setattr(
        service.storage, "get_file_bytes", MagicMock(return_value=b"uploaded-image")
    )
    upload = MagicMock(return_value="stored")
    monkeypatch.setattr(service.storage, "upload_bytes", upload)
    monkeypatch.setattr(
        service.storage,
        "get_presigned_url",
        lambda object_key, bucket=None: f"https://media/{object_key}",
    )

    result = await service.upload_character_view(
        db=db,
        current_user=_user(),
        character_id="character-1",
        view_type="face_front",
        payload=CharacterViewUploadRequest(
            source_object_key="web_uploads/123/front.png"
        ),
    )

    view = db.added[0]
    assert result["type"] == "face_front"
    assert result["status"] == "ready"
    assert view.task_id is None
    assert view.prompt == service.CHARACTER_VIEW_BY_TYPE["face_front"]["default_prompt"]
    assert view.object_key.startswith(
        f"{MINIO_BUCKET}/character_references/123/character-1/views/face_front-"
    )
    assert view.object_key.endswith(".png")
    upload.assert_called_once()
    assert upload.call_args.args[0] == b"uploaded-image"
    assert upload.call_args.args[2] == "image/png"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_character_batch_capacity_uses_identity_limit_and_live_lock_count():
    current_user = SimpleNamespace(
        id=123,
        username="tester",
        current_identity="内门弟子",
    )

    result = await service.get_character_batch_capacity(
        current_user=current_user,
        get_active_count_func=AsyncMock(return_value=3),
        get_identity_func=AsyncMock(return_value="内门弟子"),
    )

    assert result == {
        "limit": 5,
        "active": 3,
        "available": 2,
    }


@pytest.mark.asyncio
async def test_character_view_route_maps_concurrency_race_to_retryable_429(monkeypatch):
    from src.web_api.routers import characters as router
    from src.web_api.schemas.character_schema import CharacterViewGenerateRequest

    monkeypatch.setattr(
        router,
        "generate_character_view",
        AsyncMock(side_effect=ConcurrencyLimitError("已有 3 个任务正在处理中")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await router.create_character_view(
            character_id="character-1",
            view_type="body_back",
            payload=CharacterViewGenerateRequest(prompt="back view"),
            current_user=_user(),
            db=_Session([]),
        )

    assert exc_info.value.status_code == 429
    assert "正在处理中" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_save_character_requires_all_four_official_views(monkeypatch):
    character = SimpleNamespace(id="character-1", user_id=123, status="draft")
    db = _Session(
        [
            character,
            [
                SimpleNamespace(
                    view_type="face_front",
                    status="ready",
                    object_key="one.png",
                )
            ],
        ]
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.save_character(
            db=db,
            user_id=123,
            character_id="character-1",
        )

    assert exc_info.value.status_code == 409
    assert "完成全部 4 张" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_save_character_composes_ready_views_and_enters_library(monkeypatch):
    character = SimpleNamespace(
        id="character-1",
        user_id=123,
        name="Alice",
        description=None,
        status="draft",
        task_id="draft-1",
        source_object_key=f"{MINIO_BUCKET}/web_uploads/123/source.webp",
        sheet_object_key=None,
        updated_at=None,
    )
    views = [
        SimpleNamespace(
            view_type="face_front",
            prompt="front",
            status="ready",
            task_id="view-1",
            object_key=f"{MINIO_BUCKET}/views/front.png",
        ),
        SimpleNamespace(
            view_type="body_front",
            prompt="body front",
            status="ready",
            task_id="view-2",
            object_key=f"{MINIO_BUCKET}/views/body-front.png",
        ),
        SimpleNamespace(
            view_type="body_side",
            prompt="body side",
            status="ready",
            task_id="view-3",
            object_key=f"{MINIO_BUCKET}/views/body-side.png",
        ),
        SimpleNamespace(
            view_type="body_back",
            prompt="back",
            status="ready",
            task_id="view-4",
            object_key=f"{MINIO_BUCKET}/views/back.png",
        ),
    ]
    db = _Session([character, views])

    def _image_bytes(color):
        output = io.BytesIO()
        Image.new("RGB", (64, 64), color).save(output, format="PNG")
        return output.getvalue()

    colors = {
        "front.png": "red",
        "body-front.png": "green",
        "body-side.png": "blue",
        "back.png": "yellow",
    }
    monkeypatch.setattr(
        service.storage,
        "get_file_bytes",
        lambda object_key, bucket=None: _image_bytes(
            colors[object_key.rsplit("/", 1)[-1]]
        ),
    )
    upload = MagicMock()

    def _upload_bytes(data, object_key, content_type, bucket):
        upload(data, object_key, content_type, bucket)
        return object_key

    monkeypatch.setattr(service.storage, "upload_bytes", _upload_bytes)
    monkeypatch.setattr(
        service.storage,
        "get_presigned_url",
        lambda object_key, bucket=None: f"https://media/{object_key}",
    )

    result = await service.save_character(
        db=db,
        user_id=123,
        character_id="character-1",
    )

    assert result["status"] == "ready"
    assert result["sheet_object_key"].endswith(
        "/character-1/ingredients-character-panel-v2.png"
    )
    assert result["preview_url"].endswith(
        "/character-1/ingredients-character-panel-v2.png"
    )
    assert upload.call_count == 1
    with Image.open(io.BytesIO(upload.call_args.args[0])) as panel:
        assert panel.size == (1536, 896)
        assert panel.getpixel((288, 448)) == (255, 0, 0)
        assert panel.getpixel((736, 448)) == (0, 128, 0)
        assert panel.getpixel((1056, 448)) == (0, 0, 255)
        assert panel.getpixel((1376, 448)) == (255, 255, 0)


@pytest.mark.asyncio
async def test_character_view_finalizer_updates_only_matching_child(monkeypatch):
    from src.database import core as database_core

    view = SimpleNamespace(
        view_type="body_side",
        status="pending",
        object_key=None,
        updated_at=None,
    )
    db = _Session([view])
    monkeypatch.setattr(database_core, "AsyncSessionLocal", lambda: _SessionContext(db))

    await service.finalize_character_reference(
        task_id="task-view-1",
        status="done",
        result_path=f"{MINIO_BUCKET}/views/side.png",
    )

    assert view.status == "ready"
    assert view.object_key == f"{MINIO_BUCKET}/views/side.png"
    db.commit.assert_awaited_once()


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
        [
            SimpleNamespace(
                status="ready",
                sheet_object_key=(
                    "bot-data/private/ingredients-character-panel-v2.png"
                ),
            ),
        ]
    )
    assert (
        await service.resolve_ready_character_sheet(
            db=db,
            user_id=123,
            character_id="character-1",
        )
        == "bot-data/private/ingredients-character-panel-v2.png"
    )
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_ready_character_resolution_rejects_obsolete_sheet_layout():
    row = SimpleNamespace(
        id="character-1",
        user_id=123,
        status="ready",
        sheet_object_key="bot-data/private/sheet.png",
    )
    with pytest.raises(HTTPException, match="重新保存"):
        await service.resolve_ready_character_sheet(
            db=_Session([row]),
            user_id=123,
            character_id="character-1",
        )


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
