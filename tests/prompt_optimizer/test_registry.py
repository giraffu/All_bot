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
            "version": 3,
            "label": "成人电影化提示词",
            "description": "默认增强成人 NSFW 动作、镜头与多人连续性",
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
        template_version=3,
        media=_media("start_image"),
        context={"duration_seconds": 5},
    )
    flf2v = resolve_prompt_optimization(
        target_task_type="ltx_video_v2",
        template_id="ltx_scene_script_cinematic",
        template_version=3,
        media=_media("start_image", "end_image"),
        context={"duration_seconds": 20},
    )

    assert i2v.profile.ref == "ltx_eros_v14_i2v@1"
    assert flf2v.profile.ref == "ltx_eros_v14_flf2v@1"
    assert i2v.template.content_hash
    assert flf2v.template.content_hash


def test_t2v_capabilities_and_profiles_use_v4_without_frame_semantics():
    pure_capability = get_prompt_optimizer_capability("ltx_t2v")
    ic_capability = get_prompt_optimizer_capability("ltx_t2v_ic")

    assert pure_capability["media_contract"] == {"required": [], "optional": []}
    assert ic_capability["media_contract"] == {
        "required": [
            "reference_character_1",
            "reference_character_2",
            "scene_background",
        ],
        "optional": [],
    }
    assert pure_capability["templates"][0]["version"] == 4
    pure = resolve_prompt_optimization(
        target_task_type="ltx_t2v",
        template_id="ltx_scene_script_cinematic",
        template_version=4,
        media=[],
        context={"duration_seconds": 10},
    )
    ic = resolve_prompt_optimization(
        target_task_type="ltx_t2v_ic",
        template_id="ltx_scene_script_cinematic",
        template_version=4,
        media=_media(
            "reference_character_1", "reference_character_2", "scene_background"
        ),
        context={"duration_seconds": 20},
    )
    assert pure.profile.ref == "ltx_eros_t2v@1"
    assert ic.profile.ref == "ltx_eros_t2v_ic_msr@1"

    template = get_template_by_ref("ltx_scene_script_cinematic@4")
    pure_system, pure_user = render_prompt_messages(
        profile=pure.profile,
        template=template,
        prompt="Two adults meet in a bedroom.",
        context={"duration_seconds": 10},
    )
    _, ic_user = render_prompt_messages(
        profile=ic.profile,
        template=template,
        prompt="They move toward each other.",
        context={"duration_seconds": 20},
    )
    assert "此任务是文生视频" in pure_system
    assert "Use the provided start image exactly as the first frame" not in pure_system
    assert "No reference images are provided" in pure_user
    assert "reference_character_1" in ic_user
    assert "scene_background" in ic_user
    assert "not video frames" in ic_user


def test_t2v_profiles_fail_closed_on_wrong_media_or_template_version():
    with pytest.raises(PromptOptimizerRegistryError):
        resolve_prompt_optimization(
            target_task_type="ltx_t2v",
            template_id="ltx_scene_script_cinematic",
            template_version=3,
            media=[],
            context={"duration_seconds": 5},
        )
    with pytest.raises(PromptOptimizerRegistryError):
        resolve_prompt_optimization(
            target_task_type="ltx_t2v_ic",
            template_id="ltx_scene_script_cinematic",
            template_version=4,
            media=_media("reference_character_1", "scene_background"),
            context={"duration_seconds": 5},
        )


def test_v3_template_preserves_approved_chinese_prompt_and_profile_frame_constraints():
    template = get_template_by_ref("ltx_scene_script_cinematic@3")
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

    assert i2v_system.startswith("你是一名专业的短篇电影化图生视频提示词编写专家。")
    assert "此任务默认用于成年人的 NSFW、色情和性爱图生视频。" in i2v_system
    assert "不要等待用户明确写出“露骨”“色情”或具体性行为。" in i2v_system
    assert "最终英文提示词通常保持为 4～8 个信息充分的句子。" in i2v_system
    assert "媒体角色：\nImage 1 is start_image and must be used exactly as the first frame." in i2v_user
    assert "end_image" not in i2v_user
    assert "Image 2 is end_image and must be used exactly as the final frame." in flf2v_user
    assert "She slowly turns toward the camera." in flf2v_user


