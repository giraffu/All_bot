import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from ops.gpu_pool_controller.config_loader import load_controller_config
from ops.gpu_pool_controller.lan_aio_prod import (
    LanAioProdOps,
    MANAGED_MUTATION_ACTIONS,
    _release_profile_for_slot,
    _release_target_ref,
    assert_prod_compose,
    load_lan_aio_prod_slots,
    main as lan_aio_main,
    patch_baked_runpod_worker,
    runtime_env_content,
)
from ops.gpu_pool_controller.runpod_profile_catalog import (
    RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES,
)
from ops.gpu_pool_controller.runtime import (
    LAN_AIO_LTX_UNIFIED_WORKFLOW_OVERRIDES,
    LAN_AIO_MINIMAX_H3_WORKFLOW_OVERRIDES,
    LAN_AIO_SCAIL2_WORKFLOW_OVERRIDES,
    RuntimePlanner,
    RuntimeRenderOverrides,
)

SCAIL2_BAKED_LAN_IMAGE = (
    "192.168.1.115:5000/allbot/comfy-runpod-scail2"
    "@sha256:858ac45522f33189e16e6ad41c0080b785c6bb87808d890d8f9899e0ed9b7607"
)


def test_release_target_ref_allows_exact_trusted_lan_mirror():
    target = "192.168.1.115:5000/allbot/wan@sha256:" + "1" * 64
    assert _release_target_ref(
        current_repository="ghcr.io/giraffu/wan",
        target_ref=target,
        digest="sha256:" + "1" * 64,
    ) == target


def test_release_target_ref_rewrites_untrusted_repository_to_current():
    assert _release_target_ref(
        current_repository="192.168.1.115:5000/allbot/wan",
        target_ref="ghcr.io/giraffu/wan@sha256:" + "1" * 64,
        digest="sha256:" + "1" * 64,
    ) == "192.168.1.115:5000/allbot/wan@sha256:" + "1" * 64

LAN_ALL_TASK_TYPES = (
    "img2img",
    "img2img_lora",
    "image_to_video",
    "wan22_video_v2",
    "pornmaster_flux2_edit_bf16",
    "pornmaster_flux2_multi_edit_bf16",
    "scail2_action_transfer",
    "scail2_action_transfer_long",
    "scail2_video_replacement",
    "scail2_face_swap_v2",
    "ltx_video",
    "ltx_video_flf2v",
    "ltx_video_v2v_audio",
    "i2i_pro",
    "t2i-pornmaster-turbo",
    "face_swap_v2",
    "face_swap",
    "ltx_t2v",
    "ltx_t2v_ic",
)
LTX_UNIFIED_TASK_TYPES = (
    "ltx_video",
    "ltx_video_flf2v",
    "ltx_video_v2v_audio",
    "ltx_t2v",
    "ltx_t2v_ic",
)
MINIMAX_H3_TASK_TYPES = (
    "minimax_h3_t2v",
    "minimax_h3_i2v",
    "minimax_h3_flf2v",
    "minimax_h3_ref2v",
)
SCAIL2_FLEX_PREFERRED_TASK_TYPES = (
    "scail2_action_transfer",
    "scail2_action_transfer_long",
    "scail2_video_replacement",
    "scail2_face_swap_v2",
)
SCAIL2_FLEX_TASK_TYPES = (
    *SCAIL2_FLEX_PREFERRED_TASK_TYPES,
    "img2img",
    "img2img_lora",
)


@pytest.mark.parametrize(
    ("slot_profile", "release_profile"),
    [
        ("img2img_lora", "img2img"),
        ("all", "lan_all"),
        ("ltx_unified", "ltx_unified"),
    ],
)
def test_lan_release_profile_mapping(slot_profile, release_profile):
    assert _release_profile_for_slot(slot_profile) == release_profile


def test_gpu002_scail2_flex_renders_preferred_queue_without_fallback_prefetch():
    config = load_controller_config()
    profile = config.profiles["scail2_flex"]
    slots = load_lan_aio_prod_slots(include_disabled=True)
    slot = slots["gpu-002-gpu0-scail2_flex"]

    assert profile.task_types == SCAIL2_FLEX_TASK_TYPES
    assert profile.preferred_task_types == SCAIL2_FLEX_PREFERRED_TASK_TYPES
    assert profile.reset_comfy_memory_before_task is True
    assert profile.model_manifest_keys == (
        "scail2/2026-06-17-test/manifest.json",
        "img2img_lora/2026-06-10/manifest.json",
    )
    assert profile.image_ref == (
        "192.168.1.115:5000/allbot/allbot-gpu-lan-scail2-flex"
        "@sha256:7ed80ca5f2934c682ad2baaf83d56af3325ca92f00215a94cf6dcc0fc4a64552"
    )
    assert profile.all_in_one_image_ref == profile.image_ref
    assert profile.lan_workspace_key == "scail2-flex-7ed80ca5f293"
    assert slot.enabled is True
    assert slot.phase == "catalog_ready"
    assert slot.retargetable is True
    assert slot.remote_dir == (
        "/home/chuzeyu/allbot-scail2-aio-prod/gpu002-gpu0-scail2-flex"
    )
    assert slot.target_task_types == SCAIL2_FLEX_TASK_TYPES
    assert slot.legacy_worker_id == "lan_aio_prod_gpu002_gpu0_scail2_01"
    assert slot.old_runtime_container == (
        "allbot-lan-aio-gpu-002-gpu0-scail2-prod"
    )

    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    compose = yaml.safe_load(ops.render_compose(slot))
    environment = compose["services"][slot.container_name]["environment"]

    assert environment["SUPPORTED_TASK_TYPES"] == ",".join(SCAIL2_FLEX_TASK_TYPES)
    assert environment["PREFERRED_TASK_TYPES"] == ",".join(
        SCAIL2_FLEX_PREFERRED_TASK_TYPES
    )
    assert environment["PIPELINE_TASK_TYPES"] == ",".join(SCAIL2_FLEX_TASK_TYPES)
    assert environment["PREFETCH_TASK_TYPES"] == ",".join(
        SCAIL2_FLEX_PREFERRED_TASK_TYPES
    )
    assert environment["PREFETCH_RESERVE_TASK"] == "true"
    assert environment["RESET_COMFY_MEMORY_BEFORE_TASK"] == "true"
    assert environment["POOL_RUNTIME_PROFILE"] == "scail2_flex"
    assert (
        environment["PIPELINE_PROFILE_POLICY"]
        == "media_claim2_comfy1_delivery1_v1"
    )
    assert json.loads(environment["RUNPOD_MODEL_MANIFEST_KEYS"]) == list(
        profile.model_manifest_keys
    )


def test_existing_profiles_do_not_gain_preferred_queue_environment():
    slots = load_lan_aio_prod_slots(include_disabled=True)
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = slots["gpu-002-gpu0-scail2"]
    compose = yaml.safe_load(ops.render_compose(slot))
    environment = compose["services"][slot.container_name]["environment"]

    assert "PREFERRED_TASK_TYPES" not in environment
    assert environment["PREFETCH_TASK_TYPES"] == environment["SUPPORTED_TASK_TYPES"]


def test_profile_rejects_preferred_task_type_outside_supported_set(tmp_path):
    config_root = tmp_path / "config"
    shutil.copytree("ops/gpu_pool_controller/config", config_root)
    profiles_path = config_root / "task_profiles.yml"
    document = yaml.safe_load(profiles_path.read_text(encoding="utf-8"))
    document["profiles"]["scail2"]["preferred_task_types"] = [
        "scail2_action_transfer",
        "img2img",
    ]
    profiles_path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="preferred_task_types must be a subset of task_types",
    ):
        load_controller_config(config_root)


def test_gpu177_ltx_unified_candidate_renders_five_types_and_shared_model_dir():
    config = load_controller_config()
    profile = config.profiles["ltx_unified"]
    rollback_profile = config.profiles["ltx_video"]
    slots = load_lan_aio_prod_slots(include_disabled=True)
    slot = slots["gpu-177-gpu1-ltx_unified"]

    assert profile.task_types == LTX_UNIFIED_TASK_TYPES
    assert profile.lan_model_workspace_key == "ltx_video"
    assert profile.model_manifest_key == (
        "ltx_unified/2026-08-03-10eros-v14-runexx-msr/manifest.json"
    )
    assert profile.min_vram_gb == 24
    assert profile.all_in_one_image_ref == (
        "192.168.1.115:5000/allbot/allbot-gpu-ltx-unified"
        "@sha256:6672adc60eb78c4fbd5966dbdf91161e3d91b0d26223714557ffb4bd11b64202"
    )
    assert rollback_profile.all_in_one_image_ref == (
        "192.168.1.115:5000/allbot/comfy-runpod-ltx-video"
        "@sha256:e291d068ca5d0264209ba452427a55bb4fb62c95ddc1b7b657c1e7246834b4cc"
    )
    assert slot.target_task_types == LTX_UNIFIED_TASK_TYPES
    assert slot.agent_id == "lan_aio_prod_gpu177_gpu1_ltx_unified_01"
    assert slot.host_port == 8191

    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    compose = yaml.safe_load(ops.render_compose(slot))
    service = compose["services"][slot.container_name]
    environment = service["environment"]
    assert environment["SUPPORTED_TASK_TYPES"] == ",".join(
        LTX_UNIFIED_TASK_TYPES
    )
    assert environment["TASK_TYPE_WORKFLOW_OVERRIDES"] == (
        LAN_AIO_LTX_UNIFIED_WORKFLOW_OVERRIDES
    )
    assert environment["PIPELINE_MAX_RUNNING_TASKS"] == "1"
    assert "--reserve-vram 5" in environment["COMFY_EXTRA_ARGS"]
    assert "--use-pytorch-cross-attention" in environment["COMFY_EXTRA_ARGS"]
    model_mount = next(
        mount
        for mount in service["volumes"]
        if mount.endswith(":/opt/ComfyUI/models")
    )
    assert "/profiles/ltx_video/workspace/ComfyUI/models:" in model_mount


def test_gpu177_minimax_h3_candidate_renders_four_public_types_and_isolated_model_dir():
    config = load_controller_config()
    profile = config.profiles["minimax_h3"]
    slots = load_lan_aio_prod_slots(include_disabled=True)
    slot = slots["gpu-177-gpu1-minimax_h3"]

    assert profile.task_types == MINIMAX_H3_TASK_TYPES
    assert profile.lan_workspace_key == "minimax-h3-23841ed32ad7"
    assert profile.lan_model_workspace_key == "minimax_h3"
    assert profile.model_bundles == ("minimax_h3_runtime",)
    assert profile.model_manifest_key == (
        "minimax_h3/2026-08-26-10eros-v3-official-int8-h3-addon17/manifest.json"
    )
    assert profile.min_vram_gb == 32
    assert profile.all_in_one_image_ref == (
        "192.168.1.115:5000/allbot/allbot-gpu-minimax-h3@sha256:"
        "9825c263837b4baa3a1f205c54c1b3c501c50328ab41288eadaf11dd389c76cf"
    )
    # Stable catalog v2 normalizes non-blocked candidates to explicit-operator
    # eligible catalog entries; this does not enable public task intake.
    assert slot.enabled is True
    assert slot.phase == "catalog_ready"
    assert slot.retargetable is True
    assert slot.target_task_types == MINIMAX_H3_TASK_TYPES
    assert slot.agent_id == "lan_aio_prod_gpu177_gpu1_minimax_h3_01"
    assert slot.host_port == 8191
    assert slot.legacy_worker_id == "lan_aio_prod_gpu177_gpu1_ltx_unified_01"
    assert slot.old_runtime_container == "allbot-lan-aio-gpu-177-gpu1-ltx_unified-prod"
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    compose = yaml.safe_load(ops.render_compose(slot))
    service = compose["services"][slot.container_name]
    environment = service["environment"]
    assert environment["SUPPORTED_TASK_TYPES"] == ",".join(MINIMAX_H3_TASK_TYPES)
    assert environment["COMFYUI_DIR"] == "/opt/ComfyUI"
    assert environment["RUNPOD_MODEL_TARGET_DIR"] == "/opt/ComfyUI/models"
    assert environment["RESET_COMFY_MEMORY_BEFORE_TASK"] == "true"
    assert "--disable-dynamic-vram" not in environment["COMFY_EXTRA_ARGS"]
    assert "--cache-none" in environment["COMFY_EXTRA_ARGS"]
    assert "--fast-disk" in environment["COMFY_EXTRA_ARGS"]
    assert "--disable-pinned-memory" in environment["COMFY_EXTRA_ARGS"]
    assert environment["TASK_TYPE_WORKFLOW_OVERRIDES"] == (
        LAN_AIO_MINIMAX_H3_WORKFLOW_OVERRIDES
    )
    model_mount = next(
        mount
        for mount in service["volumes"]
        if mount.endswith(":/opt/ComfyUI/models")
    )
    assert "/profiles/minimax_h3/workspace/ComfyUI/models:" in model_mount


def test_gpu177_minimax_h3_test_candidate_targets_only_cloud_test():
    config = load_controller_config()
    slots = load_lan_aio_prod_slots(include_disabled=True)
    slot = slots["gpu-177-gpu1-minimax_h3_test"]

    assert slot.environment == "cloud-test"
    assert slot.agent_id == "lan_aio_test_gpu177_gpu1_minimax_h3_01"
    assert slot.target_task_types == MINIMAX_H3_TASK_TYPES[:-1]
    assert slot.legacy_worker_id == "lan_aio_prod_gpu177_gpu1_ltx_unified_01"
    assert slot.old_runtime_container == (
        "allbot-lan-aio-gpu-177-gpu1-ltx_unified-prod"
    )

    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-test.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    compose = yaml.safe_load(ops.render_compose(slot))
    environment = compose["services"][slot.container_name]["environment"]
    assert environment["RUNPOD_ENVIRONMENT"] == "cloud-test"
    assert environment["CENTRAL_API_URL"] == "https://worker-central-test.aivison.it.com"
    assert environment["MINIO_RESULT_BUCKET"] == "user-data-test"

    current = slots["gpu-177-gpu1-ltx_unified"]
    assert ops.retarget_slot(slot, current.id) == slot


def test_cloud_test_slot_uses_separate_agent_token_without_leaking_prod_token():
    values = {
        "LAN_AIO_AGENT_SECRET_TOKEN": "prod-token",
        "LAN_AIO_TEST_AGENT_SECRET_TOKEN": "test-token",
        "LAN_AIO_MINIO_ENDPOINT": "storage",
        "LAN_AIO_MINIO_ACCESS_KEY": "access",
        "LAN_AIO_MINIO_SECRET_KEY": "secret",
        "LAN_MODEL_CACHE_ACCESS_KEY": "model-access",
        "LAN_MODEL_CACHE_SECRET_KEY": "model-secret",
    }

    content = runtime_env_content(values, agent_token="test-token")

    assert "LAN_AIO_AGENT_SECRET_TOKEN=test-token" in content
    assert "prod-token" not in content


