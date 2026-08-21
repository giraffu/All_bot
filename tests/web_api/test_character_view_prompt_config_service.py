from types import SimpleNamespace

import pytest

from src.web_api.services.character_view_prompt_config_service import (
    get_builtin_character_view_config,
    render_character_view_prompts,
    save_character_view_config,
    validate_character_view_config,
)


class FakeConfigDb:
    def __init__(self):
        self.row = None
        self.commits = 0

    async def get(self, _model, view_type):
        return self.row if self.row and self.row.view_type == view_type else None

    def add(self, row):
        self.row = row

    async def commit(self):
        self.commits += 1


def test_builtin_configs_expose_per_view_names_and_effective_tag_groups():
    face = get_builtin_character_view_config("face_front")
    front = get_builtin_character_view_config("body_front")
    explicit = get_builtin_character_view_config("genitals_front")

    assert face["display_name"] == "正脸图"
    assert face["tag_groups"] == ["skin_tone"]
    assert front["tag_groups"] == ["breast_size", "pubic_hair", "skin_tone"]
    assert explicit["tag_groups"] == ["pubic_hair", "skin_tone"]
    assert set(front["prompt_templates"]) == {"neutral", "female", "male"}


def test_render_uses_only_tags_enabled_for_each_view():
    profile = {
        "gender": "female",
        "breast_size": "large",
        "pubic_hair": "none",
        "skin_tone": "fair",
    }

    prompts = render_character_view_prompts(profile)

    assert "白皙肤色" in prompts["face_front"]
    assert "巨乳" not in prompts["face_front"]
    assert "巨乳" in prompts["body_front"]
    assert "无阴毛" in prompts["body_front"]
    assert "巨乳" not in prompts["genitals_front"]
    assert "无阴毛" in prompts["genitals_front"]


def test_config_validation_rejects_unknown_placeholders_and_tag_groups():
    config = get_builtin_character_view_config("body_front")
    with pytest.raises(ValueError, match="unknown prompt variables"):
        validate_character_view_config(
            view_type="body_front",
            display_name=config["display_name"],
            prompt_templates={**config["prompt_templates"], "female": "{unknown}"},
            tag_groups=config["tag_groups"],
            tag_options=config["tag_options"],
        )
    with pytest.raises(ValueError, match="unknown tag groups"):
        validate_character_view_config(
            view_type="body_front",
            display_name=config["display_name"],
            prompt_templates=config["prompt_templates"],
            tag_groups=["height"],
            tag_options=config["tag_options"],
        )


@pytest.mark.asyncio
async def test_admin_save_publishes_new_revision_and_custom_tag_fragments():
    db = FakeConfigDb()
    config = get_builtin_character_view_config("body_front")
    payload = SimpleNamespace(
        display_name="正面身份图",
        prompt_templates=config["prompt_templates"],
        tag_groups=["skin_tone"],
        tag_options={
            **config["tag_options"],
            "skin_tone": {
                **config["tag_options"]["skin_tone"],
                "fair": "自定义冷白肤色",
            },
        },
    )

    first = await save_character_view_config(
        db, view_type="body_front", payload=payload, updated_by="admin-a"
    )
    second = await save_character_view_config(
        db, view_type="body_front", payload=payload, updated_by="admin-b"
    )

    assert first["revision"] == 1
    assert second["revision"] == 2
    assert second["display_name"] == "正面身份图"
    assert second["config_source"] == "database"
    assert db.commits == 2
