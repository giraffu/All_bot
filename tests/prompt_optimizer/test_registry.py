import pytest

from src.prompt_optimizer.registry import (
    PromptOptimizerRegistryError,
    get_prompt_optimizer_capability,
    resolve_prompt_optimization,
)


def _media(*roles: str) -> list[dict[str, str]]:
    return [
        {"role": role, "object_key": f"web_uploads/7/{role}.png"}
        for role in roles
    ]


def test_capability_exposes_versioned_template_metadata_without_prompt_bodies():
    payload = get_prompt_optimizer_capability("ltx_video_v2")

    assert payload["cost"] == 1
    assert payload["media_contract"] == {
        "required": ["start_image"],
        "optional": ["end_image"],
    }
    assert [item["id"] for item in payload["templates"]] == [
        "ltx_scene_script_cinematic",
        "ltx_timestamp_motion",
    ]
    assert payload["templates"][0]["is_default"] is True
    assert all("system_template" not in item for item in payload["templates"])
    assert all("user_template" not in item for item in payload["templates"])


def test_resolver_selects_i2v_or_flf2v_profile_from_media_roles():
    i2v = resolve_prompt_optimization(
        target_task_type="ltx_video_v2",
        template_id="ltx_scene_script_cinematic",
        template_version=1,
        media=_media("start_image"),
        context={"duration_seconds": 5},
    )
    flf2v = resolve_prompt_optimization(
        target_task_type="ltx_video_v2",
        template_id="ltx_timestamp_motion",
        template_version=1,
        media=_media("start_image", "end_image"),
        context={"duration_seconds": 20},
    )

    assert i2v.profile.ref == "ltx_eros_v14_i2v@1"
    assert flf2v.profile.ref == "ltx_eros_v14_flf2v@1"
    assert i2v.template.content_hash
    assert flf2v.template.content_hash


@pytest.mark.parametrize(
    ("template_id", "version", "media", "context"),
    [
        ("missing", 1, _media("start_image"), {"duration_seconds": 5}),
        ("ltx_scene_script_cinematic", 99, _media("start_image"), {"duration_seconds": 5}),
        ("ltx_scene_script_cinematic", 1, _media("end_image"), {"duration_seconds": 5}),
        ("ltx_scene_script_cinematic", 1, _media("start_image", "portrait"), {"duration_seconds": 5}),
        ("ltx_scene_script_cinematic", 1, _media("start_image"), {"duration_seconds": 7}),
        (
            "ltx_scene_script_cinematic",
            1,
            _media("start_image"),
            {"duration_seconds": 5, "model": "override"},
        ),
    ],
)
def test_resolver_fails_closed_for_unknown_or_incompatible_contracts(
    template_id, version, media, context
):
    with pytest.raises(PromptOptimizerRegistryError):
        resolve_prompt_optimization(
            target_task_type="ltx_video_v2",
            template_id=template_id,
            template_version=version,
            media=media,
            context=context,
        )