def test_lan_aio_prod_slots_cover_next_wave_candidates():
    slots = load_lan_aio_prod_slots()

    assert "gpu-177-gpu0-wan22_video_v2" in slots
    assert "gpu-177-gpu0-image_to_video" in slots
    assert "gpu-252-gpu0-i2i_pro" in slots
    assert "gpu-252-gpu0-image_to_video" in slots
    assert "gpu-002-gpu0-scail2" in slots
    assert "gpu-002-gpu1-i2i_pro" in slots
    assert "gpu-226-gpu0-pornmaster_flux2_edit_bf16" in slots
    assert "gpu-226-gpu0-all" in slots
    assert "gpu-177-gpu1-wan22_video_v2" not in slots
    assert "gpu-252-gpu1-scail2" not in slots
    assert all(slot.phase == "catalog_ready" for slot in slots.values())
    assert all(slot.enabled and slot.retargetable for slot in slots.values())
    assert slots["gpu-177-gpu0-wan22_video_v2"].legacy_worker_id == (
        "lan_aio_prod_gpu177_gpu0_image_to_video_01"
    )
    assert slots["gpu-177-gpu0-wan22_video_v2"].target_profile_id == "wan22_video_v2"
    assert slots["gpu-177-gpu0-wan22_video_v2"].target_task_types == ("wan22_video_v2",)
    assert slots["gpu-252-gpu0-i2i_pro"].agent_id == (
        "lan_aio_prod_gpu252_gpu0_i2i_pro_01"
    )
    assert slots["gpu-252-gpu0-i2i_pro"].target_task_types == (
        "i2i_pro",
        "t2i-pornmaster-turbo",
        "face_swap_v2",
        "face_swap",
    )
    assert (
        slots["gpu-252-gpu0-i2i_pro"].gpu_device_id
        == "GPU-09b7ea85-23df-a9b8-19d9-703534e47666"
    )
    assert slots["gpu-252-gpu1-i2i_pro"].agent_id == (
        "lan_aio_prod_gpu252_gpu1_i2i_pro_01"
    )
    assert slots["gpu-252-gpu1-i2i_pro"].target_task_types == (
        "i2i_pro",
        "t2i-pornmaster-turbo",
        "face_swap_v2",
        "face_swap",
    )
    assert (
        slots["gpu-252-gpu1-i2i_pro"].gpu_device_id
        == "GPU-3ac886ce-23af-8c9a-4509-3577e5e1fac6"
    )
    assert slots["gpu-002-gpu0-scail2"].agent_id == (
        "lan_aio_prod_gpu002_gpu0_scail2_01"
    )
    assert slots["gpu-002-gpu0-scail2"].target_task_types == (
        "scail2_action_transfer",
        "scail2_action_transfer_long",
        "scail2_video_replacement",
        "scail2_face_swap_v2",
    )
    assert slots["gpu-002-gpu1-i2i_pro"].agent_id == (
        "lan_aio_prod_gpu002_gpu1_i2i_pro_01"
    )
    assert slots["gpu-002-gpu1-i2i_pro"].legacy_worker_id == (
        "lan_aio_prod_gpu002_gpu1_image_to_video_01"
    )
    assert slots["gpu-002-gpu1-i2i_pro"].old_runtime_container == (
        "allbot-lan-aio-gpu-002-gpu1-image_to_video-prod"
    )
    assert slots["gpu-002-gpu1-i2i_pro"].target_task_types == (
        "i2i_pro",
        "t2i-pornmaster-turbo",
        "face_swap_v2",
        "face_swap",
    )
    assert slots["gpu-226-gpu0-i2i_pro"].agent_id == (
        "lan_aio_prod_gpu226_gpu0_i2i_pro_01"
    )
    assert slots["gpu-226-gpu0-all"].target_task_types == LAN_ALL_TASK_TYPES


def test_gpu226_all_profile_is_lan_only_and_renders_multi_manifest_pipeline():
    import yaml

    config = load_controller_config()
    profile = config.profiles["all"]
    assert profile.task_types == LAN_ALL_TASK_TYPES
    assert len(profile.model_manifest_keys) == 6
    assert (
        "ltx_unified/2026-08-03-10eros-v14-runexx-msr/manifest.json"
        in profile.model_manifest_keys
    )
    assert "ltx_video/2026-06-10/manifest.json" not in profile.model_manifest_keys
    assert "ltx_t2v/2026-07-22/manifest.json" not in profile.model_manifest_keys
    assert "ltx_unified_runtime" in profile.model_bundles
    assert "ltx_video_baseline" not in profile.model_bundles
    assert "ltx_t2v_runtime" not in profile.model_bundles
    assert profile.all_in_one_image_ref == (
        "192.168.1.115:5000/allbot/allbot-gpu-lan-all@sha256:"
        "c6756b3ab6981b37058f8e2fe2ef59c556f326872ab1ad75dd9d7a1398b21d33"
    )
    assert ":pending" not in profile.image_ref

    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-226-gpu0-all"]
    compose = yaml.safe_load(ops.render_compose(slot))
    service = compose["services"][slot.container_name]
    environment = service["environment"]
    expected_types = ",".join(LAN_ALL_TASK_TYPES)

    assert environment["SUPPORTED_TASK_TYPES"] == expected_types
    assert environment["PREFETCH_TASK_TYPES"] == expected_types
    assert environment["PIPELINE_TASK_TYPES"] == expected_types
    assert environment["PIPELINE_MAX_RUNNING_TASKS"] == "1"
    assert environment["PIPELINE_MAX_CLAIMED_TASKS"] == "2"
    assert "--disable-dynamic-vram" not in environment["COMFY_EXTRA_ARGS"]
    assert "--reserve-vram" not in environment["COMFY_EXTRA_ARGS"]
    assert json.loads(environment["RUNPOD_MODEL_MANIFEST_KEYS"]) == list(
        profile.model_manifest_keys
    )
    assert environment["POOL_RUNTIME_PROFILE"] == "all"
    workflow_overrides = json.loads(
        environment["TASK_TYPE_WORKFLOW_OVERRIDES"]
    )
    assert workflow_overrides["ltx_video"] == "LTX 2.3 I2V 10Eros LoRA.json"
    assert (
        workflow_overrides["ltx_video_flf2v"]
        == "LTX 2.3 FLF2V 10Eros LoRA.json"
    )
    assert (
        workflow_overrides["ltx_video_v2v_audio"]
        == "LTX 2.3 V2V Audio 10Eros LoRA.json"
    )
    assert (
        "/home/ubantu/allbot-runpod-runtime/slots/gpu-226-gpu0/profiles/"
        "all/workspace/ComfyUI/models:/opt/ComfyUI/models"
    ) in service["volumes"]


def test_gpu226_all_profile_rejects_incomplete_multi_manifest_marker(
    monkeypatch,
):
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-226-gpu0-all"]
    monkeypatch.setattr(
        ops,
        "_remote_cache_marker",
        lambda _slot: {"ok": True, "status": "ready", "profile": "all"},
    )

    with pytest.raises(RuntimeError, match="cache marker is missing or incomplete"):
        ops.start_disabled([slot])


def test_all_i2i_pro_lan_slots_accept_legacy_and_v2_face_swap():
    slots = load_lan_aio_prod_slots(include_disabled=True)

    i2i_slots = [slot for slot in slots.values() if slot.target_profile_id == "i2i_pro"]
    assert i2i_slots
    assert all(
        slot.target_task_types
        == ("i2i_pro", "t2i-pornmaster-turbo", "face_swap_v2", "face_swap")
        for slot in i2i_slots
    )


def test_gpu252_fault_card_has_disabled_v2_backed_face_swap_candidate():
    slots = load_lan_aio_prod_slots(include_disabled=True)

    slot = slots["gpu-252-gpu1-face_swap"]
    assert slot.enabled is False
    assert slot.phase == "maintenance_disabled"
    assert slot.retargetable is False
    assert slot.target_profile_id == "face_swap"
    assert slot.target_task_types == ("face_swap", "face_swap_v2")
    assert slot.gpu_device_id == "GPU-8153a439-e3f6-8922-039d-dc13e97da6d7"
    assert slot.host_port == 8191
    assert slot.agent_id == "lan_aio_prod_gpu252_gpu1_face_swap_01"

    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    rendered = ops.render_compose(slot)
    assert "SUPPORTED_TASK_TYPES: face_swap,face_swap_v2" in rendered
    assert "POOL_RUNTIME_PROFILE: face_swap" in rendered
    assert (
        "/srv/allbot/runpod-runtime/slots/gpu-252-gpu1/profiles/"
        "i2i_pro/workspace/ComfyUI/models:/workspace/ComfyUI/models"
    ) in rendered
    assert (
        'TASK_TYPE_WORKFLOW_OVERRIDES: '
        '\'{"face_swap":"face_swap_v2.json","face_swap_v2":"face_swap_v2.json"}\''
    ) in rendered


def test_gpu002_i2i_pro_renders_legacy_face_swap_through_v2_workflow():
    import yaml

    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-002-gpu1-i2i_pro"]
    compose = yaml.safe_load(ops.render_compose(slot))
    environment = compose["services"][slot.container_name]["environment"]

    expected_types = "i2i_pro,t2i-pornmaster-turbo,face_swap_v2,face_swap"
    assert environment["SUPPORTED_TASK_TYPES"] == expected_types
    assert environment["PREFETCH_TASK_TYPES"] == expected_types
    assert environment["TASK_TYPE_WORKFLOW_OVERRIDES"] == (
        '{"t2i-pornmaster-turbo":"txt2img_from_i2i_pro.json",'
        '"face_swap_v2":"face_swap_v2.json",'
        '"face_swap":"face_swap_v2.json"}'
    )


def test_lan_aio_prod_slots_keep_blocked_nodes_disabled_but_visible():
    slots = load_lan_aio_prod_slots(include_disabled=True)

    assert slots["gpu-177-gpu1-ltx_video"].enabled is True
    assert slots["gpu-177-gpu1-ltx_video"].phase == "catalog_ready"
    assert slots["gpu-252-gpu0-image_to_video"].enabled is True
    assert slots["gpu-252-gpu0-image_to_video"].phase == "catalog_ready"
    assert slots["gpu-252-gpu0-image_to_video"].retargetable is True
    assert slots["gpu-252-gpu1-scail2"].enabled is False
    assert slots["gpu-252-gpu1-scail2"].phase == "maintenance_disabled"
    assert slots["gpu-252-gpu1-scail2"].retargetable is False
    assert slots["gpu-252-gpu1-scail2"].host_port == 8191
    assert slots["gpu-252-gpu1-scail2"].legacy_preflight_required is False
    assert slots["gpu-252-gpu1-scail2"].target_task_types == (
        "scail2_action_transfer",
        "scail2_action_transfer_long",
        "scail2_video_replacement",
        "scail2_face_swap_v2",
    )
    assert (
        slots["gpu-252-gpu1-scail2"].gpu_device_id
        == "GPU-33de1af6-ca27-7eeb-ae46-6a9f4f89523e"
    )
    assert slots["gpu-252-gpu1-wan22_video_v2"].enabled is False
    assert slots["gpu-252-gpu1-wan22_video_v2"].phase == "maintenance_disabled"
    assert slots["gpu-252-gpu1-wan22_video_v2"].retargetable is False
    assert "gpu-252-gpu1-pornmaster_flux2_edit" not in slots
    assert slots["gpu-252-gpu1-img2img_lora"].enabled is True
    assert slots["gpu-252-gpu1-img2img_lora"].phase == "catalog_ready"
    assert slots["gpu-252-gpu1-img2img_lora"].retargetable is True
    assert slots["gpu-252-gpu1-img2img_lora"].host_port == 8191
    assert slots["gpu-252-gpu1-img2img_lora"].target_task_types == (
        "img2img",
        "img2img_lora",
    )
    assert slots["gpu-252-gpu1-ltx_t2v"].enabled is False
    assert slots["gpu-252-gpu1-ltx_t2v"].phase == "maintenance_disabled"
    assert slots["gpu-252-gpu1-ltx_t2v"].target_task_types == (
        "ltx_t2v",
        "ltx_t2v_ic",
    )
    assert "gpu-252-gpu0-pornmaster_flux2_edit" not in slots
    assert slots["gpu-252-gpu0-ltx_t2v"].enabled is False
    assert slots["gpu-252-gpu0-ltx_t2v"].phase == "maintenance_disabled"
    assert slots["gpu-252-gpu0-ltx_t2v"].retargetable is False
    assert slots["gpu-252-gpu0-ltx_t2v"].host_port == 8192
    assert slots["gpu-252-gpu0-ltx_t2v"].target_task_types == (
        "ltx_t2v",
        "ltx_t2v_ic",
    )
    assert (
        slots["gpu-252-gpu0-ltx_t2v"].gpu_device_id
        == "GPU-09b7ea85-23df-a9b8-19d9-703534e47666"
    )
    assert (
        slots["gpu-252-gpu1-img2img_lora"].gpu_device_id
        == "GPU-3ac886ce-23af-8c9a-4509-3577e5e1fac6"
    )
    assert slots["gpu-226-gpu0-image_to_video"].enabled is True
    assert slots["gpu-226-gpu0-image_to_video"].phase == "catalog_ready"
    assert slots["gpu-226-gpu0-image_to_video"].retargetable is True
    assert slots["gpu-226-gpu0-pornmaster_flux2_edit_bf16"].enabled is True
    assert slots["gpu-226-gpu0-pornmaster_flux2_edit_bf16"].phase == "catalog_ready"
    assert slots["gpu-226-gpu0-pornmaster_flux2_edit_bf16"].retargetable is True
    assert slots["gpu-226-gpu0-i2i_pro"].enabled is True
    assert slots["gpu-226-gpu0-i2i_pro"].phase == "catalog_ready"
    assert slots["gpu-002-gpu1-image_to_video"].enabled is True
    assert slots["gpu-002-gpu1-image_to_video"].phase == "catalog_ready"
    assert slots["gpu-002-gpu1-image_to_video"].retargetable is True
    assert "gpu-002-gpu1-pornmaster_flux2_edit" not in slots
    assert slots["gpu-177-gpu1-wan22_video_v2"].enabled is False
    assert slots["gpu-177-gpu1-wan22_video_v2"].phase == "blocked_oom_32gb"
    assert slots["gpu-177-gpu1-wan22_video_v2"].retargetable is False
    assert slots["gpu-177-gpu1-scail2"].enabled is True
    assert slots["gpu-177-gpu1-scail2"].phase == "catalog_ready"
    assert slots["gpu-177-gpu1-scail2"].retargetable is True
    assert slots["gpu-177-gpu1-scail2"].target_task_types == (
        "scail2_action_transfer",
        "scail2_action_transfer_long",
        "scail2_video_replacement",
        "scail2_face_swap_v2",
    )
    config = load_controller_config()
    assert (
        config.profiles["ltx_video"].all_in_one_image_ref
        == "192.168.1.115:5000/allbot/comfy-runpod-ltx-video"
        "@sha256:e291d068ca5d0264209ba452427a55bb4fb62c95ddc1b7b657c1e7246834b4cc"
    )
    assert slots["gpu-226-gpu0-face_i2i_t2i"].phase == "blocked_host_service_runtime"


def test_lan_aio_prod_slot_omits_gpu177_retired_hot_cache_copy():
    slot = load_lan_aio_prod_slots(include_disabled=True)["gpu-177-gpu0-image_to_video"]

    assert slot.legacy_hot_cache_copies == ()
    assert "Legacy worker 02/comfy0 were retired" in slot.notes


def test_lan_aio_prod_slot_declares_gpu252_host_rife_hot_cache_copy():
    slot = load_lan_aio_prod_slots(include_disabled=True)["gpu-252-gpu1-wan22_video_v2"]

    assert len(slot.legacy_hot_cache_copies) == 1
    hot_cache = slot.legacy_hot_cache_copies[0]
    assert hot_cache.source_container == "__host__"
    assert hot_cache.source_path == (
        "/home/user/APP/data/inst1/custom_nodes/ComfyUI_Fill-Nodes/"
        "nodes/cache/rife_models/rife49.pth"
    )
    assert hot_cache.target_paths == (
        "/default-comfyui-bundle/ComfyUI/custom_nodes/ComfyUI_Fill-Nodes/nodes/cache/rife_models/rife49.pth",
        "/default-comfyui-bundle/ComfyUI/custom_nodes/ComfyUI-Frame-Interpolation/ckpts/rife/rife49.pth",
    )


