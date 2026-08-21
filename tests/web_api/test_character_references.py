from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import io

import pytest
from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError

from config import MINIO_BUCKET
from src.core.task_core import ConcurrencyLimitError
from src.core.task_core_types import SubmissionReconciliationPending
from src.web_api.schemas.character_schema import (
    CharacterBuildRequest,
    CharacterDraftCreateRequest,
    CharacterPromptProfile,
    CharacterViewUploadRequest,
)
from src.web_api.services import character_reference_service as service
from tests.task_application_test_support import LegacyTaskApplicationAdapter


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
    def __init__(self, results, get_value=None):
        self.results = iter(results)
        self.get_value = get_value
        self.added = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def execute(self, _statement):
        return _ScalarResult(next(self.results))

    def in_transaction(self):
        return True

    def add(self, value):
        self.added.append(value)

    async def get(self, _model, _identity):
        return self.get_value


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return None


def _user():
    return SimpleNamespace(id=123, username="tester")


def _png_bytes(color="white"):
    output = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(output, format="PNG")
    return output.getvalue()


def test_character_name_rejects_whitespace_only_values():
    with pytest.raises(ValidationError):
        CharacterBuildRequest(
            name="   ",
            description="adult woman with short black hair",
            source_object_key="staging/user-uploads/123/source.webp",
            prompt_profile={"gender": "female"},
            adult_confirmed=True,
            usage_rights_confirmed=True,
        )


@pytest.mark.parametrize("description", [None, "", "   "])
def test_character_description_is_required(description):
    payload = {
        "name": "Alice",
        "source_object_key": "staging/user-uploads/123/source.webp",
    }
    if description is not None:
        payload["description"] = description

    with pytest.raises(ValidationError):
        CharacterBuildRequest(**payload)


def test_character_view_catalog_exposes_six_optional_builtin_and_four_custom_slots():
    assert [item["type"] for item in service.CHARACTER_VIEW_CATALOG] == [
        "face_front",
        "body_front_nude",
        "body_front_clothed",
        "torso_front",
        "genitals_front",
        "pelvis_back",
        "custom_1",
        "custom_2",
        "custom_3",
        "custom_4",
    ]
    assert service.CHARACTER_GENERATABLE_VIEW_TYPES == (
        "face_front",
        "body_front_nude",
        "body_front_clothed",
    )
    assert service.CHARACTER_REQUIRED_VIEW_TYPES == ()
    for item in service.CHARACTER_VIEW_CATALOG[:3]:
        assert item["default_prompt"].strip()
    for item in service.CHARACTER_VIEW_CATALOG[3:]:
        assert item["default_prompt"] == ""


def test_character_draft_requires_one_initial_image_but_not_description_gender_or_confirmations():
    payload = CharacterDraftCreateRequest(
        name="Alice",
        initial_view_type="custom_1",
        initial_view_label="脚部",
        source_object_key="staging/user-uploads/123/source.webp",
    )
    assert payload.description is None
    assert payload.prompt_profile is None

    with pytest.raises(ValidationError, match="exactly one"):
        CharacterDraftCreateRequest(name="Alice", initial_view_type="face_front")
    with pytest.raises(ValidationError, match="exactly one"):
        CharacterDraftCreateRequest(
            name="Alice",
            initial_view_type="torso_front",
            source_object_key="staging/user-uploads/123/source.webp",
            template_id="template-1",
        )


def test_female_prompt_profile_composes_selected_anatomy_and_skin_tags():
    profile = CharacterPromptProfile(
        gender="female",
        breast_size="large",
        pubic_hair="full",
        skin_tone="asian_tan",
    )

    prompts = service.compose_character_view_prompts(profile.model_dump())

    assert "成年女性" in prompts["face_front"]
    assert "巨乳" in prompts["body_front_nude"]
    assert "浓密自然阴毛" in prompts["body_front_nude"]
    assert "亚洲晒黑肤色" in prompts["body_front_nude"]
    assert "巨乳" in prompts["body_front_clothed"]
    assert "浓密自然阴毛" not in prompts["body_front_clothed"]
    assert set(prompts) == {"face_front", "body_front_nude", "body_front_clothed"}


