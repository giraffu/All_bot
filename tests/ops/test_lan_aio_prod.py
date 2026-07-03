import json
import subprocess
from pathlib import Path

import pytest

from ops.gpu_pool_controller.config_loader import load_controller_config
from ops.gpu_pool_controller.lan_aio_prod import (
    LanAioProdOps,
    assert_prod_compose,
    load_lan_aio_prod_slots,
    main as lan_aio_main,
    patch_remote_workers_mount,
)
from ops.gpu_pool_controller.runpod_profile_catalog import (
    RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES,
)
from ops.gpu_pool_controller.runtime import (
    LAN_AIO_SCAIL2_WORKFLOW_OVERRIDES,
    RuntimePlanner,
    RuntimeRenderOverrides,
)


def test_lan_aio_prod_slots_cover_next_wave_candidates():
    slots = load_lan_aio_prod_slots()

    assert list(slots) == [
        "gpu-177-gpu0-wan22_video_v2",
        "gpu-177-gpu1-ltx_video",
        "gpu-252-gpu0-pornmaster_flux2_edit",
        "gpu-252-gpu1-wan22_video_v2",
        "gpu-002-gpu0-scail2",
        "gpu-002-gpu1-pornmaster_flux2_edit",
        "gpu-226-gpu0-image_to_video",
    ]
    assert slots["gpu-177-gpu0-wan22_video_v2"].legacy_worker_id == (
        "lan_aio_prod_gpu177_gpu0_image_to_video_01"
    )
    assert slots["gpu-177-gpu0-wan22_video_v2"].target_profile_id == "wan22_video_v2"
    assert slots["gpu-177-gpu0-wan22_video_v2"].target_task_types == (
        "wan22_video_v2",
    )
    assert slots["gpu-177-gpu1-ltx_video"].legacy_worker_id == (
        "lan_aio_prod_gpu177_gpu1_scail2_01"
    )
    assert slots["gpu-252-gpu0-pornmaster_flux2_edit"].agent_id == (
        "lan_aio_prod_gpu252_gpu0_pornmaster_flux2_edit_01"
    )
    assert slots["gpu-252-gpu0-pornmaster_flux2_edit"].legacy_worker_id == (
        "lan_aio_prod_gpu252_gpu0_image_to_video_01"
    )
    assert slots["gpu-252-gpu1-wan22_video_v2"].host_port == 8191
    assert slots["gpu-002-gpu0-scail2"].agent_id == (
        "lan_aio_prod_gpu002_gpu0_scail2_01"
    )
    assert slots["gpu-002-gpu0-scail2"].legacy_worker_id == (
        "lan_aio_prod_gpu002_gpu0_img2img_lora_01"
    )
    assert slots["gpu-002-gpu0-scail2"].target_task_types == (
        "scail2_action_transfer",
        "scail2_action_transfer_long",
        "scail2_video_replacement",
        "scail2_face_swap_v2",
    )
    assert slots["gpu-002-gpu1-pornmaster_flux2_edit"].agent_id == (
        "lan_aio_prod_gpu002_gpu1_pornmaster_flux2_edit_01"
    )
    assert slots["gpu-002-gpu1-pornmaster_flux2_edit"].legacy_worker_id == (
        "lan_aio_prod_gpu002_gpu1_image_to_video_01"
    )
    assert slots["gpu-002-gpu1-pornmaster_flux2_edit"].old_runtime_container == (
        "allbot-lan-aio-gpu-002-gpu1-image_to_video-canary"
    )
    assert slots["gpu-002-gpu1-pornmaster_flux2_edit"].target_task_types == (
        "pornmaster_flux2_single_edit",
        "pornmaster_flux2_multi_edit",
    )
    assert slots["gpu-226-gpu0-image_to_video"].agent_id == (
        "lan_aio_prod_gpu226_gpu0_image_to_video_01"
    )
    assert slots["gpu-226-gpu0-image_to_video"].legacy_worker_id == (
        "cloud_prod_worker_01"
    )