def test_lan_aio_prod_slot_declares_gpu002_image_to_video_hot_cache_copy():
    slot = load_lan_aio_prod_slots(include_disabled=True)["gpu-002-gpu1-image_to_video"]

    assert len(slot.legacy_hot_cache_copies) == 1
    hot_cache = slot.legacy_hot_cache_copies[0]
    assert hot_cache.source_container == "__host__"
    assert hot_cache.source_path == (
        "/data/comfy/inst1/custom_nodes/ComfyUI_Fill-Nodes/"
        "nodes/cache/rife_models/rife49.pth"
    )
    assert hot_cache.required is True


def test_lan_aio_fleet_render_uses_baked_runpod_worker_for_gpu_252():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-252-gpu1-img2img_lora"]
    rendered = ops.render_compose(slot)

    assert "RUNPOD_ENVIRONMENT: cloud-prod" in rendered
    assert "CENTRAL_API_URL: https://worker-central.aivison.it.com" in rendered
    assert "MINIO_RESULT_BUCKET: user-data-prod" in rendered
    assert (
        "SUPPORTED_TASK_TYPES: img2img,img2img_lora"
    ) in rendered
    assert "POOL_RUNTIME_PROFILE: img2img_lora" in rendered
    assert "host_port: 8191" in rendered
    assert "--disable-dynamic-vram" not in rendered
    assert "cloud-test" not in rendered
    assert "user-data-test" not in rendered
    assert f"AGENT_ID: {slot.agent_id}" in rendered
    assert f"container_name: {slot.container_name}" in rendered
    assert "restart: unless-stopped" in rendered
    assert "RUNPOD_KEEPALIVE_ON_BOOTSTRAP_FAILURE: 'false'" in rendered
    assert (
        "process_supervision: exit_container_when_agent_relay_or_comfy_exits"
        in rendered
    )
    assert ":/opt/allbot/runtime/runpod_worker" not in rendered
    assert "PYTHONPATH: /opt/allbot/runtime/runpod_worker" in rendered
    assert "runpod_worker_bundle:" in rendered
    assert "mode: baked_immutable_artifact" in rendered


def test_lan_aio_fleet_render_passes_explicit_runtime_proxy(tmp_path: Path):
    aio_env_file = tmp_path / "lan-aio.env"
    aio_env_file.write_text(
        "LAN_AIO_PIP_DEFAULT_TIMEOUT=300\nLAN_AIO_PIP_RETRIES=10\n",
        encoding="utf-8",
    )
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=aio_env_file,
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    ops.env_values.update(
        {
            "LAN_AIO_HTTP_PROXY": "http://192.168.1.115:7890",
            "LAN_AIO_HTTPS_PROXY": "http://192.168.1.115:7890",
            "LAN_AIO_NO_PROXY": "127.0.0.1,localhost,192.168.1.115",
        }
    )
    slot = ops.slots["gpu-252-gpu0-image_to_video"]

    import yaml

    compose = yaml.safe_load(ops.render_compose(slot))
    environment = compose["services"][slot.container_name]["environment"]

    assert environment["HTTP_PROXY"] == "${LAN_AIO_HTTP_PROXY}"
    assert environment["HTTPS_PROXY"] == "${LAN_AIO_HTTPS_PROXY}"
    assert environment["NO_PROXY"] == "${LAN_AIO_NO_PROXY}"
    assert environment["PIP_DEFAULT_TIMEOUT"] == "${LAN_AIO_PIP_DEFAULT_TIMEOUT}"
    assert environment["PIP_RETRIES"] == "${LAN_AIO_PIP_RETRIES}"


def test_lan_aio_runtime_env_includes_only_explicit_proxy_values():
    values = {
        "LAN_AIO_AGENT_SECRET_TOKEN": "agent-token",
        "LAN_AIO_MINIO_ENDPOINT": "http://192.168.1.115:9000",
        "LAN_AIO_MINIO_ACCESS_KEY": "access",
        "LAN_AIO_MINIO_SECRET_KEY": "secret",
        "LAN_MODEL_CACHE_ACCESS_KEY": "model-access",
        "LAN_MODEL_CACHE_SECRET_KEY": "model-secret",
        "LAN_AIO_HTTPS_PROXY": "http://192.168.1.115:7890",
        "LAN_AIO_NO_PROXY": "127.0.0.1,localhost,192.168.1.115",
        "LAN_AIO_PIP_DEFAULT_TIMEOUT": "300",
        "LAN_AIO_PIP_RETRIES": "10",
    }

    content = runtime_env_content(values)

    assert "LAN_AIO_HTTP_PROXY=" not in content
    assert "LAN_AIO_HTTPS_PROXY=http://192.168.1.115:7890\n" in content
    assert "LAN_AIO_NO_PROXY=127.0.0.1,localhost,192.168.1.115\n" in content
    assert "LAN_AIO_PIP_DEFAULT_TIMEOUT=300\n" in content
    assert "LAN_AIO_PIP_RETRIES=10\n" in content


def test_lan_aio_fleet_render_uses_stable_gpu_device_id_for_gpu_252():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-252-gpu0-i2i_pro"]
    rendered = ops.render_compose(slot)

    import yaml

    compose = yaml.safe_load(rendered)
    service = compose["services"][slot.container_name]

    assert slot.gpu_index == 0
    assert slot.gpu_device_id == "GPU-09b7ea85-23df-a9b8-19d9-703534e47666"
    assert service["environment"]["POOL_GPU_INDEX"] == "0"
    assert (
        service["environment"]["POOL_GPU_DEVICE_ID"]
        == "GPU-09b7ea85-23df-a9b8-19d9-703534e47666"
    )
    assert (
        service["environment"]["NVIDIA_VISIBLE_DEVICES"]
        == "GPU-09b7ea85-23df-a9b8-19d9-703534e47666"
    )
    assert service["gpus"][0]["device_ids"] == [
        "GPU-09b7ea85-23df-a9b8-19d9-703534e47666"
    ]


def test_lan_aio_fleet_render_uses_rocm_devices_for_local_max395():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-115-gpu0-img2img_lora_rocm_gfx1151"]

    import yaml

    compose = yaml.safe_load(ops.render_compose(slot))
    service = compose["services"][slot.container_name]

    assert service["devices"] == ["/dev/kfd:/dev/kfd", "/dev/dri:/dev/dri"]
    assert service["group_add"] == ["video", "render"]
    assert service["ipc"] == "host"
    assert service["security_opt"] == ["seccomp=unconfined"]
    assert "gpus" not in service
    assert "NVIDIA_VISIBLE_DEVICES" not in service["environment"]
    assert service["environment"]["HIP_VISIBLE_DEVICES"] == "0"
    assert service["environment"]["ROCR_VISIBLE_DEVICES"] == "0"
    assert service["environment"]["POOL_ACCELERATOR"] == "rocm"
    assert service["environment"]["RUNPOD_MODEL_TARGET_DIR"] == "/opt/ComfyUI/models"
    assert "--lowvram" in service["environment"]["COMFY_EXTRA_ARGS"]
    assert "--disable-pinned-memory" in service["environment"]["COMFY_EXTRA_ARGS"]
    assert any(
        mount.endswith(":/opt/ComfyUI/models") for mount in service["volumes"]
    )


def test_lan_aio_local_transport_executes_without_self_ssh(tmp_path):
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.commands: list[list[str]] = []

        def _local(
            self,
            cmd: list[str],
            *,
            capture: bool = False,
            input_text: str | None = None,
            extra_env: dict[str, str] | None = None,
        ) -> str:
            self.commands.append(cmd)
            return "local-ok"

    ops = RecordingOps()
    source = tmp_path / "source.env"
    target = tmp_path / "target.env"
    source.write_text("KEY=value\n", encoding="utf-8")

    assert ops._ssh("local://", "hostname", capture=True) == "local-ok"
    ops._scp(source, "local://", str(target))

    assert ops.commands == [["bash", "-lc", "hostname"]]
    assert target.read_text(encoding="utf-8") == "KEY=value\n"


@pytest.mark.parametrize(
    "slot_id",
    [
        "gpu-177-gpu0-wan22_video_v2",
        "gpu-177-gpu1-ltx_video",
        "gpu-252-gpu0-i2i_pro",
        "gpu-002-gpu0-scail2",
        "gpu-002-gpu1-i2i_pro",
        "gpu-226-gpu0-i2i_pro",
    ],
)
def test_all_active_lan_aio_workers_reserve_and_prefetch_one_task(slot_id):
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots[slot_id]

    import yaml

    compose = yaml.safe_load(ops.render_compose(slot))
    environment = compose["services"][slot.container_name]["environment"]

    assert environment["PREFETCH_ENABLED"] == "true"
    assert environment["PREFETCH_RESERVE_TASK"] == "true"
    assert environment["PREFETCH_DEPTH"] == "1"
    assert environment["PREFETCH_TASK_TYPES"] == environment["SUPPORTED_TASK_TYPES"]
    assert environment["PREFETCH_CONSUME_WAIT_SECONDS"] == "10"


def test_fast_image_lan_aio_uses_bounded_compute_and_delivery_pipeline():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-226-gpu0-pornmaster_flux2_edit_bf16"]

    import yaml

    compose = yaml.safe_load(ops.render_compose(slot))
    environment = compose["services"][slot.container_name]["environment"]

    assert environment["PIPELINE_ENABLED"] == "true"
    assert environment["PIPELINE_MAX_RUNNING_TASKS"] == "1"
    assert environment["PIPELINE_MAX_CLAIMED_TASKS"] == "2"
    assert environment["PIPELINE_DELIVERY_CONCURRENCY"] == "1"
    assert (
        environment["PIPELINE_PROFILE_POLICY"]
        == "image_claim3_comfy2_delivery1_v1"
    )
    assert environment["PIPELINE_TASK_TYPES"] == (
        "pornmaster_flux2_edit_bf16,pornmaster_flux2_multi_edit_bf16"
    )


def test_i2i_lan_aio_uses_fast_image_pipeline_policy():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-252-gpu0-i2i_pro"]

    import yaml

    compose = yaml.safe_load(ops.render_compose(slot))
    environment = compose["services"][slot.container_name]["environment"]

    assert environment["PIPELINE_MAX_RUNNING_TASKS"] == "1"
    assert environment["PIPELINE_MAX_CLAIMED_TASKS"] == "2"
    assert environment["PIPELINE_DELIVERY_CONCURRENCY"] == "1"
    assert (
        environment["PIPELINE_PROFILE_POLICY"]
        == "image_claim3_comfy2_delivery1_v1"
    )


def test_lan_aio_stop_old_dry_run_omits_empty_local_agent_container():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-252-gpu1-img2img_lora"]

    payload = ops.dry_run_action("stop-old", [slot])

    assert payload["operations"] == [
        "set lan_aio_prod_gpu252_gpu1_i2i_pro_01=disabled",
        "ssh allbot-gpu-252 docker stop allbot-lan-aio-gpu-252-gpu1-i2i_pro-prod",
    ]


def test_lan_aio_fleet_render_supports_gpu_177_image_to_video_profile():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-177-gpu0-image_to_video"]
    rendered = ops.render_compose(slot)

    assert "POOL_NODE_ID: gpu-177" in rendered
    assert "POOL_RUNTIME_PROFILE: image_to_video" in rendered
    assert "SUPPORTED_TASK_TYPES: video_insert,video_edit,image_to_video" in rendered
    assert "SUPPORTED_TASK_TYPES: wan22_video_v2" not in rendered
    assert (
        "RUNPOD_MODEL_MANIFEST_KEY: image_to_video/2026-07-18-lora5/manifest.json"
        in rendered
    )
    assert "--disable-dynamic-vram" in rendered
    assert "host_port: 8190" in rendered


def test_lan_aio_fleet_render_keeps_gpu_177_gpu1_wan22_v2_blocked_slot_renderable():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.select_slots("gpu-177-gpu1-wan22_video_v2", include_disabled=True)[0]
    rendered = ops.render_compose(slot)

    assert slot.enabled is False
    assert slot.phase == "blocked_oom_32gb"
    assert slot.retargetable is False
    assert slot.target_task_types == ("wan22_video_v2",)
    assert slot.legacy_worker_id == "lan_aio_prod_gpu177_gpu1_ltx_video_01"
    assert "POOL_NODE_ID: gpu-177" in rendered
    assert "POOL_GPU_INDEX: '1'" in rendered
    assert "NVIDIA_VISIBLE_DEVICES: '1'" in rendered
    assert "POOL_RUNTIME_PROFILE: wan22_video_v2" in rendered
    assert "SUPPORTED_TASK_TYPES: wan22_video_v2" in rendered
    assert (
        "SUPPORTED_TASK_TYPES: wan22_video_v2,video_edit,image_to_video" not in rendered
    )
    assert (
        "RUNPOD_MODEL_MANIFEST_KEY: wan22_video_v2/2026-07-18-lora5/manifest.json"
        in rendered
    )
    assert "--disable-dynamic-vram" in rendered
    assert "host_port: 8191" in rendered


def test_lan_aio_fleet_render_supports_gpu_177_gpu1_scail2_candidate():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.select_slots("gpu-177-gpu1-scail2", include_disabled=True)[0]
    rendered = ops.render_compose(slot)

    assert slot.enabled is True
    assert slot.phase == "catalog_ready"
    assert slot.target_task_types == (
        "scail2_action_transfer",
        "scail2_action_transfer_long",
        "scail2_video_replacement",
        "scail2_face_swap_v2",
    )
    assert slot.legacy_worker_id == "lan_aio_prod_gpu177_gpu1_ltx_video_01"
    assert "POOL_NODE_ID: gpu-177" in rendered
    assert "POOL_GPU_INDEX: '1'" in rendered
    assert "NVIDIA_VISIBLE_DEVICES: '1'" in rendered
    assert "POOL_RUNTIME_PROFILE: scail2" in rendered
    assert "COMFYUI_DIR: /opt/ComfyUI" in rendered
    assert (
        "SUPPORTED_TASK_TYPES: scail2_action_transfer,scail2_action_transfer_long,"
        "scail2_video_replacement,scail2_face_swap_v2"
    ) in rendered
    assert "RUNPOD_MODEL_MANIFEST_KEY: scail2/2026-06-17-test/manifest.json" in rendered
    assert "host_port: 8191" in rendered


def test_lan_aio_fleet_render_supports_gpu_002_gpu0_scail2_current_slot():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-002-gpu0-scail2"]
    rendered = ops.render_compose(slot)

    assert slot.enabled is True
    assert slot.phase == "catalog_ready"
    assert slot.agent_id == "lan_aio_prod_gpu002_gpu0_scail2_01"
    assert slot.old_runtime_container == (
        "allbot-lan-aio-gpu-002-gpu0-img2img_lora-canary"
    )
    assert "POOL_NODE_ID: gpu-002" in rendered
    assert "POOL_GPU_INDEX: '0'" in rendered
    assert "NVIDIA_VISIBLE_DEVICES: '0'" in rendered
    assert "POOL_RUNTIME_PROFILE: scail2" in rendered
    assert (
        "SUPPORTED_TASK_TYPES: scail2_action_transfer,scail2_action_transfer_long,"
        "scail2_video_replacement,scail2_face_swap_v2"
    ) in rendered
    assert "RUNPOD_MODEL_MANIFEST_KEY: scail2/2026-06-17-test/manifest.json" in rendered
    assert "host_port: 8190" in rendered
    assert (
        "/srv/allbot/runpod-runtime/slots/gpu-002-gpu0/profiles/"
        "scail2-b2587e56/workspace:/workspace"
    ) in rendered
    assert (
        "/srv/allbot/runpod-runtime/slots/gpu-002-gpu0/profiles/"
        "scail2/workspace/ComfyUI/models:/opt/ComfyUI/models"
    ) in rendered


