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


def _projection_env_file(projection: str) -> list[dict[str, object]]:
    return [
        {
            "path": (
                "${ALLBOT_SERVICE_ENV_ROOT:?ALLBOT_SERVICE_ENV_ROOT is required}/"
                f"{projection}.env"
            ),
            "required": False,
            "format": "raw",
        }
    ]


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


def test_every_cloud_service_has_bounded_json_log_rotation():
    services = _compose(BASE)["services"]

    for name, service in services.items():
        assert service.get("logging") == {
            "driver": "json-file",
            "options": {"max-size": "50m", "max-file": "5"},
        }, f"{name} is missing bounded json-file logging"


def test_service_projection_files_are_optional_during_partial_project_parse():
    services = _compose(BASE)["services"]

    projected = {
        name: service["env_file"]
        for name, service in services.items()
        if "env_file" in service
    }
    assert projected
    for name, env_files in projected.items():
        assert len(env_files) == 1, f"{name} must use one service projection"
        assert env_files[0].get("required") is False, (
            f"{name} projection must not block parsing an unrelated module"
        )
        assert env_files[0].get("format") == "raw", (
            f"{name} projection must preserve literal dollar signs and hashes"
        )
        assert (
            str(env_files[0].get("path", "")).endswith(f"/{name}.env")
            or (
                name == "bot"
                and str(env_files[0].get("path", "")).endswith("/main-bot.env")
            )
            or (
                name == "qqcc-private-bot-worker"
                and str(env_files[0].get("path", "")).endswith(
                    "/private-bot-worker.env"
                )
            )
            or (
                name == "paid-group-guard-bot"
                and str(env_files[0].get("path", "")).endswith("/paid-group-bot.env")
            )
        )


def test_prod_dashboard_backend_enables_runpod_autoscaler_in_immutable_compose():
    prod_overlay = _compose(ROOT / "deploy/docker-compose-cloud-prod.overlay.yml")
    environment = prod_overlay["services"]["dashboard-backend"]["environment"]

    assert environment["API_BASE"] == "http://central-api:8003"
    assert environment["DASHBOARD_RUNPOD_AUTOSCALER_ENABLED"] == (
        "${DASHBOARD_RUNPOD_AUTOSCALER_ENABLED:-true}"
    )
    assert environment["DASHBOARD_RUNPOD_AUTOSCALER_MODE"] == (
        "${DASHBOARD_RUNPOD_AUTOSCALER_MODE:-execute}"
    )
    assert environment["DASHBOARD_RUNPOD_ENV_FILE"] == (
        "${DASHBOARD_RUNPOD_ENV_FILE:-/dev/null}"
    )
    assert environment["DASHBOARD_RUNPOD_PROD_ENV_FILE"] == (
        "${DASHBOARD_RUNPOD_PROD_ENV_FILE:-/dev/null}"
    )
    assert environment["RUNPOD_IMAGE_NAME_PORNMASTER_FLUX2_EDIT"] == (
        "${RUNPOD_IMAGE_NAME_PORNMASTER_FLUX2_EDIT:?"
        "RUNPOD_IMAGE_NAME_PORNMASTER_FLUX2_EDIT is required}"
    )
    assert environment["RUNPOD_RELEASE_PROFILE_PINS_JSON"] == (
        "${RUNPOD_RELEASE_PROFILE_PINS_JSON:?"
        "RUNPOD_RELEASE_PROFILE_PINS_JSON is required}"
    )


def test_prod_dashboard_backend_uses_required_remote_lan_aio_runner_contract():
    prod_overlay = _compose(ROOT / "deploy/docker-compose-cloud-prod.overlay.yml")
    dashboard = prod_overlay["services"]["dashboard-backend"]
    environment = dashboard["environment"]

    assert environment["DASHBOARD_LAN_AIO_EXECUTION_MODE"] == "ssh"
    assert environment["DASHBOARD_LAN_AIO_RUNNER_HOST"] == (
        "${DASHBOARD_LAN_AIO_RUNNER_HOST:?DASHBOARD_LAN_AIO_RUNNER_HOST is required}"
    )
    assert environment["DASHBOARD_LAN_AIO_RUNNER_PROJECT_ROOT"] == (
        "${DASHBOARD_LAN_AIO_RUNNER_PROJECT_ROOT:-/home/hfy/APP/All_bot}"
    )
    assert environment["DASHBOARD_LAN_AIO_RUNNER_SSH_COMMAND"] == (
        "ssh -p ${DASHBOARD_LAN_AIO_RUNNER_SSH_PORT:-2222} "
        "-i /app/runtime/lan-aio-runner/id_ed25519"
    )
    assert (
        "${DASHBOARD_LAN_AIO_RUNNER_KEY_DIR:?"
        "DASHBOARD_LAN_AIO_RUNNER_KEY_DIR is required}"
        "/id_ed25519:/app/runtime/lan-aio-runner/id_ed25519:ro" in dashboard["volumes"]
    )


