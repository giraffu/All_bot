from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "deploy" / "docker-compose-cloud-base.yml"
OVERLAYS = (
    ROOT / "deploy" / "docker-compose-cloud-test.overlay.yml",
    ROOT / "deploy" / "docker-compose-cloud-prod.overlay.yml",
)
WORKER_BASE = ROOT / "deploy" / "docker-compose-worker-base.yml"


def _compose(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_immutable_cloud_compose_has_no_build_or_code_mounts():
    forbidden_mounts = ("src", "backend/app", "workflows", ".env")

    for path in (BASE, *OVERLAYS, WORKER_BASE):
        compose = _compose(path)
        for service in compose.get("services", {}).values():
            assert "build" not in service, f"{path}: build is forbidden"
            for volume in service.get("volumes", []) or []:
                source = str(volume).split(":", 1)[0]
                assert not any(item in source for item in forbidden_mounts), (
                    f"{path}: source/config bind mount is forbidden: {volume}"
                )


def test_every_runtime_image_is_supplied_by_release_env():
    services = _compose(BASE)["services"]

    for name, service in services.items():
        image = str(service["image"])
        assert image.startswith("${ALLBOT_"), f"{name} does not use release.env"
        assert "latest" not in image


def test_central_and_worker_images_contain_their_dependency_closure():
    central = (ROOT / "deploy/docker/Dockerfile.central").read_text(encoding="utf-8")
    dashboard = (
        ROOT / "deploy/docker/Dockerfile.dashboard-backend"
    ).read_text(encoding="utf-8")
    worker = (ROOT / "deploy/docker/Dockerfile.worker").read_text(encoding="utf-8")

    assert "COPY backend/app /app/app" in central
    assert "COPY src /app/src" in central
    assert "COPY config.py /app/config.py" in dashboard
    assert "COPY ops /app/ops" in dashboard
    assert "COPY paid_group_guard_bot /app/paid_group_guard_bot" in dashboard
    assert "COPY workers/comfy_agent /app/worker" in worker
    assert "COPY src /app/src" in worker


def test_dashboard_frontend_image_prepares_nginx_template_directory():
    dockerfile = (
        ROOT / "deploy/docker/Dockerfile.dashboard-frontend"
    ).read_text(encoding="utf-8")

    assert "mkdir -p /etc/nginx/templates" in dockerfile


def test_worker_compose_covers_all_test_slots_and_runtime_contracts():
    services = _compose(WORKER_BASE)["services"]

    for slot in range(1, 9):
        name = f"worker-{slot:02d}"
        assert name in services
        environment = services[name]["environment"]
        for key in (
            "AGENT_ID",
            "COMFY_API_URL",
            "COMFY_WS_URL",
            "SUPPORTED_TASK_TYPES",
            "POOL_NODE_ID",
            "POOL_GPU_INDEX",
            "POOL_RUNTIME_PROFILE",
            "PREFETCH_ENABLED",
            "PIPELINE_ENABLED",
            "PIPELINE_MAX_RUNNING_TASKS",
        ):
            assert key in environment, f"{name} is missing {key}"

    worker_08 = services["worker-08"]["environment"]
    assert "TASK_TYPE_WORKFLOW_OVERRIDES" in worker_08
    assert "SCAIL2_FACE_SWAP_V10_ENABLED" in worker_08
    assert "SCAIL2_FACE_SWAP_V10_FACE_SWAP_COMFY_API_URL" in worker_08

    dormant_worker = services["worker-05"]["environment"]
    for key in (
        "POOL_NODE_ID",
        "POOL_GPU_INDEX",
        "POOL_RUNTIME_PROFILE",
        "PREFETCH_ENABLED",
        "PIPELINE_ENABLED",
        "PIPELINE_MAX_RUNNING_TASKS",
    ):
        assert ":-" in dormant_worker[key], f"dormant worker must default {key}"


def test_test_stateful_services_reuse_legacy_volumes_and_runtime_names():
    overlay = _compose(OVERLAYS[0])
    services = overlay["services"]
    volumes = overlay["volumes"]

    assert volumes["cloud-postgres-test-data"] == {
        "external": True,
        "name": "deploy_cloud-postgres-test-data",
    }
    assert volumes["cloud-redis-test-data"] == {
        "external": True,
        "name": "deploy_cloud-redis-test-data",
    }
    assert services["postgres"]["environment"] == {
        "POSTGRES_DB": "${CLOUD_TEST_POSTGRES_DB:-bot_db_test}",
        "POSTGRES_USER": "${CLOUD_TEST_POSTGRES_USER:-postgres}",
        "POSTGRES_PASSWORD": "${CLOUD_TEST_POSTGRES_PASSWORD:?CLOUD_TEST_POSTGRES_PASSWORD is required}",
    }
    assert services["postgres"]["networks"]["default"]["aliases"] == [
        "postgres-test"
    ]
    assert services["redis"]["networks"]["default"]["aliases"] == ["redis-test"]


def test_test_runtime_overrides_legacy_api_base_test_for_every_consumer():
    services = _compose(OVERLAYS[0])["services"]
    expected_api_base = "http://central-api:8003"

    for name in (
        "central-api",
        "web-api",
        "dashboard-backend",
        "qqcc-config-backend",
        "bot",
        "qqcc-bot",
        "qqcc-private-bot-worker",
    ):
        environment = services[name]["environment"]
        assert environment["BOT_TYPE"] == "TEST"
        assert environment["API_BASE"] == expected_api_base
        assert environment["API_BASE_TEST"] == expected_api_base, (
            f"{name} would let legacy env override the immutable Central alias"
        )


def test_prod_runtime_pins_internal_api_base_for_every_python_consumer():
    services = _compose(OVERLAYS[1])["services"]
    expected_api_base = "http://central-api:8003"

    for name in (
        "central-api",
        "web-api",
        "payment-api",
        "dashboard-backend",
        "qqcc-config-backend",
        "bot",
        "qqcc-bot",
        "qqcc-private-bot-worker",
        "paid-group-guard-bot",
    ):
        environment = services[name]["environment"]
        assert environment["BOT_TYPE"] == "PROD"
        assert environment["API_BASE"] == expected_api_base


def test_prod_payment_port_matches_application_listener():
    base_payment = _compose(BASE)["services"]["payment-api"]
    payment = _compose(OVERLAYS[1])["services"]["payment-api"]

    assert payment["ports"] == ["${CLOUD_PROD_BIND_IP:-127.0.0.1}:8021:8021"]
    assert payment["environment"]["PAYMENT_API_PORT"] == "8021"
    assert "http://127.0.0.1:8021/pay/result" in " ".join(
        base_payment["healthcheck"]["test"]
    )


def test_release_workflow_builds_all_images_and_never_uses_latest():
    workflow = (ROOT / ".github/workflows/control-plane-release.yml").read_text(
        encoding="utf-8"
    )

    for image in (
        "allbot-app",
        "allbot-central-api",
        "allbot-dashboard-backend",
        "allbot-dashboard-frontend",
        "allbot-worker",
        "allbot-release",
    ):
        assert image in workflow
    assert ":latest" not in workflow
    assert (
        '05-select-dashboard-spa.sh && test -f '
        '/etc/nginx/templates/default.conf.template'
    ) in workflow
    assert (
        'import dashboard.backend.main; '
        'import dashboard.backend.qqcc_config_main'
    ) in workflow
    assert "DASHBOARD_FRONTEND_MODE=qqcc" in workflow


def test_python_ci_workflows_install_backend_dependencies_and_use_test_jwt():
    runtime_version = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    workflows = (
        ROOT / ".github/workflows/control-plane-release.yml",
        ROOT / ".github/workflows/hotspot_regression_gate.yml",
    )

    for path in workflows:
        workflow = path.read_text(encoding="utf-8")
        assert "-r requirements.txt -r backend/requirements.txt" in workflow
        assert "JWT_SECRET_KEY: ci-test-only-not-for-runtime" in workflow
        assert f"python-version: '{runtime_version}'" in workflow or (
            f'python-version: "{runtime_version}"' in workflow
        )

    release_workflow = workflows[0].read_text(encoding="utf-8")
    assert "numpy==2.2.1" in release_workflow


def test_release_python_gate_shards_every_test_directory_with_timeouts():
    workflow = (ROOT / ".github/workflows/control-plane-release.yml").read_text(
        encoding="utf-8"
    )
    test_directories = sorted(
        path.name
        for path in (ROOT / "tests").iterdir()
        if path.is_dir() and path.name != "__pycache__"
    )

    assert "timeout-minutes: 20" in workflow
    assert "timeout --signal=INT --kill-after=30s 10m" in workflow
    assert "fail-fast: false" in workflow
    assert "python -m pytest -vv --maxfail=1 --durations=20" in workflow
    assert "${{ matrix.paths }}" in workflow
    assert "tests/test_*.py" in workflow
    for directory in test_directories:
        assert f"tests/{directory}" in workflow


def test_release_postgres_integration_gate_uses_isolated_migrated_database():
    workflow = (ROOT / ".github/workflows/control-plane-release.yml").read_text(
        encoding="utf-8"
    )

    assert "postgres-integration-tests:" in workflow
    assert "image: postgres:15.13-bookworm" in workflow
    assert "POSTGRES_DB: bot_db" in workflow
    assert "Base.metadata.create_all" in workflow
    assert 'command.stamp(alembic_cfg, "head")' in workflow
    assert "await init_db()" in workflow
    assert "python -m pytest -vv --maxfail=1 --durations=20 tests/integration" in workflow
    assert "needs: [python-tests, postgres-integration-tests" in workflow


def test_release_workflow_gates_pull_requests_without_publishing_images():
    workflow = (ROOT / ".github/workflows/control-plane-release.yml").read_text(
        encoding="utf-8"
    )

    assert "  pull_request:\n" in workflow
    assert "if: github.event_name == 'push' && github.ref == 'refs/heads/main'" in workflow


def test_bootstrap_sends_remote_script_over_stdin_and_archives_source_only():
    bootstrap = (ROOT / "scripts/bootstrap_release_host.sh").read_text(
        encoding="utf-8"
    )

    assert 'bash -seu <<< "$SCRIPT"' in bootstrap
    assert 'bash -ceu "$SCRIPT"' not in bootstrap
    assert "--exclude='__pycache__'" in bootstrap
    assert "--exclude='*.pyc'" in bootstrap
    assert "--role cloud-control|local-worker-host" in bootstrap
    assert 'CHECKOUT_ROOT="${HOME}/APP/All_bot-release"' in bootstrap
    assert 'CHECKOUT_ROOT="/home/deploy/APP/All_bot-release"' in bootstrap
    assert "local-worker-host only supports --target local" in bootstrap


def test_backend_httpx_pin_is_compatible_with_telegram_runtime():
    backend_requirements = (ROOT / "backend/requirements.txt").read_text(
        encoding="utf-8"
    )

    assert "httpx==0.28.1" in backend_requirements
    assert "httpx==0.26.0" not in backend_requirements


def test_dashboard_backend_bcrypt_pin_matches_root_image_dependencies():
    root_requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    dashboard_requirements = (ROOT / "dashboard/backend/requirements.txt").read_text(
        encoding="utf-8"
    )

    assert "bcrypt==4.1.2" in root_requirements
    assert "bcrypt==4.1.2" in dashboard_requirements


def test_python_310_container_bases_match_pinned_runtime_version_and_digest():
    expected = (
        "FROM python:3.10.20-slim-bookworm@sha256:"
        "ff7161e2b8e2a56fc6a62a6099ff8feb72f1a6dbae9860cdcb9a6c65cf4c6be9"
    )
    python_310_dockerfiles = []

    for path in ROOT.rglob("Dockerfile*"):
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        if first_line.startswith("FROM python:3.10"):
            python_310_dockerfiles.append(path)
            assert first_line == expected, f"{path} has a mutable or mismatched Python base"

    assert python_310_dockerfiles


def test_hotspot_regression_script_references_existing_python_tests():
    script = (ROOT / "scripts/run_hotspot_regression.sh").read_text(
        encoding="utf-8"
    )
    referenced_tests = set()
    for line in script.splitlines():
        token = line.strip().rstrip(" \\")
        if token.startswith(("tests/", "src/tests/")) and token.endswith(".py"):
            referenced_tests.add(token)

    missing = sorted(path for path in referenced_tests if not (ROOT / path).is_file())
    assert missing == []