def test_lan_aio_retarget_candidate_uses_target_gpu_and_candidate_profile():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    candidate = ops.select_slots(
        "gpu-177-gpu1-scail2",
        include_disabled=True,
    )[0]

    retargeted = ops.retarget_slot(candidate, "gpu-177-gpu1-ltx_video")
    rendered = ops.render_compose(retargeted)

    assert retargeted.assignment_id == "lan-177-8189-worker-03"
    assert retargeted.target_profile_id == "scail2"
    assert retargeted.host_port == 8191
    assert retargeted.gpu_index == 1
    assert retargeted.legacy_worker_id == "lan_aio_prod_gpu177_gpu1_ltx_video_01"
    assert retargeted.old_runtime_container == (
        "allbot-lan-aio-gpu-177-gpu1-ltx_video-prod"
    )
    assert retargeted.container_name == ("allbot-lan-aio-gpu-177-gpu1-scail2-prod")
    assert "POOL_GPU_INDEX: '1'" in rendered
    assert "NVIDIA_VISIBLE_DEVICES: '1'" in rendered
    assert "POOL_RUNTIME_PROFILE: scail2" in rendered
    assert (
        "SUPPORTED_TASK_TYPES: scail2_action_transfer,scail2_action_transfer_long,"
        "scail2_video_replacement,scail2_face_swap_v2"
    ) in rendered
    assert "host_port: 8191" in rendered


def test_lan_aio_retarget_preflight_allows_runner_local_image_fallback():
    class ImageFallbackOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )

        def render_compose(self, slot):
            return "services: {}"

        def _http_check(self, name, url):
            return {"name": name, "ok": True}

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            if "docker info" in command or "docker image inspect" in command:
                raise subprocess.CalledProcessError(1, command)
            if "df -h" in command:
                return "/dev/nvme0n1p2  915G  329G  540G  38% /"
            return ""

        def _local_image_present(self, image_ref: str | None) -> bool:
            return bool(image_ref and "scail2" in image_ref)

    ops = ImageFallbackOps()
    candidate = ops.select_slots(
        "gpu-177-gpu1-scail2",
        include_disabled=True,
    )[0]
    retargeted = ops.retarget_slot(candidate, "gpu-177-gpu1-ltx_video")

    payload = ops.preflight_payload([retargeted], execute=True)

    assert payload["ok"] is True
    image_check = next(
        check
        for check in payload["slots"][0]["checks"]
        if check["name"] == "docker_registry_or_image_present"
    )
    assert image_check["name"] == "docker_registry_or_image_present"
    assert image_check["registry_configured"] is False
    assert image_check["remote_image_present"] is False
    assert image_check["runner_image_present"] is True
    assert image_check["output"] == "runner_local_image_available_for_stream_load"


def test_lan_aio_pull_image_loads_runner_local_image_when_remote_pull_fails():
    class ImageLoadOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.loaded: list[tuple[str, str]] = []
            self.remote_commands: list[str] = []

        def _remote_image_present(self, slot, image_ref: str) -> bool:
            return False

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            self.remote_commands.append(command)
            if "timeout 3600 docker pull" in command:
                raise subprocess.CalledProcessError(
                    1,
                    command,
                    stderr="HTTP response to HTTPS client",
                )
            return ""

        def _local_image_present(self, image_ref: str | None) -> bool:
            return bool(image_ref)

        def _load_local_image_to_remote(self, slot, image_ref: str) -> str:
            self.loaded.append((slot.id, image_ref))
            return "Loaded image: sha256:abc123"

    ops = ImageLoadOps()
    candidate = ops.select_slots(
        "gpu-177-gpu1-scail2",
        include_disabled=True,
    )[0]
    retargeted = ops.retarget_slot(candidate, "gpu-177-gpu1-ltx_video")

    payload = ops.pull_image([retargeted])

    assert payload["ok"] is True
    assert payload["pulled"][0]["status"] == "loaded_from_runner"
    assert ops.remote_commands == [
        "pkill -f '^docker\\ pull\\ "
        "192\\.168\\.1\\.115:5000/allbot/comfy\\-runpod\\-scail2"
        "@sha256:858ac45522f33189e16e6ad41c0080b785c6bb87808d890d8f9899e0ed9b7607$' "
        "|| true; timeout 3600 docker pull '" + SCAIL2_BAKED_LAN_IMAGE + "'"
    ]
    assert ops.loaded == [
        (
            "gpu-177-gpu1-scail2",
            SCAIL2_BAKED_LAN_IMAGE,
        )
    ]


def test_lan_aio_cli_allows_replace_slot_for_retarget_render(
    capsys,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    result = lan_aio_main(
        [
            "render",
            "--slot",
            "gpu-177-gpu1-scail2",
            "--replace-slot",
            "gpu-177-gpu1-ltx_video",
            "--include-disabled",
            "--prod-env-file",
            str(tmp_path / "missing-prod.env"),
            "--aio-env-file",
            str(tmp_path / "missing-aio.env"),
            "--model-env-file",
            str(tmp_path / "missing-model.env"),
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "host_port: 8191" in output
    assert "POOL_GPU_INDEX: '1'" in output
    assert "POOL_RUNTIME_PROFILE: scail2" in output


def test_lan_aio_cli_rejects_replace_slot_for_dangerous_single_step(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        lan_aio_main(
            [
                "stop-old",
                "--slot",
                "gpu-177-gpu1-scail2",
                "--replace-slot",
                "gpu-177-gpu0-image_to_video",
                "--include-disabled",
                "--prod-env-file",
                str(tmp_path / "missing-prod.env"),
                "--aio-env-file",
                str(tmp_path / "missing-aio.env"),
                "--model-env-file",
                str(tmp_path / "missing-model.env"),
            ]
        )

    assert "--replace-slot is only supported for:" in str(exc_info.value)
    assert "takeover" in str(exc_info.value)


def test_lan_aio_fleet_render_supports_gpu_177_ltx_profile():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-177-gpu1-ltx_video"]
    rendered = ops.render_compose(slot)

    assert "POOL_NODE_ID: gpu-177" in rendered
    assert "POOL_GPU_INDEX: '1'" in rendered
    assert "POOL_RUNTIME_PROFILE: ltx_video" in rendered
    assert "SUPPORTED_TASK_TYPES: ltx_video" in rendered
    assert "SUPPORTED_TASK_TYPES: ltx_video,image_to_video" not in rendered
    assert "TASK_TYPE_WORKFLOW_OVERRIDES:" in rendered
    assert "LTX 2.3 10Eros v1.2 I2V 6.1.json" in rendered
    import yaml

    compose = yaml.safe_load(rendered)
    service = compose["services"][slot.container_name]
    assert (
        service["environment"]["TASK_TYPE_WORKFLOW_OVERRIDES"]
        == RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES
    )
    assert (
        json.loads(service["environment"]["TASK_TYPE_WORKFLOW_OVERRIDES"])[
            "ltx_video_flf2v"
        ]
        == "LTX 2.3 10Eros v1.2 FLF2V 6.1.json"
    )
    assert "RUNPOD_MODEL_MANIFEST_KEY: ltx_video/2026-06-10/manifest.json" in rendered
    assert "MINIO_RESULT_BUCKET: user-data-prod" in rendered
    assert "host_port: 8191" in rendered


def test_lan_aio_fleet_render_runs_ltx_t2v_from_baked_comfy_with_persistent_models():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-252-gpu0-ltx_t2v"]
    rendered = ops.render_compose(slot)

    import yaml

    compose = yaml.safe_load(rendered)
    service = compose["services"][slot.container_name]
    assert service["environment"]["COMFYUI_DIR"] == "/opt/ComfyUI"
    assert service["environment"]["RUNPOD_MODEL_TARGET_DIR"] == ("/opt/ComfyUI/models")
    assert (
        "/srv/allbot/runpod-runtime/slots/gpu-252-gpu0/profiles/"
        "ltx_t2v/workspace/ComfyUI/models:/opt/ComfyUI/models" in service["volumes"]
    )
    assert (
        "/srv/allbot/runpod-runtime/slots/gpu-252-gpu0/profiles/"
        "ltx-t2v-9ed3de73/workspace:/workspace" in service["volumes"]
    )
    assert "--reserve-vram 5" in service["environment"]["COMFY_EXTRA_ARGS"]


def test_lan_aio_fleet_render_supports_scail2_v10_face_swap_env():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-252-gpu0-scail2"]
    rendered = ops.render_compose(slot)

    import yaml

    compose = yaml.safe_load(rendered)
    service = compose["services"][slot.container_name]
    environment = service["environment"]
    workflow_overrides = json.loads(environment["TASK_TYPE_WORKFLOW_OVERRIDES"])

    assert environment["TASK_TYPE_WORKFLOW_OVERRIDES"] == (
        LAN_AIO_SCAIL2_WORKFLOW_OVERRIDES
    )
    assert workflow_overrides["scail2_action_transfer"] == (
        "SCAIL-2_Animation_multi-char_audio.api.json"
    )
    assert workflow_overrides["scail2_action_transfer_long"] == (
        "SCAIL-2_Animation_WAN-Context-Windows.api.json"
    )
    assert workflow_overrides["scail2_video_replacement"] == (
        "SCAIL-2_Replacement_audio.api.json"
    )
    assert workflow_overrides["scail2_face_swap_v2"] == (
        "SCAIL-2_FaceSwap_v10_firstframe_faceswap_replacement_audio.api.json"
    )
    assert "SCAIL2_FACE_SWAP_V10_ENABLED" not in environment
    assert "SCAIL2_FACE_SWAP_V10_FACE_SWAP_COMFY_API_URL" not in environment
    assert "SCAIL2_FACE_SWAP_V10_FACE_SWAP_WORKFLOW" not in environment


def test_ltx_video_workflow_uses_baked_sageattention():
    for path in (Path("workers/comfy_agent/workflows/LTX 2.3 I2V 6.1.json"),):
        workflow = json.loads(path.read_text(encoding="utf-8"))

        assert workflow["257"]["inputs"]["sage_attention"] == "auto"

    dockerfile = Path(
        "workers/runpod_profiles/ltx_video/Dockerfile"
    ).read_text(encoding="utf-8")
    assert "sageattention==" in dockerfile


def test_lan_aio_fleet_render_disables_dynamic_vram_for_wan22_v2():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-252-gpu1-wan22_video_v2"]
    rendered = ops.render_compose(slot)

    assert slot.phase == "maintenance_disabled"
    assert slot.target_task_types == ("wan22_video_v2",)
    assert "POOL_RUNTIME_PROFILE: wan22_video_v2" in rendered
    assert "POOL_GPU_INDEX: '1'" in rendered
    assert (
        "NVIDIA_VISIBLE_DEVICES: GPU-33de1af6-ca27-7eeb-ae46-6a9f4f89523e" in rendered
    )
    assert "POOL_GPU_DEVICE_ID: GPU-33de1af6-ca27-7eeb-ae46-6a9f4f89523e" in rendered
    assert "SUPPORTED_TASK_TYPES: wan22_video_v2" in rendered
    assert (
        "SUPPORTED_TASK_TYPES: wan22_video_v2,video_edit,image_to_video" not in rendered
    )
    assert "--disable-dynamic-vram" in rendered


def test_lan_aio_prod_compose_assertion_rejects_test_storage():
    config = load_controller_config()
    slot = load_lan_aio_prod_slots(include_disabled=True)[
        "gpu-252-gpu0-img2img_lora"
    ]
    rendered = RuntimePlanner(config).render_compose(
        slot.assignment_id,
        target_profile_id=slot.target_profile_id,
        overrides=RuntimeRenderOverrides(
            host_port=slot.host_port,
            container_name=slot.container_name,
            runtime_shape="runpod_all_in_one",
            agent_id=slot.agent_id,
        ),
    )
    patched = patch_baked_runpod_worker(rendered, slot)

    try:
        assert_prod_compose(patched, slot)
    except RuntimeError as exc:
        assert "cloud-test" in str(exc) or "user-data-test" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("cloud-test compose should be rejected for prod helper")


def test_lan_aio_prod_skips_retired_gpu177_legacy_hot_cache_paths():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.ssh_calls: list[tuple[str, str]] = []

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            self.ssh_calls.append((host, command))
            return ""

    ops = RecordingOps()
    slot = ops.slots["gpu-177-gpu0-image_to_video"]

    copied = ops._preseed_legacy_hot_caches(slot)

    assert copied == []
    assert ops.ssh_calls == []


def test_lan_aio_prod_preseeds_host_hot_cache_paths():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.ssh_calls: list[tuple[str, str]] = []

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            self.ssh_calls.append((host, command))
            return ""

    ops = RecordingOps()
    slot = ops.slots["gpu-252-gpu1-wan22_video_v2"]

    copied = ops._preseed_legacy_hot_caches(slot)

    assert copied[0]["source_container"] == "__host__"
    assert copied[0]["source_path"].startswith("/home/user/APP/data/inst1/")
    assert len(ops.ssh_calls) == 1
    host, command = ops.ssh_calls[0]
    assert host == "allbot-gpu-252"
    assert "cp /home/user/APP/data/inst1/custom_nodes/ComfyUI_Fill-Nodes" in command
    assert "docker cp __host__:" not in command
    assert "ComfyUI-Frame-Interpolation/ckpts/rife/rife49.pth" in command


def test_lan_aio_remote_status_matches_container_lines_with_status_suffix():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.command = ""

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            self.command = command
            return "\n".join(
                [
                    "allbot-lan-aio-gpu-177-gpu0-image_to_video-prod Up 2 hours (healthy)",
                    "comfy0 Up 3 weeks 0.0.0.0:8188->8188/tcp",
                ]
            )

    ops = RecordingOps()
    slot = ops.slots["gpu-177-gpu0-image_to_video"]

    rows = ops._remote_container_status(slot)

    assert rows == [
        "allbot-lan-aio-gpu-177-gpu0-image_to_video-prod Up 2 hours (healthy)",
        "comfy0 Up 3 weeks 0.0.0.0:8188->8188/tcp",
    ]
    assert f"^{slot.container_name}$" not in ops.command
    assert f"^{slot.old_runtime_container}$" not in ops.command


def test_lan_aio_remote_shell_commands_are_noninteractive():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.commands: list[list[str]] = []

        def _local(
            self,
            cmd: list[str],
            *,
            capture: bool = False,
            input_text: str | None = None,
            extra_env: dict[str, str] | None = None,
        ) -> str:
            self.commands.append(cmd)
            return ""

    ops = RecordingOps()

    ops._ssh("allbot-gpu-002", "hostname", capture=True)
    ops._scp(Path("/tmp/local.env"), "allbot-gpu-002", "/tmp/remote.env")

    for command in ops.commands:
        assert "-o" in command
        assert "BatchMode=yes" in command
        assert "ConnectTimeout=10" in command
        assert "StrictHostKeyChecking=accept-new" in command
    assert ops.commands[0][:2] == ["ssh", "-o"]
    assert ops.commands[0][-2:] == ["allbot-gpu-002", "hostname"]
    assert ops.commands[1][:2] == ["scp", "-o"]
    assert ops.commands[1][-2:] == ["/tmp/local.env", "allbot-gpu-002:/tmp/remote.env"]


def test_lan_aio_enable_rejects_old_runtime_gpu_memory():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.controls: list[tuple[str, str]] = []

        def _set_control(
            self,
            agent_id: str,
            state: str,
            reason: str,
            *,
            ttl_seconds: int | None = None,
        ) -> None:
            self.controls.append((agent_id, state))

        def _control_state(self, agent_id: str) -> str:
            return "disabled"

        def _system_workers(self) -> list[dict[str, object]]:
            return [
                {
                    "agent_id": "cloud_prod_worker_02",
                    "status": "idle",
                    "current_task_type": None,
                },
                {
                    "agent_id": "lan_aio_prod_gpu177_gpu0_image_to_video_01",
                    "status": "idle",
                    "current_task_type": None,
                },
            ]

        def _old_runtime_gpu_memory_processes(
            self,
            slot,
        ) -> list[dict[str, object]]:
            return [{"pid": "1907930", "used_gpu_memory_mib": "29762"}]

    ops = RecordingOps()
    slot = ops.slots["gpu-177-gpu0-image_to_video"]

    with pytest.raises(
        RuntimeError,
        match=(
            "old runtime container "
            "allbot-lan-aio-gpu-177-gpu0-wan22_video_v2-prod still has GPU"
        ),
    ):
        ops.enable_aio([slot])

    assert ops.controls == [("lan_aio_prod_gpu177_gpu0_wan22_video_v2_01", "disabled")]


def test_lan_aio_enable_persistently_disables_replaced_worker():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.controls: list[tuple[str, str, int | None]] = []

        def _set_control(
            self,
            agent_id: str,
            state: str,
            reason: str,
            *,
            ttl_seconds: int | None = None,
        ) -> None:
            self.controls.append((agent_id, state, ttl_seconds))

        def _control_state(self, agent_id: str) -> str:
            return "disabled"

        def _system_workers(self) -> list[dict[str, object]]:
            return [
                {
                    "agent_id": "cloud_prod_worker_02",
                    "status": "idle",
                    "current_task_type": None,
                },
                {
                    "agent_id": "lan_aio_prod_gpu177_gpu0_image_to_video_01",
                    "status": "idle",
                    "current_task_type": None,
                },
            ]

        def _old_runtime_gpu_memory_processes(self, slot):
            return []

    ops = RecordingOps()
    slot = ops.slots["gpu-177-gpu0-image_to_video"]

    result = ops.enable_aio([slot])

    assert result["ok"] is True
    assert ops.controls == [
        ("lan_aio_prod_gpu177_gpu0_wan22_video_v2_01", "disabled", None),
        ("lan_aio_prod_gpu177_gpu0_image_to_video_01", "enabled", None),
    ]


def test_lan_aio_disable_persists_until_explicit_enable():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.controls: list[tuple[str, str, str, int | None]] = []

        def _set_control(
            self,
            agent_id: str,
            state: str,
            reason: str,
            *,
            ttl_seconds: int | None = None,
        ) -> None:
            self.controls.append((agent_id, state, reason, ttl_seconds))

    ops = RecordingOps()
    slot = ops.slots["gpu-115-gpu0-img2img_lora_rocm_gfx1151"]

    result = ops.disable_aio([slot])

    assert result["ok"] is True
    assert ops.controls == [
        (
            "lan_aio_prod_gpu115_gpu0_img2img_lora_rocm_01",
            "disabled",
            "lan_aio_fleet_disable_aio",
            None,
        )
    ]


def test_lan_aio_retire_legacy_keeps_active_aio_running_and_disables_old_persistently():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.events: list[str] = []
            self.legacy_state = "enabled"

        def current_slot_id(self, physical_slot: str) -> str:
            assert physical_slot == "gpu-177:gpu0"
            return "gpu-177-gpu0-image_to_video"

        def live_current_snapshot(self, physical_slots):
            assert physical_slots == {"gpu-177:gpu0"}
            return {
                "current": {"gpu-177:gpu0": "gpu-177-gpu0-image_to_video"},
                "errors": {},
            }

        def _control_state(self, agent_id: str) -> str:
            if agent_id == "lan_aio_prod_gpu177_gpu0_image_to_video_01":
                return "enabled"
            return self.legacy_state

        def _system_workers(self) -> list[dict[str, object]]:
            return [
                {
                    "agent_id": "cloud_prod_worker_02",
                    "status": "idle",
                    "current_task_id": None,
                    "current_task_type": None,
                },
                {
                    "agent_id": "lan_aio_prod_gpu177_gpu0_image_to_video_01",
                    "status": "running",
                    "current_task_id": "task-in-progress",
                    "current_task_type": "image_to_video",
                },
            ]

        def _wait_container_health(self, slot) -> None:
            self.events.append("verify-aio-health")

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            if ".State.Running" in command:
                self.events.append("verify-old-stopped")
                return "false|unless-stopped\n"
            if "docker update --restart=no" in command:
                self.events.append("disable-old-restart")
                return ""
            if ".HostConfig.RestartPolicy.Name" in command:
                self.events.append("verify-old-restart-disabled")
                return "no\n"
            raise AssertionError(command)

        def _set_control(
            self,
            agent_id: str,
            state: str,
            reason: str,
            *,
            ttl_seconds: int | None = None,
        ) -> None:
            assert agent_id == "lan_aio_prod_gpu177_gpu0_wan22_video_v2_01"
            assert state == "disabled"
            assert ttl_seconds is None
            self.events.append("persistent-disable")
            self.legacy_state = "disabled"

    ops = RecordingOps()
    slot = ops.slots["gpu-177-gpu0-image_to_video"]

    result = ops.retire_legacy([slot])

    assert result == {
        "ok": True,
        "action": "retire-legacy",
        "slot": "gpu-177-gpu0-image_to_video",
        "legacy_agent_id": "lan_aio_prod_gpu177_gpu0_wan22_video_v2_01",
        "legacy_control": "disabled",
        "old_runtime_container": (
            "allbot-lan-aio-gpu-177-gpu0-wan22_video_v2-prod"
        ),
        "old_runtime_restart_policy": "no",
    }
    assert ops.events == [
        "verify-aio-health",
        "verify-old-stopped",
        "disable-old-restart",
        "verify-old-restart-disabled",
        "persistent-disable",
    ]


def test_node_storage_gc_rejects_current_container_before_remote_mutation():
    class RecordingOps(LanAioProdOps):
        def _node_storage_gc_host(self, node_id: str) -> str:
            assert node_id == "gpu-177"
            return "allbot-gpu-177"

        def _protected_node_containers(self, node_id: str) -> set[str]:
            assert node_id == "gpu-177"
            return {"allbot-lan-aio-gpu-177-gpu0-wan22_video_v2-prod"}

        def _run_remote_root_script(self, host: str, script: str) -> str:
            raise AssertionError("remote mutation must not run")

    ops = RecordingOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )

    with pytest.raises(RuntimeError, match="protected current container"):
        ops.node_storage_gc(
            node_id="gpu-177",
            remove_containers=[
                "allbot-lan-aio-gpu-177-gpu0-wan22_video_v2-prod"
            ],
            remove_workspaces=[],
            prune_unused_images=False,
            prune_dangling_volumes=False,
            execute=True,
        )


def test_node_storage_gc_rejects_workspace_outside_exact_node_root():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )

    with pytest.raises(RuntimeError, match="unsafe workspace path"):
        ops.node_storage_gc(
            node_id="gpu-177",
            remove_containers=[],
            remove_workspaces=[
                "/srv/allbot/runpod-runtime/slots/gpu-252-gpu0/profiles/scail2/workspace"
            ],
            prune_unused_images=False,
            prune_dangling_volumes=False,
            execute=False,
        )


def test_node_storage_gc_dry_run_uses_exact_targets_and_reports_candidates():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.script = ""

        def _node_storage_gc_host(self, node_id: str) -> str:
            return "allbot-gpu-177"

        def _protected_node_containers(self, node_id: str) -> set[str]:
            return {"allbot-lan-aio-gpu-177-gpu0-wan22_video_v2-prod"}

        def _run_remote_root_script(self, host: str, script: str) -> str:
            assert host == "allbot-gpu-177"
            self.script = script
            return (
                'ALLBOT_NODE_STORAGE_GC_RESULT={"bytes_before":850000000000,'
                '"bytes_after":850000000000,"containers":["old-scail"],'
                '"workspaces":[{"path":"/srv/allbot/runpod-runtime/slots/'
                'gpu-177-gpu0/profiles/scail2/workspace","bytes":28000000000}],'
                '"unused_images":["sha256:old"],"dangling_volumes":["old-volume"]}'
            )

    ops = RecordingOps()
    result = ops.node_storage_gc(
        node_id="gpu-177",
        remove_containers=["allbot-lan-aio-gpu-177-gpu0-scail2-prod"],
        remove_workspaces=[
            "/srv/allbot/runpod-runtime/slots/gpu-177-gpu0/profiles/scail2/workspace"
        ],
        prune_unused_images=True,
        prune_dangling_volumes=True,
        execute=False,
    )

    assert result["dry_run"] is True
    assert result["containers"] == ["old-scail"]
    assert result["unused_images"] == ["sha256:old"]
    assert "allbot-lan-aio-gpu-177-gpu0-scail2-prod" in ops.script
    assert "/profiles/scail2/workspace" in ops.script
    assert "execute=0" in ops.script
    assert "rm -rf" not in ops.script


def test_node_storage_gc_requires_explicit_builders_for_build_cache_pruning():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.script = ""

        def _node_storage_gc_host(self, node_id: str) -> str:
            assert node_id == "gpu-115"
            return "__local__"

        def _protected_node_containers(self, node_id: str) -> set[str]:
            return set()

        def _run_remote_root_script(self, host: str, script: str) -> str:
            assert host == "__local__"
            self.script = script
            return (
                'ALLBOT_NODE_STORAGE_GC_RESULT={"bytes_before":1000,'
                '"bytes_after":1000,"containers":[],"workspaces":[],'
                '"unused_images":[],"dangling_volumes":[],'
                '"build_cache_builders":["allbot-lan-insecure"]}'
            )

    ops = RecordingOps()
    result = ops.node_storage_gc(
        node_id="gpu-115",
        remove_containers=[],
        remove_workspaces=[],
        prune_unused_images=False,
        prune_dangling_volumes=False,
        prune_build_cache_builders=["allbot-lan-insecure"],
        execute=False,
    )

    assert result["build_cache_builders"] == ["allbot-lan-insecure"]
    assert '"prune_build_cache_builders": ["allbot-lan-insecure"]' in ops.script
    assert 'run("docker", "buildx", "prune", "--builder", builder, "-a", "-f")' in ops.script


def test_node_storage_gc_rejects_unsafe_build_cache_builder_name():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )

    with pytest.raises(RuntimeError, match="unsafe buildx builder"):
        ops.node_storage_gc(
            node_id="gpu-115",
            remove_containers=[],
            remove_workspaces=[],
            prune_unused_images=False,
            prune_dangling_volumes=False,
            prune_build_cache_builders=["builder;docker system prune"],
            execute=False,
        )


def test_node_storage_gc_execute_is_audited_and_preserves_current_identity(tmp_path):
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
                state_dir=tmp_path / "state",
            )
            self.live_checks = 0

        def _node_physical_slots(self, node_id: str) -> set[str]:
            assert node_id == "gpu-177"
            return {"gpu-177:gpu0", "gpu-177:gpu1"}

        def live_current_snapshot(self, physical_slots):
            assert physical_slots == {"gpu-177:gpu0", "gpu-177:gpu1"}
            self.live_checks += 1
            return {
                "current": {
                    "gpu-177:gpu0": "gpu-177-gpu0-wan22_video_v2",
                    "gpu-177:gpu1": "gpu-177-gpu1-minimax_h3_test",
                },
                "errors": {},
            }

    ops = RecordingOps()
    result = ops.execute_node_storage_mutation(
        node_id="gpu-177",
        operation_id="node-storage-gc-test",
        execute=lambda: {
            "ok": True,
            "action": "node-storage-gc",
            "node_id": "gpu-177",
            "dry_run": False,
        },
    )

    history = json.loads(
        (ops.state_store.history_dir / "node-storage-gc-test.json").read_text(
            encoding="utf-8"
        )
    )
    assert result["operation_id"] == "node-storage-gc-test"
    assert ops.live_checks == 2
    assert history["status"] == "succeeded"
    assert history["result"]["live_after"] == {
        "gpu-177:gpu0": "gpu-177-gpu0-wan22_video_v2",
        "gpu-177:gpu1": "gpu-177-gpu1-minimax_h3_test",
    }