def test_lan_aio_dashboard_runner_has_dedicated_tailscale_openssh_unit():
    unit = (
        ROOT / "deploy/systemd/allbot-lan-aio-dashboard-runner-sshd.service"
    ).read_text(encoding="utf-8")

    assert "EnvironmentFile=%h/.config/allbot/lan-aio-dashboard-runner.env" in unit
    assert "/usr/sbin/sshd -D -e" in unit
    assert (
        "HostKey=%h/.local/share/allbot/lan-aio-dashboard-runner/ssh_host_ed25519_key"
        in unit
    )
    assert "ListenAddress=${ALLBOT_LAN_AIO_RUNNER_LISTEN_ADDRESS}" in unit
    assert "${ALLBOT_LAN_AIO_RUNNER_PORT}" in unit
    assert "PasswordAuthentication=no" in unit
    assert "UsePAM=no" in unit
    assert "PermitRootLogin=no" in unit


def test_central_and_worker_images_contain_their_dependency_closure():
    central = (ROOT / "deploy/docker/Dockerfile.central").read_text(encoding="utf-8")
    control_plane = (ROOT / "deploy/docker/Dockerfile.control-plane").read_text(
        encoding="utf-8"
    )
    dashboard = (ROOT / "deploy/docker/Dockerfile.dashboard-backend").read_text(
        encoding="utf-8"
    )
    worker = (ROOT / "deploy/docker/Dockerfile.worker").read_text(encoding="utf-8")

    assert "COPY backend/app /app/app" in central
    assert "COPY src /app/src" in central
    assert "COPY config.py /app/config.py" in dashboard
    assert "COPY ops /app/ops" in dashboard
    assert "COPY paid_group_guard_bot /app/paid_group_guard_bot" in dashboard
    assert (
        "COPY scripts/runpod_prod_ops.sh /app/scripts/runpod_prod_ops.sh" in dashboard
    )
    assert (
        "COPY scripts/gpu_pool_controller.py /app/scripts/gpu_pool_controller.py"
        in dashboard
    )
    assert (
        "COPY scripts/gpu_release_rollout.py /app/scripts/gpu_release_rollout.py"
        in dashboard
    )
    assert (
        "COPY scripts/release_manifest_v2.py /app/scripts/release_manifest_v2.py"
        in dashboard
    )
    assert (
        "COPY scripts/release_strategy.py /app/scripts/release_strategy.py" in dashboard
    )
    for script in (
        "gpu_release_rollout.py",
        "release_manifest_v2.py",
        "release_strategy.py",
    ):
        assert f"COPY scripts/{script} /app/scripts/{script}" in control_plane
    chmod_lines = [line for line in dashboard.splitlines() if "chmod 755" in line]
    assert any("/app/scripts/runpod_prod_ops.sh" in line for line in chmod_lines)
    assert "COPY workers/comfy_agent /app/worker" in worker
    assert "COPY src /app/src" in worker


def test_dashboard_frontend_image_prepares_nginx_template_directory():
    dockerfile = (ROOT / "deploy/docker/Dockerfile.dashboard-frontend").read_text(
        encoding="utf-8"
    )

    assert "mkdir -p /etc/nginx/templates" in dockerfile


def test_dashboard_backend_image_contains_runpod_admin_runtime_dependencies():
    dashboard = (ROOT / "deploy/docker/Dockerfile.dashboard-backend").read_text(
        encoding="utf-8"
    )

    assert "COPY ops /app/ops" in dashboard
    assert (
        "COPY scripts/runpod_prod_ops.sh /app/scripts/runpod_prod_ops.sh" in dashboard
    )
    assert (
        "COPY scripts/gpu_pool_controller.py /app/scripts/gpu_pool_controller.py"
        in dashboard
    )
    chmod_lines = [line for line in dashboard.splitlines() if "chmod 755" in line]
    assert any("/app/scripts/runpod_prod_ops.sh" in line for line in chmod_lines)


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
    assert services["postgres"]["networks"]["default"]["aliases"] == ["postgres-test"]
    assert services["redis"]["networks"]["default"]["aliases"] == ["redis-test"]


