from pathlib import Path

from ops.gpu_pool_controller.canary import ComfyCanary
from ops.gpu_pool_controller.config_loader import load_controller_config
from ops.gpu_pool_controller.image_repo import LocalRegistry
from ops.gpu_pool_controller.model_importer import (
    FIRST_WAVE_BUNDLES,
    InventoryEntry,
    ModelImportPlanner,
    extract_dynamic_references,
    extract_references_for_task_types,
    extract_workflow_references,
)
from ops.gpu_pool_controller.model_repo import ModelRegistry
from ops.gpu_pool_controller.planner import GpuPoolPlanner
from ops.gpu_pool_controller.runtime import RuntimePlanner, RuntimeRenderOverrides
from ops.gpu_pool_controller.types import ComfyInstance, TaskProfile


def test_default_gpu_pool_config_loads_and_plans_all_local_workers():
    config = load_controller_config()

    assert sorted(config.nodes) == ["gpu-002", "gpu-177", "gpu-226", "gpu-252"]
    assert len(config.assignments) == 7

    plan = GpuPoolPlanner(config).to_jsonable()

    assert len(plan) == 7
    assert {item["worker_id"] for item in plan} == {
        "cloud_prod_worker_01",
        "cloud_prod_worker_02",
        "cloud_prod_worker_03",
        "cloud_prod_worker_04",
        "cloud_prod_worker_05",
        "cloud_prod_worker_06",
        "cloud_prod_worker_07",
    }
    wan22 = next(item for item in plan if item["worker_id"] == "cloud_prod_worker_05")
    assert wan22["node_id"] == "gpu-252"
    assert "wan22_video_v2_baseline" in wan22["model_bundles"]

    host_service = next(item for item in plan if item["worker_id"] == "cloud_prod_worker_01")
    assert "docker pull" not in "\n".join(host_service["commands"])
    assert any("host_service" in warning for warning in host_service["warnings"])


def test_runtime_schema_defaults_and_managed_pilot_flags_load():
    config = load_controller_config()

    gpu_226 = config.nodes["gpu-226"].comfy[0]
    assert gpu_226.comfy_runtime_kind == "host_service"
    assert gpu_226.comfy_runtime_managed is False
    assert gpu_226.input_dir == "/home/ubantu/comfyui/input"

    gpu_002 = next(item for item in config.nodes["gpu-002"].comfy if item.id == "comfy0")
    assert gpu_002.comfy_runtime_kind == "docker_container"
    assert gpu_002.comfy_runtime_managed is True
    assert gpu_002.container_name == "allbot-comfy-gpu0"
    assert gpu_002.rollback_state["container_name"] == "comfy0"


def test_runtime_plan_renders_worker_env_and_diffs_for_gpu_002():
    config = load_controller_config()
    payload = RuntimePlanner(config).build_plan("lan-002-8188-worker-06")

    assert payload.runtime_kind == "docker_container"
    assert payload.runtime_managed is True
    assert payload.worker_env["POOL_RUNTIME_PROFILE"] == "img2img_lora"
    assert payload.worker_env["SUPPORTED_TASK_TYPES"] == "img2img,img2img_lora"
    assert payload.model_bundle_versions == {"img2img_lora_baseline": "2026-06-10"}
    assert payload.diff["runtime_image"]["current"] == "yanwk/comfyui-boot:cu128-slim"
    assert payload.diff["runtime_image"]["target"].endswith("/allbot/comfy-cu128-img2img:baseline")
    assert payload.diff["runtime_image"]["changed"] is True


def test_runtime_render_outputs_standard_compose_for_gpu_002():
    config = load_controller_config()
    rendered = RuntimePlanner(config).render_compose("lan-002-8188-worker-06")

    assert "container_name: allbot-comfy-gpu0" in rendered
    assert "- 8188:8188" in rendered
    assert "/data/comfy/inst0/input:/data/comfy/input" in rendered
    assert "allbot.gpu_pool.runtime_profile: img2img_lora" in rendered
    assert "rendered_for: dry_run_review" in rendered


def test_runtime_render_outputs_canary_compose_for_gpu_002():
    config = load_controller_config()
    rendered = RuntimePlanner(config).render_compose(
        "lan-002-8188-worker-06",
        target_profile_id="video_basic",
        overrides=RuntimeRenderOverrides(host_port=8190),
    )

    assert "name: allbot-comfy-gpu-002-comfy0-canary-8190" in rendered
    assert "container_name: allbot-comfy-gpu0-canary" in rendered
    assert "- 8190:8188" in rendered
    assert "allbot.gpu_pool.render_mode: canary" in rendered
    assert "allbot.gpu_pool.production_port_unchanged: 'true'" in rendered
    assert "render_mode: canary" in rendered
    assert "production_port_unchanged: true" in rendered
    assert "comfy_api_url: http://192.168.1.2:8190" in rendered
    assert "comfy_ws_url: ws://192.168.1.2:8190/ws" in rendered


