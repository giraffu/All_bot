import json

import pytest

from ops.gpu_pool_controller.providers.lan_ssh import LanSshProvider
from ops.gpu_pool_controller.providers.runpod import (
    RUNPOD_I2I_PRO_CONTAINER_DISK_GB,
    RUNPOD_I2I_PRO_GPU_TYPE_IDS,
    RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY,
    RUNPOD_I2I_PRO_MODEL_PREFIX,
    RUNPOD_I2I_PRO_SUPPORTED_TASK_TYPES,
    RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES,
    RUNPOD_IMG2IMG_LORA_DOCKER_START_CMD,
    RUNPOD_LTX_VIDEO_CONTAINER_DISK_GB,
    RUNPOD_LTX_VIDEO_DOCKER_START_CMD,
    RUNPOD_LTX_VIDEO_GPU_TYPE_IDS,
    RUNPOD_LTX_VIDEO_MODEL_MANIFEST_KEY,
    RUNPOD_LTX_VIDEO_MODEL_PREFIX,
    RUNPOD_LTX_VIDEO_SUPPORTED_TASK_TYPES,
    RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES,
    RUNPOD_MODEL_CACHE_R2_ACCESS_KEY_REF,
    RUNPOD_MODEL_CACHE_R2_SECRET_KEY_REF,
    RUNPOD_PORNMASTER_FLUX2_EDIT_CONTAINER_DISK_GB,
    RUNPOD_PORNMASTER_FLUX2_EDIT_DOCKER_START_CMD,
    RUNPOD_PORNMASTER_FLUX2_EDIT_GPU_TYPE_IDS,
    RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_MANIFEST_KEY,
    RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_PREFIX,
    RUNPOD_PORNMASTER_FLUX2_EDIT_SUPPORTED_TASK_TYPES,
    RUNPOD_PROD_AGENT_ID,
    RUNPOD_PROD_AGENT_SECRET_TOKEN_REF,
    RUNPOD_PROD_BUCKET,
    RUNPOD_PROD_GPU_TYPE_IDS,
    RUNPOD_PROD_NODE_ID,
    RUNPOD_PROD_R2_ACCESS_KEY_REF,
    RUNPOD_PROD_R2_SECRET_KEY_REF,
    RUNPOD_PROD_SUPPORTED_TASK_TYPES,
    RUNPOD_PROD_WORKER_CENTRAL_URL,
    RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE,
    RUNPOD_PUBLIC_LTX_VIDEO_IMAGE_PREFIX,
    RUNPOD_PUBLIC_PORNMASTER_FLUX2_EDIT_IMAGE_PREFIX,
    RUNPOD_PUBLIC_SCAIL2_IMAGE_PREFIX,
    RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE,
    RUNPOD_PUBLIC_WAN22_VIDEO_V2_IMAGE_PREFIX,
    RUNPOD_SCAIL2_CONTAINER_DISK_GB,
    RUNPOD_SCAIL2_DOCKER_START_CMD,
    RUNPOD_SCAIL2_GPU_TYPE_IDS,
    RUNPOD_SCAIL2_MODEL_MANIFEST_KEY,
    RUNPOD_SCAIL2_MODEL_PREFIX,
    RUNPOD_SCAIL2_SUPPORTED_TASK_TYPES,
    RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS,
    RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY,
    RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX,
    RUNPOD_WAN22_VIDEO_V2_COMFY_EXTRA_ARGS,
    RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY,
    RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX,
    RunPodProvider,
    RunPodProviderError,
    RunPodSettings,
    prod_agent_id_from_slot,
)
from ops.gpu_pool_controller.types import GpuNode


class FakeRunPodApi:
    def __init__(self, response=None, exc: Exception | None = None):
        self.response = response if response is not None else {"pods": []}
        self.exc = exc
        self.calls = []

    def __call__(self, method, path, *, params=None, json_body=None, headers=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "params": params or {},
                "json_body": json_body,
                "headers": headers or {},
            }
        )
        if self.exc:
            raise self.exc
        return self.response


def _settings(**overrides) -> RunPodSettings:
    values = {
        "api_key": "rp_secret_api_key",
        "agent_secret_token": "agent_secret_token",
        "minio_endpoint": "https://r2.example.test",
        "minio_access_key": "r2_access_key",
        "minio_secret_key": "r2_secret_key",
        "worker_central_url_cloud_test": "https://worker-central-test.aivison.it.com",
        "template_id_img2img_lora": "runpod-template-img2img-lora",
        "gpu_type_ids_img2img_lora": ("NVIDIA GeForce RTX 4090",),
    }
    values.update(overrides)
    return RunPodSettings(**values)


def test_validate_key_uses_bearer_auth_header_without_mutation():
    fake = FakeRunPodApi({"pods": []})
    provider = RunPodProvider(
        _settings(pod_ports=("8888/http", "22/tcp")),
        request_func=fake,
    )

    payload = provider.validate_key()

    assert payload == {"ok": True, "message": "RunPod API key accepted"}
    assert fake.calls == [
        {
            "method": "GET",
            "path": "/pods",
            "params": {"computeType": "GPU"},
            "json_body": None,
            "headers": {
                "Authorization": "Bearer rp_secret_api_key",
                "Content-Type": "application/json",
            },
        }
    ]


def test_list_pods_filters_managed_pods_and_redacts_secrets():
    fake = FakeRunPodApi(
        {
            "pods": [
                {
                    "id": "pod-1",
                    "name": "allbot-runpod-test-img2img-lora",
                    "status": "RUNNING",
                    "env": {
                        "RUNPOD_TASK_TYPE": "img2img_lora",
                        "AGENT_ID": "runpod_test_img2img_lora_pod-1",
                        "AGENT_SECRET_TOKEN": "agent_secret_token",
                        "OUTPUT_URL": (
                            "https://r2.example.test/result.png?"
                            "X-Amz-Signature=signature_leak&"
                            "X-Amz-Credential=credential_leak"
                        ),
                    },
                },
                {
                    "id": "pod-2",
                    "name": "manual-runpod",
                    "env": {
                        "RUNPOD_MANAGED": "true",
                        "RUNPOD_TASK_TYPE": "img2img_lora",
                        "AGENT_ID": "runpod_test_img2img_lora_pod-2",
                        "MINIO_SECRET_KEY": "r2_secret_key",
                    },
                },
                {"id": "pod-3", "name": "manual-other", "env": {}},
            ]
        }
    )
    provider = RunPodProvider(
        _settings(pod_ports=("8888/http", "22/tcp")),
        request_func=fake,
    )

    payload = provider.list_pods()
    rendered = json.dumps(payload, ensure_ascii=False)

    assert payload["ok"] is True
    assert payload["count"] == 2
    assert {pod["id"] for pod in payload["pods"]} == {"pod-1", "pod-2"}
    assert "agent_secret_token" not in rendered
    assert "r2_secret_key" not in rendered
    assert "signature_leak" not in rendered
    assert "credential_leak" not in rendered


def test_get_pod_uses_rest_pod_id_and_redacts_env_secrets():
    fake = FakeRunPodApi(
        {
            "id": "pod-1",
            "name": "allbot-runpod-test-img2img-lora",
            "desiredStatus": "RUNNING",
            "publicIp": "203.0.113.10",
            "portMappings": {"22": 10341},
            "env": {"AGENT_SECRET_TOKEN": "agent_secret_token"},
        }
    )
    provider = RunPodProvider(
        _settings(pod_ports=("8888/http", "22/tcp")),
        request_func=fake,
    )

    payload = provider.get_pod(pod_id="pod-1")
    rendered = json.dumps(payload, ensure_ascii=False)

    assert payload["ok"] is True
    assert payload["pod"]["id"] == "pod-1"
    assert fake.calls == [
        {
            "method": "GET",
            "path": "/pods/pod-1",
            "params": {
                "includeMachine": "true",
                "includeTemplate": "true",
                "includeNetworkVolume": "true",
            },
            "json_body": None,
            "headers": {
                "Authorization": "Bearer rp_secret_api_key",
                "Content-Type": "application/json",
            },
        }
    ]
    assert "agent_secret_token" not in rendered


def test_pod_readiness_reports_initializing_when_port_mappings_are_empty():
    fake = FakeRunPodApi(
        {
            "id": "pod-1",
            "name": "allbot-official-ready-check",
            "desiredStatus": "RUNNING",
            "cloudType": "SECURE",
            "ports": ["8888/http", "22/tcp"],
            "publicIp": "",
            "portMappings": {},
        }
    )
    provider = RunPodProvider(
        _settings(pod_ports=("8888/http", "22/tcp")),
        request_func=fake,
    )

    payload = provider.pod_readiness(pod_id="pod-1")
    readiness = payload["readiness"]

    assert payload["ok"] is True
    assert readiness["infrastructure_ready"] is False
    assert readiness["confidence"] == "initializing_or_unmapped"
    assert "public_ip_missing" in readiness["reasons"]
    assert "port_mappings_empty_for_exposed_ports" in readiness["reasons"]
    assert "public_ip_missing_for_tcp_ports" in readiness["reasons"]
    assert readiness["network"]["public_ip_present"] is False
    assert readiness["network"]["port_mappings_present"] is False
    assert "uptimeSeconds" not in readiness["signals"]


def test_pod_readiness_reports_network_mapping_confirmed_for_running_mapped_pod():
    fake = FakeRunPodApi(
        {
            "id": "pod-1",
            "name": "allbot-official-ready-check",
            "desiredStatus": "RUNNING",
            "cloudType": "SECURE",
            "ports": ["8888/http", "22/tcp"],
            "publicIp": "203.0.113.10",
            "portMappings": {"22": 10341},
        }
    )
    provider = RunPodProvider(
        _settings(pod_ports=("8888/http", "22/tcp")),
        request_func=fake,
    )

    payload = provider.pod_readiness(pod_id="pod-1")
    readiness = payload["readiness"]

    assert readiness["infrastructure_ready"] is True
    assert readiness["confidence"] == "network_mapping_confirmed"
    assert readiness["reasons"] == []
    assert readiness["signals"]["public_ip_present"] is True
    assert readiness["signals"]["port_mappings_present"] is True
    assert readiness["network"]["public_ip_present"] is True
    assert readiness["network"]["port_mappings_present"] is True


def test_pod_readiness_treats_running_worker_without_exposed_ports_as_ready():
    fake = FakeRunPodApi(
        {
            "id": "pod-1",
            "name": "allbot-runpod-test-img2img-lora",
            "desiredStatus": "RUNNING",
            "machine": {"secureCloud": True, "supportPublicIp": True},
            "ports": [],
            "publicIp": "",
            "portMappings": {},
        }
    )
    provider = RunPodProvider(_settings(), request_func=fake)

    payload = provider.pod_readiness(pod_id="pod-1")
    readiness = payload["readiness"]

    assert readiness["infrastructure_ready"] is True
    assert readiness["confidence"] == "status_only_no_exposed_ports"
    assert readiness["reasons"] == []
    assert readiness["signals"]["public_ip_expected"] is True