@pytest.mark.parametrize(
    ("template_id", "version"),
    [
        ("ltx_scene_script_cinematic", 1),
        ("ltx_timestamp_motion", 1),
        ("ltx_scene_script_cinematic", 2),
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
        ("ltx_scene_script_cinematic", 3, _media("end_image"), {"duration_seconds": 5}),
        ("ltx_scene_script_cinematic", 3, _media("start_image", "portrait"), {"duration_seconds": 5}),
        ("ltx_scene_script_cinematic", 3, _media("start_image"), {"duration_seconds": 7}),
        (
            "ltx_scene_script_cinematic",
            3,
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


@pytest.mark.parametrize(
    ("target_task_type", "roles", "profile_ref"),
    [
        ("minimax_h3_t2v", (), "minimax_h3_t2v_prompt@4"),
        ("minimax_h3_i2v", ("start_image",), "minimax_h3_i2v_prompt@4"),
        (
            "minimax_h3_flf2v",
            ("start_image", "end_image"),
            "minimax_h3_flf2v_prompt@4",
        ),
    ],
)
def test_minimax_h3_profiles_share_official_base_prompt_template(
    target_task_type, roles, profile_ref
):
    capability = get_prompt_optimizer_capability(target_task_type)
    resolved = resolve_prompt_optimization(
        target_task_type=target_task_type,
        template_id="minimax_h3_10eros_naughtytimes",
        template_version=3,
        media=_media(*roles),
        context={"duration_seconds": 15},
    )

    assert resolved.profile.ref == profile_ref
    assert capability["templates"] == [
        {
            "id": "minimax_h3_10eros_naughtytimes",
            "version": 3,
            "label": "高级图生视频pro",
            "description": "MiniMax H3 官方结构与自动对白语言保留",
            "is_default": True,
        }
    ]


@pytest.mark.parametrize(
    ("target_task_type", "roles", "expected_alignment"),
    [
        ("minimax_h3_t2v", (), None),
        (
            "minimax_h3_i2v",
            ("start_image",),
            (
                "For the target video, at 0.00 seconds into the target video, "
                "<Picture 1> (from [Shot 1]) is fully referenced."
            ),
        ),
        (
            "minimax_h3_flf2v",
            ("start_image", "end_image"),
            (
                "Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; "
                "Picture 2 (from Shot N) aligns with the 10.00-second mark of the target video."
            ),
        ),
    ],
)
def test_minimax_h3_prompt_renders_official_three_fields_and_mode_alignment(
    target_task_type, roles, expected_alignment
):
    resolved = resolve_prompt_optimization(
        target_task_type=target_task_type,
        template_id="minimax_h3_10eros_naughtytimes",
        template_version=3,
        media=_media(*roles),
        context={"duration_seconds": 10},
    )
    system, user = render_prompt_messages(
        profile=resolved.profile,
        template=resolved.template,
        prompt="Keep the same adults and continue the action.",
        context=resolved.normalized_context,
    )

    assert "integrated_multimodal_description" in system
    assert "overall_soundscape" in system
    assert "non_diegetic_music" in system
    assert "strictly earlier than 10.00 seconds" in system
    assert "200-270 words" not in system
    assert "Begin the output with \"hmmotion" not in system
    assert "Do not output LoRA names or trigger tokens" in system
    if expected_alignment is None:
        assert "No images are attached" in user
        assert "For the target video, at 0.00 seconds" not in user
        assert "How the reference pictures align" not in user
    else:
        assert expected_alignment in user


@pytest.mark.parametrize(
    ("target", "roles", "duration"),
    [
        ("minimax_h3_t2v", ("start_image",), 5),
        ("minimax_h3_i2v", (), 10),
        ("minimax_h3_flf2v", ("end_image", "start_image"), 15),
        ("minimax_h3_i2v", ("start_image",), 7),
    ],
)
def test_minimax_h3_profiles_fail_closed_on_wrong_media_order_or_duration(
    target, roles, duration
):
    with pytest.raises(PromptOptimizerRegistryError):
        resolve_prompt_optimization(
            target_task_type=target,
            template_id="minimax_h3_10eros_naughtytimes",
            template_version=3,
            media=_media(*roles),
            context={"duration_seconds": duration},
        )


def test_minimax_h3_v1_prompt_assets_remain_readable_but_inactive():
    assert get_template_by_ref("minimax_h3_hmnsfw@1").active is False
    assert get_profile_by_ref("minimax_h3_i2v_prompt@1").active is False
    assert get_template_by_ref("minimax_h3_10eros_naughtytimes@1").active is False
    assert get_profile_by_ref("minimax_h3_i2v_prompt@2").active is False
    assert get_template_by_ref("minimax_h3_10eros_naughtytimes@2").active is False
    assert get_profile_by_ref("minimax_h3_i2v_prompt@3").active is False


def test_minimax_h3_current_template_injects_detected_dialogue_language_contract():
    resolved = resolve_prompt_optimization(
        target_task_type="minimax_h3_t2v",
        template_id="minimax_h3_10eros_naughtytimes",
        template_version=3,
        media=[],
        context={"duration_seconds": 10},
    )
    _system, user = render_prompt_messages(
        profile=resolved.profile,
        template=resolved.template,
        prompt='中文场景描述，女人 says: "Keep looking at me."',
        context=resolved.normalized_context,
    )

    assert resolved.profile.ref == "minimax_h3_t2v_prompt@4"
    assert "Server-detected dialogue language contract" in user
    assert "[English]" in user
    assert "Keep looking at me." in user