def test_test_runtime_uses_scoped_host_projections_without_test_aliases():
    base = _compose(BASE)["services"]
    overlay = _compose(OVERLAYS[0])["services"]
    projections = {
        "central-api": "central-api",
        "web-api": "web-api",
        "bot": "main-bot",
        "qqcc-bot": "qqcc-bot",
        "qqcc-private-bot-worker": "private-bot-worker",
    }

    for service, projection in projections.items():
        assert base[service]["env_file"] == _projection_env_file(projection)
        environment = overlay.get(service, {}).get("environment", {})
        assert "BOT_TYPE" not in environment
        assert "API_BASE" not in environment
        assert "API_BASE_TEST" not in environment


def test_qqcc_config_is_in_test_overlay_while_dashboard_remains_absent():
    base = _compose(BASE)["services"]
    test_services = _compose(OVERLAYS[0])["services"]

    for name in (
        "dashboard-backend",
        "dashboard-frontend",
        "qqcc-config-backend",
        "qqcc-config-frontend",
    ):
        assert base[name]["profiles"] == ["owner-tools"]

    assert "dashboard-backend" not in test_services
    assert "dashboard-frontend" not in test_services
    assert test_services["qqcc-config-backend"]["ports"] == [
        "${CLOUD_TEST_BIND_IP:-127.0.0.1}:8045:8045"
    ]
    assert "environment" not in test_services["qqcc-config-backend"]
    assert base["qqcc-config-backend"]["env_file"] == _projection_env_file(
        "qqcc-config-backend"
    )
    assert test_services["qqcc-config-frontend"]["ports"] == [
        "${CLOUD_TEST_BIND_IP:-127.0.0.1}:8088:8088"
    ]


def test_legacy_cloud_test_compose_no_longer_defines_owner_tools():
    services = _compose(ROOT / "deploy/docker-compose-cloud-test.yml")["services"]

    assert (
        not {
            "dashboard-backend-test",
            "dashboard-frontend-test",
            "qqcc-config-backend-test",
            "qqcc-config-frontend-test",
        }
        & services.keys()
    )


def test_prod_runtime_uses_host_projections_for_python_consumers():
    base = _compose(BASE)["services"]
    overlay = _compose(OVERLAYS[1])["services"]
    projections = {
        "central-api": "central-api",
        "web-api": "web-api",
        "payment-api": "payment-api",
        "dashboard-backend": "dashboard-backend",
        "qqcc-config-backend": "qqcc-config-backend",
        "bot": "main-bot",
        "qqcc-bot": "qqcc-bot",
        "qqcc-private-bot-worker": "private-bot-worker",
        "paid-group-guard-bot": "paid-group-bot",
    }

    for service, projection in projections.items():
        assert base[service]["env_file"] == _projection_env_file(projection)
        environment = overlay.get(service, {}).get("environment", {})
        assert "BOT_TYPE" not in environment
        if service == "dashboard-backend":
            assert environment["API_BASE"] == "http://central-api:8003"
        else:
            assert "API_BASE" not in environment


def test_release_workflow_builds_all_images_and_never_uses_latest():
    workflow = (ROOT / ".github/workflows/modular-release-v2.yml").read_text(
        encoding="utf-8"
    )

    for contract in (
        "release-index.json",
        "control-plane-manifest.json",
        "test-execution-manifest.json",
        "gpu-execution-manifest.json",
        "allbot-release-v2",
    ):
        assert contract in workflow
    assert "scripts/ci_release_v2.py" in workflow
    assert ":latest" not in workflow
    assert (
        "05-select-dashboard-spa.sh && test -f "
        "/etc/nginx/templates/default.conf.template"
    ) in workflow
    assert (
        "import dashboard.backend.main; import dashboard.backend.qqcc_config_main"
    ) in workflow
    assert "DASHBOARD_FRONTEND_MODE=qqcc" in workflow
    assert "MINIO_ENDPOINT=127.0.0.1:1" in workflow
    for synthetic_runtime_key in (
        "ALLBOT_ENV=test",
        "BOT_TYPE=TEST",
        "DASHBOARD_SECRET_KEY=ci-smoke-dashboard-secret",
        "DASHBOARD_ADMIN_USERNAME=ci-smoke-admin",
        "DASHBOARD_ADMIN_PASSWORD_HASH=ci-smoke-password-hash",
        "QQCC_CONFIG_SECRET_KEY=ci-smoke-qqcc-secret",
        "QQCC_CONFIG_ADMIN_USERNAME=ci-smoke-qqcc-admin",
        "QQCC_CONFIG_ADMIN_PASSWORD_HASH=ci-smoke-qqcc-password-hash",
    ):
        assert synthetic_runtime_key in workflow
    assert "oras repo tags" in workflow
    assert 'git rev-list --first-parent "${SOURCE_SHA}^"' in workflow
    assert "--skip-git-checks --skip-ci-checks --skip-env-checks" in workflow
    assert "allbot-release-v2-test-candidate" not in workflow
    assert "branches: [main]" in workflow
    assert "EVENT_RUN_ID: ${{ github.event.workflow_run.id }}" in workflow
    assert '--ci-run "$TRUSTED_CI_RUN"' in workflow
    assert "previous-release/release-v2/release-index.json" in workflow
    assert "previous-release/promoted-release/release-index.json" in workflow
    assert 'echo "bundle=${previous_bundle_dir}"' in workflow
    assert 'echo "sha=${previous_sha}"' in workflow
    assert "PREVIOUS_SHA: ${{ steps.previous.outputs.sha }}" in workflow
    assert "--previous-catalog" in workflow
    assert 'git show "${PREVIOUS_SHA}:deploy/release-artifacts-v2.json"' in workflow
    assert "options: [build-only]" in workflow
    assert "manual dispatch cannot claim full validation" in workflow
    assert '--validation-mode "$VALIDATION_MODE"' in workflow
    assert "if: steps.source.outputs.validation_mode == 'full'" in workflow
    assert "validation_mode=full" in workflow
    assert "allbot-gpu-release-manifests" in workflow
    assert "gpu-execution-manifest.json" in workflow
    # A trusted main bundle is complete; GPU mutation still remains outside
    # release.py and uses the dedicated profile operator.
    assert "--require-complete-gpu" in workflow
    assert 'if [ "$RELEASE_CHANNEL" = main ]' in workflow