def test_pod_readiness_treats_image_exposed_ports_as_outbound_worker_ready():
    fake = FakeRunPodApi(
        {
            "id": "pod-1",
            "name": "allbot-runpod-test-wan22-video-v2",
            "desiredStatus": "RUNNING",
            "cloudType": "SECURE",
            "ports": ["8888/http", "22/tcp"],
            "publicIp": "",
            "portMappings": {},
        }
    )
    provider = RunPodProvider(_settings(pod_ports=()), request_func=fake)

    payload = provider.pod_readiness(pod_id="pod-1")
    readiness = payload["readiness"]

    assert readiness["infrastructure_ready"] is True
    assert readiness["confidence"] == "status_only_with_image_exposed_ports"
    assert readiness["reasons"] == []
    assert readiness["network"]["exposed_ports"] == ["8888/http", "22/tcp"]
    assert readiness["network"]["port_mappings_present"] is False


def test_render_create_pod_request_cloud_test_profile_is_redacted():
    provider = RunPodProvider(_settings())

    payload = provider.render_create_pod_request(
        task_type="img2img_lora",
        environment="cloud-test",
    )
    env = payload["json"]["env"]
    rendered = json.dumps(payload, ensure_ascii=False)

    assert payload["dry_run"] is True
    assert payload["method"] == "POST"
    assert payload["url"].endswith("/pods")
    assert payload["json"]["templateId"] == "runpod-template-img2img-lora"
    assert payload["json"]["gpuTypeIds"] == ["NVIDIA GeForce RTX 4090"]
    assert payload["json"]["volumeInGb"] == 0
    assert payload["json"]["volumeMountPath"] == "/workspace"
    assert "ports" not in payload["json"]
    assert env["SUPPORTED_TASK_TYPES"] == "img2img,img2img_lora"
    assert env["AGENT_ID_PREFIX"] == "runpod_test_img2img_lora"
    assert env["AGENT_ID"] == "runpod_test_img2img_lora_${RUNPOD_POD_ID:-pending}"
    assert env["POOL_PROVIDER"] == "runpod"
    assert env["POOL_RUNTIME_PROFILE"] == "img2img_lora"
    assert env["PIPELINE_MAX_RUNNING_TASKS"] == "1"
    assert env["COMFY_API_URL"] == "http://127.0.0.1:8188"
    assert env["MINIO_RESULT_BUCKET"] == "user-data-test"
    assert '"AGENT_SECRET_TOKEN": "agent_secret_token"' not in rendered
    assert '"MINIO_ACCESS_KEY": "r2_access_key"' not in rendered
    assert '"MINIO_SECRET_KEY": "r2_secret_key"' not in rendered


def test_render_create_can_expose_explicit_debug_ports_without_defaulting_comfy_port():
    provider = RunPodProvider(_settings(pod_ports=("22/tcp",)))

    payload = provider.render_create_pod_request(
        task_type="img2img_lora",
        environment="cloud-test",
    )

    assert payload["json"]["ports"] == ["22/tcp"]
    assert "8188/http" not in payload["json"]["ports"]


def test_render_create_can_use_bootstrap_image_without_template():
    provider = RunPodProvider(
        _settings(
            use_template_img2img_lora=False,
            image_name_img2img_lora="yanwk/comfyui-boot:cu128-slim",
            docker_start_cmd_img2img_lora=("bash", "-lc", "echo bootstrap"),
            keepalive_on_bootstrap_failure=True,
        )
    )

    payload = provider.render_create_pod_request(
        task_type="img2img_lora",
        environment="cloud-test",
    )
    body = payload["json"]
    env = body["env"]

    assert "templateId" not in body
    assert body["imageName"] == "yanwk/comfyui-boot:cu128-slim"
    assert body["dockerStartCmd"] == ["bash", "-lc", "echo bootstrap"]
    assert "ALLBOT_RUNPOD_GIT_URL" not in env
    assert "ALLBOT_RUNPOD_GIT_BRANCH" not in env
    assert env["RUNPOD_PREPARE_COMFYUI_ON_VOLUME"] == "false"
    assert env["RUNPOD_KEEPALIVE_ON_BOOTSTRAP_FAILURE"] == "true"


def test_render_create_can_use_baked_runpod_profile_image_without_runtime_custom_node_install():
    provider = RunPodProvider(
        _settings(
            use_template_img2img_lora=False,
            image_name_img2img_lora="docker.io/allbot/comfy-runpod-img2img-lora:20260612",
            docker_start_cmd_img2img_lora=("bash", "-lc", "echo bootstrap"),
            comfy_custom_nodes_enabled=False,
            comfy_kjnodes_enabled=False,
        )
    )

    payload = provider.render_create_pod_request(
        task_type="img2img_lora",
        environment="cloud-test",
    )
    body = payload["json"]
    env = body["env"]

    assert "templateId" not in body
    assert body["imageName"] == "docker.io/allbot/comfy-runpod-img2img-lora:20260612"
    assert body["dockerStartCmd"] == ["bash", "-lc", "echo bootstrap"]
    assert env["RUNPOD_COMFY_CUSTOM_NODES_ENABLED"] == "false"
    assert env["RUNPOD_COMFY_KJNODES_ENABLED"] == "false"
    assert env["RUNPOD_MODEL_SYNC_ENABLED"] == "false"
    assert env["MINIO_RESULT_BUCKET"] == "user-data-test"


def test_render_create_injects_r2_model_cache_env_without_inline_secrets():
    provider = RunPodProvider(
        _settings(
            model_sync_enabled=True,
            model_bucket="allbot-model-cache-test",
            model_prefix="img2img_lora/2026-06-10",
            model_manifest_key="img2img_lora/2026-06-10/manifest.json",
            model_endpoint="https://r2-model.example.test",
            model_access_key_ref="{{ RUNPOD_SECRET_model_access }}",
            model_secret_key_ref="{{ RUNPOD_SECRET_model_secret }}",
            minio_access_key="inline_r2_access_value",
            minio_secret_key="inline_r2_secret_value",
        )
    )

    payload = provider.render_create_pod_request(
        task_type="img2img_lora",
        environment="cloud-test",
    )
    env = payload["json"]["env"]
    rendered = json.dumps(payload, ensure_ascii=False)

    assert env["RUNPOD_MODEL_SYNC_ENABLED"] == "true"
    assert env["RUNPOD_MODEL_BUCKET"] == "allbot-model-cache-test"
    assert env["RUNPOD_MODEL_PREFIX"] == "img2img_lora/2026-06-10"
    assert env["RUNPOD_MODEL_MANIFEST_KEY"] == "img2img_lora/2026-06-10/manifest.json"
    assert env["RUNPOD_MODEL_ENDPOINT"] == "https://r2-model.example.test"
    assert env["RUNPOD_MODEL_ACCESS_KEY"] == "<redacted>"
    assert env["RUNPOD_MODEL_SECRET_KEY"] == "<redacted>"
    assert "inline_r2_access_value" not in rendered
    assert "inline_r2_secret_value" not in rendered


def test_render_create_wan22_aio_video_cloud_test_profile_uses_5090_and_test_refs():
    provider = RunPodProvider(
        _settings(
            image_name_wan22_aio_video=(
                "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:"
                "20260612-wan22aio-test"
            ),
            model_sync_enabled=True,
            model_bucket="allbot-model-cache",
            model_prefix="wan22_aio_video/2026-06-12-test",
            model_manifest_key="wan22_aio_video/2026-06-12-test/manifest.json",
            comfy_custom_nodes_enabled=False,
            comfy_kjnodes_enabled=False,
            agent_secret_token="inline_agent_value",
            minio_access_key="inline_r2_access_value",
            minio_secret_key="inline_r2_secret_value",
        )
    )

    payload = provider.render_create_pod_request(
        task_type="wan22_aio_video",
        environment="cloud-test",
        redact=False,
    )
    body = payload["json"]
    env = body["env"]
    rendered = json.dumps(payload, ensure_ascii=False)

    assert "templateId" not in body
    assert body["name"] == "allbot-runpod-test-wan22-aio-video"
    assert body["imageName"].startswith(
        "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:"
    )
    assert body["gpuTypeIds"] == list(RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS)
    assert env["ENVIRONMENT"] == "test"
    assert env["RUNPOD_ENVIRONMENT"] == "cloud-test"
    assert env["RUNPOD_TASK_TYPE"] == "wan22_aio_video"
    assert env["AGENT_ID_PREFIX"] == "runpod_test_wan22_aio_video"
    assert env["AGENT_ID"] == "runpod_test_wan22_aio_video_${RUNPOD_POD_ID:-pending}"
    assert env["SUPPORTED_TASK_TYPES"] == "image_to_video,wan22_video_v2"
    assert env["CENTRAL_API_URL"] == "https://worker-central-test.aivison.it.com"
    assert env["POOL_PROVIDER"] == "runpod"
    assert env["POOL_NODE_ID"] == "runpod-cloud-test"
    assert env["POOL_RUNTIME_PROFILE"] == "wan22_aio_video"
    assert env["MINIO_INPUT_BUCKET"] == "user-data-test"
    assert env["MINIO_RESULT_BUCKET"] == "user-data-test"
    assert env["RUNPOD_MODEL_SYNC_ENABLED"] == "true"
    assert env["RUNPOD_MODEL_BUCKET"] == "allbot-model-cache"
    assert env["RUNPOD_MODEL_PREFIX"] == "wan22_aio_video/2026-07-18-lora5"
    assert env["RUNPOD_MODEL_MANIFEST_KEY"] == (
        "wan22_aio_video/2026-07-18-lora5/manifest.json"
    )
    assert env["RUNPOD_COMFY_CUSTOM_NODES_ENABLED"] == "false"
    assert env["RUNPOD_COMFY_KJNODES_ENABLED"] == "false"
    assert (
        env["AGENT_SECRET_TOKEN"]
        == "{{ RUNPOD_SECRET_allbot_cloud_test_agent_secret_token }}"
    )
    assert (
        env["MINIO_ACCESS_KEY"] == "{{ RUNPOD_SECRET_allbot_cloud_test_r2_access_key }}"
    )
    assert (
        env["MINIO_SECRET_KEY"] == "{{ RUNPOD_SECRET_allbot_cloud_test_r2_secret_key }}"
    )
    assert env["RUNPOD_MODEL_ACCESS_KEY"] == RUNPOD_MODEL_CACHE_R2_ACCESS_KEY_REF
    assert env["RUNPOD_MODEL_SECRET_KEY"] == RUNPOD_MODEL_CACHE_R2_SECRET_KEY_REF
    assert "inline_agent_value" not in rendered
    assert "inline_r2_access_value" not in rendered
    assert "inline_r2_secret_value" not in rendered