def test_lan_aio_start_disabled_force_recreates_container():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.compose_ops: list[str] = []
            self.env_values.update(
                {
                    "LAN_AIO_AGENT_SECRET_TOKEN": "test-token",
                    "LAN_AIO_MINIO_ENDPOINT": "minio.example",
                    "LAN_AIO_MINIO_ACCESS_KEY": "minio-access",
                    "LAN_AIO_MINIO_SECRET_KEY": "minio-secret",
                    "LAN_MODEL_CACHE_ACCESS_KEY": "model-access",
                    "LAN_MODEL_CACHE_SECRET_KEY": "model-secret",
                }
            )

        def _set_control(
            self,
            agent_id: str,
            state: str,
            reason: str,
            *,
            ttl_seconds: int | None = None,
        ) -> None:
            return None

        def _sync_runpod_worker(self, slot) -> None:
            return None

        def _scp(self, source: Path, host: str, target: str) -> None:
            return None

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            return ""

        def _remote_compose(self, slot, op: str) -> None:
            self.compose_ops.append(op)

        def _wait_container_health(self, slot) -> None:
            return None

        def _preseed_legacy_hot_caches(self, slot) -> list[dict[str, object]]:
            return []

        def _verify_disabled_heartbeat(self, slot) -> None:
            return None

    ops = RecordingOps()
    slot = ops.slots["gpu-177-gpu0-image_to_video"]

    result = ops.start_disabled([slot])

    assert result["ok"] is True
    assert ops.compose_ops == ["up -d --force-recreate"]


def test_lan_release_rollout_failure_restores_only_selected_slot():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.compose_ops: list[str] = []
            self.controls: list[tuple[str, str]] = []

        def pull_image(self, slots):
            return {"ok": True}

        def _set_control(self, agent_id, state, reason, *, ttl_seconds=None):
            self.controls.append((state, reason))

        def _wait_worker_ids_idle(self, agent_ids):
            return None

        def _exact_remote_image_ref(self, slot, image_ref):
            assert "@sha256:" in image_ref
            return image_ref

        def _write_remote_runtime_files(self, slot):
            return None

        def _remote_compose(self, slot, op):
            self.compose_ops.append(op)

        def _wait_container_health(self, slot):
            return None

        def _verify_release_runtime(self, slot, resolved):
            raise RuntimeError("target revision mismatch")

        def _verify_exact_runtime_ref(self, slot, image_ref):
            assert image_ref == old_ref

        def _verify_disabled_heartbeat(self, slot):
            return None

    ops = RecordingOps()
    slot = ops.slots["gpu-252-gpu0-i2i_pro"]
    old_ref = ops.config.profiles["i2i_pro"].all_in_one_image_ref
    resolved = {
        "profile": "i2i_pro",
        "ref": "ghcr.io/giraffu/allbot-gpu-i2i-pro@sha256:" + "1" * 64,
        "digest": "sha256:" + "1" * 64,
        "oci_revision": "a" * 40,
        "model_manifest_key": "i2i_pro/release/manifest.json",
        "validation_level": "attested",
    }

    with pytest.raises(RuntimeError, match="old image was restored"):
        ops.release_rollout(slot, resolved)

    assert old_ref is not None and "@sha256:" in old_ref
    assert ops.config.profiles["i2i_pro"].all_in_one_image_ref == old_ref
    assert ops.compose_ops == ["up -d --force-recreate"] * 2
    assert ops.controls[-1] == (
        "enabled",
        "lan_aio_release_rollout_rollback_complete",
    )


