import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.core.task_core_types import CoreDomainError
from src.prompt_optimizer.config_snapshot import snapshot_content_hash
from src.web_api.services.prompt_optimizer_config_service import (
    get_default_config,
    render_config_snapshot,
)
from src.web_api.services.reference_asset_service import (
    build_h3_character_reference_binding,
    normalize_reference_inputs,
    resolve_h3_reference_audio_ref,
    resolve_h3_reference_refs,
    resolve_reference_set,
)


@pytest.mark.asyncio
async def test_h3_gallery_reference_audio_is_scoped_to_current_template_post():
    loader = AsyncMock(return_value="task-inputs/source-task/3.m4a")
    object_size = AsyncMock(return_value=1024)

    result = await resolve_h3_reference_audio_ref(
        user_id=7,
        reference_audio_ref={"source": "gallery_post", "post_id": 29},
        source_post_id=29,
        is_template=True,
        gallery_reference_loader=loader,
        object_size=object_size,
    )

    assert result == "task-inputs/source-task/3.m4a"
    loader.assert_awaited_once_with(29)
    object_size.assert_awaited_once()


@pytest.mark.asyncio
async def test_h3_gallery_reference_audio_rejects_cross_post_reuse():
    with pytest.raises(CoreDomainError, match="当前一键应用投稿"):
        await resolve_h3_reference_audio_ref(
            user_id=7,
            reference_audio_ref={"source": "gallery_post", "post_id": 29},
            source_post_id=30,
            is_template=True,
            gallery_reference_loader=AsyncMock(return_value="task-inputs/source/3.m4a"),
            object_size=AsyncMock(return_value=1024),
        )


def test_h3_character_binding_groups_multiple_views_of_the_same_identity():
    binding = build_h3_character_reference_binding(
        [
            {
                "source": "private_character_view",
                "character_id": "alice",
                "view_type": "face_front",
            },
            {"source": "upload", "object_key": "staging/user-uploads/7/room.png"},
            {
                "source": "private_character_view",
                "character_id": "alice",
                "view_type": "body_front_clothed",
            },
        ]
    )

    assert (
        "<Picture 1> and <Picture 3> are different views of the same one target character"
        in binding
    )
    assert "Render exactly one instance of this character" in binding
    assert "<Picture 2>" not in binding
    assert "contact sheets, split screens, grids, panels" in binding


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Db:
    def __init__(self, values):
        self.values = iter(values)

    async def execute(self, _query):
        return _ScalarResult(next(self.values))


@pytest.mark.asyncio
async def test_h3_private_character_views_and_uploads_resolve_in_user_order():
    character = SimpleNamespace(
        id="character-1",
        name="Alice",
        description="adult woman with short black hair",
        status="ready",
        moderation_status="active",
        adult_confirmed_at=object(),
        usage_rights_confirmed_at=object(),
    )
    face = SimpleNamespace(
        view_type="face_front",
        status="ready",
        object_key="bot-data/character_references/7/character-1/views/face.png",
    )
    result = await resolve_h3_reference_refs(
        db=_Db([character, face]),
        user_id=7,
        reference_refs=[
            {
                "source": "private_character_view",
                "character_id": "character-1",
                "view_type": "face_front",
            },
            {
                "source": "upload",
                "object_key": "staging/user-uploads/7/style.webp",
            },
        ],
        object_size=AsyncMock(return_value=1024),
        explicit_views_enabled=True,
    )

    assert result.images == (
        "character_references/7/character-1/views/face.png",
        "staging/user-uploads/7/style.webp",
    )
    assert result.descriptions[0].startswith("Adult character Alice")
    assert "front face" in result.descriptions[0]
    assert "User-uploaded" in result.descriptions[1]


@pytest.mark.asyncio
async def test_h3_private_character_sheet_is_rejected_to_prevent_collage_leakage():
    character = SimpleNamespace(
        id="character-1",
        name="Detail-only character",
        description="Only lower-body details appear in the target video.",
        status="ready",
        moderation_status="active",
        sheet_object_key=(
            "bot-data/character_references/7/character-1/character-asset-mosaic-v1.png"
        ),
        views=[
            SimpleNamespace(
                view_type="genitals_front",
                display_name="正面细节",
                description="Use the visible shape and skin details.",
                status="ready",
                object_key="bot-data/views/front.png",
            ),
            SimpleNamespace(
                view_type="custom_1",
                display_name="脚部",
                description="Bare feet with red nail polish.",
                status="ready",
                object_key="bot-data/views/feet.png",
            ),
        ],
    )

    with pytest.raises(CoreDomainError, match="H3 参考图来源无效"):
        await resolve_h3_reference_refs(
            db=_Db([character]),
            user_id=7,
            reference_refs=[
                {"source": "private_character_sheet", "character_id": "character-1"}
            ],
            object_size=AsyncMock(return_value=4096),
            explicit_views_enabled=True,
        )