def test_render_create_wan22_aio_video_can_use_template_with_bootstrap():
    provider = RunPodProvider(
        _settings(
            use_template_wan22_aio_video=True,
            template_id_wan22_aio_video="77gi0wqo8x",
            image_name_wan22_aio_video=(
                "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:"
                "20260613-wan22aio-yanwkclean-108c7ea"
            ),
            docker_start_cmd_wan22_aio_video=("bash", "-lc", "echo wan22 bootstrap"),
            model_sync_enabled=True,
            model_bucket="allbot-model-cache",
            model_prefix="wan22_aio_video/2026-06-12-test",
            model_manifest_key="wan22_aio_video/2026-06-12-test/manifest.json",
            comfy_custom_nodes_enabled=False,
            comfy_kjnodes_enabled=False,
        )
    )

    payload = provider.render_create_pod_request(
        task_type="wan22_aio_video",
        environment="cloud-test",
        redact=False,
    )
    body = payload["json"]
    env = body["env"]

    assert body["templateId"] == "77gi0wqo8x"
    assert "imageName" not in body
    assert body["dockerStartCmd"] == ["bash", "-lc", "echo wan22 bootstrap"]
    assert body["gpuTypeIds"] == list(RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS)
    assert env["RUNPOD_TASK_TYPE"] == "wan22_aio_video"
    assert env["SUPPORTED_TASK_TYPES"] == "image_to_video,wan22_video_v2"
    assert env["RUNPOD_MODEL_PREFIX"] == "wan22_aio_video/2026-07-18-lora5"
    assert env["RUNPOD_COMFY_CUSTOM_NODES_ENABLED"] == "false"
    assert env["RUNPOD_COMFY_KJNODES_ENABLED"] == "false"


def test_render_create_split_video_profiles_share_template_with_distinct_runtime_env():
    image_ref = (
        "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:"
        "20260613-wan22aio-yanwkclean-108c7ea"
    )
    provider = RunPodProvider(
        _settings(
            use_template_image_to_video=True,
            use_template_wan22_video_v2=True,
            template_id_image_to_video="77gi0wqo8x",
            template_id_wan22_video_v2="77gi0wqo8x",
            image_name_image_to_video=image_ref,
            image_name_wan22_video_v2=image_ref,
            docker_start_cmd_image_to_video=("bash", "-lc", "echo image-to-video"),
            docker_start_cmd_wan22_video_v2=("bash", "-lc", "echo wan22-v2"),
            model_sync_enabled=True,
            model_bucket="allbot-model-cache",
            model_prefix_image_to_video=RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX,
            model_manifest_key_image_to_video=RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY,
            model_prefix_wan22_video_v2=RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX,
            model_manifest_key_wan22_video_v2=RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY,
            comfy_custom_nodes_enabled=False,
            comfy_kjnodes_enabled=False,
        )
    )

    image_to_video = provider.render_create_pod_request(
        task_type="image_to_video",
        environment="cloud-test",
        redact=False,
    )["json"]
    wan22_v2 = provider.render_create_pod_request(
        task_type="wan22_video_v2",
        environment="cloud-test",
        redact=False,
    )["json"]
    image_to_video_env = image_to_video["env"]
    wan22_v2_env = wan22_v2["env"]

    assert image_to_video["templateId"] == "77gi0wqo8x"
    assert wan22_v2["templateId"] == "77gi0wqo8x"
    assert "imageName" not in image_to_video
    assert "imageName" not in wan22_v2
    assert image_to_video["gpuTypeIds"] == list(RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS)
    assert wan22_v2["gpuTypeIds"] == list(RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS)
    assert image_to_video["dockerStartCmd"] == ["bash", "-lc", "echo image-to-video"]
    assert wan22_v2["dockerStartCmd"] == ["bash", "-lc", "echo wan22-v2"]

    assert image_to_video_env["RUNPOD_TASK_TYPE"] == "image_to_video"
    assert image_to_video_env["SUPPORTED_TASK_TYPES"] == "image_to_video"
    assert image_to_video_env["POOL_RUNTIME_PROFILE"] == "image_to_video"
    assert image_to_video_env["AGENT_ID_PREFIX"] == "runpod_test_image_to_video"
    assert (
        image_to_video_env["RUNPOD_MODEL_PREFIX"] == RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX
    )
    assert (
        image_to_video_env["RUNPOD_MODEL_MANIFEST_KEY"]
        == RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY
    )

    assert wan22_v2_env["RUNPOD_TASK_TYPE"] == "wan22_video_v2"
    assert wan22_v2_env["SUPPORTED_TASK_TYPES"] == "wan22_video_v2"
    assert wan22_v2_env["POOL_RUNTIME_PROFILE"] == "wan22_video_v2"
    assert wan22_v2_env["AGENT_ID_PREFIX"] == "runpod_test_wan22_video_v2"
    assert wan22_v2_env["RUNPOD_MODEL_PREFIX"] == RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX
    assert (
        wan22_v2_env["RUNPOD_MODEL_MANIFEST_KEY"]
        == RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY
    )
    assert wan22_v2_env["WAN22_VIDEO_V2_COMPLETION_TIMEOUT_SECONDS"] == "600"
    assert wan22_v2_env["WAN22_VIDEO_V2_EXIT_ON_TIMEOUT"] == "true"
    assert wan22_v2_env["COMFY_EXTRA_ARGS"] == RUNPOD_WAN22_VIDEO_V2_COMFY_EXTRA_ARGS


def test_render_create_i2i_pro_cloud_test_profile_uses_dedicated_manifest_and_disk():
    image_ref = "ghcr.io/giraffu/allbot-comfy-runpod-i2i-pro:20260614-i2ipro-test"
    provider = RunPodProvider(
        _settings(
            image_name_i2i_pro=image_ref,
            docker_start_cmd_i2i_pro=("bash", "-lc", "echo i2i bootstrap"),
            model_sync_enabled=True,
            model_bucket="allbot-model-cache",
            model_prefix_i2i_pro=RUNPOD_I2I_PRO_MODEL_PREFIX,
            model_manifest_key_i2i_pro=RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY,
            comfy_custom_nodes_enabled=False,
            comfy_kjnodes_enabled=False,
            container_disk_gb=80,
        )
    )

    payload = provider.render_create_pod_request(
        task_type="i2i_pro",
        environment="cloud-test",
        redact=False,
    )
    body = payload["json"]
    env = body["env"]

    assert "templateId" not in body
    assert body["name"] == "allbot-runpod-test-i2i-pro"
    assert body["imageName"] == image_ref
    assert body["gpuTypeIds"] == list(RUNPOD_I2I_PRO_GPU_TYPE_IDS)
    assert body["containerDiskInGb"] == RUNPOD_I2I_PRO_CONTAINER_DISK_GB
    assert body["dockerStartCmd"] == ["bash", "-lc", "echo i2i bootstrap"]
    assert env["RUNPOD_ENVIRONMENT"] == "cloud-test"
    assert env["RUNPOD_TASK_TYPE"] == "i2i_pro"
    assert env["AGENT_ID_PREFIX"] == "runpod_test_i2i_pro"
    assert env["SUPPORTED_TASK_TYPES"] == ",".join(RUNPOD_I2I_PRO_SUPPORTED_TASK_TYPES)
    assert env["TASK_TYPE_WORKFLOW_OVERRIDES"] == RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES
    assert env["POOL_RUNTIME_PROFILE"] == "i2i_pro"
    assert env["RUNPOD_MODEL_BUCKET"] == "allbot-model-cache"
    assert env["RUNPOD_MODEL_PREFIX"] == RUNPOD_I2I_PRO_MODEL_PREFIX
    assert env["RUNPOD_MODEL_MANIFEST_KEY"] == RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY
    assert env["RUNPOD_COMFY_CUSTOM_NODES_ENABLED"] == "false"
    assert env["RUNPOD_COMFY_KJNODES_ENABLED"] == "false"


def test_render_create_scail2_cloud_test_profile_uses_r2_manifest_and_bootstrap():
    image_ref = RUNPOD_PUBLIC_SCAIL2_IMAGE_PREFIX + "20260617-scail2-test"
    provider = RunPodProvider(
        _settings(
            image_name_scail2=image_ref,
            model_sync_enabled=True,
            model_bucket="allbot-model-cache",
            model_prefix_scail2=RUNPOD_SCAIL2_MODEL_PREFIX,
            model_manifest_key_scail2=RUNPOD_SCAIL2_MODEL_MANIFEST_KEY,
            comfy_custom_nodes_enabled=False,
            comfy_kjnodes_enabled=False,
            container_disk_gb=80,
        )
    )

    payload = provider.render_create_pod_request(
        task_type="scail2",
        environment="cloud-test",
        redact=False,
    )
    body = payload["json"]
    env = body["env"]

    assert "templateId" not in body
    assert body["name"] == "allbot-runpod-test-scail2"
    assert body["imageName"] == image_ref
    assert body["gpuTypeIds"] == list(RUNPOD_SCAIL2_GPU_TYPE_IDS)
    assert body["containerDiskInGb"] == RUNPOD_SCAIL2_CONTAINER_DISK_GB
    assert body["dockerStartCmd"] == list(RUNPOD_SCAIL2_DOCKER_START_CMD)
    assert env["RUNPOD_ENVIRONMENT"] == "cloud-test"
    assert env["RUNPOD_TASK_TYPE"] == "scail2"
    assert env["AGENT_ID_PREFIX"] == "runpod_test_scail2"
    assert env["SUPPORTED_TASK_TYPES"] == ",".join(RUNPOD_SCAIL2_SUPPORTED_TASK_TYPES)
    assert env["POOL_RUNTIME_PROFILE"] == "scail2"
    assert env["MINIO_RESULT_BUCKET"] == "user-data-test"
    assert env["RUNPOD_MODEL_BUCKET"] == "allbot-model-cache"
    assert env["RUNPOD_MODEL_PREFIX"] == RUNPOD_SCAIL2_MODEL_PREFIX
    assert env["RUNPOD_MODEL_MANIFEST_KEY"] == RUNPOD_SCAIL2_MODEL_MANIFEST_KEY
    assert env["RUNPOD_COMFY_CUSTOM_NODES_ENABLED"] == "false"
    assert env["RUNPOD_COMFY_KJNODES_ENABLED"] == "false"
    assert "TASK_TYPE_WORKFLOW_OVERRIDES" not in env


def test_render_create_rejects_retired_pornmaster_flux2_fp8_profile():
    provider = RunPodProvider(_settings())

    with pytest.raises(ValueError):
        provider.render_create_pod_request(
            task_type="pornmaster_flux2_edit",
            environment="cloud-test",
            redact=False,
        )


