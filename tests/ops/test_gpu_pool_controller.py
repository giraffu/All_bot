from pathlib import Path

from ops.gpu_pool_controller.canary import ComfyCanary
from ops.gpu_pool_controller.config_loader import load_controller_config
from ops.gpu_pool_controller.image_repo import LocalRegistry
from ops.gpu_pool_controller.model_importer import (
    extract_dynamic_references,
    extract_workflow_references,
)
from ops.gpu_pool_controller.model_repo import ModelRegistry
from ops.gpu_pool_controller.planner import GpuPoolPlanner
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