def test_male_prompt_profile_has_no_female_options_and_requires_visible_erect_anatomy():
    profile = CharacterPromptProfile(gender="male")

    prompts = service.compose_character_view_prompts(profile.model_dump())

    assert "成年男性" in prompts["face_front"]
    assert "成年男性" in prompts["body_front_nude"]
    assert "完全裸体" in prompts["body_front_nude"]
    assert "成年男性" in prompts["body_front_clothed"]
    assert set(prompts) == {"face_front", "body_front_nude", "body_front_clothed"}


def test_male_prompt_profile_rejects_female_only_tags():
    with pytest.raises(ValidationError):
        CharacterPromptProfile(gender="male", breast_size="large")


@pytest.mark.asyncio
async def test_character_list_upgrades_only_the_previous_default_black_prompt():
    config = service.CHARACTER_VIEW_BY_TYPE["face_front"]
    previous_default = config["default_prompt"].replace("纯白背景", "纯黑背景")
    character = SimpleNamespace(
        id="character-1",
        name="Alice",
        description="adult woman",
        status="draft",
        task_id="draft-1",
        source_object_key="bot-data/source.png",
        sheet_object_key=None,
        created_at=None,
        views=[
            SimpleNamespace(
                view_type="face_front",
                prompt=previous_default,
                status="ready",
                task_id=None,
                object_key=None,
            ),
            SimpleNamespace(
                view_type="body_front_nude",
                prompt="自定义保留纯黑背景",
                status="ready",
                task_id=None,
                object_key=None,
            ),
        ],
    )

    result = await service.list_characters(
        db=_Session([[character]]),
        user_id=123,
    )

    assert result[0]["views"][0]["prompt"] == config["default_prompt"]
    assert result[0]["views"][1]["prompt"] == "自定义保留纯黑背景"


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
    image = io.BytesIO()
    Image.new("RGB", (320, 640), "red").save(image, format="PNG")
    monkeypatch.setattr(
        service.storage,
        "get_file_bytes",
        MagicMock(return_value=image.getvalue()),
    )
    monkeypatch.setattr(
        service.storage,
        "upload_bytes",
        MagicMock(return_value="stored"),
    )

    result = await service.create_character_draft(
        db=db,
        current_user=_user(),
        payload=CharacterDraftCreateRequest(
            name="Alice",
            source_object_key="staging/user-uploads/123/source.webp",
            initial_view_type="custom_1",
            initial_view_label="脚部",
        ),
    )

    assert result["status"] == "ready"
    assert result["description"] is None
    assert result["views"][0]["type"] == "custom_1"
    assert result["views"][0]["label"] == "脚部"
    assert result["prompt_profile"] is None
    assert db.added[0].status == "ready"
    assert db.added[0].adult_confirmed_at is not None
    assert db.added[0].usage_rights_confirmed_at is not None
    assert db.added[0].sheet_object_key.endswith("/character-asset-mosaic-v1.png")
    assert db.added[1].view_type == "custom_1"
    assert db.added[1].display_name == "脚部"


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
        source_object_key=f"{MINIO_BUCKET}/staging/user-uploads/123/source.webp",
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
        view_type="body_front_nude",
        payload=CharacterViewGenerateRequest(
            prompt="custom side portrait",
            engine=engine,
        ),
    )

    assert result["cost"] == cost
    assert result["status"] == "pending"
    assert db.added[0].view_type == "body_front_nude"
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
            "view_type": "body_front_nude",
        },
        "record_history": False,
    }
    assert kwargs["allow_contribute_override"] is False


