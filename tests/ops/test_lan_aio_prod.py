import json
from pathlib import Path

import pytest

from ops.gpu_pool_controller.config_loader import load_controller_config
from ops.gpu_pool_controller.lan_aio_prod import (
    LanAioProdOps,
    assert_prod_compose,
    load_lan_aio_prod_slots,
    patch_remote_workers_mount,
)
from ops.gpu_pool_controller.runpod_profile_catalog import (
    RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES,
)
from ops.gpu_pool_controller.runtime import RuntimePlanner, RuntimeRenderOverrides


def test_lan_aio_prod_slots_cover_next_wave_candidates():
    slots = load_lan_aio_prod_slots()

    assert list(slots) == [
        "gpu-177-gpu0-image_to_video",
        "gpu-177-gpu1-ltx_video",
        "gpu-252-gpu0-pornmaster_flux2_edit",
        "gpu-252-gpu1-wan22_video_v2",
    ]
    assert slots["gpu-177-gpu0-image_to_video"].legacy_worker_id == "cloud_prod_worker_02"
    assert slots["gpu-177-gpu0-image_to_video"].target_profile_id == "wan22_video_v2"
    assert slots["gpu-177-gpu0-image_to_video"].target_task_types == ("wan22_video_v2",)
    assert slots["gpu-177-gpu1-ltx_video"].legacy_worker_id == "cloud_prod_worker_03"
    assert slots["gpu-252-gpu0-pornmaster_flux2_edit"].agent_id == (
        "lan_aio_prod_gpu252_gpu0_pornmaster_flux2_edit_01"
    )
    assert slots["gpu-252-gpu0-pornmaster_flux2_edit"].legacy_worker_id == (
        "lan_aio_prod_gpu252_gpu0_img2img_lora_01"
    )
    assert slots["gpu-252-gpu1-wan22_video_v2"].host_port == 8191


def test_lan_aio_prod_slots_keep_blocked_nodes_disabled_but_visible():
    slots = load_lan_aio_prod_slots(include_disabled=True)

    assert slots["gpu-177-gpu1-ltx_video"].enabled is True
    assert slots["gpu-177-gpu1-ltx_video"].phase == "prod_enabled"
    assert slots["gpu-252-gpu0-img2img_lora"].enabled is False
    assert slots["gpu-252-gpu0-img2img_lora"].phase == (
        "superseded_by_pornmaster_flux2_edit"
    )
    assert slots["gpu-002-gpu1-pornmaster_flux2_edit"].enabled is False
    assert slots["gpu-002-gpu1-pornmaster_flux2_edit"].phase == (
        "superseded_by_image_to_video"
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
    assert "legacy worker 02/comfy0 were retired" in slot.notes


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
        "set lan_aio_prod_gpu252_gpu0_img2img_lora_01=disabled",
        "ssh allbot-gpu-252 docker stop allbot-lan-aio-gpu-252-gpu0-img2img_lora-prod",
    ]


def test_lan_aio_fleet_render_supports_gpu_177_wan22_v2_profile():
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
    )
    slot = ops.slots["gpu-177-gpu0-image_to_video"]
    rendered = ops.render_compose(slot)

    assert "POOL_NODE_ID: gpu-177" in rendered
    assert "POOL_RUNTIME_PROFILE: wan22_video_v2" in rendered
    assert "SUPPORTED_TASK_TYPES: wan22_video_v2" in rendered
    assert "SUPPORTED_TASK_TYPES: wan22_video_v2,video_edit,image_to_video" not in rendered
    assert "RUNPOD_MODEL_MANIFEST_KEY: wan22_video_v2/2026-06-13-test/manifest.json" in rendered
    assert "--disable-dynamic-vram" in rendered
    assert "host_port: 8190" in rendered


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