def test_runpod_settings_from_env_split_video_profiles_ignore_legacy_wan22_image_template(
    tmp_path,
    monkeypatch,
):
    script = tmp_path / "wan22-bootstrap.sh"
    script.write_text("echo shared wan22 bootstrap\n", encoding="utf-8")
    monkeypatch.setenv("RUNPOD_USE_TEMPLATE_WAN22_AIO_VIDEO", "true")
    monkeypatch.setenv("RUNPOD_TEMPLATE_ID_WAN22_AIO_VIDEO", "77gi0wqo8x")
    monkeypatch.setenv(
        "RUNPOD_IMAGE_NAME_WAN22_AIO_VIDEO",
        "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:shared",
    )
    monkeypatch.setenv(
        "RUNPOD_DOCKER_START_SCRIPT_FILE_WAN22_AIO_VIDEO",
        str(script),
    )
    monkeypatch.setenv(
        "RUNPOD_WAN22_VIDEO_V2_COMFY_EXTRA_ARGS",
        "--disable-dynamic-vram --disable-async-offload",
    )
    monkeypatch.setenv("RUNPOD_MODEL_BUCKET", "allbot-model-cache")
    monkeypatch.delenv("RUNPOD_TEMPLATE_ID_IMAGE_TO_VIDEO", raising=False)
    monkeypatch.delenv("RUNPOD_TEMPLATE_ID_WAN22_VIDEO_V2", raising=False)
    monkeypatch.delenv("RUNPOD_IMAGE_NAME_IMAGE_TO_VIDEO", raising=False)
    monkeypatch.delenv("RUNPOD_IMAGE_NAME_WAN22_VIDEO_V2", raising=False)

    settings = RunPodSettings.from_env()

    assert settings.use_template_image_to_video is False
    assert settings.use_template_wan22_video_v2 is False
    assert settings.template_id_image_to_video == ""
    assert settings.template_id_wan22_video_v2 == ""
    assert (
        settings.image_name_image_to_video
        == RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE
    )
    assert (
        settings.image_name_wan22_video_v2
        == RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE
    )
    assert settings.docker_start_cmd_image_to_video == (
        "bash",
        "-lc",
        "echo shared wan22 bootstrap\n",
    )
    assert (
        settings.docker_start_cmd_wan22_video_v2
        == settings.docker_start_cmd_image_to_video
    )
    assert settings.model_prefix_image_to_video == RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX
    assert (
        settings.model_manifest_key_wan22_video_v2
        == RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY
    )
    assert (
        settings.wan22_video_v2_comfy_extra_args
        == "--disable-dynamic-vram --disable-async-offload"
    )


def test_runpod_settings_from_env_supports_i2i_pro_profile_keys(
    tmp_path,
    monkeypatch,
):
    script = tmp_path / "i2i-bootstrap.sh"
    script.write_text("echo i2i bootstrap\n", encoding="utf-8")
    monkeypatch.setenv("RUNPOD_USE_TEMPLATE_I2I_PRO", "true")
    monkeypatch.setenv("RUNPOD_TEMPLATE_ID_I2I_PRO", "i2i-template")
    monkeypatch.setenv(
        "RUNPOD_IMAGE_NAME_I2I_PRO",
        "ghcr.io/giraffu/allbot-comfy-runpod-i2i-pro:shared",
    )
    monkeypatch.setenv("RUNPOD_DOCKER_START_SCRIPT_FILE_I2I_PRO", str(script))
    monkeypatch.setenv("RUNPOD_GPU_TYPE_IDS_I2I_PRO", "NVIDIA L40S")
    monkeypatch.setenv("RUNPOD_PROJECTED_COST_PER_HR_I2I_PRO", "0.77")
    monkeypatch.setenv("RUNPOD_MODEL_PREFIX_I2I_PRO", RUNPOD_I2I_PRO_MODEL_PREFIX)
    monkeypatch.setenv(
        "RUNPOD_MODEL_MANIFEST_KEY_I2I_PRO",
        RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY,
    )
    monkeypatch.setenv(
        "RUNPOD_TASK_TYPE_WORKFLOW_OVERRIDES_I2I_PRO",
        RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES,
    )

    settings = RunPodSettings.from_env()

    assert settings.use_template_i2i_pro is True
    assert settings.template_id_i2i_pro == "i2i-template"
    assert settings.image_name_i2i_pro.endswith(":shared")
    assert settings.docker_start_cmd_i2i_pro == (
        "bash",
        "-lc",
        "echo i2i bootstrap\n",
    )
    assert settings.gpu_type_ids_i2i_pro == ("NVIDIA L40S",)
    assert settings.projected_cost_per_hr_i2i_pro == 0.77
    assert settings.model_prefix_i2i_pro == RUNPOD_I2I_PRO_MODEL_PREFIX
    assert settings.model_manifest_key_i2i_pro == RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY
    assert (
        settings.task_type_workflow_overrides_i2i_pro
        == RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES
    )


def test_runpod_settings_from_env_supports_scail2_profile_keys(tmp_path, monkeypatch):
    script = tmp_path / "scail2-bootstrap.sh"
    script.write_text("echo scail2 bootstrap\n", encoding="utf-8")
    monkeypatch.setenv("RUNPOD_USE_TEMPLATE_SCAIL2", "true")
    monkeypatch.setenv("RUNPOD_TEMPLATE_ID_SCAIL2", "scail2-template")
    monkeypatch.setenv(
        "RUNPOD_IMAGE_NAME_SCAIL2",
        RUNPOD_PUBLIC_SCAIL2_IMAGE_PREFIX + "20260617-scail2-test",
    )
    monkeypatch.setenv("RUNPOD_DOCKER_START_SCRIPT_FILE_SCAIL2", str(script))
    monkeypatch.setenv(
        "RUNPOD_GPU_TYPE_IDS_SCAIL2",
        "NVIDIA GeForce RTX 5090,NVIDIA GeForce RTX 4090",
    )
    monkeypatch.setenv("RUNPOD_PROJECTED_COST_PER_HR_SCAIL2", "1.23")
    monkeypatch.setenv("RUNPOD_MODEL_PREFIX_SCAIL2", RUNPOD_SCAIL2_MODEL_PREFIX)
    monkeypatch.setenv(
        "RUNPOD_MODEL_MANIFEST_KEY_SCAIL2",
        RUNPOD_SCAIL2_MODEL_MANIFEST_KEY,
    )

    settings = RunPodSettings.from_env()

    assert settings.use_template_scail2 is True
    assert settings.template_id_scail2 == "scail2-template"
    assert settings.image_name_scail2.endswith(":20260617-scail2-test")
    assert settings.docker_start_cmd_scail2 == (
        "bash",
        "-lc",
        "echo scail2 bootstrap\n",
    )
    assert settings.gpu_type_ids_scail2 == RUNPOD_SCAIL2_GPU_TYPE_IDS
    assert settings.projected_cost_per_hr_scail2 == 1.23
    assert settings.model_prefix_scail2 == RUNPOD_SCAIL2_MODEL_PREFIX
    assert settings.model_manifest_key_scail2 == RUNPOD_SCAIL2_MODEL_MANIFEST_KEY


def test_runpod_settings_from_env_scail2_uses_git_bootstrap_by_default(monkeypatch):
    monkeypatch.delenv("RUNPOD_DOCKER_START_CMD_JSON_SCAIL2", raising=False)
    monkeypatch.delenv("RUNPOD_DOCKER_START_SCRIPT_SCAIL2", raising=False)
    monkeypatch.delenv("RUNPOD_DOCKER_START_SCRIPT_FILE_SCAIL2", raising=False)

    settings = RunPodSettings.from_env()

    assert settings.docker_start_cmd_scail2 == RUNPOD_SCAIL2_DOCKER_START_CMD


def test_runpod_settings_from_env_supports_ltx_video_profile_keys(
    tmp_path,
    monkeypatch,
):
    script = tmp_path / "ltx-bootstrap.sh"
    script.write_text("echo ltx bootstrap\n", encoding="utf-8")
    image_ref = RUNPOD_PUBLIC_LTX_VIDEO_IMAGE_PREFIX + "20260622-ltx-prod"
    monkeypatch.setenv("RUNPOD_USE_TEMPLATE_LTX_VIDEO", "true")
    monkeypatch.setenv("RUNPOD_TEMPLATE_ID_LTX_VIDEO", "ltx-template")
    monkeypatch.setenv("RUNPOD_IMAGE_NAME_LTX_VIDEO", image_ref)
    monkeypatch.setenv("RUNPOD_DOCKER_START_SCRIPT_FILE_LTX_VIDEO", str(script))
    monkeypatch.setenv(
        "RUNPOD_GPU_TYPE_IDS_LTX_VIDEO",
        "NVIDIA GeForce RTX 5090,NVIDIA GeForce RTX 4090",
    )
    monkeypatch.setenv("RUNPOD_CONTAINER_DISK_GB_LTX_VIDEO", "200")
    monkeypatch.setenv("RUNPOD_PROJECTED_COST_PER_HR_LTX_VIDEO", "1.89")
    monkeypatch.setenv("RUNPOD_MODEL_PREFIX_LTX_VIDEO", RUNPOD_LTX_VIDEO_MODEL_PREFIX)
    monkeypatch.setenv(
        "RUNPOD_MODEL_MANIFEST_KEY_LTX_VIDEO",
        RUNPOD_LTX_VIDEO_MODEL_MANIFEST_KEY,
    )
    monkeypatch.setenv(
        "RUNPOD_TASK_TYPE_WORKFLOW_OVERRIDES_LTX_VIDEO",
        RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES,
    )

    settings = RunPodSettings.from_env()

    assert settings.use_template_ltx_video is True
    assert settings.template_id_ltx_video == "ltx-template"
    assert settings.image_name_ltx_video == image_ref
    assert settings.docker_start_cmd_ltx_video == (
        "bash",
        "-lc",
        "echo ltx bootstrap\n",
    )
    assert settings.gpu_type_ids_ltx_video == RUNPOD_LTX_VIDEO_GPU_TYPE_IDS
    assert settings.container_disk_gb_ltx_video == 200
    assert settings.projected_cost_per_hr_ltx_video == 1.89
    assert settings.model_prefix_ltx_video == RUNPOD_LTX_VIDEO_MODEL_PREFIX
    assert settings.model_manifest_key_ltx_video == RUNPOD_LTX_VIDEO_MODEL_MANIFEST_KEY
    assert (
        settings.task_type_workflow_overrides_ltx_video
        == RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES
    )


def test_runpod_settings_from_env_ltx_video_uses_git_bootstrap_by_default(monkeypatch):
    monkeypatch.delenv("RUNPOD_DOCKER_START_CMD_JSON_LTX_VIDEO", raising=False)
    monkeypatch.delenv("RUNPOD_DOCKER_START_SCRIPT_LTX_VIDEO", raising=False)
    monkeypatch.delenv("RUNPOD_DOCKER_START_SCRIPT_FILE_LTX_VIDEO", raising=False)

    settings = RunPodSettings.from_env()

    assert settings.docker_start_cmd_ltx_video == RUNPOD_LTX_VIDEO_DOCKER_START_CMD