@pytest.mark.asyncio
async def test_local_detail_views_reject_prompt_generation_and_accept_multiple_admin_templates(
    monkeypatch,
):
    from src.web_api.schemas.character_schema import (
        CharacterViewGenerateRequest,
        CharacterViewTemplateApplyRequest,
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.generate_character_view(
            db=_Session([]),
            current_user=_user(),
            character_id="character-1",
            view_type="torso_front",
            payload=CharacterViewGenerateRequest(prompt="must not run"),
        )
    assert exc_info.value.status_code == 405

    character = SimpleNamespace(
        id="character-1",
        user_id=123,
        status="ready",
        prompt_profile=None,
    )
    template = SimpleNamespace(
        id="template-2",
        view_type="torso_front",
        status="active",
        object_key=f"{MINIO_BUCKET}/character_assets/view_templates/template-2.jpg",
    )
    db = _Session([character, None], get_value=template)
    monkeypatch.setattr(
        service.storage,
        "get_file_bytes",
        MagicMock(return_value=b"template-image"),
    )
    monkeypatch.setattr(
        service.storage,
        "upload_bytes",
        MagicMock(return_value="stored"),
    )
    monkeypatch.setattr(
        service,
        "_try_auto_materialize_character_sheet",
        AsyncMock(return_value=True),
    )

    result = await service.apply_character_view_template(
        db=db,
        current_user=_user(),
        character_id="character-1",
        view_type="torso_front",
        payload=CharacterViewTemplateApplyRequest(template_id="template-2"),
    )

    assert result["type"] == "torso_front"
    assert result["status"] == "ready"
    assert db.added[0].prompt == ""
    assert db.added[0].display_name == "胸部镜头"


@pytest.mark.asyncio
async def test_explicit_detail_kill_switch_filters_templates_and_rejects_upload(monkeypatch):
    monkeypatch.setattr(service, "character_explicit_views_enabled", lambda: False)
    monkeypatch.setattr(
        service,
        "list_character_view_templates",
        AsyncMock(return_value=[
            {"id": "torso", "view_type": "torso_front"},
            {"id": "front", "view_type": "genitals_front"},
            {"id": "back", "view_type": "pelvis_back"},
        ]),
    )

    templates = await service.list_available_character_view_templates(db=object())
    assert templates == [{"id": "torso", "view_type": "torso_front"}]
    with pytest.raises(HTTPException) as exc_info:
        await service.upload_character_view(
            db=_Session([]),
            current_user=_user(),
            character_id="character-1",
            view_type="pelvis_back",
            payload=CharacterViewUploadRequest(
                source_object_key="staging/user-uploads/123/rear.png"
            ),
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_generate_genitals_view_is_template_or_upload_only(
    monkeypatch,
):
    from src.web_api.schemas.character_schema import CharacterViewGenerateRequest

    character = SimpleNamespace(
        id="character-1",
        user_id=123,
        status="ready",
        source_object_key=f"{MINIO_BUCKET}/staging/user-uploads/123/source.webp",
        prompt_profile={"gender": "female"},
        adult_confirmed_at=object(),
        usage_rights_confirmed_at=object(),
    )
    body_front = SimpleNamespace(
        view_type="body_front",
        status="ready",
        object_key=f"{MINIO_BUCKET}/character_references/123/character-1/views/body-front.png",
    )
    db = _Session([character, None, body_front])
    submit = AsyncMock(
        return_value=SimpleNamespace(
            task_id="task-genitals-1",
            cost=3,
            status="pending",
            balance_remaining=97,
        )
    )
    monkeypatch.setattr(service, "submit_generation_task", submit)
    monkeypatch.setattr(service, "character_explicit_views_enabled", lambda: True)
    monkeypatch.setattr(
        service.storage, "async_object_exists", AsyncMock(return_value=True)
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.generate_character_view(
            db=db,
            current_user=_user(),
            character_id="character-1",
            view_type="genitals_front",
            payload=CharacterViewGenerateRequest(
                prompt="preserve the same synthetic adult character",
                engine="free_edit_v2_5",
            ),
        )
    assert exc_info.value.status_code == 405
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_genitals_view_rejection_does_not_depend_on_page_confirmation(monkeypatch):
    from src.web_api.schemas.character_schema import CharacterViewGenerateRequest

    character = SimpleNamespace(
        id="character-1",
        user_id=123,
        status="ready",
        prompt_profile={"gender": "female"},
        adult_confirmed_at=None,
        usage_rights_confirmed_at=None,
    )
    monkeypatch.setattr(service, "character_explicit_views_enabled", lambda: True)
    with pytest.raises(HTTPException, match="只支持选择模板或上传"):
        await service.generate_character_view(
            db=_Session([character, None]),
            current_user=_user(),
            character_id="character-1",
            view_type="genitals_front",
            payload=CharacterViewGenerateRequest(prompt="synthetic adult character"),
        )


@pytest.mark.asyncio
async def test_upload_character_view_persists_owned_image_as_ready_without_task(
    monkeypatch,
):
    character = SimpleNamespace(
        id="character-1",
        user_id=123,
        status="draft",
    )
    db = _Session([character, None, []])
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
            source_object_key="staging/user-uploads/123/front.png"
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
async def test_save_character_accepts_one_optional_view(monkeypatch):
    character = SimpleNamespace(
        id="character-1",
        user_id=123,
        status="draft",
        name="Alice",
        description=None,
        task_id=None,
        source_object_key="bot-data/source.png",
        sheet_object_key=None,
        updated_at=None,
        prompt_profile=None,
    )
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

    monkeypatch.setattr(service.storage, "get_file_bytes", MagicMock(return_value=_png_bytes()))
    monkeypatch.setattr(service.storage, "upload_bytes", MagicMock(return_value="stored"))
    result = await service.save_character(db=db, user_id=123, character_id="character-1")
    assert result["status"] == "ready"


@pytest.mark.asyncio
async def test_save_character_composes_ready_views_and_enters_library(monkeypatch):
    character = SimpleNamespace(
        id="character-1",
        user_id=123,
        name="Alice",
        description="adult woman with short black hair",
        status="draft",
        task_id="draft-1",
        source_object_key=f"{MINIO_BUCKET}/staging/user-uploads/123/source.webp",
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
            view_type="body_front_nude",
            prompt="body front",
            status="ready",
            task_id="view-2",
            object_key=f"{MINIO_BUCKET}/views/body-front.png",
        ),
        SimpleNamespace(
            view_type="body_front_clothed",
            prompt="body side",
            status="ready",
            task_id="view-3",
            object_key=f"{MINIO_BUCKET}/views/body-side.png",
        ),
        SimpleNamespace(
            view_type="torso_front",
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
        f"/character-1/{service.CHARACTER_ASSET_MOSAIC_VERSION}.png"
    )
    assert result["preview_url"].endswith(
        f"/character-1/{service.CHARACTER_ASSET_MOSAIC_VERSION}.png"
    )
    assert upload.call_count == 1
    with Image.open(io.BytesIO(upload.call_args.args[0])) as panel:
        assert panel.width <= 1536
        assert panel.height <= 1536


@pytest.mark.asyncio
async def test_ready_child_views_automatically_materialize_the_character_panel(monkeypatch):
    character = SimpleNamespace(
        id="character-auto",
        user_id=123,
        name="Alice",
        description="adult character",
        status="draft",
        task_id="draft-auto",
        source_object_key=f"{MINIO_BUCKET}/source.png",
        sheet_object_key=None,
        updated_at=None,
    )
    views = [
        SimpleNamespace(
            view_type=view_type,
            prompt=view_type,
            status="ready",
            task_id=f"task-{view_type}",
            object_key=f"{MINIO_BUCKET}/views/{view_type}.png",
        )
        for view_type in ("face_front",)
    ]
    db = _Session([views])
    monkeypatch.setattr(
        service,
        "_read_character_view_bytes",
        MagicMock(return_value=[(0, b"front")]),
    )
    monkeypatch.setattr(
        service,
        "_compose_character_sheet",
        MagicMock(return_value=b"panel"),
    )
    monkeypatch.setattr(
        service.storage,
        "upload_bytes",
        MagicMock(return_value="stored"),
    )

    materialized = await service._try_auto_materialize_character_sheet(
        db=db,
        character=character,
    )

    assert materialized is True
    assert character.status == "ready"
    assert character.sheet_object_key.endswith(
        f"/{service.CHARACTER_ASSET_MOSAIC_VERSION}.png"
    )
    assert db.commit.await_count == 1


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
    monkeypatch.setattr(
        service,
        "get_task_application",
        lambda: LegacyTaskApplicationAdapter(submit),
    )
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
            description="adult woman with short black hair",
            source_object_key="staging/user-uploads/123/source.webp",
            prompt_profile={"gender": "female"},
            adult_confirmed=True,
            usage_rights_confirmed=True,
        ),
    )

    assert result["cost"] == 18
    assert result["balance_remaining"] == 82
    assert db.added[0].status == "pending"
    assert db.added[0].adult_confirmed_at is not None
    assert db.added[0].usage_rights_confirmed_at is not None
    assert submit.await_args.kwargs["allow_contribute_override"] is False
    assert submit.await_args.kwargs["submission_before_dispatch_func"] is not None
    assert submit.await_args.kwargs["submission_should_compensate_func"] is not None
    assert submit.await_args.kwargs["inputs"]["images"] == [
        f"{MINIO_BUCKET}/staging/user-uploads/123/source.webp"
    ]
    assert submit.await_args.kwargs["inputs"]["record_history"] is False
    assert submit.await_args.kwargs["registry_metadata"]["record_history"] is False


@pytest.mark.asyncio
async def test_character_build_stays_pending_while_dispatch_reconciles(monkeypatch):
    db = _Session([0])
    monkeypatch.setattr(
        service.storage, "async_object_exists", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        service.storage, "async_object_size", AsyncMock(return_value=1024)
    )
    monkeypatch.setattr(
        service,
        "get_task_application",
        lambda: LegacyTaskApplicationAdapter(
            AsyncMock(
                side_effect=SubmissionReconciliationPending(
                    registry_task_id="task-reconciling",
                    cost=18,
                )
            )
        ),
    )
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
            description="adult woman with short black hair",
            source_object_key="staging/user-uploads/123/source.webp",
            prompt_profile={"gender": "female"},
            adult_confirmed=True,
            usage_rights_confirmed=True,
        ),
    )

    assert result["task_id"] == "task-reconciling"
    assert db.added[0].status == "pending"