@pytest.mark.asyncio
async def test_h3_character_view_descriptions_do_not_bind_output_composition():
    character = SimpleNamespace(
        id="character-1",
        name="Alice",
        description="synthetic adult identity",
        status="ready",
        moderation_status="active",
        adult_confirmed_at=object(),
        usage_rights_confirmed_at=object(),
    )
    face = SimpleNamespace(
        view_type="face_front",
        status="ready",
        object_key="bot-data/face.png",
    )
    body = SimpleNamespace(
        view_type="body_front",
        status="ready",
        object_key="bot-data/body.png",
    )
    genitals = SimpleNamespace(
        view_type="genitals_front",
        status="ready",
        object_key="bot-data/genitals.png",
    )

    result = await resolve_h3_reference_refs(
        db=_Db(
            [
                character,
                face,
                character,
                body,
                character,
                genitals,
            ]
        ),
        user_id=7,
        reference_refs=[
            {
                "source": "private_character_view",
                "character_id": "character-1",
                "view_type": "face_front",
            },
            {
                "source": "private_character_view",
                "character_id": "character-1",
                "view_type": "body_front",
            },
            {
                "source": "private_character_view",
                "character_id": "character-1",
                "view_type": "genitals_front",
            },
        ],
        object_size=AsyncMock(return_value=1024),
        explicit_views_enabled=True,
    )

    assert "do not copy this close-up crop" in result.descriptions[0]
    assert "do not copy the reference pose" in result.descriptions[1]
    assert "Localized anatomy evidence only" in result.descriptions[2]
    assert (
        "never create an inset, overlay, split screen, or collage"
        in (result.descriptions[2])
    )


@pytest.mark.asyncio
async def test_h3_character_reference_does_not_require_page_confirmation_and_rejects_duplicates():
    unconfirmed = SimpleNamespace(
        status="ready",
        moderation_status="active",
        name="Alice",
        description=None,
        adult_confirmed_at=None,
        usage_rights_confirmed_at=None,
    )
    view = SimpleNamespace(
        status="ready",
        object_key="bot-data/views/face.png",
        description=None,
    )
    result = await resolve_h3_reference_refs(
        db=_Db([unconfirmed, view]),
        user_id=7,
        reference_refs=[
            {
                "source": "private_character_view",
                "character_id": "character-1",
                "view_type": "face_front",
            }
        ],
        object_size=AsyncMock(return_value=1024),
        explicit_views_enabled=True,
    )
    assert result.images == ("views/face.png",)

    duplicate = {
        "source": "upload",
        "object_key": "staging/user-uploads/7/same.png",
    }
    with pytest.raises(CoreDomainError, match="重复"):
        await resolve_h3_reference_refs(
            db=_Db([]),
            user_id=7,
            reference_refs=[duplicate, duplicate],
            object_size=AsyncMock(return_value=1024),
            explicit_views_enabled=True,
        )


def test_typed_references_require_two_unique_characters_and_one_environment():
    refs, environment = normalize_reference_inputs(
        {
            "character_refs": [
                {"source": "private", "id": "mine"},
                {"source": "official", "id": "official"},
            ],
            "environment_ref": {"source": "official", "id": "room"},
        }
    )
    assert refs == [
        {"source": "private", "id": "mine"},
        {"source": "official", "id": "official"},
    ]
    assert environment == {"source": "official", "id": "room"}
    with pytest.raises(CoreDomainError, match="不能重复"):
        normalize_reference_inputs(
            {
                "character_refs": [
                    {"source": "official", "id": "same"},
                    {"source": "official", "id": "same"},
                ],
                "environment_ref": {"source": "official", "id": "room"},
            }
        )


def test_legacy_references_are_normalized_without_changing_worker_contract():
    refs, environment = normalize_reference_inputs(
        {
            "character_ids": ["a", "b"],
            "background_object_key": "web_uploads/7/room.png",
        }
    )
    assert refs == [
        {"source": "private", "id": "a"},
        {"source": "private", "id": "b"},
    ]
    assert environment == {
        "source": "upload",
        "object_key": "web_uploads/7/room.png",
    }


def test_prompt_config_snapshot_is_rendered_and_fenced():
    config = get_default_config("ltx_t2v_ic")
    snapshot = render_config_snapshot(
        config=config,
        profile_ref="ltx_eros_t2v_ic_msr@1",
        variables={
            "duration_seconds": 5,
            "end_frame_clause": "",
            "media_frame_instructions": "three references",
            "original_prompt": "scene",
            "character_descriptions": "Character 1: A\nCharacter 2: B",
            "environment_description": "room",
        },
    )
    assert snapshot["scene_key"] == "ltx_t2v_ic"
    assert snapshot["snapshot_hash"] == snapshot_content_hash(snapshot)
    snapshot["user_message"] += "tampered"
    assert snapshot["snapshot_hash"] != snapshot_content_hash(snapshot)


@pytest.mark.asyncio
async def test_mixed_private_official_characters_and_official_environment_resolve_in_order(
    monkeypatch,
):
    monkeypatch.setattr(
        "src.web_api.services.character_reference_service.resolve_ready_character_sheet",
        AsyncMock(
            return_value=SimpleNamespace(
                sheet_object_key="private-panel.png", description="private adult"
            )
        ),
    )
    result = await resolve_reference_set(
        db=_Db(
            [
                SimpleNamespace(
                    sheet_object_key="official-panel.png", description="official adult"
                ),
                SimpleNamespace(
                    object_key="official-room.png", description="warm bedroom"
                ),
            ]
        ),
        user_id=7,
        character_refs=[
            {"source": "private", "id": "mine"},
            {"source": "official", "id": "shared"},
        ],
        environment_ref={"source": "official", "id": "room"},
    )
    assert result.character_sheets == ("private-panel.png", "official-panel.png")
    assert result.character_descriptions == ("private adult", "official adult")
    assert result.environment_object_key == "official-room.png"
    assert result.environment_description == "warm bedroom"