def test_runpod_settings_from_env_supports_pornmaster_flux2_edit_profile_keys(
    tmp_path,
    monkeypatch,
):
    script = tmp_path / "pornmaster-bootstrap.sh"
    script.write_text("echo pornmaster bootstrap\n", encoding="utf-8")
    image_ref = (
        RUNPOD_PUBLIC_PORNMASTER_FLUX2_EDIT_IMAGE_PREFIX
        + "20260701-pornmaster-flux2-edit"
    )
    monkeypatch.setenv("RUNPOD_USE_TEMPLATE_PORNMASTER_FLUX2_EDIT", "true")
    monkeypatch.setenv(
        "RUNPOD_TEMPLATE_ID_PORNMASTER_FLUX2_EDIT",
        "pornmaster-template",
    )
    monkeypatch.setenv("RUNPOD_IMAGE_NAME_PORNMASTER_FLUX2_EDIT", image_ref)
    monkeypatch.setenv(
        "RUNPOD_DOCKER_START_SCRIPT_FILE_PORNMASTER_FLUX2_EDIT",
        str(script),
    )
    monkeypatch.setenv(
        "RUNPOD_GPU_TYPE_IDS_PORNMASTER_FLUX2_EDIT",
        "NVIDIA GeForce RTX 4090,NVIDIA L40S,NVIDIA GeForce RTX 5090",
    )
    monkeypatch.setenv("RUNPOD_CONTAINER_DISK_GB_PORNMASTER_FLUX2_EDIT", "140")
    monkeypatch.setenv(
        "RUNPOD_PROJECTED_COST_PER_HR_PORNMASTER_FLUX2_EDIT",
        "0.88",
    )
    monkeypatch.setenv(
        "RUNPOD_MODEL_PREFIX_PORNMASTER_FLUX2_EDIT",
        RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_PREFIX,
    )
    monkeypatch.setenv(
        "RUNPOD_MODEL_MANIFEST_KEY_PORNMASTER_FLUX2_EDIT",
        RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_MANIFEST_KEY,
    )

    settings = RunPodSettings.from_env()

    assert settings.use_template_pornmaster_flux2_edit is True
    assert settings.template_id_pornmaster_flux2_edit == "pornmaster-template"
    assert settings.image_name_pornmaster_flux2_edit == image_ref
    assert settings.docker_start_cmd_pornmaster_flux2_edit == (
        "bash",
        "-lc",
        "echo pornmaster bootstrap\n",
    )
    assert (
        settings.gpu_type_ids_pornmaster_flux2_edit
        == RUNPOD_PORNMASTER_FLUX2_EDIT_GPU_TYPE_IDS
    )
    assert settings.container_disk_gb_pornmaster_flux2_edit == 140
    assert settings.projected_cost_per_hr_pornmaster_flux2_edit == 0.88
    assert (
        settings.model_prefix_pornmaster_flux2_edit
        == RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_PREFIX
    )
    assert (
        settings.model_manifest_key_pornmaster_flux2_edit
        == RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_MANIFEST_KEY
    )


def test_runpod_settings_from_env_pornmaster_uses_git_bootstrap_by_default(
    monkeypatch,
):
    monkeypatch.delenv(
        "RUNPOD_DOCKER_START_CMD_JSON_PORNMASTER_FLUX2_EDIT",
        raising=False,
    )
    monkeypatch.delenv(
        "RUNPOD_DOCKER_START_SCRIPT_PORNMASTER_FLUX2_EDIT",
        raising=False,
    )
    monkeypatch.delenv(
        "RUNPOD_DOCKER_START_SCRIPT_FILE_PORNMASTER_FLUX2_EDIT",
        raising=False,
    )

    settings = RunPodSettings.from_env()

    assert (
        settings.docker_start_cmd_pornmaster_flux2_edit
        == RUNPOD_PORNMASTER_FLUX2_EDIT_DOCKER_START_CMD
    )