def test_lan_aio_prod_slots_keep_blocked_nodes_disabled_but_visible():
    slots = load_lan_aio_prod_slots(include_disabled=True)

    assert slots["gpu-177-gpu1-ltx_video"].enabled is True
    assert slots["gpu-177-gpu1-ltx_video"].phase == "prod_enabled"
    assert slots["gpu-252-gpu0-img2img_lora"].enabled is False
    assert slots["gpu-252-gpu0-img2img_lora"].phase == (
        "superseded_by_pornmaster_flux2_edit"
    )
    assert slots["gpu-252-gpu0-img2img_lora"].retargetable is True
    assert slots["gpu-002-gpu1-image_to_video"].enabled is False
    assert slots["gpu-002-gpu1-image_to_video"].phase == (
        "superseded_by_pornmaster_flux2_edit"
    )
    assert slots["gpu-002-gpu1-image_to_video"].retargetable is True
    assert slots["gpu-002-gpu1-image_to_video"].legacy_worker_id == (
        "lan_aio_prod_gpu002_gpu1_pornmaster_flux2_edit_01"
    )
    assert slots["gpu-002-gpu1-image_to_video"].old_runtime_container == (
        "allbot-lan-aio-gpu-002-gpu1-pornmaster-flux2-edit-prod"
    )
    assert slots["gpu-177-gpu1-wan22_video_v2"].enabled is False
    assert slots["gpu-177-gpu1-wan22_video_v2"].phase == "blocked_oom_32gb"
    assert slots["gpu-177-gpu1-wan22_video_v2"].retargetable is False
    assert slots["gpu-177-gpu1-wan22_video_v2"].legacy_worker_id == (
        "lan_aio_prod_gpu177_gpu1_ltx_video_01"
    )
    assert slots["gpu-177-gpu1-wan22_video_v2"].old_runtime_container == (
        "allbot-lan-aio-gpu-177-gpu1-ltx_video-prod"
    )
    assert slots["gpu-177-gpu1-scail2"].enabled is False
    assert slots["gpu-177-gpu1-scail2"].phase == "candidate"
    assert slots["gpu-177-gpu1-scail2"].retargetable is True
    assert slots["gpu-177-gpu1-scail2"].target_task_types == (
        "scail2_action_transfer",
        "scail2_action_transfer_long",
        "scail2_video_replacement",
        "scail2_face_swap_v2",
    )
    assert slots["gpu-177-gpu1-scail2"].legacy_worker_id == (
        "lan_aio_prod_gpu177_gpu1_ltx_video_01"
    )
    assert slots["gpu-177-gpu1-scail2"].old_runtime_container == (
        "allbot-lan-aio-gpu-177-gpu1-ltx_video-prod"
    )
    config = load_controller_config()
    assert (
        config.profiles["ltx_video"].all_in_one_image_ref
        == "192.168.1.115:5000/allbot/comfy-runpod-ltx-video:20260618-ltx-min-cu128-sageattn1"
    )
    assert slots["gpu-226-gpu0-face_i2i_t2i"].phase == "blocked_host_service_runtime"


def test_lan_aio_prod_slot_omits_gpu177_retired_hot_cache_copy():
    slot = load_lan_aio_prod_slots()["gpu-177-gpu0-image_to_video"]

    assert slot.legacy_hot_cache_copies == ()
    assert "Legacy worker 02/comfy0 were retired" in slot.notes


def test_lan_aio_prod_slot_declares_gpu252_host_rife_hot_cache_copy():
    slot = load_lan_aio_prod_slots()["gpu-252-gpu1-wan22_video_v2"]

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
    slot = load_lan_aio_prod_slots(include_disabled=True)[
        "gpu-002-gpu1-image_to_video"
    ]

    assert len(slot.legacy_hot_cache_copies) == 1
    hot_cache = slot.legacy_hot_cache_copies[0]
    assert hot_cache.source_container == "__host__"
    assert hot_cache.source_path == (
        "/data/comfy/inst1/custom_nodes/ComfyUI_Fill-Nodes/"
        "nodes/cache/rife_models/rife49.pth"
    )
    assert hot_cache.required is True


def test_lan_aio_fleet_render_patches_remote_workers_mount_for_gpu_252():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-252-gpu0-pornmaster_flux2_edit"]
    rendered = ops.render_compose(slot)

    assert "RUNPOD_ENVIRONMENT: cloud-prod" in rendered
    assert "CENTRAL_API_URL: https://worker-central.aivison.it.com" in rendered
    assert "MINIO_RESULT_BUCKET: user-data-prod" in rendered
    assert (
        "SUPPORTED_TASK_TYPES: pornmaster_flux2_single_edit,"
        "pornmaster_flux2_multi_edit"
    ) in rendered
    assert "POOL_RUNTIME_PROFILE: pornmaster_flux2_edit" in rendered
    assert "host_port: 8192" in rendered
    assert "--disable-dynamic-vram" not in rendered
    assert "cloud-test" not in rendered
    assert "user-data-test" not in rendered
    assert f"AGENT_ID: {slot.agent_id}" in rendered
    assert f"container_name: {slot.container_name}" in rendered
    assert "restart: unless-stopped" in rendered
    assert "RUNPOD_KEEPALIVE_ON_BOOTSTRAP_FAILURE: 'false'" in rendered
    assert "process_supervision: exit_container_when_agent_relay_or_comfy_exits" in rendered
    assert f"{slot.remote_workers_dir}:/workspace/allbot/remote_workers" in rendered
    assert "PYTHONPATH: /workspace/allbot/remote_workers" in rendered
    assert "remote_workers_bundle:" in rendered