def test_lan_release_rollout_accepts_explicit_exact_rollback_ref():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.verified_rollback_ref = None
            self.pulled_refs = []
            self.verified_target_ref = None

        def pull_image(self, slots):
            self.pulled_refs.append(
                self.config.profiles[slots[0].target_profile_id].all_in_one_image_ref
            )
            return {"ok": True}

        def _set_control(self, agent_id, state, reason, *, ttl_seconds=None):
            return None

        def _wait_worker_ids_idle(self, agent_ids):
            return None

        def _exact_remote_image_ref(self, slot, image_ref):
            raise AssertionError("explicit rollback ref must bypass legacy tag lookup")

        def _write_remote_runtime_files(self, slot):
            return None

        def _remote_compose(self, slot, op):
            return None

        def _wait_container_health(self, slot):
            return None

        def _verify_release_runtime(self, slot, resolved):
            self.verified_target_ref = resolved["ref"]
            raise RuntimeError("target revision mismatch")

        def _verify_exact_runtime_ref(self, slot, image_ref):
            self.verified_rollback_ref = image_ref

        def _verify_disabled_heartbeat(self, slot):
            return None

    ops = RecordingOps()
    slot = ops.slots["gpu-177-gpu0-image_to_video"]
    rollback_ref = (
        "192.168.1.115:5000/allbot/comfy-runpod-wan22-aio-video@sha256:"
        + "9" * 64
    )
    resolved = {
        "profile": "image_to_video",
        "ref": "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video@sha256:" + "1" * 64,
        "digest": "sha256:" + "1" * 64,
        "oci_revision": "a" * 40,
        "model_manifest_key": "image_to_video/release/manifest.json",
        "validation_level": "attested",
    }

    with pytest.raises(RuntimeError, match="old image was restored"):
        ops.release_rollout(slot, resolved, rollback_ref=rollback_ref)

    assert ops.verified_rollback_ref == rollback_ref
    expected_target_ref = (
        "192.168.1.115:5000/allbot/comfy-runpod-wan22-aio-video@sha256:"
        + "1" * 64
    )
    assert ops.pulled_refs == [rollback_ref, expected_target_ref]
    assert ops.verified_target_ref == expected_target_ref


def test_lan_release_rollout_accepts_img2img_artifact_for_lora_slot():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.verified_target_ref = None

        def pull_image(self, slots):
            return {"ok": True}

        def _set_control(self, agent_id, state, reason, *, ttl_seconds=None):
            return None

        def _wait_worker_ids_idle(self, agent_ids):
            return None

        def _write_remote_runtime_files(self, slot):
            return None

        def _remote_compose(self, slot, op):
            return None

        def _wait_container_health(self, slot):
            return None

        def _verify_release_runtime(self, slot, resolved):
            self.verified_target_ref = resolved["ref"]

        def _verify_disabled_heartbeat(self, slot):
            return None

    ops = RecordingOps()
    slot = ops.slots["gpu-252-gpu1-img2img_lora"]
    rollback_ref = (
        "192.168.1.115:5000/allbot/comfy-runpod-img2img@sha256:" + "9" * 64
    )
    resolved = {
        "profile": "img2img",
        "ref": "ghcr.io/giraffu/allbot-comfy-runpod-img2img@sha256:" + "1" * 64,
        "digest": "sha256:" + "1" * 64,
        "oci_revision": "a" * 40,
        "model_manifest_key": "img2img/release/manifest.json",
        "validation_level": "attested",
    }

    result = ops.release_rollout(slot, resolved, rollback_ref=rollback_ref)

    assert result["ok"] is True
    assert ops.verified_target_ref == (
        "192.168.1.115:5000/allbot/comfy-runpod-img2img@sha256:" + "1" * 64
    )


@pytest.mark.parametrize(
    "rollback_ref, error",
    [
        (
            "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:mutable",
            "exact digest-pinned",
        ),
        (
            "ghcr.io/giraffu/allbot/different-image@sha256:" + "9" * 64,
            "same repository",
        ),
    ],
)
def test_lan_release_rollout_rejects_unsafe_explicit_rollback_ref(rollback_ref, error):
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-177-gpu0-image_to_video"]
    resolved = {
        "profile": "image_to_video",
        "ref": "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video@sha256:" + "1" * 64,
        "digest": "sha256:" + "1" * 64,
        "oci_revision": "a" * 40,
        "model_manifest_key": "image_to_video/release/manifest.json",
        "validation_level": "attested",
    }

    with pytest.raises(RuntimeError, match=error):
        ops.release_rollout(slot, resolved, rollback_ref=rollback_ref)


def test_bf16_release_and_rollback_verify_versioned_pipeline_contract():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.commands: list[str] = []

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            self.commands.append(command)
            return ""

    ops = RecordingOps()
    slot = ops.slots["gpu-226-gpu0-pornmaster_flux2_edit_bf16"]
    digest = "sha256:" + "1" * 64
    image_ref = f"192.168.1.115:5000/allbot/pornmaster@{digest}"

    ops._verify_release_runtime(
        slot,
        {
            "ref": image_ref,
            "oci_revision": "a" * 40,
        },
    )
    ops._verify_exact_runtime_ref(slot, image_ref)

    assert len(ops.commands) == 2
    for command in ops.commands:
        assert "PIPELINE_PROFILE_POLICY=image_claim3_comfy2_delivery1_v1" in command
        assert "PIPELINE_MAX_RUNNING_TASKS=1" in command
        assert "PIPELINE_MAX_CLAIMED_TASKS=2" in command
        assert "PIPELINE_DELIVERY_CONCURRENCY=1" in command


def test_lan_aio_start_disabled_removes_safe_exited_target_container():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.compose_ops: list[str] = []
            self.removed: list[str] = []
            self.env_values.update(
                {
                    "LAN_AIO_AGENT_SECRET_TOKEN": "test-token",
                    "LAN_AIO_MINIO_ENDPOINT": "minio.example",
                    "LAN_AIO_MINIO_ACCESS_KEY": "minio-access",
                    "LAN_AIO_MINIO_SECRET_KEY": "minio-secret",
                    "LAN_MODEL_CACHE_ACCESS_KEY": "model-access",
                    "LAN_MODEL_CACHE_SECRET_KEY": "model-secret",
                }
            )

        def _set_control(
            self,
            agent_id: str,
            state: str,
            reason: str,
            *,
            ttl_seconds: int | None = None,
        ) -> None:
            return None

        def _sync_runpod_worker(self, slot) -> None:
            return None

        def _scp(self, source: Path, host: str, target: str) -> None:
            return None

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            return ""

        def _remote_target_container_state(self, slot) -> dict[str, object]:
            return {
                "exists": True,
                "name": slot.container_name,
                "status": "exited",
                "running": False,
            }

        def _remove_remote_container(self, slot, container_name: str) -> None:
            self.removed.append(container_name)

        def _remote_compose(self, slot, op: str) -> None:
            self.compose_ops.append(op)

        def _wait_container_health(self, slot) -> None:
            return None

        def _preseed_legacy_hot_caches(self, slot) -> list[dict[str, object]]:
            return []

        def _verify_disabled_heartbeat(self, slot) -> None:
            return None

    ops = RecordingOps()
    slot = ops.slots["gpu-252-gpu0-img2img_lora"]

    result = ops.start_disabled([slot])

    assert result["ok"] is True
    assert result["stale_target_container"] == {
        "status": "removed",
        "container_name": slot.container_name,
        "previous_state": "exited",
    }
    assert ops.removed == [slot.container_name]
    assert ops.compose_ops == ["up -d --force-recreate"]


def test_lan_aio_preflight_blocks_unexpected_host_port_owner():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )

        def _http_ok(self, url: str) -> None:
            return None

        def _remote_check(self, slot, name: str, command: str, **kwargs):
            return {"name": name, "ok": True, "output": "ok"}

        def _image_readiness_check(self, slot, image_ref):
            return {"name": "docker_registry_or_image_present", "ok": True}

        def _remote_published_port_owners(self, slot, host_port: int):
            return [
                {
                    "name": "rogue-gpu002-gpu1-owner",
                    "ports": "0.0.0.0:8191->8188/tcp",
                }
            ]

    ops = RecordingOps()
    slot = ops.slots["gpu-002-gpu1-image_to_video"]

    payload = ops.preflight_payload([slot], execute=True)

    slot_checks = payload["slots"][0]["checks"]
    port_check = next(
        check for check in slot_checks if check["name"] == "host_port_owner"
    )
    assert payload["ok"] is False
    assert port_check["ok"] is False
    assert port_check["allowed_containers"] == [
        "allbot-lan-aio-gpu-002-gpu1-i2i_pro-prod",
        "allbot-lan-aio-gpu-002-gpu1-image_to_video-prod",
    ]
    assert port_check["unexpected_owners"] == [
        {
            "name": "rogue-gpu002-gpu1-owner",
            "ports": "0.0.0.0:8191->8188/tcp",
        }
    ]


def test_lan_aio_status_lists_unexpected_host_port_owner():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            return "allbot-lan-aio-gpu-002-gpu1-pornmaster-flux2-edit-prod Created"

        def _remote_published_port_owners(self, slot, host_port: int):
            return [
                {
                    "name": "allbot-lan-aio-gpu-002-gpu1-image_to_video-prod",
                    "ports": "0.0.0.0:8191->8188/tcp",
                    "status": "Up 10 hours (healthy)",
                }
            ]

    ops = RecordingOps()
    slot = ops.slots["gpu-002-gpu1-image_to_video"]

    lines = ops._remote_container_status(slot)

    assert lines == [
        "allbot-lan-aio-gpu-002-gpu1-pornmaster-flux2-edit-prod Created",
        (
            "allbot-lan-aio-gpu-002-gpu1-image_to_video-prod "
            "Up 10 hours (healthy) 0.0.0.0:8191->8188/tcp host_port_owner"
        ),
    ]


def test_lan_aio_start_disabled_refuses_lingering_host_port_owner():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.env_values.update(
                {
                    "LAN_AIO_AGENT_SECRET_TOKEN": "test-token",
                    "LAN_AIO_MINIO_ENDPOINT": "minio.example",
                    "LAN_AIO_MINIO_ACCESS_KEY": "minio-access",
                    "LAN_AIO_MINIO_SECRET_KEY": "minio-secret",
                    "LAN_MODEL_CACHE_ACCESS_KEY": "model-access",
                    "LAN_MODEL_CACHE_SECRET_KEY": "model-secret",
                }
            )

        def _set_control(
            self,
            agent_id: str,
            state: str,
            reason: str,
            *,
            ttl_seconds: int | None = None,
        ) -> None:
            return None

        def _sync_runpod_worker(self, slot) -> None:
            return None

        def _scp(self, source: Path, host: str, target: str) -> None:
            return None

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            return ""

        def _remote_target_container_state(self, slot) -> dict[str, object]:
            return {
                "exists": False,
                "name": slot.container_name,
                "status": "missing",
                "running": False,
            }

        def _remote_published_port_owners(self, slot, host_port: int):
            return [
                {
                    "name": "allbot-lan-aio-gpu-002-gpu1-image_to_video-prod",
                    "ports": "0.0.0.0:8191->8188/tcp",
                }
            ]

        def _remote_compose(self, slot, op: str) -> None:
            raise AssertionError("compose must not run while host port is occupied")

    ops = RecordingOps()
    slot = ops.slots["gpu-002-gpu1-image_to_video"]

    with pytest.raises(RuntimeError, match="host port 8191.*image_to_video-prod"):
        ops.start_disabled([slot])


def test_lan_aio_start_disabled_blocks_running_target_container():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.env_values.update(
                {
                    "LAN_AIO_AGENT_SECRET_TOKEN": "test-token",
                    "LAN_AIO_MINIO_ENDPOINT": "minio.example",
                    "LAN_AIO_MINIO_ACCESS_KEY": "minio-access",
                    "LAN_AIO_MINIO_SECRET_KEY": "minio-secret",
                    "LAN_MODEL_CACHE_ACCESS_KEY": "model-access",
                    "LAN_MODEL_CACHE_SECRET_KEY": "model-secret",
                }
            )

        def _set_control(
            self,
            agent_id: str,
            state: str,
            reason: str,
            *,
            ttl_seconds: int | None = None,
        ) -> None:
            return None

        def _sync_runpod_worker(self, slot) -> None:
            return None

        def _scp(self, source: Path, host: str, target: str) -> None:
            return None

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            return ""

        def _remote_target_container_state(self, slot) -> dict[str, object]:
            return {
                "exists": True,
                "name": slot.container_name,
                "status": "running",
                "running": True,
            }

        def _remote_compose(self, slot, op: str) -> None:
            raise AssertionError(
                "compose must not run when target container is running"
            )

    ops = RecordingOps()
    slot = ops.slots["gpu-252-gpu0-img2img_lora"]

    with pytest.raises(RuntimeError, match="target container already exists"):
        ops.start_disabled([slot])


def test_lan_aio_takeover_rolls_back_after_stop_old_failure_window():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.steps: list[str] = []

        def preflight_payload(self, slots, *, execute: bool):
            self.steps.append("preflight")
            return {"ok": True}

        def pull_image(self, slots):
            self.steps.append("pull-image")
            return {"ok": True}

        def warm_cache(self, slots):
            self.steps.append("warm-cache")
            return {"ok": True}

        def drain_legacy(self, slots):
            self.steps.append("drain-legacy")
            return {"ok": True}

        def wait_idle(self, slots):
            self.steps.append("wait-idle")
            return {"ok": True}

        def stop_old(self, slots):
            self.steps.append("stop-old")
            return {"ok": True}

        def start_disabled(self, slots):
            self.steps.append("start-disabled")
            raise RuntimeError("container name conflict")

        def rollback(self, slots):
            self.steps.append("rollback")
            return {"ok": True, "recovery_status": "succeeded"}

    ops = RecordingOps()
    slot = ops.slots["gpu-252-gpu0-img2img_lora"]

    with pytest.raises(RuntimeError, match="recovery_status=succeeded"):
        ops.takeover([slot])

    assert ops.steps == [
        "preflight",
        "pull-image",
        "warm-cache",
        "drain-legacy",
        "wait-idle",
        "stop-old",
        "start-disabled",
        "rollback",
    ]


def test_lan_aio_candidate_plan_generates_stable_yaml_patch(tmp_path):
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
        state_dir=tmp_path / "state",
    )

    payload = ops.candidate_plan(
        node_id="gpu-252",
        profile="image_to_video",
        replace_slot_id="gpu-252-gpu0-i2i_pro",
    )

    assert payload["ok"] is True
    assert payload["action"] == "candidate-plan"
    assert payload["candidate_slot"]["id"] == "gpu-252-gpu0-image_to_video"
    assert payload["candidate_slot"]["host_port"] == 8192
    assert payload["candidate_slot"]["target_task_types"] == [
        "video_insert",
        "video_edit",
        "image_to_video",
    ]
    assert payload["candidate_slot"]["agent_id"] == (
        "lan_aio_prod_gpu252_gpu0_image_to_video_01"
    )
    assert "old_runtime_container" not in payload["candidate_slot"]
    assert "legacy_worker_id" not in payload["candidate_slot"]
    assert (
        payload["candidate_slot"]["gpu_device_id"]
        == "GPU-09b7ea85-23df-a9b8-19d9-703534e47666"
    )
    assert payload["render_summary"]["model_manifest_key"] == (
        "image_to_video/2026-07-18-lora5/manifest.json"
    )
    assert "target_profile_id: image_to_video" in payload["yaml_patch"]
    assert "enabled: false" in payload["yaml_patch"]
    assert "retargetable: true" in payload["yaml_patch"]


def test_gpu226_pornmaster_bf16_rollback_slot_keeps_isolated_manifest():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )

    slot = load_lan_aio_prod_slots(include_disabled=True)[
        "gpu-226-gpu0-pornmaster_flux2_edit_bf16"
    ]
    profile = ops.config.profiles[slot.target_profile_id]

    assert slot.enabled is True
    assert slot.phase == "catalog_ready"
    assert slot.retargetable is True
    assert slot.target_task_types == (
        "pornmaster_flux2_edit_bf16",
        "pornmaster_flux2_multi_edit_bf16",
    )
    assert profile.image_ref.endswith(
        "comfy-runpod-pornmaster-flux2-edit:"
        "20260628-pornmaster-flux2-edit-cu128-smallvae1"
    )
    assert profile.model_manifest_key == (
        "pornmaster_flux2_edit_bf16/2026-07-12/manifest.json"
    )


