import pytest

from src.prompt_optimizer.registry import (
    PromptOptimizerRegistryError,
    get_profile_by_ref,
    get_prompt_optimizer_capability,
    get_template_by_ref,
    render_prompt_messages,
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
    assert payload["templates"] == [
        {
            "id": "ltx_scene_script_cinematic",
            "version": 2,
            "label": "图生视频场景提示词",
            "description": "自然、电影化且从首帧连续演进的表演与动作",
            "is_default": True,
        }
    ]
    assert payload["templates"][0]["is_default"] is True
    assert all("system_template" not in item for item in payload["templates"])
    assert all("user_template" not in item for item in payload["templates"])


def test_resolver_selects_i2v_or_flf2v_profile_from_media_roles():
    i2v = resolve_prompt_optimization(
        target_task_type="ltx_video_v2",
        template_id="ltx_scene_script_cinematic",
        template_version=2,
        media=_media("start_image"),
        context={"duration_seconds": 5},
    )
    flf2v = resolve_prompt_optimization(
        target_task_type="ltx_video_v2",
        template_id="ltx_scene_script_cinematic",
        template_version=2,
        media=_media("start_image", "end_image"),
        context={"duration_seconds": 20},
    )

    assert i2v.profile.ref == "ltx_eros_v14_i2v@1"
    assert flf2v.profile.ref == "ltx_eros_v14_flf2v@1"
    assert i2v.template.content_hash
    assert flf2v.template.content_hash


def test_v2_template_preserves_supplied_prompt_and_profile_frame_constraints():
    template = get_template_by_ref("ltx_scene_script_cinematic@2")
    i2v_profile = get_profile_by_ref("ltx_eros_v14_i2v@1")
    flf2v_profile = get_profile_by_ref("ltx_eros_v14_flf2v@1")

    i2v_system, i2v_user = render_prompt_messages(
        profile=i2v_profile,
        template=template,
        prompt="She slowly turns toward the camera.",
        context={"duration_seconds": 5},
    )
    _, flf2v_user = render_prompt_messages(
        profile=flf2v_profile,
        template=template,
        prompt="She slowly turns toward the camera.",
        context={"duration_seconds": 5},
    )

    assert i2v_system.startswith(
        "You are an expert at creating short cinematic video prompts from a single attached reference image."
    )
    assert "Use the provided start image exactly as the first frame." in i2v_system
    assert "Keep the entire response to 4-8 sentences maximum." in i2v_system
    assert "Image 1 is start_image and must be used exactly as the first frame." in i2v_user
    assert "end_image" not in i2v_user
    assert "Image 2 is end_image and must be used exactly as the final frame." in flf2v_user
    assert "She slowly turns toward the camera." in flf2v_user


@pytest.mark.parametrize(
    ("template_id", "version"),
    [
        ("ltx_scene_script_cinematic", 1),
        ("ltx_timestamp_motion", 1),
    ],
)
def test_inactive_legacy_templates_are_rejected_for_new_submissions(template_id, version):
    with pytest.raises(PromptOptimizerRegistryError):
        resolve_prompt_optimization(
            target_task_type="ltx_video_v2",
            template_id=template_id,
            template_version=version,
            media=_media("start_image"),
            context={"duration_seconds": 5},
        )


@pytest.mark.parametrize(
    ("template_id", "version", "media", "context"),
    [
        ("missing", 1, _media("start_image"), {"duration_seconds": 5}),
        ("ltx_scene_script_cinematic", 99, _media("start_image"), {"duration_seconds": 5}),
        ("ltx_scene_script_cinematic", 2, _media("end_image"), {"duration_seconds": 5}),
        ("ltx_scene_script_cinematic", 2, _media("start_image", "portrait"), {"duration_seconds": 5}),
        ("ltx_scene_script_cinematic", 2, _media("start_image"), {"duration_seconds": 7}),
        (
            "ltx_scene_script_cinematic",
            2,
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
