import json

from ops.gpu_pool_controller.providers.lan_ssh import LanSshProvider
from ops.gpu_pool_controller.providers.runpod import (
    RUNPOD_MODEL_CACHE_R2_ACCESS_KEY_REF,
    RUNPOD_MODEL_CACHE_R2_SECRET_KEY_REF,
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
    RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS,
    RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY,
    RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX,
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
    provider = RunPodProvider(_settings(), request_func=fake)

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
    provider = RunPodProvider(_settings(), request_func=fake)

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
    provider = RunPodProvider(_settings(), request_func=fake)

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
    provider = RunPodProvider(_settings(), request_func=fake)

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
    provider = RunPodProvider(_settings(), request_func=fake)

    payload = provider.pod_readiness(pod_id="pod-1")
    readiness = payload["readiness"]

    assert readiness["infrastructure_ready"] is True
    assert readiness["confidence"] == "network_mapping_confirmed"
    assert readiness["reasons"] == []
    assert readiness["signals"]["public_ip_present"] is True
    assert readiness["signals"]["port_mappings_present"] is True
    assert readiness["network"]["public_ip_present"] is True
    assert readiness["network"]["port_mappings_present"] is True


def test_pod_readiness_does_not_treat_secure_pod_without_public_ip_as_ready():
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

    assert readiness["infrastructure_ready"] is False
    assert readiness["confidence"] == "status_only_no_exposed_ports"
    assert "public_ip_missing" in readiness["reasons"]
    assert readiness["signals"]["public_ip_expected"] is True


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
            bootstrap_git_url="https://github.com/giraffu/All_bot.git",
            bootstrap_git_branch="deploy",
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
    assert env["ALLBOT_RUNPOD_GIT_URL"] == "https://github.com/giraffu/All_bot.git"
    assert env["ALLBOT_RUNPOD_GIT_BRANCH"] == "deploy"
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
    assert env["RUNPOD_MODEL_PREFIX"] == "wan22_aio_video/2026-06-12-test"
    assert env["RUNPOD_MODEL_MANIFEST_KEY"] == (
        "wan22_aio_video/2026-06-12-test/manifest.json"
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
    assert env["RUNPOD_MODEL_PREFIX"] == "wan22_aio_video/2026-06-12-test"
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


def test_runpod_settings_from_env_split_video_profiles_fallback_to_wan22_image_template(
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
    monkeypatch.setenv("RUNPOD_MODEL_BUCKET", "allbot-model-cache")
    monkeypatch.delenv("RUNPOD_TEMPLATE_ID_IMAGE_TO_VIDEO", raising=False)
    monkeypatch.delenv("RUNPOD_TEMPLATE_ID_WAN22_VIDEO_V2", raising=False)
    monkeypatch.delenv("RUNPOD_IMAGE_NAME_IMAGE_TO_VIDEO", raising=False)
    monkeypatch.delenv("RUNPOD_IMAGE_NAME_WAN22_VIDEO_V2", raising=False)

    settings = RunPodSettings.from_env()

    assert settings.use_template_image_to_video is True
    assert settings.use_template_wan22_video_v2 is True
    assert settings.template_id_image_to_video == "77gi0wqo8x"
    assert settings.template_id_wan22_video_v2 == "77gi0wqo8x"
    assert settings.image_name_image_to_video.endswith(":shared")
    assert settings.image_name_wan22_video_v2.endswith(":shared")
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


def test_prod_slot_default_max_rejects_third_slot(monkeypatch):
    monkeypatch.delenv("RUNPOD_PROD_MAX_MANUAL_SLOTS", raising=False)

    try:
        prod_agent_id_from_slot("03")
    except ValueError as exc:
        assert "between 01 and 02" in str(exc)
    else:
        raise AssertionError("slot 03 should require explicit max slot configuration")


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


def test_mutation_gate_blocks_more_than_one_total_pod_or_type():
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

    assert payload["ok"] is False
    assert "runpod active pod total limit reached" in payload["guard"]["reasons"]
    assert (
        "runpod active pod limit reached for img2img_lora"
        in payload["guard"]["reasons"]
    )
    assert fake.calls == []


def test_mutation_gate_blocks_hourly_cost_limit():
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

    assert payload["ok"] is False
    assert "RUNPOD_MAX_HOURLY_COST_USD would be exceeded" in payload["guard"]["reasons"]
    assert fake.calls == []


def test_wan22_mutation_gate_blocks_same_type_and_hourly_cost_limit():
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

    assert payload["ok"] is False
    assert "runpod active pod total limit reached" in payload["guard"]["reasons"]
    assert (
        "runpod active pod limit reached for wan22_aio_video"
        in payload["guard"]["reasons"]
    )
    assert "RUNPOD_MAX_HOURLY_COST_USD would be exceeded" in payload["guard"]["reasons"]
    assert fake.calls == []


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


def test_mutation_gate_caps_v0_managed_pods_at_two():
    provider = RunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            max_pods_total=3,
        ),
        request_func=FakeRunPodApi({"id": "pod-created"}),
    )

    payload = provider.create_pod(
        task_type="img2img_lora",
        environment="cloud-test",
        existing_pods=[],
        execute=True,
    )

    assert payload["ok"] is False
    assert (
        "RUNPOD_MAX_PODS_TOTAL must be between 1 and 2 for v0"
        in payload["guard"]["reasons"]
    )


def test_mutation_gate_caps_v0_managed_pods_at_configured_max():
    provider = RunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            max_pods_total=9,
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

    assert payload["ok"] is False
    assert (
        "RUNPOD_MAX_PODS_TOTAL must be between 1 and 8 for v0"
        in payload["guard"]["reasons"]
    )


def test_start_stop_delete_are_guarded_by_default():
    fake = FakeRunPodApi({"ok": True})
    provider = RunPodProvider(_settings(), request_func=fake)

    start = provider.start_pod(pod_id="pod-1", execute=True)
    stop = provider.stop_pod(pod_id="pod-1", execute=True)
    delete = provider.delete_pod(pod_id="pod-1", execute=True)

    assert start["ok"] is False
    assert stop["ok"] is False
    assert delete["ok"] is False
    assert "RUNPOD_DRY_RUN=true" in start["guard"]["reasons"]
    assert "RUNPOD_DRY_RUN=true" in stop["guard"]["reasons"]
    assert "RUNPOD_DRY_RUN=true" in delete["guard"]["reasons"]
    assert fake.calls == []


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

    assert payload["ok"] is False
    assert "runpod active pod total limit reached" in payload["guard"]["reasons"]
    assert [call["method"] for call in fake.calls] == ["GET"]


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
