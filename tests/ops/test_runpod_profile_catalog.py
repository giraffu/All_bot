import pytest

from dashboard.backend.services.runpod_admin_commands import RUNPOD_PROFILE_OPTIONS
from ops.gpu_pool_controller import runpod_profile_catalog as catalog
from ops.gpu_pool_controller.providers import runpod as provider


def test_provider_reexports_profile_catalog_symbols_for_old_imports():
    assert provider.RUNPOD_TASK_PROFILES is catalog.RUNPOD_TASK_PROFILES
    assert provider.RUNPOD_PROD_AGENT_ID_PREFIX == catalog.RUNPOD_PROD_AGENT_ID_PREFIX
    assert provider.prod_agent_id_from_slot("03") == catalog.prod_agent_id_from_slot(
        "03"
    )
    assert (
        provider.prod_pod_name_from_agent_id(
            "runpod_prod_image_to_video_manual_02",
            profile="image_to_video",
        )
        == "allbot-runpod-prod-image-to-video-manual-02"
    )


@pytest.mark.parametrize(
    ("task_type", "profile"),
    [
        ("img2img", "img2img"),
        ("img2img_lora", "img2img"),
        ("image_to_video", "image_to_video"),
        ("wan22_video_v2", "wan22_video_v2"),
        ("i2i_pro", "i2i_pro"),
        ("t2i-pornmaster-turbo", "i2i_pro"),
        ("face_swap", "i2i_pro"),
        ("scail2", "scail2"),
        ("scail2_action_transfer", "scail2"),
        ("scail2_video_replacement", "scail2"),
        ("ltx_video", "ltx_video"),
        ("ltx_video_flf2v", "ltx_video"),
        ("ltx_video_v2v_audio", "ltx_video"),
    ],
)
def test_prod_worker_profile_for_task_type_matches_catalog(task_type, profile):
    assert catalog.prod_worker_profile_for_task_type(task_type) == profile


@pytest.mark.parametrize(
    ("profile", "agent_id", "pod_name"),
    [
        (
            "img2img",
            "runpod_prod_img2img_manual_01",
            "allbot-runpod-prod-img2img-manual-01",
        ),
        (
            "image_to_video",
            "runpod_prod_image_to_video_manual_01",
            "allbot-runpod-prod-image-to-video-manual-01",
        ),
        (
            "wan22_video_v2",
            "runpod_prod_wan22_video_v2_manual_01",
            "allbot-runpod-prod-wan22-video-v2-manual-01",
        ),
        (
            "i2i_pro",
            "runpod_prod_i2i_pro_manual_01",
            "allbot-runpod-prod-i2i-pro-manual-01",
        ),
        (
            "scail2",
            "runpod_prod_scail2_manual_01",
            "allbot-runpod-prod-scail2-manual-01",
        ),
        (
            "ltx_video",
            "runpod_prod_ltx_video_manual_01",
            "allbot-runpod-prod-ltx-video-manual-01",
        ),
    ],
)
def test_prod_agent_and_pod_names_are_profile_specific(profile, agent_id, pod_name):
    assert catalog.prod_agent_id_from_slot("01", profile=profile) == agent_id
    assert catalog.prod_slot_from_agent_id(agent_id, profile=profile) == "01"
    assert catalog.prod_pod_name_from_agent_id(agent_id, profile=profile) == pod_name


def test_dashboard_profile_options_are_sourced_from_catalog():
    assert RUNPOD_PROFILE_OPTIONS is catalog.RUNPOD_ADMIN_PROFILE_OPTIONS
    options = {
        str(option["profile"]): list(option["supported_task_types"])
        for option in catalog.RUNPOD_ADMIN_PROFILE_OPTIONS
    }
    assert options["img2img"] == ["img2img", "img2img_lora"]
    assert options["image_to_video"] == [
        "image_to_video",
        "video_insert",
        "video_edit",
    ]
    assert options["wan22_video_v2"] == ["wan22_video_v2"]
    assert options["i2i_pro"] == ["i2i_pro", "t2i-pornmaster-turbo", "face_swap"]
    assert options["scail2"] == [
        "scail2_action_transfer",
        "scail2_video_replacement",
    ]
    assert options["ltx_video"] == [
        "ltx_video",
        "ltx_video_flf2v",
        "ltx_video_v2v_audio",
    ]