def test_disabled_heartbeat_accepts_declared_runtime_profile_for_bf16_candidate(
    monkeypatch,
):
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = load_lan_aio_prod_slots(include_disabled=True)[
        "gpu-226-gpu0-pornmaster_flux2_edit_bf16"
    ]
    monkeypatch.setattr(ops, "_control_state", lambda _agent_id: "disabled")
    monkeypatch.setattr(
        ops,
        "_system_workers",
        lambda: [
            {
                "agent_id": slot.agent_id,
                "status": "idle",
                "current_task_type": None,
                "node_id": "gpu-226",
                "provider": "lan_ssh",
                "runtime_profile": "pornmaster_flux2_edit",
                "pool_managed": True,
            }
        ],
    )

    ops._verify_disabled_heartbeat(slot)


def test_lan_aio_candidate_plan_rejects_disabled_gpu252_wan22_target(tmp_path):
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
        state_dir=tmp_path / "state",
    )

    with pytest.raises(RuntimeError, match="not an enabled current slot"):
        ops.candidate_plan(
            node_id="gpu-252",
            profile="scail2",
            replace_slot_id="gpu-252-gpu1-wan22_video_v2",
        )


def test_lan_aio_warm_cache_runs_one_off_model_sync_without_agent_or_ports():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.commands: list[str] = []
            self.marker: dict[str, object] | None = None
            self.env_values.update(
                {
                    "LAN_AIO_AGENT_SECRET_TOKEN": "test-token",
                    "LAN_AIO_MINIO_ENDPOINT": "minio.example",
                    "LAN_AIO_MINIO_ACCESS_KEY": "minio-access",
                    "LAN_AIO_MINIO_SECRET_KEY": "minio-secret",
                    "LAN_MODEL_CACHE_ACCESS_KEY": "model-access",
                    "LAN_MODEL_CACHE_SECRET_KEY": "model-secret",
                }
            )

        def _sync_runpod_worker(self, slot) -> None:
            return None

        def _scp(self, source: Path, host: str, target: str) -> None:
            return None

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            self.commands.append(command)
            return ""

        def _write_cache_marker(self, slot, marker: dict[str, object]) -> None:
            self.marker = marker

    ops = RecordingOps()
    slot = ops.slots["gpu-226-gpu0-all"]

    result = ops.warm_cache([slot])

    assert result["ok"] is True
    assert result["action"] == "warm-cache"
    docker_command = next(
        command for command in ops.commands if "docker run" in command
    )
    docker_run_line = next(
        line.strip()
        for line in docker_command.splitlines()
        if line.strip().startswith("docker run")
    )
    assert "docker run --rm" in docker_run_line
    assert "--env-file" in docker_run_line
    assert "RUNPOD_MODEL_DOWNLOAD_CONCURRENCY=8" in docker_run_line
    assert "runpod_sync_models_from_r2.py" in docker_command
    assert " -p " not in docker_run_line
    assert "--publish" not in docker_run_line
    assert "AGENT_ID" not in docker_run_line
    assert (
        "-v /home/ubantu/allbot-runpod-runtime/slots/gpu-226-gpu0/profiles/"
        "all/workspace/ComfyUI/models:/opt/ComfyUI/models"
    ) in docker_run_line
    assert (
        "find /home/ubantu/allbot-runpod-runtime/slots/gpu-226-gpu0/profiles/"
        "all/workspace/ComfyUI/models -type f -print -quit"
    ) in docker_command
    assert ops.marker is not None
    assert ops.marker["profile"] == "all"
    assert ops.marker["physical_slot_key"] == "gpu-226:gpu0"


def test_lan_local_model_token_uses_ephemeral_remote_env_file_not_command_line():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.commands: list[str] = []
            self.copies: list[tuple[str, str]] = []
            self.env_values.update(
                {
                    "LAN_AIO_AGENT_SECRET_TOKEN": "test-token",
                    "LAN_AIO_MINIO_ENDPOINT": "minio.example",
                    "LAN_AIO_MINIO_ACCESS_KEY": "minio-access",
                    "LAN_AIO_MINIO_SECRET_KEY": "minio-secret",
                    "LAN_MODEL_CACHE_ACCESS_KEY": "model-access",
                    "LAN_MODEL_CACHE_SECRET_KEY": "model-secret",
                    "CIVITAI_API_TOKEN": "must-not-appear-in-command",
                }
            )

        def _sync_runpod_worker(self, slot) -> None:
            return None

        def _scp(self, source: Path, host: str, target: str) -> None:
            self.copies.append((source.read_text(encoding="utf-8"), target))

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            self.commands.append(command)
            return ""

        def _write_cache_marker(self, slot, marker: dict[str, object]) -> None:
            return None

    ops = RecordingOps()
    ops.warm_cache([ops.slots["gpu-177-gpu0-wan22_video_v2"]])

    assert all("must-not-appear-in-command" not in command for command in ops.commands)
    secret_copy = next(copy for copy in ops.copies if "CIVITAI_API_TOKEN=" in copy[0])
    assert secret_copy[1].endswith("/.env.local-model-download")
    assert any(
        "rm -f" in command and secret_copy[1] in command for command in ops.commands
    )


def test_lan_aio_warm_cache_can_prepare_root_owned_retarget_workspace():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.commands: list[str] = []
            self.env_values.update(
                {
                    "LAN_AIO_AGENT_SECRET_TOKEN": "test-token",
                    "LAN_AIO_MINIO_ENDPOINT": "minio.example",
                    "LAN_AIO_MINIO_ACCESS_KEY": "minio-access",
                    "LAN_AIO_MINIO_SECRET_KEY": "minio-secret",
                    "LAN_MODEL_CACHE_ACCESS_KEY": "model-access",
                    "LAN_MODEL_CACHE_SECRET_KEY": "model-secret",
                }
            )

        def _sync_runpod_worker(self, slot) -> None:
            return None

        def _scp(self, source: Path, host: str, target: str) -> None:
            return None

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            self.commands.append(command)
            return ""

        def _write_cache_marker(self, slot, marker: dict[str, object]) -> None:
            return None

    ops = RecordingOps()
    candidate = ops.slots["gpu-177-gpu1-scail2"]
    retargeted = ops.retarget_slot(candidate, "gpu-177-gpu1-ltx_video")

    ops.warm_cache([retargeted])

    docker_command = next(
        command for command in ops.commands if "docker run" in command
    )
    assert (
        "if ! mkdir -p /srv/allbot/runpod-runtime/slots/gpu-177-gpu1/profiles/"
        "scail2-b2587e56/workspace/ComfyUI/models || ! test -w "
        "/srv/allbot/runpod-runtime/slots/gpu-177-gpu1/profiles/"
        "scail2-b2587e56/workspace/ComfyUI/models; then docker run --rm"
    ) in docker_command
    assert (
        "-v "
        "/srv/allbot/runpod-runtime/slots/gpu-177-gpu1/profiles/scail2-b2587e56:"
        "/srv/allbot/runpod-runtime/slots/gpu-177-gpu1/profiles/scail2-b2587e56 "
    ) in docker_command
    assert "host_uid=$(id -u)" in docker_command
    assert "host_gid=$(id -g)" in docker_command
    assert "ALLBOT_HOST_UID=$host_uid" in docker_command
    assert "ALLBOT_HOST_GID=$host_gid" in docker_command
    assert (
        'chown -R "$ALLBOT_HOST_UID:$ALLBOT_HOST_GID" '
        "/srv/allbot/runpod-runtime/slots/gpu-177-gpu1/profiles/"
        "scail2-b2587e56/workspace"
    ) in docker_command
    assert (
        "test -w /srv/allbot/runpod-runtime/slots/gpu-177-gpu1/profiles/"
        "scail2-b2587e56/workspace/ComfyUI/models"
    ) in docker_command
    assert (
        "test -w /srv/allbot/runpod-runtime/slots/gpu-177-gpu1/profiles/"
        "scail2/workspace/ComfyUI/models"
    ) not in docker_command
    assert (
        "-v /srv/allbot/runpod-runtime/slots/gpu-177-gpu1/profiles/scail2/"
        "workspace/ComfyUI/models:/opt/ComfyUI/models"
    ) in docker_command
    assert SCAIL2_BAKED_LAN_IMAGE in docker_command


def test_lan_aio_takeover_runs_single_slot_sequence():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.events: list[str] = []

        def preflight_payload(self, slots, *, execute: bool = False):
            self.events.append(f"preflight:{execute}")
            return {"ok": True, "action": "preflight"}

        def pull_image(self, slots):
            self.events.append("pull-image")
            return {"ok": True, "action": "pull-image"}

        def warm_cache(self, slots):
            self.events.append("warm-cache")
            return {"ok": True, "action": "warm-cache"}

        def drain_legacy(self, slots):
            self.events.append("drain-legacy")
            return {"ok": True, "action": "drain-legacy"}

        def wait_idle(self, slots):
            self.events.append("wait-idle")
            return {"ok": True, "action": "wait-idle"}

        def stop_old(self, slots):
            self.events.append("stop-old")
            return {"ok": True, "action": "stop-old"}

        def start_disabled(self, slots):
            self.events.append("start-disabled")
            return {"ok": True, "action": "start-disabled"}

        def enable_aio(self, slots):
            self.events.append("enable-aio")
            return {"ok": True, "action": "enable-aio"}

    ops = RecordingOps()
    slot = ops.slots["gpu-002-gpu1-image_to_video"]

    result = ops.takeover([slot])

    assert result["ok"] is True
    assert result["action"] == "takeover"
    assert result["slot"] == "gpu-002-gpu1-image_to_video"
    assert [step["action"] for step in result["steps"]] == [
        "preflight",
        "pull-image",
        "warm-cache",
        "drain-legacy",
        "wait-idle",
        "stop-old",
        "start-disabled",
        "enable-aio",
    ]
    assert ops.events == [
        "preflight:True",
        "pull-image",
        "warm-cache",
        "drain-legacy",
        "wait-idle",
        "stop-old",
        "start-disabled",
        "enable-aio",
    ]


def test_lan_aio_disabled_canary_start_never_enables_intake():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.events: list[str] = []

        def preflight_payload(self, slots, *, execute: bool = False):
            self.events.append(f"preflight:{execute}")
            return {"ok": True, "action": "preflight"}

        def pull_image(self, slots):
            self.events.append("pull-image")
            return {"ok": True, "action": "pull-image"}

        def warm_cache(self, slots):
            self.events.append("warm-cache")
            return {"ok": True, "action": "warm-cache"}

        def start_disabled(self, slots):
            self.events.append("start-disabled")
            return {"ok": True, "action": "start-disabled", "slot": slots[0].id}

        def enable_aio(self, slots):  # pragma: no cover - safety tripwire
            raise AssertionError("disabled canary must never enable intake")

    ops = RecordingOps()
    slot = ops.slots["gpu-252-gpu1-ltx_t2v"]

    result = ops.start_disabled_canary([slot])

    assert result["ok"] is True
    assert result["action"] == "canary-start-disabled"
    assert ops.events == [
        "preflight:True",
        "pull-image",
        "warm-cache",
        "start-disabled",
    ]


def test_lan_aio_release_disabled_canary_uses_exact_digest_and_stays_disabled():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.events: list[str] = []

        def start_disabled_canary(self, slots):
            profile = self.config.profiles[slots[0].target_profile_id]
            self.events.append(f"canary:{profile.all_in_one_image_ref}")
            return {
                "ok": True,
                "action": "canary-start-disabled",
                "slot": slots[0].id,
                "intake": "disabled",
            }

        def _verify_release_runtime(self, slot, resolved):
            self.events.append(f"verify:{resolved['ref']}")

        def enable_aio(self, slots):  # pragma: no cover - safety tripwire
            raise AssertionError("release disabled canary must never enable intake")

    ops = RecordingOps()
    slot = ops.slots["gpu-252-gpu1-face_swap"]
    digest = "sha256:" + "1" * 64
    resolved = {
        "profile": "face_swap",
        "ref": "ghcr.io/giraffu/allbot-gpu-face-swap@" + digest,
        "digest": digest,
        "model_manifest_key": "face_swap_v2/release/manifest.json",
        "oci_revision": "a" * 40,
    }

    result = ops.start_release_disabled_canary(slot, resolved)

    assert result["ok"] is True
    assert result["action"] == "release-canary-start-disabled"
    assert result["intake"] == "disabled"
    assert result["target_ref"] == resolved["ref"]
    assert ops.events == [
        f"canary:{resolved['ref']}",
        f"verify:{resolved['ref']}",
    ]


def test_lan_aio_disabled_canary_stop_waits_for_worker_and_comfy_idle():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.events: list[str] = []

        def disable_aio(self, slots):
            self.events.append("disable-aio")
            return {"ok": True, "action": "disable-aio"}

        def _wait_worker_ids_idle(self, targets):
            self.events.append("worker-idle")

        def _verify_comfy_queue_idle(self, slot):
            self.events.append("comfy-idle")

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            if "docker update" in command:
                self.events.append("restart-disabled")
            else:
                assert "docker stop" in command
                self.events.append("docker-stop")
            return ""

    ops = RecordingOps()
    slot = ops.slots["gpu-252-gpu1-ltx_t2v"]

    result = ops.stop_disabled_canary([slot])

    assert result["ok"] is True
    assert result["action"] == "canary-stop-disabled"
    assert ops.events == [
        "disable-aio",
        "worker-idle",
        "comfy-idle",
        "restart-disabled",
        "docker-stop",
    ]


@pytest.mark.parametrize("worker_status", ["quarantined", "error", None])
def test_lan_aio_quarantined_slot_isolation_stops_without_comfy_queue(
    worker_status,
):
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.events: list[str] = []

        def _system_workers(self):
            if worker_status is None:
                return []
            return [
                {
                    "agent_id": "lan_aio_prod_gpu252_gpu1_img2img_lora_01",
                    "status": worker_status,
                    "current_task_id": None,
                    "current_task_type": None,
                }
            ]

        def _control_state(self, agent_id):
            assert agent_id == "lan_aio_prod_gpu252_gpu1_img2img_lora_01"
            return "disabled"

        def _set_control(self, agent_id, state, reason, *, ttl_seconds=None):
            assert agent_id == "lan_aio_prod_gpu252_gpu1_img2img_lora_01"
            assert state == "disabled"
            assert ttl_seconds is None
            self.events.append("persistent-disable")

        def _verify_comfy_queue_idle(self, slot):  # pragma: no cover - tripwire
            raise AssertionError("fault isolation must not depend on dead Comfy")

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            if "docker update --restart=no" in command:
                self.events.append("disable-restart")
                return ""
            if ".HostConfig.RestartPolicy.Name" in command:
                self.events.append("verify-restart-disabled")
                return "no\n"
            if "docker stop" in command:
                self.events.append("docker-stop")
                return ""
            assert "docker inspect" in command
            self.events.append("verify-stopped")
            return "false\n"

    ops = RecordingOps()
    slot = ops.slots["gpu-252-gpu1-img2img_lora"]

    result = ops.isolate_quarantined([slot])

    assert result == {
        "ok": True,
        "action": "isolate-quarantined",
        "slot": "gpu-252-gpu1-img2img_lora",
        "intake": "disabled",
        "container": "stopped",
    }
    assert ops.events == [
        "persistent-disable",
        "disable-restart",
        "verify-restart-disabled",
        "docker-stop",
        "verify-stopped",
    ]


def test_lan_aio_quarantined_isolation_is_a_managed_mutation():
    assert "isolate-quarantined" in MANAGED_MUTATION_ACTIONS


def test_lan_aio_disabled_canary_queue_check_retries_transient_failure():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.attempts = 0
            self.sleeps: list[float] = []

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            self.attempts += 1
            if self.attempts == 1:
                raise subprocess.CalledProcessError(28, command)
            return ""

        def _sleep(self, seconds: float) -> None:
            self.sleeps.append(seconds)

    ops = RecordingOps()

    ops._verify_comfy_queue_idle(ops.slots["gpu-252-gpu1-ltx_t2v"])

    assert ops.attempts == 2
    assert ops.sleeps == [5.0]