def test_runtime_plan_canary_overrides_worker_env_for_gpu_002():
    config = load_controller_config()
    payload = RuntimePlanner(config).build_plan(
        "lan-002-8188-worker-06",
        target_profile_id="video_basic",
        overrides=RuntimeRenderOverrides(host_port=8190),
    )

    assert payload.worker_env["COMFY_API_URL"] == "http://192.168.1.2:8190"
    assert payload.worker_env["COMFY_WS_URL"] == "ws://192.168.1.2:8190/ws"
    assert payload.runtime["render_mode"] == "canary"
    assert payload.runtime["production_port_unchanged"] is True
    assert payload.diff["container"]["target_name"] == "allbot-comfy-gpu0-canary"
    assert payload.diff["container"]["host_port"] == 8190
    assert any("canary render only" in warning for warning in payload.warnings)
    assert any("--profile video_basic --host-port 8190" in command for command in payload.commands)
    assert not any("docker up" in command or "restart" in command for command in payload.commands)


def test_runtime_plan_supports_canonical_image_to_video_profile():
    config = load_controller_config()
    payload = RuntimePlanner(config).build_plan(
        "lan-002-8188-worker-06",
        target_profile_id="image_to_video",
        overrides=RuntimeRenderOverrides(host_port=8190),
    )

    assert payload.target_profile_id == "image_to_video"
    assert payload.worker_env["POOL_RUNTIME_PROFILE"] == "image_to_video"
    assert payload.worker_env["SUPPORTED_TASK_TYPES"] == "video_insert,video_edit,image_to_video"
    assert payload.model_bundle_versions == {"video_basic_baseline": "2026-06-10"}
    assert payload.runtime["production_port_unchanged"] is True


def test_runpod_all_in_one_profiles_use_lan_mirrors_of_ghcr_images():
    config = load_controller_config()

    img2img = "192.168.1.115:5000/allbot/comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946"
    i2i_pro = "192.168.1.115:5000/allbot/comfy-runpod-i2i-pro:20260614-i2ipro-b75c6a9-cu128-min5-ssh"
    wan22 = "192.168.1.115:5000/allbot/comfy-runpod-wan22-aio-video:20260613-wan22aio-lanbase-ab9b7ea"

    assert config.profiles["img2img_lora"].all_in_one_image_ref == img2img
    assert config.profiles["i2i_pro"].all_in_one_image_ref == i2i_pro
    assert config.profiles["image_to_video"].all_in_one_image_ref == wan22
    assert config.profiles["video_basic"].all_in_one_image_ref == wan22
    assert config.profiles["wan22_video_v2"].all_in_one_image_ref == wan22
    assert config.profiles["wan22_aio_video"].all_in_one_image_ref == wan22

    rendered = RuntimePlanner(config).render_compose(
        "lan-002-8188-worker-06",
        target_profile_id="i2i_pro",
        overrides=RuntimeRenderOverrides(
            host_port=8193,
            runtime_shape="runpod_all_in_one",
            agent_id="render_check_i2i_pro",
        ),
    )
    assert f"image: {i2i_pro}" in rendered
    assert f"POOL_IMAGE_REF: {i2i_pro}" in rendered
    assert "RUNPOD_MODEL_MANIFEST_KEY: i2i_pro/2026-06-14-test/manifest.json" in rendered


def test_runtime_canary_explicit_overrides_take_precedence():
    config = load_controller_config()
    overrides = RuntimeRenderOverrides(
        host_port=8190,
        container_name="allbot-comfy-gpu0-review",
        api_url="http://127.0.0.1:9190",
        ws_url="ws://127.0.0.1:9190/ws",
    )
    planner = RuntimePlanner(config)
    payload = planner.build_plan(
        "lan-002-8188-worker-06",
        target_profile_id="video_basic",
        overrides=overrides,
    )
    rendered = planner.render_compose(
        "lan-002-8188-worker-06",
        target_profile_id="video_basic",
        overrides=overrides,
    )

    assert payload.worker_env["COMFY_API_URL"] == "http://127.0.0.1:9190"
    assert payload.worker_env["COMFY_WS_URL"] == "ws://127.0.0.1:9190/ws"
    assert payload.diff["container"]["target_name"] == "allbot-comfy-gpu0-review"
    assert "container_name: allbot-comfy-gpu0-review" in rendered
    assert "comfy_api_url: http://127.0.0.1:9190" in rendered


def test_runtime_render_rejects_host_service_runtime():
    config = load_controller_config()

    try:
        RuntimePlanner(config).render_compose("lan-226-8188-worker-01")
    except ValueError as exc:
        assert "host_service" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("host_service runtime-render should fail")


