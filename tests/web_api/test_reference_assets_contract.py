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
    normalize_reference_inputs,
    resolve_reference_set,
)


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
