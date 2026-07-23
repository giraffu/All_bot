from src.domain_config.worker_pool_registry import (
    get_worker_pool_profile,
    iter_worker_pool_profiles,
)


def test_worker_pool_registry_groups_execution_types_by_shared_capacity():
    profiles = {
        profile.name: set(profile.supported_task_types)
        for profile in iter_worker_pool_profiles()
    }

    assert profiles == {
        "img2img": {"img2img", "img2img_lora"},
        "image_to_video": {"image_to_video"},
        "wan22_video_v2": {"wan22_video_v2"},
        "i2i_pro": {"i2i_pro", "t2i-pornmaster-turbo", "face_swap_v2"},
        "scail2": {
            "scail2_action_transfer",
            "scail2_action_transfer_long",
            "scail2_video_replacement",
            "scail2_face_swap_v2",
        },
        "ltx_video": {"ltx_video", "ltx_video_flf2v", "ltx_video_v2v_audio"},
        "ltx_t2v": {"ltx_t2v", "ltx_t2v_ic"},
        "pornmaster_flux2_edit_bf16": {
            "pornmaster_flux2_edit_bf16",
            "pornmaster_flux2_multi_edit_bf16",
        },
    }


def test_worker_pool_registry_normalizes_public_and_legacy_task_types():
    expected_profiles = {
        "image": "img2img",
        "video_insert": "image_to_video",
        "txt2img": "i2i_pro",
        "face_swap_v2": "i2i_pro",
        "free_edit_v2_5": "pornmaster_flux2_edit_bf16",
        "scail2_action_transfer_long": "scail2",
    }

    assert {
        task_type: get_worker_pool_profile(task_type).name
        for task_type in expected_profiles
    } == expected_profiles


def test_worker_pool_registry_returns_none_for_unmanaged_task_type():
    assert get_worker_pool_profile("unknown_legacy_task") is None
    assert get_worker_pool_profile("face_swap") is None
    assert get_worker_pool_profile("pornmaster_flux2_single_edit") is None
    assert get_worker_pool_profile("character_reference_build") is None