def test_runtime_plan_rejects_host_service_overrides():
    config = load_controller_config()

    try:
        RuntimePlanner(config).build_plan(
            "lan-226-8188-worker-01",
            overrides=RuntimeRenderOverrides(host_port=8190),
        )
    except ValueError as exc:
        assert "host_service" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("host_service runtime-plan override should fail")


def test_runtime_overrides_reject_invalid_host_port():
    try:
        RuntimeRenderOverrides(host_port=70000)
    except ValueError as exc:
        assert "--host-port" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("invalid host port should fail")


def test_runtime_rollback_plan_exposes_previous_state_without_execute():
    config = load_controller_config()
    payload = RuntimePlanner(config).build_rollback_plan("lan-002-8188-worker-06")

    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["rollback_state"]["container_name"] == "comfy0"
    assert payload["commands"]


def test_model_registry_imports_file_by_sha_and_renders_rsync_plan(tmp_path: Path):
    source = tmp_path / "model.safetensors"
    source.write_bytes(b"tiny model")
    registry = ModelRegistry(tmp_path / "registry")

    manifest = registry.import_file(
        bundle="tiny_bundle",
        version="v1",
        source_path=source,
        relative_path="loras/tiny.safetensors",
        source_node="unit-test",
        profiles=["img2img_lora"],
    )

    file_info = manifest["files"][0]
    assert file_info["relative_path"] == "loras/tiny.safetensors"
    assert registry.blob_path(file_info["sha256"]).exists()

    commands = registry.render_rsync_plan(
        bundle="tiny_bundle",
        version="v1",
        target_host="allbot-gpu-002",
        target_model_dir="/data/comfy/models",
    )

    assert commands == [
        f"rsync -avh --checksum {registry.blob_path(file_info['sha256'])} "
        "allbot-gpu-002:/data/comfy/models/loras/tiny.safetensors"
    ]


def test_local_registry_renders_publish_plan():
    registry = LocalRegistry(host="192.168.1.115", port=5000)

    commands = registry.render_publish_plan(
        source_image="workers_cloud-prod-comfy-agent-1:latest",
        repository="allbot/worker-agent",
        tag="abc123",
    )

    assert commands == [
        "docker tag workers_cloud-prod-comfy-agent-1:latest "
        "192.168.1.115:5000/allbot/worker-agent:abc123",
        "docker push 192.168.1.115:5000/allbot/worker-agent:abc123",
        "docker pull 192.168.1.115:5000/allbot/worker-agent:abc123",
    ]


def test_model_importer_extracts_dynamic_lora_refs_without_blank_video_lora():
    refs = extract_dynamic_references(groups=["video_lora", "ltx_lora", "image_lora"])
    values = {ref.value for ref in refs}

    assert "_high_noise.safetensors" not in values
    assert "BreastGrow_high_noise.safetensors" in values
    assert "qwen/YARN_1.0.safetensors" in values
    assert "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors" in values


def test_model_importer_i2i_pro_baseline_resolves_six_workflow_models():
    config = load_controller_config()
    planner = ModelImportPlanner(config)
    model_paths = [
        ("text_encoders/qwen_3_8b_fp8mixed.safetensors", 8664848742),
        ("vae/flux2-vae.safetensors", 336213556),
        ("unet/DarkBeast-Klein9b-V2-BFS-FP8-ComfyUI.safetensors", 9078610848),
        ("text_encoders/z_image/qwen_3_4b.safetensors", 8044982048),
        ("vae/z_image/ae.safetensors", 335304388),
        ("unet/DarkBeastZ6-BlitZ-BF16-ComfyUI.safetensors", 12309878608),
    ]
    inventory = [
        InventoryEntry(
            node_id="gpu-226",
            host="allbot-gpu-226",
            model_dir="/home/ubantu/comfyui/models",
            relative_path=relative_path,
            size_bytes=size_bytes,
        )
        for relative_path, size_bytes in model_paths
    ]
    planner.remote_inventory = lambda _node: inventory  # type: ignore[method-assign]

    plan = planner.build_import_plans(
        bundle_ids=["i2i_pro_baseline"],
        include_sha256=False,
    )[0]

    assert plan.bundle == "i2i_pro_baseline"
    assert plan.version == "2026-06-14-test"
    assert plan.profiles == ("i2i_pro",)
    assert plan.missing == ()
    assert {item.entry.relative_path for item in plan.files} == {
        relative_path for relative_path, _size_bytes in model_paths
    }
    assert sum(item.entry.size_bytes for item in plan.files) == 38769838190