def test_schema_v1_shared_image_release_is_retired():
    workflow = (ROOT / ".github/workflows/control-plane-release.yml").read_text(
        encoding="utf-8"
    )
    release_section = workflow.split("\n  release:\n", 1)[1]
    assert "if: ${{ false }}" in release_section


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
    assert (
        "python -m pytest -vv --maxfail=1 --durations=20 tests/integration" in workflow
    )
    assert "  ci-gate:\n" in workflow
    assert "      - python-tests\n" in workflow
    assert "      - postgres-integration-tests\n" in workflow


def test_release_workflow_gates_pull_requests_without_publishing_images():
    workflow = (ROOT / ".github/workflows/control-plane-release.yml").read_text(
        encoding="utf-8"
    )
    modular = (ROOT / ".github/workflows/modular-release-v2.yml").read_text(
        encoding="utf-8"
    )

    assert "  pull_request:\n" in workflow
    assert "python scripts/classify_ci_change.py" in workflow
    assert "needs.change-scope.outputs.requires_full_ci == 'true'" in workflow
    assert "needs.change-scope.outputs.requires_release_ci == 'true'" in workflow
    assert "needs.change-scope.outputs.requires_operator_ci == 'true'" in workflow
    assert "  release-tooling-tests:\n" in workflow
    assert "  operator-tests:\n" in workflow
    assert (
        "tests/ops/test_release_cli.py tests/ops/test_release_strategy.py" in workflow
    )
    assert (
        "python -m pytest -vv --maxfail=1 --durations=20 tests/ops tests/scripts"
        in workflow
    )
    assert "if: ${{ false }}" in workflow
    assert "workflow_run:" in modular
    assert "python scripts/classify_ci_change.py" in modular
    assert "needs.change-scope.outputs.requires_release_bundle == 'true'" in modular
    assert '--expected-scope "${{ needs.change-scope.outputs.scope }}"' in modular
    assert 'workflows: ["Immutable control-plane release"]' in modular
    assert "github.event.workflow_run.conclusion == 'success'" in modular
    assert "github.event.workflow_run.event == 'push'" in modular
    assert "github.event.workflow_run.event == 'workflow_dispatch'" in modular
    assert "python scripts/validate_upstream_ci_run.py" in modular
    assert "actions: read" in modular
    assert "if: steps.source.outputs.validation_mode == 'full'" in modular
    assert "manual dispatch cannot claim full validation" in modular


def test_bootstrap_sends_remote_script_over_stdin_and_archives_source_only():
    bootstrap = (ROOT / "scripts/bootstrap_release_host.sh").read_text(encoding="utf-8")

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
            assert first_line.removesuffix(" AS python-runtime-base") == expected, (
                f"{path} has a mutable or mismatched Python base"
            )

    assert python_310_dockerfiles


def test_hotspot_regression_script_references_existing_python_tests():
    script = (ROOT / "scripts/run_hotspot_regression.sh").read_text(encoding="utf-8")
    referenced_tests = set()
    for line in script.splitlines():
        token = line.strip().rstrip(" \\")
        if token.startswith(("tests/", "src/tests/")) and token.endswith(".py"):
            referenced_tests.add(token)

    missing = sorted(path for path in referenced_tests if not (ROOT / path).is_file())
    assert missing == []