def test_runpod_settings_from_env_injects_public_key_file(
    tmp_path,
    monkeypatch,
):
    public_key_file = tmp_path / "runpod_debug.pub"
    public_key_file.write_text(
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest allbot-runpod-debug\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RUNPOD_PUBLIC_KEY_FILE", str(public_key_file))

    settings = RunPodSettings.from_env()
    provider = RunPodProvider(settings)
    payload = provider.render_create_pod_request(
        task_type="i2i_pro",
        environment="cloud-test",
        redact=False,
    )
    prod_payload = provider.render_create_pod_request(
        task_type="img2img_lora",
        environment="cloud-prod",
        redact=False,
    )

    assert settings.extra_env == {
        "PUBLIC_KEY": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest allbot-runpod-debug"
    }
    assert payload["json"]["env"]["PUBLIC_KEY"] == settings.extra_env["PUBLIC_KEY"]
    assert "PUBLIC_KEY" not in prod_payload["json"]["env"]


def test_runpod_settings_from_env_supports_wan22_docker_start_script_file(
    tmp_path,
    monkeypatch,
):
    script = tmp_path / "wan22-bootstrap.sh"
    script.write_text("echo wan22 bootstrap\n", encoding="utf-8")
    monkeypatch.setenv("RUNPOD_USE_TEMPLATE_WAN22_AIO_VIDEO", "true")
    monkeypatch.setenv("RUNPOD_TEMPLATE_ID_WAN22_AIO_VIDEO", "77gi0wqo8x")
    monkeypatch.setenv(
        "RUNPOD_DOCKER_START_SCRIPT_FILE_WAN22_AIO_VIDEO",
        str(script),
    )
    monkeypatch.delenv("RUNPOD_DOCKER_START_CMD_JSON_WAN22_AIO_VIDEO", raising=False)
    monkeypatch.delenv("RUNPOD_DOCKER_START_SCRIPT_WAN22_AIO_VIDEO", raising=False)

    settings = RunPodSettings.from_env()

    assert settings.use_template_wan22_aio_video is True
    assert settings.template_id_wan22_aio_video == "77gi0wqo8x"
    assert settings.docker_start_cmd_wan22_aio_video == (
        "bash",
        "-lc",
        "echo wan22 bootstrap\n",
    )


def test_render_create_cloud_prod_manual_worker_uses_prod_refs_and_bucket():
    provider = RunPodProvider(
        _settings(
            use_template_img2img_lora=True,
            image_name_img2img_lora="",
            model_bucket="",
            model_prefix="",
            model_manifest_key="",
            comfy_custom_nodes_enabled=True,
            comfy_kjnodes_enabled=True,
        )
    )

    payload = provider.render_create_pod_request(
        task_type="img2img",
        environment="cloud-prod",
        redact=False,
    )
    body = payload["json"]
    env = body["env"]
    rendered = json.dumps(payload, ensure_ascii=False)

    assert "templateId" not in body
    assert body["name"] == "allbot-runpod-prod-img2img-manual-01"
    assert body["imageName"] == RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE
    assert body["dockerStartCmd"] == list(RUNPOD_IMG2IMG_LORA_DOCKER_START_CMD)
    assert body["dockerStartCmd"][2].startswith("set -euo pipefail;")
    assert "git clone" not in body["dockerStartCmd"][2]
    assert "runpod_baked_runtime_entrypoint.sh" in body["dockerStartCmd"][2]
    assert body["gpuTypeIds"] == list(RUNPOD_PROD_GPU_TYPE_IDS)
    assert env["ENVIRONMENT"] == "prod"
    assert env["RUNPOD_ENVIRONMENT"] == "cloud-prod"
    assert env["AGENT_ID"] == RUNPOD_PROD_AGENT_ID
    assert env["AGENT_ID_PREFIX"] == RUNPOD_PROD_AGENT_ID
    assert env["SUPPORTED_TASK_TYPES"] == ",".join(RUNPOD_PROD_SUPPORTED_TASK_TYPES)
    assert env["CENTRAL_API_URL"] == RUNPOD_PROD_WORKER_CENTRAL_URL
    assert env["POOL_PROVIDER"] == "runpod"
    assert env["POOL_NODE_ID"] == RUNPOD_PROD_NODE_ID
    assert env["POOL_RUNTIME_PROFILE"] == "img2img_lora"
    assert env["MINIO_RESULT_BUCKET"] == RUNPOD_PROD_BUCKET
    assert env["MINIO_INPUT_BUCKET"] == RUNPOD_PROD_BUCKET
    assert env["RUNPOD_MODEL_SYNC_ENABLED"] == "true"
    assert env["RUNPOD_MODEL_BUCKET"] == "allbot-model-cache"
    assert env["RUNPOD_MODEL_PREFIX"] == "img2img_lora/2026-06-10"
    assert env["RUNPOD_MODEL_MANIFEST_KEY"] == ("img2img_lora/2026-06-10/manifest.json")
    assert env["RUNPOD_COMFY_CUSTOM_NODES_ENABLED"] == "false"
    assert env["RUNPOD_COMFY_KJNODES_ENABLED"] == "false"
    assert env["RUNPOD_START_SSHD"] == "false"
    assert env["AGENT_SECRET_TOKEN"] == RUNPOD_PROD_AGENT_SECRET_TOKEN_REF
    assert env["MINIO_ACCESS_KEY"] == RUNPOD_PROD_R2_ACCESS_KEY_REF
    assert env["MINIO_SECRET_KEY"] == RUNPOD_PROD_R2_SECRET_KEY_REF
    assert env["RUNPOD_MODEL_ACCESS_KEY"] == RUNPOD_MODEL_CACHE_R2_ACCESS_KEY_REF
    assert env["RUNPOD_MODEL_SECRET_KEY"] == RUNPOD_MODEL_CACHE_R2_SECRET_KEY_REF
    assert '"AGENT_SECRET_TOKEN": "agent_secret_token"' not in rendered
    assert '"MINIO_ACCESS_KEY": "r2_access_key"' not in rendered
    assert '"MINIO_SECRET_KEY": "r2_secret_key"' not in rendered


def test_render_create_cloud_prod_manual_worker_can_use_second_slot():
    agent_id = prod_agent_id_from_slot("02")
    provider = RunPodProvider(
        _settings(
            image_name_img2img_lora=RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE,
            prod_agent_id=agent_id,
        )
    )

    payload = provider.render_create_pod_request(
        task_type="img2img",
        environment="cloud-prod",
        redact=False,
    )
    body = payload["json"]
    env = body["env"]

    assert body["name"] == "allbot-runpod-prod-img2img-manual-02"
    assert env["AGENT_ID"] == "runpod_prod_img2img_manual_02"
    assert env["AGENT_ID_PREFIX"] == "runpod_prod_img2img_manual_02"


def test_render_create_cloud_prod_wan22_video_v2_uses_prod_refs_and_split_manifest():
    image_ref = RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE
    agent_id = prod_agent_id_from_slot("01", profile="wan22_video_v2")
    provider = RunPodProvider(
        _settings(
            image_name_wan22_video_v2=image_ref,
            prod_agent_id=agent_id,
            model_bucket="allbot-model-cache",
            model_prefix="img2img_lora/2026-06-10",
            model_manifest_key="img2img_lora/2026-06-10/manifest.json",
        )
    )

    payload = provider.render_create_pod_request(
        task_type="wan22_video_v2",
        environment="cloud-prod",
        redact=False,
    )
    body = payload["json"]
    env = body["env"]

    assert "templateId" not in body
    assert body["name"] == "allbot-runpod-prod-wan22-video-v2-manual-01"
    assert body["imageName"] == image_ref
    assert body["gpuTypeIds"] == list(RUNPOD_PROD_GPU_TYPE_IDS)
    assert env["ENVIRONMENT"] == "prod"
    assert env["RUNPOD_ENVIRONMENT"] == "cloud-prod"
    assert env["RUNPOD_TASK_TYPE"] == "wan22_video_v2"
    assert env["AGENT_ID"] == "runpod_prod_wan22_video_v2_manual_01"
    assert env["AGENT_ID_PREFIX"] == "runpod_prod_wan22_video_v2_manual_01"
    assert env["SUPPORTED_TASK_TYPES"] == "wan22_video_v2"
    assert env["CENTRAL_API_URL"] == RUNPOD_PROD_WORKER_CENTRAL_URL
    assert env["POOL_RUNTIME_PROFILE"] == "wan22_video_v2"
    assert env["MINIO_RESULT_BUCKET"] == RUNPOD_PROD_BUCKET
    assert env["RUNPOD_MODEL_BUCKET"] == "allbot-model-cache"
    assert env["RUNPOD_MODEL_PREFIX"] == RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX
    assert env["RUNPOD_MODEL_MANIFEST_KEY"] == RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY
    assert env["WAN22_VIDEO_V2_COMPLETION_TIMEOUT_SECONDS"] == "600"
    assert env["WAN22_VIDEO_V2_EXIT_ON_TIMEOUT"] == "true"
    assert env["COMFY_EXTRA_ARGS"] == RUNPOD_WAN22_VIDEO_V2_COMFY_EXTRA_ARGS
    assert env["RUNPOD_COMFY_CUSTOM_NODES_ENABLED"] == "false"
    assert env["RUNPOD_COMFY_KJNODES_ENABLED"] == "false"
    assert env["RUNPOD_START_SSHD"] == "false"
    assert env["AGENT_SECRET_TOKEN"] == RUNPOD_PROD_AGENT_SECRET_TOKEN_REF
    assert env["MINIO_ACCESS_KEY"] == RUNPOD_PROD_R2_ACCESS_KEY_REF
    assert env["MINIO_SECRET_KEY"] == RUNPOD_PROD_R2_SECRET_KEY_REF
    assert env["RUNPOD_MODEL_ACCESS_KEY"] == RUNPOD_MODEL_CACHE_R2_ACCESS_KEY_REF
    assert env["RUNPOD_MODEL_SECRET_KEY"] == RUNPOD_MODEL_CACHE_R2_SECRET_KEY_REF


def test_render_create_cloud_prod_image_to_video_uses_prod_refs_and_split_manifest():
    image_ref = RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE
    agent_id = prod_agent_id_from_slot("01", profile="image_to_video")
    provider = RunPodProvider(
        _settings(
            image_name_image_to_video=image_ref,
            prod_agent_id=agent_id,
            model_bucket="allbot-model-cache",
            model_prefix="img2img_lora/2026-06-10",
            model_manifest_key="img2img_lora/2026-06-10/manifest.json",
            keepalive_on_bootstrap_failure=True,
        )
    )

    payload = provider.render_create_pod_request(
        task_type="image_to_video",
        environment="cloud-prod",
        redact=False,
    )
    body = payload["json"]
    env = body["env"]

    assert "templateId" not in body
    assert body["name"] == "allbot-runpod-prod-image-to-video-manual-01"
    assert body["imageName"] == image_ref
    assert body["gpuTypeIds"] == list(RUNPOD_PROD_GPU_TYPE_IDS)
    assert body["containerDiskInGb"] == 100
    assert env["ENVIRONMENT"] == "prod"
    assert env["RUNPOD_ENVIRONMENT"] == "cloud-prod"
    assert env["RUNPOD_TASK_TYPE"] == "image_to_video"
    assert env["AGENT_ID"] == "runpod_prod_image_to_video_manual_01"
    assert env["AGENT_ID_PREFIX"] == "runpod_prod_image_to_video_manual_01"
    assert env["SUPPORTED_TASK_TYPES"] == "image_to_video"
    assert env["CENTRAL_API_URL"] == RUNPOD_PROD_WORKER_CENTRAL_URL
    assert env["POOL_RUNTIME_PROFILE"] == "image_to_video"
    assert env["MINIO_RESULT_BUCKET"] == RUNPOD_PROD_BUCKET
    assert env["RUNPOD_MODEL_BUCKET"] == "allbot-model-cache"
    assert env["RUNPOD_MODEL_PREFIX"] == RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX
    assert env["RUNPOD_MODEL_MANIFEST_KEY"] == RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY
    assert env["RUNPOD_COMFY_CUSTOM_NODES_ENABLED"] == "false"
    assert env["RUNPOD_COMFY_KJNODES_ENABLED"] == "false"
    assert env["RUNPOD_START_SSHD"] == "false"
    assert env["RUNPOD_KEEPALIVE_ON_BOOTSTRAP_FAILURE"] == "false"
    assert env["AGENT_SECRET_TOKEN"] == RUNPOD_PROD_AGENT_SECRET_TOKEN_REF
    assert env["MINIO_ACCESS_KEY"] == RUNPOD_PROD_R2_ACCESS_KEY_REF
    assert env["MINIO_SECRET_KEY"] == RUNPOD_PROD_R2_SECRET_KEY_REF
    assert env["RUNPOD_MODEL_ACCESS_KEY"] == RUNPOD_MODEL_CACHE_R2_ACCESS_KEY_REF
    assert env["RUNPOD_MODEL_SECRET_KEY"] == RUNPOD_MODEL_CACHE_R2_SECRET_KEY_REF


def test_render_create_cloud_prod_split_video_defaults_to_rife_image():
    agent_id = prod_agent_id_from_slot("02", profile="image_to_video")
    provider = RunPodProvider(
        _settings(
            prod_agent_id=agent_id,
            model_bucket="allbot-model-cache",
        )
    )

    payload = provider.render_create_pod_request(
        task_type="image_to_video",
        environment="cloud-prod",
        redact=False,
    )

    assert payload["json"]["imageName"] == RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE


@pytest.mark.parametrize("task_type", ["image_to_video", "wan22_video_v2"])
def test_render_create_cloud_prod_split_video_accepts_canonical_digest(task_type):
    image_ref = (
        "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video@sha256:"
        + "1" * 64
    )
    agent_id = prod_agent_id_from_slot("02", profile=task_type)
    provider = RunPodProvider(
        _settings(
            prod_agent_id=agent_id,
            image_name_image_to_video=image_ref,
            image_name_wan22_video_v2=image_ref,
            model_bucket="allbot-model-cache",
        )
    )

    payload = provider.render_create_pod_request(
        task_type=task_type,
        environment="cloud-prod",
        redact=False,
    )

    assert payload["json"]["imageName"] == image_ref


@pytest.mark.parametrize(
    "image_ref",
    [
        RUNPOD_PUBLIC_WAN22_VIDEO_V2_IMAGE_PREFIX
        + "20260613-wan22aio-lanbase-ab9b7ea",
        "ghcr.io/example/allbot-comfy-runpod-wan22-aio-video@sha256:" + "1" * 64,
        "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video@sha256:" + "A" * 64,
    ],
)
def test_render_create_cloud_prod_split_video_rejects_noncanonical_image(image_ref):
    agent_id = prod_agent_id_from_slot("02", profile="wan22_video_v2")
    provider = RunPodProvider(
        _settings(
            prod_agent_id=agent_id,
            image_name_wan22_video_v2=image_ref,
            model_bucket="allbot-model-cache",
        )
    )

    with pytest.raises(ValueError, match="must be .*20260619-wan22aio-rife"):
        provider.render_create_pod_request(
            task_type="wan22_video_v2",
            environment="cloud-prod",
            redact=False,
        )


def test_render_create_cloud_prod_split_video_ignores_template():
    agent_id = prod_agent_id_from_slot("02", profile="image_to_video")
    provider = RunPodProvider(
        _settings(
            prod_agent_id=agent_id,
            use_template_image_to_video=True,
            template_id_image_to_video="old-wan22-template",
            model_bucket="allbot-model-cache",
        )
    )

    payload = provider.render_create_pod_request(
        task_type="image_to_video",
        environment="cloud-prod",
        redact=False,
    )

    assert "templateId" not in payload["json"]
    assert payload["json"]["imageName"] == RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE


def test_render_create_cloud_prod_i2i_pro_uses_prod_refs_and_multitask_manifest():
    image_ref = (
        "ghcr.io/giraffu/allbot-comfy-runpod-i2i-pro:"
        "20260614-i2ipro-b75c6a9-cu128-min5-ssh"
    )
    agent_id = prod_agent_id_from_slot("01", profile="i2i_pro")
    provider = RunPodProvider(
        _settings(
            image_name_i2i_pro=image_ref,
            prod_agent_id=agent_id,
            model_bucket="allbot-model-cache",
            model_prefix_i2i_pro=RUNPOD_I2I_PRO_MODEL_PREFIX,
            model_manifest_key_i2i_pro=RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY,
            container_disk_gb=80,
        )
    )

    payload = provider.render_create_pod_request(
        task_type="i2i_pro",
        environment="cloud-prod",
        redact=False,
    )
    body = payload["json"]
    env = body["env"]

    assert "templateId" not in body
    assert body["name"] == "allbot-runpod-prod-i2i-pro-manual-01"
    assert body["imageName"] == image_ref
    assert body["gpuTypeIds"] == list(RUNPOD_PROD_GPU_TYPE_IDS)
    assert body["containerDiskInGb"] == RUNPOD_I2I_PRO_CONTAINER_DISK_GB
    assert env["ENVIRONMENT"] == "prod"
    assert env["RUNPOD_ENVIRONMENT"] == "cloud-prod"
    assert env["RUNPOD_TASK_TYPE"] == "i2i_pro"
    assert env["AGENT_ID"] == "runpod_prod_i2i_pro_manual_01"
    assert env["AGENT_ID_PREFIX"] == "runpod_prod_i2i_pro_manual_01"
    assert env["SUPPORTED_TASK_TYPES"] == ",".join(RUNPOD_I2I_PRO_SUPPORTED_TASK_TYPES)
    assert env["TASK_TYPE_WORKFLOW_OVERRIDES"] == RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES
    assert env["CENTRAL_API_URL"] == RUNPOD_PROD_WORKER_CENTRAL_URL
    assert env["POOL_RUNTIME_PROFILE"] == "i2i_pro"
    assert env["MINIO_RESULT_BUCKET"] == RUNPOD_PROD_BUCKET
    assert env["RUNPOD_MODEL_BUCKET"] == "allbot-model-cache"
    assert env["RUNPOD_MODEL_PREFIX"] == RUNPOD_I2I_PRO_MODEL_PREFIX
    assert env["RUNPOD_MODEL_MANIFEST_KEY"] == RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY
    assert env["RUNPOD_COMFY_CUSTOM_NODES_ENABLED"] == "false"
    assert env["RUNPOD_COMFY_KJNODES_ENABLED"] == "false"
    assert env["RUNPOD_START_SSHD"] == "false"
    assert env["AGENT_SECRET_TOKEN"] == RUNPOD_PROD_AGENT_SECRET_TOKEN_REF
    assert env["MINIO_ACCESS_KEY"] == RUNPOD_PROD_R2_ACCESS_KEY_REF
    assert env["MINIO_SECRET_KEY"] == RUNPOD_PROD_R2_SECRET_KEY_REF
    assert env["RUNPOD_MODEL_ACCESS_KEY"] == RUNPOD_MODEL_CACHE_R2_ACCESS_KEY_REF
    assert env["RUNPOD_MODEL_SECRET_KEY"] == RUNPOD_MODEL_CACHE_R2_SECRET_KEY_REF


def test_render_create_cloud_prod_scail2_uses_prod_refs_and_manifest():
    image_ref = RUNPOD_PUBLIC_SCAIL2_IMAGE_PREFIX + "20260617-scail2-prod"
    agent_id = prod_agent_id_from_slot("01", profile="scail2")
    provider = RunPodProvider(
        _settings(
            image_name_scail2=image_ref,
            prod_agent_id=agent_id,
            model_bucket="allbot-model-cache",
            model_prefix_scail2=RUNPOD_SCAIL2_MODEL_PREFIX,
            model_manifest_key_scail2=RUNPOD_SCAIL2_MODEL_MANIFEST_KEY,
            container_disk_gb=80,
        )
    )

    payload = provider.render_create_pod_request(
        task_type="scail2",
        environment="cloud-prod",
        redact=False,
    )
    body = payload["json"]
    env = body["env"]

    assert "templateId" not in body
    assert body["name"] == "allbot-runpod-prod-scail2-manual-01"
    assert body["imageName"] == image_ref
    assert body["gpuTypeIds"] == list(RUNPOD_PROD_GPU_TYPE_IDS)
    assert body["containerDiskInGb"] == RUNPOD_SCAIL2_CONTAINER_DISK_GB
    assert env["ENVIRONMENT"] == "prod"
    assert env["RUNPOD_ENVIRONMENT"] == "cloud-prod"
    assert env["RUNPOD_TASK_TYPE"] == "scail2"
    assert env["AGENT_ID"] == "runpod_prod_scail2_manual_01"
    assert env["AGENT_ID_PREFIX"] == "runpod_prod_scail2_manual_01"
    assert env["SUPPORTED_TASK_TYPES"] == ",".join(RUNPOD_SCAIL2_SUPPORTED_TASK_TYPES)
    assert env["CENTRAL_API_URL"] == RUNPOD_PROD_WORKER_CENTRAL_URL
    assert env["POOL_RUNTIME_PROFILE"] == "scail2"
    assert env["MINIO_RESULT_BUCKET"] == RUNPOD_PROD_BUCKET
    assert env["RUNPOD_MODEL_BUCKET"] == "allbot-model-cache"
    assert env["RUNPOD_MODEL_PREFIX"] == RUNPOD_SCAIL2_MODEL_PREFIX
    assert env["RUNPOD_MODEL_MANIFEST_KEY"] == RUNPOD_SCAIL2_MODEL_MANIFEST_KEY
    assert env["RUNPOD_COMFY_CUSTOM_NODES_ENABLED"] == "false"
    assert env["RUNPOD_COMFY_KJNODES_ENABLED"] == "false"
    assert env["RUNPOD_START_SSHD"] == "false"
    assert env["AGENT_SECRET_TOKEN"] == RUNPOD_PROD_AGENT_SECRET_TOKEN_REF
    assert env["MINIO_ACCESS_KEY"] == RUNPOD_PROD_R2_ACCESS_KEY_REF
    assert env["MINIO_SECRET_KEY"] == RUNPOD_PROD_R2_SECRET_KEY_REF
    assert env["RUNPOD_MODEL_ACCESS_KEY"] == RUNPOD_MODEL_CACHE_R2_ACCESS_KEY_REF
    assert env["RUNPOD_MODEL_SECRET_KEY"] == RUNPOD_MODEL_CACHE_R2_SECRET_KEY_REF


def test_render_create_cloud_prod_ltx_video_uses_v12_override_and_manifest():
    image_ref = RUNPOD_PUBLIC_LTX_VIDEO_IMAGE_PREFIX + "20260622-ltx-prod"
    agent_id = prod_agent_id_from_slot("01", profile="ltx_video")
    provider = RunPodProvider(
        _settings(
            image_name_ltx_video=image_ref,
            prod_agent_id=agent_id,
            model_bucket="allbot-model-cache",
            model_prefix_ltx_video=RUNPOD_LTX_VIDEO_MODEL_PREFIX,
            model_manifest_key_ltx_video=RUNPOD_LTX_VIDEO_MODEL_MANIFEST_KEY,
            container_disk_gb=80,
            prod_gpu_type_ids=("NVIDIA GeForce RTX 4090",),
        )
    )

    payload = provider.render_create_pod_request(
        task_type="ltx_video",
        environment="cloud-prod",
        redact=False,
    )
    body = payload["json"]
    env = body["env"]

    assert "templateId" not in body
    assert body["name"] == "allbot-runpod-prod-ltx-video-manual-01"
    assert body["imageName"] == image_ref
    assert body["gpuTypeIds"] == list(RUNPOD_LTX_VIDEO_GPU_TYPE_IDS)
    assert body["containerDiskInGb"] == RUNPOD_LTX_VIDEO_CONTAINER_DISK_GB
    assert body["dockerStartCmd"] == list(RUNPOD_LTX_VIDEO_DOCKER_START_CMD)
    assert env["ENVIRONMENT"] == "prod"
    assert env["RUNPOD_ENVIRONMENT"] == "cloud-prod"
    assert env["RUNPOD_TASK_TYPE"] == "ltx_video"
    assert env["AGENT_ID"] == "runpod_prod_ltx_video_manual_01"
    assert env["AGENT_ID_PREFIX"] == "runpod_prod_ltx_video_manual_01"
    assert env["SUPPORTED_TASK_TYPES"] == ",".join(
        RUNPOD_LTX_VIDEO_SUPPORTED_TASK_TYPES
    )
    assert env["TASK_TYPE_WORKFLOW_OVERRIDES"] == RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES
    assert env["CENTRAL_API_URL"] == RUNPOD_PROD_WORKER_CENTRAL_URL
    assert env["POOL_RUNTIME_PROFILE"] == "ltx_video"
    assert env["MINIO_RESULT_BUCKET"] == RUNPOD_PROD_BUCKET
    assert env["RUNPOD_MODEL_BUCKET"] == "allbot-model-cache"
    assert env["RUNPOD_MODEL_PREFIX"] == RUNPOD_LTX_VIDEO_MODEL_PREFIX
    assert env["RUNPOD_MODEL_MANIFEST_KEY"] == RUNPOD_LTX_VIDEO_MODEL_MANIFEST_KEY
    assert env["RUNPOD_COMFY_CUSTOM_NODES_ENABLED"] == "false"
    assert env["RUNPOD_COMFY_KJNODES_ENABLED"] == "false"
    assert env["RUNPOD_START_SSHD"] == "false"
    assert env["AGENT_SECRET_TOKEN"] == RUNPOD_PROD_AGENT_SECRET_TOKEN_REF
    assert env["MINIO_ACCESS_KEY"] == RUNPOD_PROD_R2_ACCESS_KEY_REF
    assert env["MINIO_SECRET_KEY"] == RUNPOD_PROD_R2_SECRET_KEY_REF
    assert env["RUNPOD_MODEL_ACCESS_KEY"] == RUNPOD_MODEL_CACHE_R2_ACCESS_KEY_REF
    assert env["RUNPOD_MODEL_SECRET_KEY"] == RUNPOD_MODEL_CACHE_R2_SECRET_KEY_REF


def test_prod_slot_default_max_allows_hundred_slot_namespace(monkeypatch):
    monkeypatch.delenv("RUNPOD_PROD_MAX_MANUAL_SLOTS", raising=False)

    assert prod_agent_id_from_slot("03") == "runpod_prod_img2img_manual_03"
    assert prod_agent_id_from_slot("100") == "runpod_prod_img2img_manual_100"
    try:
        prod_agent_id_from_slot("101")
    except ValueError as exc:
        assert "between 01 and 100" in str(exc)
    else:
        raise AssertionError("slot 101 should require explicit max slot configuration")


def test_render_create_cloud_prod_manual_worker_can_use_configured_eighth_slot():
    agent_id = prod_agent_id_from_slot("08", max_manual_slots=8)
    provider = RunPodProvider(
        _settings(
            image_name_img2img_lora=RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE,
            prod_agent_id=agent_id,
            prod_max_manual_slots=8,
        )
    )

    payload = provider.render_create_pod_request(
        task_type="img2img",
        environment="cloud-prod",
        redact=False,
    )
    body = payload["json"]
    env = body["env"]

    assert body["name"] == "allbot-runpod-prod-img2img-manual-08"
    assert env["AGENT_ID"] == "runpod_prod_img2img_manual_08"


def test_render_create_uses_network_volume_without_ephemeral_volume():
    provider = RunPodProvider(
        _settings(
            network_volume_id="boh3dica3z",
            volume_mount_path="/workspace",
        )
    )

    payload = provider.render_create_pod_request(
        task_type="img2img_lora",
        environment="cloud-test",
    )
    body = payload["json"]
    env = body["env"]

    assert body["networkVolumeId"] == "boh3dica3z"
    assert body["volumeMountPath"] == "/workspace"
    assert "volumeInGb" not in body
    assert env["ALLBOT_RUNPOD_ROOT"] == "/workspace/allbot"
    assert env["RUNPOD_WORKSPACE_DIR"] == "/workspace"
    assert env["RUNPOD_VOLUME_COMFYUI_DIR"] == "/workspace/ComfyUI"
    assert env["RUNPOD_PREPARE_COMFYUI_ON_VOLUME"] == "true"


def test_mutations_are_dry_run_by_default_and_do_not_call_api():
    fake = FakeRunPodApi({"id": "pod-created"})
    provider = RunPodProvider(_settings(), request_func=fake)

    payload = provider.create_pod(
        task_type="img2img_lora",
        environment="cloud-test",
        existing_pods=[],
        execute=True,
    )

    assert payload["ok"] is False
    assert payload["dry_run"] is True
    assert "RUNPOD_DRY_RUN=true" in payload["guard"]["reasons"]
    assert "RUNPOD_AUTOSCALER_ENABLED=false" in payload["guard"]["reasons"]
    assert fake.calls == []


def test_mutation_gate_allows_existing_pods_after_capacity_limits_removed():
    fake = FakeRunPodApi({"id": "pod-created"})
    provider = RunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            agent_secret_token="inline_agent_value",
            minio_access_key="inline_r2_access_value",
            minio_secret_key="inline_r2_secret_value",
        ),
        request_func=fake,
    )
    existing = [
        {
            "id": "pod-existing",
            "desiredStatus": "RUNNING",
            "adjustedCostPerHr": 0.5,
            "env": {"RUNPOD_TASK_TYPE": "img2img_lora"},
        }
    ]

    payload = provider.create_pod(
        task_type="img2img_lora",
        environment="cloud-test",
        existing_pods=existing,
        execute=True,
    )

    assert payload["ok"] is True
    assert fake.calls[0]["method"] == "POST"