def test_lan_aio_stop_old_dry_run_omits_empty_local_agent_container():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-252-gpu0-pornmaster_flux2_edit"]

    payload = ops.dry_run_action("stop-old", [slot])

    assert payload["operations"] == [
        "set lan_aio_prod_gpu252_gpu0_image_to_video_01=disabled",
        "ssh allbot-gpu-252 docker stop allbot-lan-aio-gpu-252-gpu0-image_to_video-prod",
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
    assert "RUNPOD_MODEL_MANIFEST_KEY: image_to_video/2026-06-13-test/manifest.json" in rendered
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
    assert "SUPPORTED_TASK_TYPES: wan22_video_v2,video_edit,image_to_video" not in rendered
    assert "RUNPOD_MODEL_MANIFEST_KEY: wan22_video_v2/2026-06-13-test/manifest.json" in rendered
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

    assert slot.enabled is False
    assert slot.phase == "candidate"
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
    assert slot.phase == "prod_enabled"
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

    retargeted = ops.retarget_slot(candidate, "gpu-177-gpu0-image_to_video")
    rendered = ops.render_compose(retargeted)

    assert retargeted.assignment_id == "lan-177-8188-worker-02"
    assert retargeted.target_profile_id == "scail2"
    assert retargeted.host_port == 8190
    assert retargeted.gpu_index == 0
    assert retargeted.legacy_worker_id == "lan_aio_prod_gpu177_gpu0_image_to_video_01"
    assert retargeted.old_runtime_container == (
        "allbot-lan-aio-gpu-177-gpu0-image_to_video-prod"
    )
    assert retargeted.container_name == (
        "allbot-lan-aio-gpu-177-gpu0-scail2-prod"
    )
    assert "POOL_GPU_INDEX: '0'" in rendered
    assert "NVIDIA_VISIBLE_DEVICES: '0'" in rendered
    assert "POOL_RUNTIME_PROFILE: scail2" in rendered
    assert (
        "SUPPORTED_TASK_TYPES: scail2_action_transfer,scail2_action_transfer_long,"
        "scail2_video_replacement,scail2_face_swap_v2"
    ) in rendered
    assert "host_port: 8190" in rendered


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
    retargeted = ops.retarget_slot(candidate, "gpu-177-gpu0-image_to_video")

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

        def _remote_image_present(self, slot, image_ref: str) -> bool:
            return False

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            if command.startswith("docker pull"):
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
    retargeted = ops.retarget_slot(candidate, "gpu-177-gpu0-image_to_video")

    payload = ops.pull_image([retargeted])

    assert payload["ok"] is True
    assert payload["pulled"][0]["status"] == "loaded_from_runner"
    assert ops.loaded == [
        (
            "gpu-177-gpu1-scail2",
            "192.168.1.115:5000/allbot/comfy-runpod-scail2:20260617-scail2-cu128-a492b2b-proddeps1",
        )
    ]


def test_lan_aio_cli_allows_replace_slot_for_retarget_render(capsys, tmp_path):
    result = lan_aio_main(
        [
            "render",
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

    output = capsys.readouterr().out
    assert result == 0
    assert "host_port: 8190" in output
    assert "POOL_GPU_INDEX: '0'" in output
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
    assert environment["SCAIL2_FACE_SWAP_V10_ENABLED"] == "true"
    assert environment["SCAIL2_FACE_SWAP_V10_FACE_SWAP_COMFY_API_URL"] == (
        "http://192.168.1.226:8188"
    )
    assert (
        environment["SCAIL2_FACE_SWAP_V10_FACE_SWAP_WORKFLOW"]
        == "face_swap_v2.json"
    )


def test_ltx_video_workflow_uses_baked_sageattention():
    for path in (
        Path("workers/comfy_agent/workflows/LTX 2.3 I2V 6.1.json"),
        Path("remote_workers/comfy_agent/workflows/LTX 2.3 I2V 6.1.json"),
    ):
        workflow = json.loads(path.read_text(encoding="utf-8"))

        assert workflow["257"]["inputs"]["sage_attention"] == "auto"

    dockerfile = Path("remote_workers/docker/runpod_profiles/ltx_video/Dockerfile").read_text(
        encoding="utf-8"
    )
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
    assert "NVIDIA_VISIBLE_DEVICES: '1'" in rendered
    assert "SUPPORTED_TASK_TYPES: wan22_video_v2" in rendered
    assert "SUPPORTED_TASK_TYPES: wan22_video_v2,video_edit,image_to_video" not in rendered
    assert "--disable-dynamic-vram" in rendered


def test_lan_aio_prod_compose_assertion_rejects_test_storage():
    config = load_controller_config()
    slot = load_lan_aio_prod_slots()["gpu-252-gpu0-pornmaster_flux2_edit"]
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
    patched = patch_remote_workers_mount(rendered, slot)

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

    with pytest.raises(RuntimeError, match="old runtime container comfy0 still has GPU"):
        ops.enable_aio([slot])

    assert ops.controls == [("cloud_prod_worker_02", "disabled")]


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

        def _sync_remote_workers(self, slot) -> None:
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

        def _sync_remote_workers(self, slot) -> None:
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
                    "name": "allbot-lan-aio-gpu-002-gpu1-image_to_video-prod",
                    "ports": "0.0.0.0:8191->8188/tcp",
                }
            ]

    ops = RecordingOps()
    slot = ops.slots["gpu-002-gpu1-pornmaster_flux2_edit"]

    payload = ops.preflight_payload([slot], execute=True)

    slot_checks = payload["slots"][0]["checks"]
    port_check = next(check for check in slot_checks if check["name"] == "host_port_owner")
    assert payload["ok"] is False
    assert port_check["ok"] is False
    assert port_check["allowed_containers"] == [
        "allbot-lan-aio-gpu-002-gpu1-image_to_video-canary",
        "allbot-lan-aio-gpu-002-gpu1-pornmaster-flux2-edit-prod",
    ]
    assert port_check["unexpected_owners"] == [
        {
            "name": "allbot-lan-aio-gpu-002-gpu1-image_to_video-prod",
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
    slot = ops.slots["gpu-002-gpu1-pornmaster_flux2_edit"]

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

        def _sync_remote_workers(self, slot) -> None:
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
    slot = ops.slots["gpu-002-gpu1-pornmaster_flux2_edit"]

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

        def _sync_remote_workers(self, slot) -> None:
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
            raise AssertionError("compose must not run when target container is running")

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
    slot = ops.slots["gpu-252-gpu0-pornmaster_flux2_edit"]

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


def test_lan_aio_candidate_plan_generates_stable_yaml_patch():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )

    payload = ops.candidate_plan(
        node_id="gpu-252",
        profile="img2img_lora",
        replace_slot_id="gpu-252-gpu0-pornmaster_flux2_edit",
    )

    assert payload["ok"] is True
    assert payload["action"] == "candidate-plan"
    assert payload["candidate_slot"]["id"] == "gpu-252-gpu0-img2img_lora"
    assert payload["candidate_slot"]["host_port"] == 8192
    assert payload["candidate_slot"]["target_task_types"] == [
        "img2img",
        "img2img_lora",
    ]
    assert payload["candidate_slot"]["agent_id"] == (
        "lan_aio_prod_gpu252_gpu0_img2img_lora_01"
    )
    assert payload["candidate_slot"]["old_runtime_container"] == (
        "allbot-lan-aio-gpu-252-gpu0-pornmaster_flux2_edit-prod"
    )
    assert payload["render_summary"]["model_manifest_key"] == (
        "img2img_lora/2026-06-10/manifest.json"
    )
    assert "target_profile_id: img2img_lora" in payload["yaml_patch"]
    assert "enabled: false" in payload["yaml_patch"]
    assert "retargetable: true" in payload["yaml_patch"]


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

        def _sync_remote_workers(self, slot) -> None:
            return None

        def _scp(self, source: Path, host: str, target: str) -> None:
            return None

        def _ssh(self, host: str, command: str, *, capture: bool = False) -> str:
            self.commands.append(command)
            return ""

        def _write_cache_marker(self, slot, marker: dict[str, object]) -> None:
            self.marker = marker

    ops = RecordingOps()
    slot = ops.slots["gpu-252-gpu0-pornmaster_flux2_edit"]

    result = ops.warm_cache([slot])

    assert result["ok"] is True
    assert result["action"] == "warm-cache"
    docker_command = next(command for command in ops.commands if "docker run" in command)
    docker_run_line = next(
        line.strip()
        for line in docker_command.splitlines()
        if line.strip().startswith("docker run")
    )
    assert "docker run --rm" in docker_run_line
    assert "--env-file" in docker_run_line
    assert "runpod_sync_models_from_r2.py" in docker_command
    assert " -p " not in docker_run_line
    assert "--publish" not in docker_run_line
    assert "AGENT_ID" not in docker_run_line
    assert ops.marker is not None
    assert ops.marker["profile"] == "pornmaster_flux2_edit"
    assert ops.marker["physical_slot_key"] == "gpu-252:gpu0"


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

        def _sync_remote_workers(self, slot) -> None:
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
    retargeted = ops.retarget_slot(candidate, "gpu-177-gpu0-image_to_video")

    ops.warm_cache([retargeted])

    docker_command = next(command for command in ops.commands if "docker run" in command)
    assert (
        "mkdir -p /srv/allbot/runpod-runtime/slots/gpu-177-gpu0/profiles/scail2/workspace "
        "|| docker run --rm -v "
        "/srv/allbot/runpod-runtime/slots/gpu-177-gpu0/profiles/scail2:"
        "/srv/allbot/runpod-runtime/slots/gpu-177-gpu0/profiles/scail2 "
    ) in docker_command
    assert (
        "192.168.1.115:5000/allbot/comfy-runpod-scail2:"
        "20260617-scail2-cu128-a492b2b-proddeps1"
    ) in docker_command


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
    slot = ops.slots["gpu-002-gpu1-pornmaster_flux2_edit"]

    result = ops.takeover([slot])

    assert result["ok"] is True
    assert result["action"] == "takeover"
    assert result["slot"] == "gpu-002-gpu1-pornmaster_flux2_edit"
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
    slot = ops.slots["gpu-002-gpu1-pornmaster_flux2_edit"]

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
        "gpu-177-gpu0-image_to_video",
    )

    payload = ops.preflight_payload([slot], execute=True)

    assert payload["ok"] is True
    assert ops.stats_attempts == 2
    assert ops.queue_attempts == 2
    assert ops.sleeps == [3.0, 3.0]


def test_lan_aio_takeover_dry_run_shows_full_sequence():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-002-gpu1-pornmaster_flux2_edit"]

    payload = ops.dry_run_action("takeover", [slot])

    assert payload["operations"][:8] == [
        "run preflight for gpu-002-gpu1-pornmaster_flux2_edit",
        "run pull-image for gpu-002-gpu1-pornmaster_flux2_edit",
        "run warm-cache for gpu-002-gpu1-pornmaster_flux2_edit",
        "run drain-legacy for gpu-002-gpu1-pornmaster_flux2_edit",
        "run wait-idle for gpu-002-gpu1-pornmaster_flux2_edit",
        "run stop-old for gpu-002-gpu1-pornmaster_flux2_edit",
        "run start-disabled for gpu-002-gpu1-pornmaster_flux2_edit",
        "run enable-aio for gpu-002-gpu1-pornmaster_flux2_edit",
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
        selected_slot_id="gpu-252-gpu0-img2img_lora",
    )

    assert result["ok"] is True
    assert result["action"] == "recover"
    assert result["selected_slot"] == "gpu-252-gpu0-img2img_lora"
    assert result["start"]["action"] == "start-disabled"
    assert ops.started_disabled_slots == ["gpu-252-gpu0-img2img_lora"]
    assert (
        "docker stop 'allbot-lan-aio-gpu-252-gpu0-pornmaster_flux2_edit-prod'"
        in "\n".join(ops.ssh_commands)
    )
    assert ops.controls[0][0] == "lan_aio_prod_gpu252_gpu0_pornmaster_flux2_edit_01"
    assert ops.controls[0][1] == "disabled"
    assert ops.controls[-1][0] == "lan_aio_prod_gpu252_gpu0_img2img_lora_01"
    assert ops.controls[-1][1] == "enabled"


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
    assert ops.compose_ops == ["restart"]
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
        "compose:restart",
        "health",
        "heartbeat",
        "control:enabled",
    ]