def test_lan_aio_takeover_stops_after_failed_preflight(capsys):
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.events: list[str] = []

        def preflight_payload(self, slots, *, execute: bool = False):
            self.events.append("preflight")
            return {
                "ok": False,
                "action": "preflight",
                "checks": [{"name": "lan_registry_health", "ok": False}],
            }

        def pull_image(self, slots):
            self.events.append("pull-image")
            return {"ok": True, "action": "pull-image"}

    ops = RecordingOps()
    slot = ops.slots["gpu-002-gpu1-image_to_video"]

    with pytest.raises(RuntimeError, match="preflight failed"):
        ops.takeover([slot])

    assert ops.events == ["preflight"]
    output = capsys.readouterr().out
    assert "[lan-aio-takeover] preflight failed" in output
    assert "lan_registry_health" in output


def test_lan_aio_preflight_retries_transient_legacy_endpoint_reset():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.stats_attempts = 0
            self.queue_attempts = 0
            self.sleeps: list[float] = []

        def _http_check(self, name: str, url: str) -> dict[str, object]:
            return {"name": name, "ok": True}

        def render_compose(self, slot) -> str:
            return "services: {}\n"

        def _sleep(self, seconds: float) -> None:
            self.sleeps.append(seconds)

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            if "/system_stats" in command:
                self.stats_attempts += 1
                if self.stats_attempts == 1:
                    raise subprocess.CalledProcessError(
                        56,
                        ["ssh", host],
                        stderr="curl: (56) Recv failure: connection reset",
                    )
            if "/queue" in command:
                self.queue_attempts += 1
                if self.queue_attempts == 1:
                    raise subprocess.CalledProcessError(
                        56,
                        ["ssh", host],
                        stderr="curl: (56) Recv failure: connection reset",
                    )
            if command == "df -h / | tail -1":
                return "/dev/nvme0n1p2  915G  324G  546G  38% /"
            return ""

    ops = RecordingOps()
    slot = ops.retarget_slot(
        ops.slots["gpu-177-gpu1-scail2"],
        "gpu-177-gpu1-ltx_video",
    )

    payload = ops.preflight_payload([slot], execute=True)

    assert payload["ok"] is True
    assert ops.stats_attempts == 2
    assert ops.queue_attempts == 2
    assert ops.sleeps == [3.0, 3.0]


def test_lan_aio_preflight_skips_legacy_health_for_intentionally_empty_slot(
    tmp_path: Path,
):
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
                state_dir=tmp_path / "state",
            )
            self.legacy_checks: list[str] = []

        def _http_check(self, name: str, url: str) -> dict[str, object]:
            return {"name": name, "ok": True}

        def render_compose(self, slot) -> str:
            return "services: {}\n"

        def _remote_check(self, slot, name: str, command: str, **kwargs):
            if name.startswith("legacy_"):
                self.legacy_checks.append(name)
            return {"name": name, "ok": True, "output": "ok"}

        def _image_readiness_check(self, slot, image_ref):
            return {"name": "docker_registry_or_image_present", "ok": True}

        def _remote_published_port_owners(self, slot, host_port: int):
            return []

    ops = RecordingOps()
    slot = ops.slots["gpu-226-gpu0-all"]
    ops.state_store.write_current(
        {
            "catalog_sha256": ops.catalog_sha256,
            "physical_slots": {
                "gpu-226:gpu0": {
                    "current": {},
                    "intentionally_empty": {
                        "reason": "disabled canary stopped",
                        "operation_id": "stop-disabled",
                    },
                }
            },
        },
        operation_id="stop-disabled",
    )

    payload = ops.preflight_payload([slot], execute=True)

    assert payload["ok"] is True
    assert ops.legacy_checks == []
    assert payload["slots"][0]["checks"][0] == {
        "name": "legacy_health_skipped_intentionally_empty",
        "ok": True,
        "physical_slot": "gpu-226:gpu0",
    }


@pytest.mark.parametrize("action", ["pull-image", "warm-cache"])
def test_lan_aio_cli_allows_cache_preparation_for_intentionally_empty_slot(
    action: str,
    tmp_path: Path,
    capsys,
):
    state_dir = tmp_path / "state"
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=tmp_path / "missing-prod.env",
        aio_env_file=tmp_path / "missing-aio.env",
        model_env_file=tmp_path / "missing-model.env",
        state_dir=state_dir,
    )
    ops.state_store.write_current(
        {
            "catalog_sha256": ops.catalog_sha256,
            "physical_slots": {
                "gpu-226:gpu0": {
                    "current": {},
                    "intentionally_empty": {
                        "reason": "disabled canary stopped",
                        "operation_id": "stop-disabled",
                    },
                }
            },
        },
        operation_id="stop-disabled",
    )

    result = lan_aio_main(
        [
            action,
            "--slot",
            "gpu-226-gpu0-all",
            "--include-disabled",
            "--state-dir",
            str(state_dir),
            "--prod-env-file",
            str(tmp_path / "missing-prod.env"),
            "--aio-env-file",
            str(tmp_path / "missing-aio.env"),
            "--model-env-file",
            str(tmp_path / "missing-model.env"),
        ]
    )

    assert result == 0
    assert f'"action": "{action}"' in capsys.readouterr().out


def test_lan_aio_takeover_dry_run_shows_full_sequence():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-002-gpu1-image_to_video"]

    payload = ops.dry_run_action("takeover", [slot])

    assert payload["operations"][:8] == [
        "run preflight for gpu-002-gpu1-image_to_video",
        "run pull-image for gpu-002-gpu1-image_to_video",
        "run warm-cache for gpu-002-gpu1-image_to_video",
        "run drain-legacy for gpu-002-gpu1-image_to_video",
        "run wait-idle for gpu-002-gpu1-image_to_video",
        "run stop-old for gpu-002-gpu1-image_to_video",
        "run start-disabled for gpu-002-gpu1-image_to_video",
        "run enable-aio for gpu-002-gpu1-image_to_video",
    ]


def test_lan_aio_recover_physical_slot_can_restore_exact_candidate():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.controls: list[tuple[str, str, str, int | None]] = []
            self.ssh_commands: list[str] = []
            self.started_disabled_slots: list[str] = []

        def _set_control(
            self,
            agent_id: str,
            state: str,
            reason: str,
            *,
            ttl_seconds: int | None = None,
        ) -> None:
            self.controls.append((agent_id, state, reason, ttl_seconds))

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            self.ssh_commands.append(command)
            return ""

        def _remote_target_container_state(self, slot):
            return {
                "exists": False,
                "name": slot.container_name,
                "status": "missing",
                "running": False,
            }

        def start_disabled(self, slots):
            self.started_disabled_slots.extend(slot.id for slot in slots)
            return {"ok": True, "action": "start-disabled", "slot": slots[0].id}

    ops = RecordingOps()

    result = ops.recover_physical_slot(
        physical_slot="gpu-252:gpu0",
        prefer="candidate",
        selected_slot_id="gpu-252-gpu0-image_to_video",
    )

    assert result["ok"] is True
    assert result["action"] == "recover"
    assert result["selected_slot"] == "gpu-252-gpu0-image_to_video"
    assert result["start"]["action"] == "start-disabled"
    assert ops.started_disabled_slots == ["gpu-252-gpu0-image_to_video"]
    assert "docker stop 'allbot-lan-aio-gpu-252-gpu0-img2img_lora-prod'" in "\n".join(
        ops.ssh_commands
    )
    assert any(
        agent_id == "lan_aio_prod_gpu252_gpu0_img2img_lora_01" and state == "disabled"
        for agent_id, state, _reason, _ttl in ops.controls
    )
    assert ops.controls[-1][0] == "lan_aio_prod_gpu252_gpu0_image_to_video_01"
    assert ops.controls[-1][1] == "enabled"


def test_lan_aio_recover_recreates_exited_candidate_with_stale_image():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.started_disabled_slots: list[str] = []
            self.ssh_commands: list[str] = []

        def _set_control(self, *args, **kwargs):
            return None

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            self.ssh_commands.append(command)
            return ""

        def _remote_target_container_state(self, slot):
            return {
                "exists": True,
                "name": slot.container_name,
                "status": "exited",
                "running": False,
            }

        def _remote_target_container_image_ref(self, slot):
            return "registry.example/wan22:stale"

        def _wait_container_health(self, slot):
            return None

        def _verify_disabled_heartbeat(self, slot):
            return None

        def start_disabled(self, slots):
            self.started_disabled_slots.extend(slot.id for slot in slots)
            return {"ok": True, "action": "start-disabled", "slot": slots[0].id}

    ops = RecordingOps()

    result = ops.recover_physical_slot(
        physical_slot="gpu-252:gpu0",
        prefer="candidate",
        selected_slot_id="gpu-252-gpu0-image_to_video",
    )

    assert result["start"]["action"] == "start-disabled"
    assert ops.started_disabled_slots == ["gpu-252-gpu0-image_to_video"]
    assert not any(
        "docker start 'allbot-lan-aio-gpu-252-gpu0-image_to_video-prod'" in command
        for command in ops.ssh_commands
    )


def test_lan_aio_recover_recreates_exited_candidate_with_current_image():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.started_disabled_slots: list[str] = []
            self.ssh_commands: list[str] = []

        def _set_control(self, *args, **kwargs):
            return None

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            self.ssh_commands.append(command)
            return ""

        def _remote_target_container_state(self, slot):
            return {
                "exists": True,
                "name": slot.container_name,
                "status": "exited",
                "running": False,
            }

        def _remote_target_container_image_ref(self, slot):
            return self.config.profiles[
                slot.target_profile_id
            ].all_in_one_image_ref

        def _wait_container_health(self, slot):
            return None

        def _verify_disabled_heartbeat(self, slot):
            return None

        def start_disabled(self, slots):
            self.started_disabled_slots.extend(slot.id for slot in slots)
            return {"ok": True, "action": "start-disabled", "slot": slots[0].id}

    ops = RecordingOps()

    result = ops.recover_physical_slot(
        physical_slot="gpu-252:gpu0",
        prefer="candidate",
        selected_slot_id="gpu-252-gpu0-image_to_video",
    )

    assert result["start"]["action"] == "start-disabled"
    assert ops.started_disabled_slots == ["gpu-252-gpu0-image_to_video"]
    assert not any(
        "docker start 'allbot-lan-aio-gpu-252-gpu0-image_to_video-prod'" in command
        for command in ops.ssh_commands
    )


def test_lan_aio_recovery_guard_accepts_explicit_slot_from_intentionally_empty_state(
    tmp_path: Path,
):
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
        state_dir=tmp_path / "state",
    )
    ops.state_store.write_current(
        {
            "catalog_sha256": ops.catalog_sha256,
            "physical_slots": {
                "gpu-252:gpu0": {
                    "current": {},
                    "intentionally_empty": {
                        "reason": "failed rollout inspected empty",
                        "operation_id": "reconcile-empty",
                    },
                }
            },
        },
        operation_id="reconcile-empty",
    )

    assert (
        ops.recovery_guard_slot_id(
            "gpu-252:gpu0",
            selected_slot_id="gpu-252-gpu0-image_to_video",
        )
        == "gpu-252-gpu0-image_to_video"
    )


def test_configure_registry_does_not_wait_for_stopped_candidate():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.configured_hosts: list[str] = []
            self.health_waits: list[str] = []

        def _ssh(self, host, command, *, capture=False):
            assert "docker inspect" in command
            return "false\n"

        def _configure_registry_on_host(self, host):
            self.configured_hosts.append(host)

        def _wait_container_health(self, slot):
            self.health_waits.append(slot.id)

    ops = RecordingOps()
    slot = ops.slots["gpu-252-gpu0-i2i_pro"]

    result = ops.configure_registry([slot])

    assert result["ok"] is True
    assert ops.configured_hosts == [slot.ssh_host]
    assert ops.health_waits == []


def test_configure_registry_updates_daemon_proxy_bypass(monkeypatch):
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.input_text = ""
            self.command = []

        def _local(self, args, *, input_text=None, capture=False):
            self.command = args
            self.input_text = input_text or ""
            return ""

    monkeypatch.setenv("LAN_AIO_GPU_SUDO_PASSWORD", "dummy")
    ops = RecordingOps()

    ops._configure_registry_on_host("gpu226")

    assert 'proxies = dict(data.get("proxies") or {})' in ops.input_text
    assert 'proxies.get("no-proxy")' in ops.input_text
    assert 'proxies["no-proxy"] = ",".join(no_proxy)' in ops.input_text
    assert '("192.168.1.115", "192.168.1.115:5000")' in ops.input_text

    ops._configure_registry_on_host("local://")

    assert ops.command == [
        "bash",
        "-lc",
        "IFS= read -r LAN_AIO_GPU_SUDO_PASSWORD; "
        "export LAN_AIO_GPU_SUDO_PASSWORD; bash -s",
    ]


def test_configure_registry_waits_for_previously_running_candidate():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.health_waits: list[str] = []

        def _ssh(self, host, command, *, capture=False):
            assert "docker inspect" in command
            return "true\n"

        def _configure_registry_on_host(self, host):
            return None

        def _wait_container_health(self, slot):
            self.health_waits.append(slot.id)

    ops = RecordingOps()
    slot = ops.slots["gpu-252-gpu0-i2i_pro"]

    result = ops.configure_registry([slot])

    assert result["recovered_running_slots"] == [slot.id]
    assert ops.health_waits == [slot.id]


def test_lan_aio_restart_disables_restarts_and_reenables_slot():
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
            )
            self.controls: list[tuple[str, str, str, int | None]] = []
            self.compose_ops: list[str] = []
            self.events: list[str] = []

        def _set_control(
            self,
            agent_id: str,
            state: str,
            reason: str,
            *,
            ttl_seconds: int | None = None,
        ) -> None:
            self.controls.append((agent_id, state, reason, ttl_seconds))
            self.events.append(f"control:{state}")

        def _remote_compose(self, slot, op: str) -> None:
            self.compose_ops.append(op)
            self.events.append(f"compose:{op}")

        def _write_remote_runtime_files(self, slot) -> None:
            self.events.append("write-runtime")

        def _wait_worker_ids_idle(self, worker_ids) -> None:
            self.events.append(f"wait-idle:{','.join(sorted(worker_ids))}")

        def _host_port_owner_check(self, slot, allowed_containers):
            self.events.append(f"port-owner:{','.join(sorted(allowed_containers))}")
            return {"ok": True}

        def _wait_container_health(self, slot) -> None:
            self.events.append("health")

        def _verify_disabled_heartbeat(self, slot) -> None:
            self.events.append("heartbeat")

    ops = RecordingOps()
    slot = ops.slots["gpu-177-gpu0-image_to_video"]

    result = ops.restart_aio([slot])

    assert result == {
        "ok": True,
        "action": "restart-aio",
        "slot": "gpu-177-gpu0-image_to_video",
    }
    assert ops.compose_ops == ["up -d --force-recreate"]
    assert ops.controls == [
        (
            "lan_aio_prod_gpu177_gpu0_image_to_video_01",
            "disabled",
            "lan_aio_fleet_restart_disable_aio",
            3600,
        ),
        (
            "lan_aio_prod_gpu177_gpu0_image_to_video_01",
            "enabled",
            "lan_aio_fleet_restart_enable_aio",
            None,
        ),
    ]
    assert ops.events == [
        "control:disabled",
        "wait-idle:lan_aio_prod_gpu177_gpu0_image_to_video_01",
        "write-runtime",
        "port-owner:allbot-lan-aio-gpu-177-gpu0-image_to_video-prod",
        "compose:up -d --force-recreate",
        "health",
        "heartbeat",
        "control:enabled",
    ]