def test_mutation_gate_allows_create_after_hourly_cost_limit_removed():
    fake = FakeRunPodApi({"id": "pod-created"})
    provider = RunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            max_hourly_cost_usd=0.25,
            projected_cost_per_hr_img2img_lora=0.5,
        ),
        request_func=fake,
    )

    payload = provider.create_pod(
        task_type="img2img_lora",
        environment="cloud-test",
        existing_pods=[],
        execute=True,
    )

    assert payload["ok"] is True
    assert fake.calls[0]["method"] == "POST"


def test_wan22_mutation_gate_allows_existing_same_type_and_cost_after_limits_removed():
    fake = FakeRunPodApi({"id": "pod-created"})
    provider = RunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            max_hourly_cost_usd=0.25,
            projected_cost_per_hr_wan22_aio_video=0.5,
            image_name_wan22_aio_video=(
                "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:"
                "20260612-wan22aio-test"
            ),
        ),
        request_func=fake,
    )
    existing = [
        {
            "id": "pod-existing",
            "desiredStatus": "RUNNING",
            "adjustedCostPerHr": 0.1,
            "env": {"RUNPOD_TASK_TYPE": "wan22_aio_video"},
        }
    ]

    payload = provider.create_pod(
        task_type="wan22_aio_video",
        environment="cloud-test",
        existing_pods=existing,
        execute=True,
    )

    assert payload["ok"] is True
    assert fake.calls[0]["method"] == "POST"


