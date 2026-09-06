from types import SimpleNamespace

import pytest

from src.prompt_optimizer.minimax_h3_prompt import (
    MINIMAX_H3_HMNSFW_TRANSLATION_ZH,
)
from src.web_api.services.prompt_optimizer_config_service import (
    get_default_config,
    get_scene_config_variables,
    save_config,
    serialize_config,
    validate_scene_config_templates,
)


class FakeConfigDb:
    def __init__(self):
        self.row = None
        self.commits = 0

    async def get(self, _model, scene_key):
        return self.row if self.row and self.row.scene_key == scene_key else None

    def add(self, row):
        self.row = row

    async def commit(self):
        self.commits += 1


def test_h3_admin_default_is_one_shared_english_runtime_config():
    config = get_default_config("minimax_h3")

    assert config["display_name"] == "高级图生视频pro"
    assert config["revision"] == 0
    assert config["template_ref"] == "minimax_h3_10eros_naughtytimes@6"
    assert config["config_source"] == "built-in"
    assert config["compatibility_status"] == "current"
    assert config["fallback_reason"] == "no_saved_config"
    assert config["stored_revision"] is None
    assert "{duration_seconds}" in config["system_template"]
    assert "{addon_rules}" not in config["user_template"]
    assert "integrated_multimodal_description" in config["system_template"]
    assert "overall_soundscape" in config["system_template"]
    assert "non_diegetic_music" in config["system_template"]
    assert "official H3 base prompt structure" in config["system_template"]
    assert "SERVER-DETECTED DIALOGUE LANGUAGE" in config["system_template"]
    assert "{dialogue_language_instructions}" in config["user_template"]
    assert MINIMAX_H3_HMNSFW_TRANSLATION_ZH not in config["system_template"]


def test_h3_legacy_saved_config_falls_forward_to_official_built_in_template():
    legacy = SimpleNamespace(
        scene_key="minimax_h3",
        display_name="legacy",
        description="legacy",
        system_template="old single paragraph system {duration_seconds}",
        user_template="{media_frame_instructions} {original_prompt}",
        revision=7,
        content_hash="legacy-hash",
        updated_by="admin",
    )

    config = serialize_config(legacy, "minimax_h3")

    assert config["revision"] == 0
    assert config["updated_by"] == "built-in"
    assert config["config_source"] == "built-in"
    assert config["compatibility_status"] == "fallback"
    assert config["fallback_reason"] == "incompatible_saved_config"
    assert config["stored_revision"] == 7
    assert "integrated_multimodal_description" in config["system_template"]


def test_h3_saved_official_config_without_dialogue_contract_falls_forward():
    old_official = SimpleNamespace(
        scene_key="minimax_h3",
        display_name="old official",
        description="old official",
        system_template=(
            "integrated_multimodal_description overall_soundscape "
            "non_diegetic_music {duration_seconds}"
        ),
        user_template="{media_frame_instructions} {original_prompt}",
        revision=8,
        content_hash="old-official-hash",
        updated_by="admin",
    )

    config = serialize_config(old_official, "minimax_h3")

    assert config["revision"] == 0
    assert config["compatibility_status"] == "fallback"
    assert config["stored_revision"] == 8
    assert "{dialogue_language_instructions}" in config["user_template"]


def test_h3_fixed_naughtytimes_saved_config_falls_forward_to_optional_addons():
    default = get_default_config("minimax_h3")
    fixed_naughty = SimpleNamespace(
        scene_key="minimax_h3",
        display_name="fixed NaughtyTimes",
        description="old fixed stack",
        system_template=default["system_template"].replace(
            "optional server-selected add-ons",
            "the fixed NaughtyTimes v2 add-on stack",
        ),
        user_template=default["user_template"],
        revision=9,
        content_hash="fixed-naughty-hash",
        updated_by="admin",
    )

    config = serialize_config(fixed_naughty, "minimax_h3")

    assert config["revision"] == 0
    assert config["config_source"] == "built-in"
    assert config["compatibility_status"] == "fallback"
    assert config["stored_revision"] == 9
    assert "optional server-selected add-ons" in config["system_template"]


def test_h3_current_saved_config_is_reported_as_database_source():
    default = get_default_config("minimax_h3")
    saved = SimpleNamespace(
        scene_key="minimax_h3",
        display_name=default["display_name"],
        description=default["description"],
        system_template=default["system_template"],
        user_template=default["user_template"],
        revision=4,
        content_hash="saved-hash",
        updated_by="admin",
    )

    config = serialize_config(saved, "minimax_h3")

    assert config["revision"] == 4
    assert config["config_source"] == "database"
    assert config["compatibility_status"] == "current"
    assert config["fallback_reason"] is None
    assert config["stored_revision"] == 4


def test_h3_admin_preview_uses_current_scene_variables_and_validation():
    default = get_default_config("minimax_h3")

    variables = validate_scene_config_templates(
        "minimax_h3",
        default["system_template"],
        default["user_template"],
    )

    assert variables == get_scene_config_variables("minimax_h3")
    assert "dialogue_language_instructions" in variables
    assert "addon_summary" not in variables

    with pytest.raises(ValueError, match="official three fields"):
        validate_scene_config_templates(
            "minimax_h3",
            "legacy {duration_seconds}",
            "{media_frame_instructions} {original_prompt}",
        )


@pytest.mark.asyncio
async def test_h3_admin_save_increments_revision_for_new_task_snapshots_only():
    db = FakeConfigDb()
    default = get_default_config("minimax_h3")
    payload = SimpleNamespace(
        display_name=default["display_name"],
        description=default["description"],
        system_template=default["system_template"],
        user_template=default["user_template"],
    )

    first = await save_config(
        db, scene_key="minimax_h3", payload=payload, updated_by="a"
    )
    second = await save_config(
        db, scene_key="minimax_h3", payload=payload, updated_by="b"
    )

    assert first["revision"] == 1
    assert second["revision"] == 2
    assert first["content_hash"] == second["content_hash"]
    assert db.commits == 2


@pytest.mark.asyncio
async def test_h3_admin_rejects_legacy_template_without_official_fields():
    db = FakeConfigDb()
    default = get_default_config("minimax_h3")
    payload = SimpleNamespace(
        display_name=default["display_name"],
        description=default["description"],
        system_template="old single paragraph system {duration_seconds}",
        user_template=default["user_template"],
    )

    with pytest.raises(ValueError, match="official three fields"):
        await save_config(
            db, scene_key="minimax_h3", payload=payload, updated_by="admin"
        )

    assert db.row is None
    assert db.commits == 0