def test_model_importer_i2i_pro_spec_uses_multitask_overrides():
    workflow_dir = Path("workers/comfy_agent/workflows")
    spec = FIRST_WAVE_BUNDLES["i2i_pro_baseline"]
    refs = extract_references_for_task_types(
        workflow_dir,
        spec.task_types,
        workflow_overrides=spec.workflow_overrides,
    )
    values = {ref.value for ref in refs}

    assert values == {
        "qwen_3_8b_fp8mixed.safetensors",
        "flux2-vae.safetensors",
        "DarkBeast-Klein9b-V2-BFS-FP8-ComfyUI.safetensors",
        "z_image/qwen_3_4b.safetensors",
        "z_image/ae.safetensors",
        "DarkBeastZ6-BlitZ-BF16-ComfyUI.safetensors",
    }
    assert "pornmasterZImage_turboV2.safetensors" not in values
    assert "bfs_head_v1_flux-klein_9b_step3750_rank64.safetensors" not in values


def test_model_importer_face_i2i_t2i_spec_uses_runtime_overrides_for_face_and_t2i():
    workflow_dir = Path("workers/comfy_agent/workflows")
    spec = FIRST_WAVE_BUNDLES["face_i2i_t2i_baseline"]
    refs = extract_references_for_task_types(
        workflow_dir,
        spec.task_types,
        workflow_overrides=spec.workflow_overrides,
    )
    values = {ref.value for ref in refs}

    assert "face_swap_v2.json" in {ref.workflow for ref in refs}
    assert "txt2img_from_i2i_pro.json" in {ref.workflow for ref in refs}
    assert "pornmasterZImage_turboV2.safetensors" not in values
    assert "z-image-turbo-fp8-e4m3fn.safetensors" not in values
    assert "bfs_head_v1_flux-klein_9b_step3750_rank64.safetensors" not in values
    assert "DarkBeast-Klein9b-V2-BFS-FP8-ComfyUI.safetensors" in values
    assert "DarkBeastZ6-BlitZ-BF16-ComfyUI.safetensors" in values


def test_i2i_pro_multitask_workflows_stay_within_baseline_models():
    workflow_dir = Path("workers/comfy_agent/workflows")
    refs = []
    refs.extend(extract_workflow_references(workflow_dir / "i2i_pro.json", "i2i_pro"))
    refs.extend(
        extract_workflow_references(
            workflow_dir / "txt2img_from_i2i_pro.json",
            "t2i-pornmaster-turbo",
        )
    )
    refs.extend(
        extract_workflow_references(
            workflow_dir / "face_swap_v2.json",
            "face_swap",
        )
    )
    values = {ref.value for ref in refs}

    assert values <= {
        "qwen_3_8b_fp8mixed.safetensors",
        "flux2-vae.safetensors",
        "DarkBeast-Klein9b-V2-BFS-FP8-ComfyUI.safetensors",
        "z_image/qwen_3_4b.safetensors",
        "z_image/ae.safetensors",
        "DarkBeastZ6-BlitZ-BF16-ComfyUI.safetensors",
    }
    assert "pornmasterZImage_turboV2.safetensors" not in values


def test_t2i_workflow_uses_existing_z_image_unet_name():
    path = Path(
        "workers/comfy_agent/workflows/"
        "Pornmaster Z-Image Turbo_t2i_Double checkpoints & realism enhancer_V1_2026_01_24.json"
    )
    refs = extract_workflow_references(path, "t2i-pornmaster-turbo")
    values = {ref.value for ref in refs}

    assert "z-image-turbo-fp8-e4m3fn.safetensors" in values
    assert "z image\\z_image_turbo_fp8_e4m3fn.safetensors" not in values


def test_canary_compares_min_vram_as_decimal_gb():
    canary = ComfyCanary()

    def fake_get_json(url: str):
        if url.endswith("/system_stats"):
            return {"devices": [{"vram_total": 32_000_000_000}]}
        if url.endswith("/queue"):
            return {"queue_running": [], "queue_pending": []}
        if url.endswith("/object_info"):
            return {"KSampler": {}}
        raise AssertionError(url)

    canary._get_json = fake_get_json  # type: ignore[method-assign]
    result = canary.run(
        comfy=ComfyInstance(
            id="unit",
            port=8188,
            gpu_index=0,
            worker_id="worker",
            api_url="http://127.0.0.1:8188",
            ws_url="ws://127.0.0.1:8188/ws",
            model_dir="/models",
            runtime="docker",
        ),
        profile=TaskProfile(
            id="unit",
            task_types=("t2i",),
            runtime_profile="unit",
            model_bundles=("unit",),
            required_nodes=("KSampler",),
            min_vram_gb=32,
        ),
    )

    assert result.ok is True
    assert result.details["vram_total_gb"] == 32.0
    assert result.details["vram_total_gib"] < 32.0
