import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_cloud_compose_uses_one_image_contract_per_module():
    compose = yaml.safe_load(
        (ROOT / "deploy/docker-compose-cloud-base.yml").read_text(encoding="utf-8")
    )
    services = compose["services"]
    expected = {
        "central-api": "ALLBOT_CENTRAL_IMAGE",
        "web-api": "ALLBOT_WEB_API_IMAGE",
        "payment-api": "ALLBOT_PAYMENT_API_IMAGE",
        "dashboard-backend": "ALLBOT_DASHBOARD_BACKEND_IMAGE",
        "dashboard-frontend": "ALLBOT_DASHBOARD_FRONTEND_IMAGE",
        "qqcc-config-backend": "ALLBOT_QQCC_CONFIG_BACKEND_IMAGE",
        "qqcc-config-frontend": "ALLBOT_QQCC_CONFIG_FRONTEND_IMAGE",
        "bot": "ALLBOT_MAIN_BOT_IMAGE",
        "qqcc-bot": "ALLBOT_QQCC_BOT_IMAGE",
        "qqcc-private-bot-worker": "ALLBOT_PRIVATE_BOT_WORKER_IMAGE",
        "paid-group-guard-bot": "ALLBOT_PAID_GROUP_BOT_IMAGE",
    }
    for service, variable in expected.items():
        assert variable in services[service]["image"]
    assert len({services[name]["image"] for name in expected}) == len(expected)


def test_test_worker_agent_and_relay_have_distinct_thin_images():
    compose = yaml.safe_load(
        (ROOT / "deploy/docker-compose-worker-base.yml").read_text(encoding="utf-8")
    )
    assert "ALLBOT_WORKER_AGENT_IMAGE" in compose["x-worker-base"]["image"]
    assert "ALLBOT_WORKER_RELAY_IMAGE" in compose["services"]["worker-relay"]["image"]
    assert compose["x-worker-base"]["image"] != compose["services"]["worker-relay"]["image"]


def test_python_bases_and_thin_targets_are_explicit():
    control = (ROOT / "deploy/docker/Dockerfile.control-plane").read_text(
        encoding="utf-8"
    )
    worker = (ROOT / "deploy/docker/Dockerfile.test-execution").read_text(
        encoding="utf-8"
    )
    runtime = (ROOT / "deploy/docker/Dockerfile.python-runtime-base").read_text(
        encoding="utf-8"
    )
    assert "AS python-runtime-base" in runtime
    assert "ARG RUNTIME_BASE_IMAGE" in control
    targets = (
        "central-api",
        "web-api",
        "payment-api",
        "main-bot",
        "qqcc-bot",
        "private-bot-worker",
        "paid-group-bot",
        "support-bot",
        "dashboard-backend",
        "qqcc-config-backend",
    )
    for target in targets:
        assert f"AS {target}" in control
        section = control.split(f"AS {target}", 1)[1]
        assert "ARG ALLBOT_GIT_SHA" in section
        assert "org.opencontainers.image.revision=$ALLBOT_GIT_SHA" in section
    assert control.count("COPY config.py /app/config.py") == len(targets)
    dashboard_section = control.split("AS dashboard-backend", 1)[1].split(
        "AS qqcc-config-backend", 1
    )[0]
    assert "COPY ops /app/ops" in dashboard_section
    assert "COPY paid_group_guard_bot /app/paid_group_guard_bot" in dashboard_section
    assert "scripts/runpod_prod_ops.sh" in dashboard_section
    assert "scripts/gpu_pool_controller.py" in dashboard_section
    assert "AS python-worker-base" in worker
    assert "AS worker-agent" in worker
    assert "AS worker-relay" in worker
    relay_section = worker.split("AS worker-relay", 1)[1]
    assert "workers/comfy_agent" not in relay_section
    assert "workflows" not in relay_section