@pytest.mark.asyncio
async def test_character_build_rejects_foreign_or_oversized_upload(monkeypatch):
    payload = CharacterBuildRequest(
        name="Alice",
        description="adult woman with short black hair",
        source_object_key="staging/user-uploads/999/source.png",
        prompt_profile={"gender": "female"},
        adult_confirmed=True,
        usage_rights_confirmed=True,
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
                description="adult woman with short black hair",
                source_object_key="staging/user-uploads/123/source.png",
                prompt_profile={"gender": "female"},
                adult_confirmed=True,
                usage_rights_confirmed=True,
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
                description="an adult woman with short black hair",
                sheet_object_key=(
                    "bot-data/private/ingredients-character-panel-v3.png"
                ),
            ),
        ]
    )
    ingredient = await service.resolve_ready_character_sheet(
        db=db,
        user_id=123,
        character_id="character-1",
    )
    assert ingredient.sheet_object_key == (
        "bot-data/private/ingredients-character-panel-v3.png"
    )
    assert ingredient.description == "an adult woman with short black hair"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_ready_character_resolution_rejects_obsolete_sheet_layout():
    row = SimpleNamespace(
        id="character-1",
        user_id=123,
        status="ready",
        sheet_object_key="bot-data/private/ingredients-character-panel-v2.png",
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