def test_execute_create_posts_runpod_secret_references_not_inline_local_secrets():
    fake = FakeRunPodApi({"id": "pod-created"})
    provider = RunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            agent_secret_token="inline_agent_value",
            minio_access_key="inline_r2_access_value",
            minio_secret_key="inline_r2_secret_value",
        ),
        request_func=fake,
    )

    payload = provider.create_pod(
        task_type="img2img_lora",
        environment="cloud-test",
        existing_pods=[],
        execute=True,
    )
    posted_env = fake.calls[0]["json_body"]["env"]
    rendered = json.dumps(fake.calls[0]["json_body"], ensure_ascii=False)

    assert payload["ok"] is True
    assert posted_env["AGENT_SECRET_TOKEN"] == (
        "{{ RUNPOD_SECRET_allbot_cloud_test_agent_secret_token }}"
    )
    assert posted_env["MINIO_ACCESS_KEY"] == (
        "{{ RUNPOD_SECRET_allbot_cloud_test_r2_access_key }}"
    )
    assert posted_env["MINIO_SECRET_KEY"] == (
        "{{ RUNPOD_SECRET_allbot_cloud_test_r2_secret_key }}"
    )
    assert "inline_agent_value" not in rendered
    assert "inline_r2_access_value" not in rendered
    assert "inline_r2_secret_value" not in rendered


def test_execute_create_allows_second_prod_manual_worker_when_limit_is_two():
    fake = FakeRunPodApi({"id": "pod-created"})
    provider = RunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            max_pods_total=2,
            max_pods_per_type=2,
            image_name_img2img_lora=RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE,
            prod_agent_id=prod_agent_id_from_slot("02"),
        ),
        request_func=fake,
    )
    existing = [
        {
            "id": "pod-existing",
            "name": "allbot-runpod-prod-img2img-manual-01",
            "desiredStatus": "RUNNING",
            "env": {
                "RUNPOD_ENVIRONMENT": "cloud-prod",
                "RUNPOD_TASK_TYPE": "img2img_lora",
                "AGENT_ID": "runpod_prod_img2img_manual_01",
            },
        }
    ]

    payload = provider.create_pod(
        task_type="img2img",
        environment="cloud-prod",
        existing_pods=existing,
        execute=True,
    )

    assert payload["ok"] is True
    assert fake.calls[0]["json_body"]["name"] == "allbot-runpod-prod-img2img-manual-02"
    assert (
        fake.calls[0]["json_body"]["env"]["AGENT_ID"] == "runpod_prod_img2img_manual_02"
    )


def test_execute_create_allows_third_prod_manual_worker_when_configured_limit_is_three():
    fake = FakeRunPodApi({"id": "pod-created"})
    provider = RunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            max_pods_total=3,
            max_pods_per_type=3,
            image_name_img2img_lora=RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE,
            prod_agent_id=prod_agent_id_from_slot("03", max_manual_slots=8),
            prod_max_manual_slots=8,
        ),
        request_func=fake,
    )
    existing = [
        {
            "id": "pod-existing-01",
            "name": "allbot-runpod-prod-img2img-manual-01",
            "desiredStatus": "RUNNING",
            "env": {
                "RUNPOD_ENVIRONMENT": "cloud-prod",
                "RUNPOD_TASK_TYPE": "img2img_lora",
                "AGENT_ID": "runpod_prod_img2img_manual_01",
            },
        },
        {
            "id": "pod-existing-02",
            "name": "allbot-runpod-prod-img2img-manual-02",
            "desiredStatus": "RUNNING",
            "env": {
                "RUNPOD_ENVIRONMENT": "cloud-prod",
                "RUNPOD_TASK_TYPE": "img2img_lora",
                "AGENT_ID": "runpod_prod_img2img_manual_02",
            },
        },
    ]

    payload = provider.create_pod(
        task_type="img2img",
        environment="cloud-prod",
        existing_pods=existing,
        execute=True,
    )

    assert payload["ok"] is True
    assert fake.calls[0]["json_body"]["name"] == "allbot-runpod-prod-img2img-manual-03"
    assert (
        fake.calls[0]["json_body"]["env"]["AGENT_ID"] == "runpod_prod_img2img_manual_03"
    )


def test_mutation_gate_allows_global_total_above_manual_slots():
    fake = FakeRunPodApi({"id": "pod-created"})
    provider = RunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            max_pods_total=5,
            max_pods_per_type=1,
            max_hourly_cost_usd=10.0,
            image_name_wan22_video_v2=RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE,
            prod_agent_id=prod_agent_id_from_slot(
                "01",
                profile="wan22_video_v2",
            ),
        ),
        request_func=fake,
    )
    existing = [
        {
            "id": f"pod-existing-{index}",
            "desiredStatus": "RUNNING",
            "adjustedCostPerHr": 0.5,
            "env": {"RUNPOD_TASK_TYPE": task_type},
        }
        for index, task_type in enumerate(
            ["i2i_pro", "img2img_lora", "img2img_lora", "image_to_video"],
            start=1,
        )
    ]

    payload = provider.create_pod(
        task_type="wan22_video_v2",
        environment="cloud-prod",
        existing_pods=existing,
        execute=True,
    )

    assert payload["ok"] is True
    assert fake.calls[0]["method"] == "POST"
    assert fake.calls[0]["json_body"]["env"]["RUNPOD_TASK_TYPE"] == "wan22_video_v2"


def test_mutation_gate_ignores_removed_per_type_capacity_limit():
    provider = RunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            max_pods_total=9,
            max_pods_per_type=9,
            prod_max_manual_slots=8,
        ),
        request_func=FakeRunPodApi({"id": "pod-created"}),
    )

    payload = provider.create_pod(
        task_type="img2img_lora",
        environment="cloud-test",
        existing_pods=[],
        execute=True,
    )

    assert payload["ok"] is True


def test_start_stop_restart_delete_are_guarded_by_default():
    fake = FakeRunPodApi({"ok": True})
    provider = RunPodProvider(_settings(), request_func=fake)

    start = provider.start_pod(pod_id="pod-1", execute=True)
    stop = provider.stop_pod(pod_id="pod-1", execute=True)
    restart = provider.restart_pod(pod_id="pod-1", execute=True)
    delete = provider.delete_pod(pod_id="pod-1", execute=True)

    assert start["ok"] is False
    assert stop["ok"] is False
    assert restart["ok"] is False
    assert delete["ok"] is False
    assert "RUNPOD_DRY_RUN=true" in start["guard"]["reasons"]
    assert "RUNPOD_DRY_RUN=true" in stop["guard"]["reasons"]
    assert "RUNPOD_DRY_RUN=true" in restart["guard"]["reasons"]
    assert "RUNPOD_DRY_RUN=true" in delete["guard"]["reasons"]
    assert fake.calls == []


def test_restart_pod_uses_runpod_native_restart_endpoint():
    fake = FakeRunPodApi({"id": "pod-1", "desiredStatus": "RUNNING"})
    provider = RunPodProvider(
        _settings(dry_run=False, autoscaler_enabled=True),
        request_func=fake,
    )

    payload = provider.restart_pod(pod_id="pod-1", execute=True)

    assert payload["ok"] is True
    assert payload["action"] == "restart"
    assert fake.calls == [
        {
            "method": "POST",
            "path": "/pods/pod-1/restart",
            "params": {},
            "json_body": None,
            "headers": {
                "Authorization": "Bearer rp_secret_api_key",
                "Content-Type": "application/json",
            },
        }
    ]


def test_api_errors_are_redacted_before_returning_to_cli():
    fake = FakeRunPodApi(
        exc=RunPodProviderError(
            "Authorization: Bearer rp_secret_api_key "
            "token=agent_secret_token secret=r2_secret_key "
            "https://r2.example.test/result.png?X-Amz-Signature=signature_leak"
        )
    )
    provider = RunPodProvider(_settings(), request_func=fake)

    payload = provider.validate_key()
    rendered = json.dumps(payload, ensure_ascii=False)

    assert payload["ok"] is False
    assert "rp_secret_api_key" not in rendered
    assert "agent_secret_token" not in rendered
    assert "r2_secret_key" not in rendered
    assert "signature_leak" not in rendered


def test_execute_errors_are_returned_as_redacted_json():
    fake = FakeRunPodApi(
        exc=RunPodProviderError(
            "create failed api_key=rp_secret_api_key secret=r2_secret_key"
        )
    )
    provider = RunPodProvider(
        _settings(dry_run=False, autoscaler_enabled=True),
        request_func=fake,
    )

    payload = provider.create_pod(
        task_type="img2img_lora",
        environment="cloud-test",
        existing_pods=[],
        execute=True,
    )
    rendered = json.dumps(payload, ensure_ascii=False)

    assert payload["ok"] is False
    assert payload["dry_run"] is False
    assert payload["action"] == "create"
    assert "rp_secret_api_key" not in rendered
    assert "r2_secret_key" not in rendered


def test_execute_create_reconciles_existing_pods_before_posting():
    fake = FakeRunPodApi(
        {
            "pods": [
                {
                    "id": "pod-existing",
                    "desiredStatus": "RUNNING",
                    "adjustedCostPerHr": 0.5,
                    "name": "allbot-runpod-test-img2img-lora",
                    "env": {"RUNPOD_TASK_TYPE": "img2img_lora"},
                }
            ]
        }
    )
    provider = RunPodProvider(
        _settings(dry_run=False, autoscaler_enabled=True),
        request_func=fake,
    )

    payload = provider.create_pod(
        task_type="img2img_lora",
        environment="cloud-test",
        execute=True,
    )

    assert payload["ok"] is True
    assert [call["method"] for call in fake.calls] == ["GET", "POST"]


def test_runpod_provider_does_not_enter_lan_ssh_inventory():
    inventory = LanSshProvider().inventory_from_config(
        {
            "lan-node": GpuNode(
                id="lan-node",
                provider="lan_ssh",
                host="lan-host",
                ip="192.0.2.10",
                ssh_alias="allbot-lan",
                model_dir="/data/models",
                runtime="docker",
                gpus=(),
                comfy=(),
            ),
            "runpod-node": GpuNode(
                id="runpod-node",
                provider="runpod",
                host="runpod",
                ip="",
                ssh_alias="",
                model_dir="/workspace/ComfyUI/models",
                runtime="pod",
                gpus=(),
                comfy=(),
            ),
        }
    )

    assert "lan-node" in inventory
    assert "runpod-node" not in inventory