def test_private_bot_worker_image_contains_its_qqcc_runtime_dependency():
    control = (ROOT / "deploy/docker/Dockerfile.control-plane").read_text(
        encoding="utf-8"
    )
    private_worker = control.split("AS private-bot-worker", 1)[1].split(
        "AS paid-group-bot", 1
    )[0]
    assert "COPY qqcc_private_bot /app/qqcc_private_bot" in private_worker
    assert "COPY qqcc_bot /app/qqcc_bot" in private_worker

    catalog = json.loads(
        (ROOT / "deploy/release-artifacts-v2.json").read_text(encoding="utf-8")
    )
    assert "qqcc_bot/**" in catalog["artifacts"]["private-bot-worker"]["inputs"]


def test_i2i_pro_gpu_release_contract_includes_legacy_face_swap():
    catalog = json.loads(
        (ROOT / "deploy/release-artifacts-v2.json").read_text(encoding="utf-8")
    )
    assert catalog["artifacts"]["i2i_pro"]["profile"]["task_types"] == [
        "i2i_pro",
        "t2i-pornmaster-turbo",
        "face_swap_v2",
        "face_swap",
    ]


def test_web_api_image_and_release_smoke_require_ffmpeg():
    control = (ROOT / "deploy/docker/Dockerfile.control-plane").read_text(
        encoding="utf-8"
    )
    web_api = control.split("AS web-api", 1)[1].split("AS payment-api", 1)[0]
    assert "apt-get install -y --no-install-recommends ffmpeg" in web_api

    workflow = (ROOT / ".github/workflows/modular-release-v2.yml").read_text(
        encoding="utf-8"
    )
    assert "web_ref=" in workflow
    assert 'docker run --rm --entrypoint ffmpeg "$web_ref" -version' in workflow


def test_qqcc_video_chain_runtime_images_and_release_smoke_require_ffmpeg_tools():
    media_runtime = (ROOT / "deploy/docker/Dockerfile.media-runtime-base").read_text(
        encoding="utf-8"
    )
    assert "AS python-media-runtime-base" in media_runtime
    assert "apt-get install -y --no-install-recommends ffmpeg" in media_runtime

    catalog = json.loads(
        (ROOT / "deploy/release-artifacts-v2.json").read_text(encoding="utf-8")
    )["artifacts"]
    media_base = catalog["python-media-runtime-base"]
    assert media_base["base"] == "python-runtime-base"
    assert media_base["dockerfile"] == "deploy/docker/Dockerfile.media-runtime-base"
    for target in (
        "qqcc-bot",
        "private-bot-worker",
        "dashboard-backend",
        "qqcc-config-backend",
    ):
        assert catalog[target]["base"] == "python-media-runtime-base"
    assert catalog["central-api"]["base"] == "python-runtime-base"
    assert catalog["main-bot"]["base"] == "python-runtime-base"

    workflow = (ROOT / ".github/workflows/modular-release-v2.yml").read_text(
        encoding="utf-8"
    )
    assert "qqcc_bot_ref=" in workflow
    assert "private_bot_ref=" in workflow
    assert "qqcc_config_backend_ref=" in workflow
    assert (
        'docker run --rm --entrypoint sh "$qqcc_bot_ref" '
        "-c 'ffmpeg -version && ffprobe -version'"
    ) in workflow
    assert (
        'docker run --rm --entrypoint sh "$private_bot_ref" '
        "-c 'ffmpeg -version && ffprobe -version'"
    ) in workflow
    assert (
        'docker run --rm --entrypoint sh "$backend_ref" '
        "-c 'ffmpeg -version && ffprobe -version'"
    ) in workflow
    assert (
        'docker run --rm --entrypoint sh "$qqcc_config_backend_ref" '
        "-c 'ffmpeg -version && ffprobe -version'"
    ) in workflow


def test_dashboard_and_qqcc_frontends_are_separate_targets():
    dockerfile = (ROOT / "deploy/docker/Dockerfile.frontends").read_text(
        encoding="utf-8"
    )
    assert "AS dashboard-frontend" in dockerfile
    assert "AS qqcc-config-frontend" in dockerfile
    qqcc = dockerfile.split("AS qqcc-config-frontend", 1)[1]
    assert "index.private-bot.html" in qqcc
    assert dockerfile.count("mkdir -p /etc/nginx/templates") == 2
