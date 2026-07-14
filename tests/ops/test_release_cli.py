import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "release.py"
POLICY_PATH = ROOT / "deploy" / "release-policy.yml"
SCHEMA_PATH = ROOT / "deploy" / "env.schema.yml"
CONFIG_UPDATER_PATH = ROOT / "scripts" / "update_deploy_config.py"
FULL_SHA = "a" * 40


def _load_module():
    spec = importlib.util.spec_from_file_location("allbot_release", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_config_updater():
    spec = importlib.util.spec_from_file_location(
        "allbot_config_updater", CONFIG_UPDATER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest(sha: str = FULL_SHA) -> dict:
    return {
        "schema_version": 1,
        "git_sha": sha,
        "ci_run": "https://github.com/giraffu/All_bot/actions/runs/1",
        "images": {
            "app": "ghcr.io/giraffu/allbot-app@sha256:" + "1" * 64,
            "central": "ghcr.io/giraffu/allbot-central-api@sha256:" + "2" * 64,
            "dashboard_backend": "ghcr.io/giraffu/allbot-dashboard-backend@sha256:"
            + "3" * 64,
            "dashboard_frontend": "ghcr.io/giraffu/allbot-dashboard-frontend@sha256:"
            + "4" * 64,
            "worker": "ghcr.io/giraffu/allbot-worker@sha256:" + "5" * 64,
        },
        "vendor_images": {
            "imgproxy": "docker.io/darthsim/imgproxy@sha256:" + "7" * 64,
            "postgres": "docker.io/library/postgres@sha256:" + "8" * 64,
            "redis": "docker.io/library/redis@sha256:" + "9" * 64,
        },
        "web_artifact_sha256": "6" * 64,
    }


def _valid_test_environment(*, worker_slots: tuple[str, ...] = ()) -> dict[str, str]:
    values = {
        "ALLBOT_ENV": "test",
        "ALLBOT_ENV_FILE": "/etc/allbot/test.env",
        "ALLBOT_STATE_ROOT": "/var/lib/allbot/test",
        "DATABASE_URL": "postgresql+asyncpg://test-db",
        "REDIS_URL": "redis://test-control/0",
        "WORKER_REDIS_URL": "redis://test-worker/0",
        "AGENT_SECRET_TOKEN": "test-agent-secret",
        "API_TOKEN": "test-api-token",
        "MINIO_ENDPOINT": "test-minio",
        "MINIO_ACCESS_KEY": "test-access-key",
        "MINIO_SECRET_KEY": "test-secret-key",
        "MINIO_SECURE": "false",
        "BOT_TOKEN_TEST": "test-bot-token",
        "CLOUD_TEST_BIND_IP": "127.0.0.1",
        "CLOUD_TEST_CONTROL_HOST": "test-control",
        "CLOUD_TEST_DATABASE_URL": "postgresql+asyncpg://test-db",
        "CLOUD_TEST_REDIS_URL": "redis://test-control/0",
        "CLOUD_TEST_WORKER_REDIS_URL": "redis://test-worker/0",
        "QQCC_CONFIG_ADMIN_HOST": "qqcc-admin-test.example.com",
        "PRIVATE_QQCC_BOT_OWNER_HOST": "private-bot-test.example.com",
    }
    if worker_slots:
        values.update(
            {
                "ALLBOT_WORKER_SERVICES": ",".join(
                    f"worker-{slot}" for slot in worker_slots
                ),
                "ALLBOT_WORKER_STATE_ROOT": "/var/lib/allbot/test-worker",
                "ALLBOT_WORKER_CENTRAL_API_URL": "http://test-control:8004",
                "ALLBOT_WORKER_RELAY_PORT": "8014",
            }
        )
    for slot in worker_slots:
        values.update(
            {
                f"ALLBOT_WORKER_{slot}_AGENT_ID": f"cloud_worker_test_{slot}",
                f"ALLBOT_WORKER_{slot}_COMFY_API_URL": "http://gpu:8188",
                f"ALLBOT_WORKER_{slot}_COMFY_WS_URL": "ws://gpu:8188/ws",
                f"ALLBOT_WORKER_{slot}_TASK_TYPES": "image_to_video",
                f"ALLBOT_WORKER_{slot}_NODE_ID": "gpu-test",
                f"ALLBOT_WORKER_{slot}_GPU_INDEX": "0",
                f"ALLBOT_WORKER_{slot}_RUNTIME_PROFILE": "test-profile",
                f"ALLBOT_WORKER_{slot}_PREFETCH_ENABLED": "false",
                f"ALLBOT_WORKER_{slot}_PIPELINE_ENABLED": "false",
                f"ALLBOT_WORKER_{slot}_PIPELINE_MAX_RUNNING_TASKS": "1",
            }
        )
    return values


def test_shared_runtime_changes_expand_to_every_python_consumer():
    module = _load_module()
    policy = module.load_structured_file(POLICY_PATH)

    impact = module.plan_changed_paths(
        policy,
        [
            "src/core/task_core.py",
            "src/services/redis_client.py",
            "shared/locales/zh.json",
        ],
    )

    assert impact.level == "rolling"
    assert {
        "central-api",
        "web-api",
        "payment-api",
        "dashboard-backend",
        "qqcc-config-backend",
        "bot",
        "qqcc-bot",
        "qqcc-private-bot-worker",
        "paid-group-guard-bot",
        "worker",
    } <= impact.services


def test_migration_forces_maintenance_and_unknown_path_falls_back_to_full_stack():
    module = _load_module()
    policy = module.load_structured_file(POLICY_PATH)

    migration = module.plan_changed_paths(
        policy,
        ["migrations/versions/example.py"],
    )
    unknown = module.plan_changed_paths(policy, ["unexpected/new_runtime/file.bin"])

    assert migration.level == "maintenance"
    assert migration.requires_db_upgrade is True
    assert unknown.level == "maintenance"
    assert unknown.services == set(policy["all_services"])
    assert unknown.unknown_paths == ["unexpected/new_runtime/file.bin"]


def test_gpu_runtime_change_blocks_the_normal_release_path():
    module = _load_module()
    policy = module.load_structured_file(POLICY_PATH)

    impact = module.plan_changed_paths(
        policy,
        ["remote_workers/comfy_agent/workflow_task_patchers.py"],
    )

    assert impact.blockers == {"gpu-runtime-release-required"}


def test_explicit_services_can_only_widen_the_computed_set():
    module = _load_module()

    selected = module.merge_requested_services(
        computed={"bot", "central-api"},
        requested={"bot"},
    )

    assert selected == {"bot", "central-api"}


def test_release_manifest_requires_exact_sha_and_digest_pinned_images():
    module = _load_module()

    module.validate_release_manifest(_manifest(), FULL_SHA)

    mutable = _manifest()
    mutable["images"]["app"] = "ghcr.io/giraffu/allbot-app:latest"
    with pytest.raises(module.ReleaseError, match="digest-pinned"):
        module.validate_release_manifest(mutable, FULL_SHA)

    with pytest.raises(module.ReleaseError, match="git_sha"):
        module.validate_release_manifest(_manifest("b" * 40), FULL_SHA)

    mutable_vendor = _manifest()
    mutable_vendor["vendor_images"]["redis"] = "redis:latest"
    with pytest.raises(module.ReleaseError, match="vendor images"):
        module.validate_release_manifest(mutable_vendor, FULL_SHA)


def test_release_ci_must_be_completed_successfully_for_the_same_sha(monkeypatch):
    module = _load_module()

    def successful_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {"status": "completed", "conclusion": "success", "headSha": FULL_SHA}
            ),
            stderr="",
        )

    monkeypatch.setattr(module, "_run", successful_run)
    module.verify_release_ci(_manifest(), FULL_SHA)

    def wrong_sha(*_args, **_kwargs):
        result = successful_run()
        result.stdout = json.dumps(
            {"status": "completed", "conclusion": "success", "headSha": "b" * 40}
        )
        return result

    monkeypatch.setattr(module, "_run", wrong_sha)
    with pytest.raises(module.ReleaseError, match="another SHA"):
        module.verify_release_ci(_manifest(), FULL_SHA)


def test_environment_validation_reports_names_without_secret_values():
    module = _load_module()
    schema = module.load_structured_file(SCHEMA_PATH)
    values = {
        "ALLBOT_ENV": "test",
        "ALLBOT_ENV_FILE": "/etc/allbot/test.env",
        "ALLBOT_STATE_ROOT": "/var/lib/allbot/test",
        "BOT_TOKEN": "super-secret-token",
        "BOT_TOKEN_TEST": "super-secret-token",
    }

    with pytest.raises(module.ReleaseError) as exc_info:
        module.validate_environment(schema, "test", values)

    message = str(exc_info.value)
    assert "super-secret-token" not in message
    assert "BOT_TOKEN" in message


def test_environment_contract_accepts_worker_08_and_rejects_unknown_slots():
    module = _load_module()
    schema = module.load_structured_file(SCHEMA_PATH)
    values = _valid_test_environment(worker_slots=("01", "08"))

    revision = module.validate_environment(schema, "test", values)

    assert len(revision) == 64
    invalid = dict(values, ALLBOT_WORKER_SERVICES="worker-09")
    with pytest.raises(module.ReleaseError, match="invalid worker slot"):
        module.validate_environment(schema, "test", invalid)


def test_initial_worker_cutover_maps_legacy_slots_and_holds_maintenance():
    module = _load_module()
    impact = module.ReleaseImpact(
        services={"central-api", "worker", "web-static"},
        level="maintenance",
        matched_rules=["initial-release"],
    )

    assert module.legacy_worker_containers(
        "test", {"worker-01", "worker-08"}
    ) == [
        "cloud-comfy-agent-test-1",
        "cloud-comfy-agent-test-8",
        "cloud-worker-relay-test",
    ]
    assert module.legacy_worker_containers(
        "prod", {"worker-01", "worker-08"}
    ) == [
        "cloud-prod-comfy-agent-1",
        "cloud-prod-comfy-agent-8",
        "cloud-prod-worker-relay",
    ]
    assert module.hold_maintenance_for_worker_cutover("test", impact) is True
    assert module.hold_maintenance_for_worker_cutover("prod", impact) is False
    assert module.maintenance_files("prod", initial_cutover=True) == [
        "/var/lib/allbot/prod/runtime/GENERATION_MAINTENANCE",
        "/home/deploy/APP/All_bot/runtime/cloud-prod/GENERATION_MAINTENANCE",
    ]


def test_production_release_scope_excludes_gpu_workers():
    module = _load_module()
    prod_impact = module.ReleaseImpact(
        services={"central-api", "worker", "web-static"},
        level="maintenance",
    )
    test_impact = module.ReleaseImpact(
        services={"central-api", "worker", "web-static"},
        level="maintenance",
    )

    module.scope_release_impact("prod", prod_impact, requested=set())
    module.scope_release_impact("test", test_impact, requested=set())

    assert prod_impact.services == {"central-api", "web-static"}
    assert "worker" in test_impact.services
    with pytest.raises(module.ReleaseError, match="GPU hosts"):
        module.scope_release_impact("prod", prod_impact, requested={"worker"})


def test_state_marks_web_skipped_instead_of_claiming_checksum_passed(monkeypatch):
    module = _load_module()
    captured = {}

    def capture_run(*_args, **kwargs):
        captured["payload"] = kwargs["input_text"]
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "_run", capture_run)
    args = SimpleNamespace(
        env="test",
        remote_host="test-control",
        execute=True,
        command="deploy",
        skip_web=True,
    )
    impact = module.ReleaseImpact(
        services={"central-api", "web-static"},
        level="maintenance",
    )

    module._write_state(args, impact, _manifest(), "config-revision")

    state = json.loads(captured["payload"])
    assert state["health"]["web"] == "skipped"


def test_state_records_pages_deployment_metadata(monkeypatch):
    module = _load_module()
    captured = {}

    def capture_run(*_args, **kwargs):
        captured["payload"] = kwargs["input_text"]
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "_run", capture_run)
    args = SimpleNamespace(
        env="test",
        remote_host="test-control",
        execute=True,
        command="deploy",
        skip_web=False,
    )
    impact = module.ReleaseImpact(services={"web-static"}, level="rolling")
    web_deployment = {
        "project": "allbot-web-cf-test",
        "branch": "test",
        "deployment_id": "production-deployment-id",
        "environment": "production",
        "canonical_url": "https://web-cf-test.aivison.it.com",
        "canonical_verified": True,
        "runtime_config_revision": "f" * 64,
    }

    module._write_state(
        args,
        impact,
        _manifest(),
        "config-revision",
        web_deployment=web_deployment,
    )

    state = json.loads(captured["payload"])
    assert state["schema_version"] == 2
    assert state["health"]["web"] == "canonical-runtime-verified"
    assert state["web_deployment"] == web_deployment


def test_test_web_no_longer_uses_edge_ssh_or_scp():
    source = MODULE_PATH.read_text(encoding="utf-8")

    web_section = source[
        source.index("def _deploy_web(") : source.index("def _deploy_worker(")
    ]
    assert '"ssh"' not in web_section
    assert '"scp"' not in web_section
    assert '"allbot-web-cf-test"' in source
    assert '"allbot-web-prod"' in source


def test_initial_cloud_cutover_includes_stateful_dependencies_and_legacy_names():
    module = _load_module()
    impact = module.ReleaseImpact(
        services={"central-api", "web-api", "bot"},
        level="maintenance",
        matched_rules=["initial-release"],
    )

    selected = module.cloud_services_for_release("test", impact)

    assert selected == {"postgres", "redis", "central-api", "web-api", "bot"}
    assert module.legacy_cloud_containers("test", selected) == [
        "cloud-postgres-test",
        "cloud-redis-test",
        "cloud-central-api-test",
        "cloud-web-api-test",
        "cloud-tg-bot-test",
    ]


def test_optional_cloud_bots_are_filtered_only_by_validated_runtime_config():
    module = _load_module()
    selected = {
        "central-api",
        "bot",
        "qqcc-bot",
        "qqcc-private-bot-worker",
        "paid-group-guard-bot",
    }

    test_enabled, test_disabled = module.filter_enabled_cloud_services(
        "test",
        selected,
        _valid_test_environment(),
    )

    assert test_enabled == {"central-api", "bot"}
    assert test_disabled == {
        "qqcc-bot",
        "qqcc-private-bot-worker",
        "paid-group-guard-bot",
    }

    enabled_values = dict(
        _valid_test_environment(),
        QQCC_BOT_TOKEN_TEST="test-qqcc-token",
        PRIVATE_QQCC_BOT_ENABLED="true",
        PAID_GROUP_BOT_TOKEN="test-paid-group-token",
    )
    enabled, disabled = module.filter_enabled_cloud_services(
        "test", selected, enabled_values
    )

    assert enabled == selected
    assert disabled == set()


def test_ci_plan_can_skip_runtime_env_but_deploy_cannot(tmp_path):
    head_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    manifest = tmp_path / "release.json"
    manifest.write_text(json.dumps(_manifest(head_sha)), encoding="utf-8")
    missing_env = tmp_path / "missing.env"
    common = [
        "--env",
        "test",
        "--sha",
        head_sha,
        "--manifest",
        str(manifest),
        "--from-sha",
        head_sha,
        "--env-file",
        str(missing_env),
        "--skip-git-checks",
        "--skip-ci-checks",
        "--skip-env-checks",
    ]

    plan = subprocess.run(
        ["python", str(MODULE_PATH), "plan", *common],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    deploy = subprocess.run(
        ["python", str(MODULE_PATH), "deploy", *common],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert plan.returncode == 0, plan.stderr
    assert json.loads(plan.stdout)["config_validation"] == "skipped"
    assert deploy.returncode == 2
    assert "only available for plan" in deploy.stderr


def test_initial_cloud_cutover_pulls_before_stopping_legacy_and_restores_on_failure(
    tmp_path, monkeypatch
):
    module = _load_module()
    impact = module.ReleaseImpact(
        services={"central-api", "web-api", "bot", "worker"},
        level="maintenance",
        matched_rules=["initial-release"],
    )
    args = SimpleNamespace(
        execute=True,
        env="test",
        remote_host="cloud-test",
        remote_checkout_root="/release-root",
        remote_env_file="/etc/allbot/test.env",
        confirm_legacy_cutover=True,
        drain_timeout_seconds=30,
        drain_interval_seconds=1,
    )
    remote_calls = []

    monkeypatch.setattr(
        module,
        "_run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, stdout="", stderr=""
        ),
    )

    def fake_remote(host, script, *, execute):
        remote_calls.append((host, script, execute))
        return f"ALLBOT_CLOUD_RELEASE_VERIFIED:{FULL_SHA}\n"

    monkeypatch.setattr(module, "_remote_shell", fake_remote)

    module._deploy_cloud(
        args,
        impact,
        _manifest(),
        "ALLBOT_RELEASE_SHA=x\n",
        _valid_test_environment(),
    )

    assert len(remote_calls) == 1
    host, script, execute = remote_calls[0]
    assert host == "cloud-test"
    assert execute is True
    pull = script.index(" pull postgres redis bot central-api web-api")
    stop = script.index("docker stop $legacy_running")
    start = script.index(
        " up -d --no-deps --wait --wait-timeout 180 postgres redis bot central-api web-api"
    )
    assert pull < stop < start
    assert "cloud-postgres-test" in script
    assert "cloud-redis-test" in script
    assert "cloud-tg-bot-test" in script
    assert "docker exec cloud-central-api-test python -c" in script
    assert "</dev/null" in script
    assert (
        "exec -T bot python -c 'import config; "
        'assert config.API_BASE == "http://central-api:8003"\''
    ) in script
    assert (
        "exec -T web-api python -c 'import config; "
        'assert config.API_BASE == "http://central-api:8003"\''
    ) in script
    assert "docker inspect --format '{{.Config.Image}}'" in script
    assert 'test "$actual_image" = "$ALLBOT_APP_IMAGE"' in script
    assert "org.opencontainers.image.revision" in script
    assert f"ALLBOT_CLOUD_RELEASE_VERIFIED:{FULL_SHA}" in script
    assert " rm -sf postgres redis bot central-api web-api" in script
    assert 'docker start "$name"' in script
    assert "legacy_cutover_committed=1" in script


def test_cloud_deploy_rejects_missing_remote_completion_marker(monkeypatch):
    module = _load_module()
    impact = module.ReleaseImpact(services={"central-api"}, level="restart")
    args = SimpleNamespace(
        execute=True,
        env="test",
        remote_host="cloud-test",
        remote_checkout_root="/release-root",
        remote_env_file="/etc/allbot/test.env",
        confirm_legacy_cutover=False,
        drain_timeout_seconds=30,
        drain_interval_seconds=1,
    )

    monkeypatch.setattr(
        module,
        "_run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, stdout="", stderr=""
        ),
    )
    monkeypatch.setattr(
        module,
        "_remote_shell",
        lambda host, script, *, execute: "",
    )

    with pytest.raises(module.ReleaseError, match="completion marker"):
        module._deploy_cloud(
            args,
            impact,
            _manifest(),
            "ALLBOT_RELEASE_SHA=x\n",
            _valid_test_environment(),
        )


def test_initial_worker_cutover_snapshots_and_stops_legacy_before_start(
    tmp_path, monkeypatch
):
    module = _load_module()
    root = tmp_path / "release-root"
    (root / "repo" / ".git").mkdir(parents=True)
    env_file = tmp_path / "test.env"
    env_file.write_text("ALLBOT_ENV=test\n", encoding="utf-8")
    impact = module.ReleaseImpact(
        services={"central-api", "worker", "web-static"},
        level="maintenance",
        matched_rules=["initial-release"],
    )
    args = SimpleNamespace(
        execute=True,
        env="test",
        env_file=str(env_file),
        worker_checkout_root=str(root),
        remote_host="cloud-test",
    )
    commands = []
    command_options = []
    remote_calls = []

    def fake_run(command, **kwargs):
        commands.append(command)
        command_options.append(kwargs)
        stdout = ""
        if command[:4] == ["git", "-C", str(root / "releases" / FULL_SHA), "rev-parse"]:
            stdout = FULL_SHA + "\n"
        elif command[:4] == ["docker", "image", "inspect", "--format"]:
            stdout = FULL_SHA + "\n"
        elif command[:3] == ["docker", "inspect", "--format"]:
            stdout = "true\n"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    def fake_remote(host, script, *, execute):
        remote_calls.append((host, script, execute, len(commands)))

    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(module, "_remote_shell", fake_remote)

    module._deploy_worker(
        args,
        impact,
        _manifest(),
        "ALLBOT_WORKER_IMAGE=example@sha256:" + "5" * 64 + "\n",
        {"ALLBOT_WORKER_SERVICES": "worker-01,worker-08"},
    )

    legacy_stop = next(
        index
        for index, command in enumerate(commands)
        if command[:2] == ["docker", "stop"]
    )
    immutable_start = next(
        index
        for index, command in enumerate(commands)
        if command[:2] == ["docker", "compose"] and "up" in command
    )
    assert commands[legacy_stop] == [
        "docker",
        "stop",
        "cloud-comfy-agent-test-1",
        "cloud-comfy-agent-test-8",
        "cloud-worker-relay-test",
    ]
    assert legacy_stop < immutable_start
    compose_calls = [
        options
        for command, options in zip(commands, command_options, strict=True)
        if command[:2] == ["docker", "compose"]
    ]
    assert compose_calls
    assert all(
        options["env"]["ALLBOT_ENV_FILE"] == str(env_file)
        for options in compose_calls
    )
    assert remote_calls == []
    assert (
        root / "release-env" / FULL_SHA / "legacy-worker-running.txt"
    ).read_text(encoding="utf-8").splitlines() == [
        "cloud-comfy-agent-test-1",
        "cloud-comfy-agent-test-8",
        "cloud-worker-relay-test",
    ]


def test_prod_execute_requires_explicit_confirmation_before_other_checks(tmp_path):
    manifest = tmp_path / "release.json"
    manifest.write_text(json.dumps(_manifest()), encoding="utf-8")

    result = subprocess.run(
        [
            "python",
            str(MODULE_PATH),
            "deploy",
            "--env",
            "prod",
            "--sha",
            FULL_SHA,
            "--manifest",
            str(manifest),
            "--execute",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--confirm-prod" in result.stderr


def test_test_acceptance_requires_same_digest_and_24_hour_observation():
    module = _load_module()
    manifest = _manifest()
    completed = datetime.now(timezone.utc) - timedelta(minutes=1)
    evidence = {
        "git_sha": FULL_SHA,
        "images": manifest["images"],
        "vendor_images": manifest["vendor_images"],
        "observation_started_at": (completed - timedelta(hours=24)).isoformat(),
        "completed_at": completed.isoformat(),
        "approved_by": "ops",
        "checks": {key: True for key in module.REQUIRED_ACCEPTANCE_CHECKS},
    }

    module.validate_test_acceptance(evidence, manifest)

    evidence["completed_at"] = (completed - timedelta(hours=1)).isoformat()
    with pytest.raises(module.ReleaseError, match="24 hours"):
        module.validate_test_acceptance(evidence, manifest)


def test_test_acceptance_rejects_runtime_when_web_was_skipped():
    module = _load_module()
    state = {"health": {"web": "skipped"}}

    with pytest.raises(module.ReleaseError, match="Web artifact"):
        module.validate_test_runtime_for_acceptance(state)

    state["health"]["web"] = "artifact-checksum-passed"
    module.validate_test_runtime_for_acceptance(state)


def test_web_runtime_config_is_public_versioned_and_environment_specific(tmp_path):
    module = _load_module()
    config_path = tmp_path / "web-runtime-config.yml"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "test": {
                    "api_base_url": "https://api-test.example.com/api",
                    "telegram_bot_username": "test_bot",
                    "enable_free_edit_v3": True,
                },
                "prod": {
                    "api_base_url": "https://api.example.com/api",
                    "telegram_bot_username": "prod_bot",
                },
            }
        ),
        encoding="utf-8",
    )

    values, revision = module.load_web_runtime_config(config_path, "test")
    script = module.render_web_runtime_config_script(
        values,
        git_sha=FULL_SHA,
        config_revision=revision,
    )

    assert values["api_base_url"] == "https://api-test.example.com/api"
    assert values["telegram_bot_username"] == "test_bot"
    assert values["enable_free_edit_v3"] is True
    assert len(revision) == 64
    assert "api-test.example.com" in script
    assert FULL_SHA in script
    assert "prod_bot" not in script


def test_web_runtime_config_rejects_unknown_or_secret_fields(tmp_path):
    module = _load_module()
    config_path = tmp_path / "web-runtime-config.yml"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "test": {"api_base_url": "/api", "api_token": "secret"},
                "prod": {"api_base_url": "/api"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        module.ReleaseError, match="unsupported public Web runtime fields"
    ):
        module.load_web_runtime_config(config_path, "test")


@pytest.mark.parametrize(
    ("environment", "expected_project", "expected_branch"),
    [
        ("test", "allbot-web-cf-test", "test"),
        ("prod", "allbot-web-prod", "main"),
    ],
)
def test_test_and_prod_web_use_same_pages_deployer(
    tmp_path,
    monkeypatch,
    environment,
    expected_project,
    expected_branch,
):
    module = _load_module()
    artifact = tmp_path / "web-dist.tgz"
    source = tmp_path / "source" / "dist"
    source.mkdir(parents=True)
    (source / "index.html").write_text("ok", encoding="utf-8")
    with tarfile.open(artifact, "w:gz") as archive:
        archive.add(source, arcname="dist")
    manifest = _manifest()
    manifest["web_artifact_sha256"] = module.hashlib.sha256(
        artifact.read_bytes()
    ).hexdigest()
    token_file = tmp_path / "pages.token"
    token_file.write_text("test-token\n", encoding="utf-8")
    token_file.chmod(0o600)
    runtime_path = tmp_path / "web-runtime-config.yml"
    runtime_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "test": {"api_base_url": "https://api-test.example.com/api"},
                "prod": {"api_base_url": "https://api.example.com/api"},
            }
        ),
        encoding="utf-8",
    )
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Deployment complete! https://abc.allbot-web-cf-test.pages.dev\n",
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        module,
        "verify_pages_canonical_deployment",
        lambda *_args, **_kwargs: {
            "deployment_id": "deployment-id",
            "environment": "production",
            "canonical_url": module.WEB_PAGES_TARGETS[environment]["canonical_url"],
            "canonical_verified": True,
        },
        raising=False,
    )
    args = SimpleNamespace(
        skip_web=False,
        web_artifact=str(artifact),
        bundle_cache=str(tmp_path),
        execute=True,
        env=environment,
        cloudflare_token_file=str(token_file),
        cloudflare_account_id="account-id",
        web_runtime_config=str(runtime_path),
    )

    result = module._deploy_web(args, manifest)

    command = calls[-1][0]
    assert command[:5] == ["npx", "--no-install", "wrangler", "pages", "deploy"]
    assert command[command.index("--project-name") + 1] == expected_project
    assert command[command.index("--branch") + 1] == expected_branch
    assert result["project"] == expected_project
    assert result["deployment_id"] == "deployment-id"
    assert result["canonical_verified"] is True
    assert len(result["runtime_config_revision"]) == 64
    assert not any(command[0] in {"ssh", "scp"} for command, _ in calls)


def test_config_impact_recreates_consumers_and_unknown_keys_fail_wide():
    module = _load_module()
    updater = _load_config_updater()
    policy = module.load_structured_file(ROOT / "deploy/config-impact.yml")

    known = updater.affected_services(policy, {"BOT_TOKEN_TEST"})
    unknown = updater.affected_services(policy, {"NEW_UNMAPPED_CONFIG"})

    assert {"bot", "qqcc-bot", "qqcc-private-bot-worker"} <= known
    assert unknown == set(module.load_structured_file(POLICY_PATH)["all_services"])


def test_release_cli_defaults_to_allbot_cloudflare_account():
    module = _load_module()

    args = module.build_parser().parse_args(
        ["plan", "--env", "test", "--sha", "0" * 40]
    )

    assert args.cloudflare_account_id == "c7220eb751acc6f7ab8255b4a0394ef3"


def test_release_cli_uses_operator_home_for_local_release_inputs():
    module = _load_module()
    args = module.build_parser().parse_args(
        ["plan", "--env", "prod", "--sha", "0" * 40]
    )

    assert module.local_env_file(args) == Path.home() / ".config/allbot/prod.env"
    assert args.worker_checkout_root == str(Path.home() / "APP/All_bot-release")
    assert args.cloudflare_token_file == str(
        Path.home() / ".config/allbot/cloudflare-pages.token"
    )


def test_preflight_collects_every_read_only_blocker_before_refusing_release():
    module = _load_module()
    calls = []

    def check(name, blockers):
        def run(*_args, **_kwargs):
            calls.append(name)
            return blockers

        return run

    dependencies = module.PreflightDependencies(
        operator=check("operator", ["operator-gh-auth-unavailable"]),
        cloud=check("cloud", ["cloud-release-host-not-bootstrapped"]),
        worker=check("worker", ["worker-relay-owner-mismatch"]),
        pages=check("pages", ["pages-production-branch-mismatch"]),
        rollback=check("rollback", ["rollback-materials-unavailable"]),
    )
    args = SimpleNamespace(env="test")
    impact = module.ReleaseImpact(
        services={"central-api", "worker", "web-static"},
        level="maintenance",
        matched_rules=["initial-release"],
    )

    report = module.preflight_release(
        args,
        impact,
        _manifest(),
        {"ALLBOT_WORKER_SERVICES": "worker-01"},
        dependencies=dependencies,
    )

    assert calls == ["operator", "cloud", "worker", "pages", "rollback"]
    assert report["status"] == "blocked"
    assert report["mutation_allowed"] is False
    assert report["blockers"] == [
        "cloud-release-host-not-bootstrapped",
        "operator-gh-auth-unavailable",
        "pages-production-branch-mismatch",
        "rollback-materials-unavailable",
        "worker-relay-owner-mismatch",
    ]
    with pytest.raises(module.ReleaseError, match="preflight blocked"):
        module.require_preflight(report)


def test_prod_preflight_skips_gpu_worker_checks():
    module = _load_module()
    calls = []

    def check(name):
        def run(*_args, **_kwargs):
            calls.append(name)
            return []

        return run

    def unexpected_worker_check(*_args, **_kwargs):
        raise AssertionError("production release must not inspect GPU Worker runtime")

    dependencies = module.PreflightDependencies(
        operator=check("operator"),
        cloud=check("cloud"),
        worker=unexpected_worker_check,
        pages=check("pages"),
        rollback=check("rollback"),
    )
    report = module.preflight_release(
        SimpleNamespace(env="prod"),
        module.ReleaseImpact(
            services={"central-api", "worker", "web-static"},
            level="maintenance",
        ),
        _manifest(),
        {},
        dependencies=dependencies,
    )

    assert calls == ["operator", "cloud", "pages", "rollback"]
    assert report["checks"]["worker"] == {"status": "skipped", "blockers": []}
    assert report["status"] == "passed"


def test_release_cli_exposes_read_only_preflight_command():
    module = _load_module()

    args = module.build_parser().parse_args(
        ["preflight", "--env", "prod", "--sha", "0" * 40]
    )

    assert args.command == "preflight"
    assert args.execute is False


def test_pages_release_requires_matching_production_canonical_and_runtime_sha(
    monkeypatch,
):
    module = _load_module()
    sha = "b" * 40
    revision = "c" * 64
    deployment = {
        "id": "new-production-id",
        "environment": "production",
        "deployment_trigger": {
            "metadata": {"branch": "main", "commit_hash": sha}
        },
        "latest_stage": {"status": "success"},
    }

    def fake_api(_args, _method, path, **_kwargs):
        if path.endswith("/deployments?env=production"):
            return {"success": True, "result": [deployment]}
        return {
            "success": True,
            "result": {"canonical_deployment": {"id": "new-production-id"}},
        }

    class FakeResponse:
        headers = {"Content-Type": "application/javascript; charset=UTF-8"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return module.render_web_runtime_config_script(
                {"api_base_url": "https://api.example.test"},
                git_sha=sha,
                config_revision=revision,
            ).encode()

    requests = []

    def fake_urlopen(request, **_kwargs):
        requests.append(request)
        return FakeResponse()

    monkeypatch.setattr(module, "_pages_api_request", fake_api)
    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    args = SimpleNamespace(env="prod")

    result = module.verify_pages_canonical_deployment(args, sha, revision)

    assert result == {
        "deployment_id": "new-production-id",
        "environment": "production",
        "canonical_url": "https://web.aivison.it.com",
        "canonical_verified": True,
    }
    assert requests[0].get_header("User-agent") == "AllBotReleaseVerifier/1.0"


@pytest.mark.parametrize(
    ("canonical_id", "content_type", "runtime_sha", "message"),
    [
        ("old-id", "application/javascript", "b" * 40, "canonical deployment"),
        (
            "new-production-id",
            "text/html",
            "b" * 40,
            "JavaScript",
        ),
        (
            "new-production-id",
            "application/javascript",
            "d" * 40,
            "release SHA",
        ),
    ],
)
def test_pages_canonical_verification_rejects_stale_or_html_runtime(
    monkeypatch, canonical_id, content_type, runtime_sha, message
):
    module = _load_module()
    sha = "b" * 40
    revision = "c" * 64
    deployment = {
        "id": "new-production-id",
        "environment": "production",
        "deployment_trigger": {
            "metadata": {"branch": "main", "commit_hash": sha}
        },
        "latest_stage": {"status": "success"},
    }

    def fake_api(_args, _method, path, **_kwargs):
        result = [deployment] if "deployments?" in path else {
            "canonical_deployment": {"id": canonical_id}
        }
        return {"success": True, "result": result}

    class FakeResponse:
        headers = {"Content-Type": content_type}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return module.render_web_runtime_config_script(
                {"api_base_url": "https://api.example.test"},
                git_sha=runtime_sha,
                config_revision=revision,
            ).encode()

    monkeypatch.setattr(module, "_pages_api_request", fake_api)
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    with pytest.raises(module.ReleaseError, match=message):
        module.verify_pages_canonical_deployment(
            SimpleNamespace(env="prod"), sha, revision
        )


def test_transaction_compensates_attempted_stages_in_reverse_and_then_clears_maintenance():
    module = _load_module()
    calls = []
    journals = []

    def action(name, result=None, error=None):
        def run():
            calls.append(name)
            if error:
                raise module.ReleaseError(error)
            return result

        return run

    dependencies = module.ReleaseTransactionDependencies(
        cloud=action("cloud"),
        worker=action("worker"),
        pages=action("pages", error="canonical remained stale"),
        state=action("state"),
        rollback_pages=action("rollback-pages"),
        rollback_worker=action("rollback-worker"),
        rollback_cloud=action("rollback-cloud"),
        validate_recovery=action("validate-recovery"),
        clear_maintenance=action("clear-maintenance"),
        journal=lambda value: journals.append(dict(value)),
    )
    transaction = module.new_release_transaction(
        environment="prod",
        target_sha="a" * 40,
        previous_sha="b" * 40,
        previous_kind="immutable",
        previous_pages_deployment_id="old-pages-id",
    )

    with pytest.raises(module.ReleaseError, match="release failed and was recovered"):
        module.execute_release_transaction(transaction, dependencies)

    assert calls == [
        "cloud",
        "worker",
        "pages",
        "rollback-pages",
        "rollback-worker",
        "rollback-cloud",
        "validate-recovery",
        "clear-maintenance",
    ]
    assert "state" not in calls
    assert transaction["status"] == "rolled_back"
    assert transaction["phase"] == "recovery_verified"
    assert journals[-1]["status"] == "rolled_back"


def test_recovery_validation_checks_only_stages_the_transaction_attempted(monkeypatch):
    module = _load_module()
    remote_calls = []

    monkeypatch.setattr(
        module,
        "_remote_shell",
        lambda host, script, *, execute: remote_calls.append((host, script, execute)),
    )

    def unexpected_local_command(*_args, **_kwargs):
        raise AssertionError("untouched Worker must not be recovery-validated")

    def unexpected_pages_lookup(*_args, **_kwargs):
        raise AssertionError("untouched Pages must not be recovery-validated")

    monkeypatch.setattr(module, "_run", unexpected_local_command)
    monkeypatch.setattr(module, "_current_pages_deployment_id", unexpected_pages_lookup)

    args = SimpleNamespace(
        env="test",
        remote_host="cloud-test",
        remote_checkout_root="/home/deploy/APP/All_bot-release",
        remote_env_file=None,
    )
    impact = module.ReleaseImpact(
        services={"central-api", "worker", "web-static"},
        level="maintenance",
    )
    transaction = module.new_release_transaction(
        environment="test",
        target_sha="a" * 40,
        previous_sha="b" * 40,
        previous_kind="immutable",
        previous_pages_deployment_id="old-pages-id",
    )
    transaction["attempted_stages"] = ["cloud"]

    module._validate_recovered_stack(
        args,
        impact,
        transaction,
        {
            "ALLBOT_WORKER_SERVICES": "worker-01",
            "ALLBOT_WORKER_RELAY_PORT": "8014",
            "ALLBOT_WORKER_CENTRAL_API_URL": "http://cloud-test:8004",
            "ALLBOT_WORKER_01_AGENT_ID": "cloud_worker_test_01",
        },
    )

    assert len(remote_calls) == 1
    assert remote_calls[0][0] == "cloud-test"


def test_transaction_keeps_maintenance_when_compensation_is_incomplete():
    module = _load_module()
    calls = []

    def action(name, error=None):
        def run():
            calls.append(name)
            if error:
                raise module.ReleaseError(error)

        return run

    dependencies = module.ReleaseTransactionDependencies(
        cloud=action("cloud"),
        worker=action("worker", error="worker failed"),
        pages=action("pages"),
        state=action("state"),
        rollback_pages=action("rollback-pages"),
        rollback_worker=action("rollback-worker", error="old relay unavailable"),
        rollback_cloud=action("rollback-cloud"),
        validate_recovery=action("validate-recovery"),
        clear_maintenance=action("clear-maintenance"),
        journal=lambda _value: None,
    )
    transaction = module.new_release_transaction(
        environment="prod",
        target_sha="a" * 40,
        previous_sha=None,
        previous_kind="legacy",
        previous_pages_deployment_id="old-pages-id",
    )

    with pytest.raises(module.ReleaseError, match="rollback incomplete"):
        module.execute_release_transaction(transaction, dependencies)

    assert calls == ["cloud", "worker", "rollback-worker", "rollback-cloud"]
    assert transaction["status"] == "rollback_failed"
    assert "clear-maintenance" not in calls


def test_transaction_commits_state_before_releasing_maintenance():
    module = _load_module()
    calls = []

    def action(name, result=None):
        def run():
            calls.append(name)
            return result

        return run

    dependencies = module.ReleaseTransactionDependencies(
        cloud=action("cloud"),
        worker=action("worker"),
        pages=action("pages", {"deployment_id": "new-pages-id"}),
        state=action("state"),
        rollback_pages=action("rollback-pages"),
        rollback_worker=action("rollback-worker"),
        rollback_cloud=action("rollback-cloud"),
        validate_recovery=action("validate-recovery"),
        clear_maintenance=action("clear-maintenance"),
        journal=lambda _value: None,
    )
    transaction = module.new_release_transaction(
        environment="prod",
        target_sha="a" * 40,
        previous_sha="b" * 40,
        previous_kind="immutable",
        previous_pages_deployment_id="old-pages-id",
    )

    result = module.execute_release_transaction(transaction, dependencies)

    assert result == {"deployment_id": "new-pages-id"}
    assert calls == ["cloud", "worker", "pages", "state", "clear-maintenance"]
    assert transaction["status"] == "committed"
    assert transaction["phase"] == "maintenance_released"


def test_recover_is_idempotent_for_an_already_recovered_transaction():
    module = _load_module()
    calls = []

    def action(name):
        def run():
            calls.append(name)

        return run

    dependencies = module.ReleaseTransactionDependencies(
        cloud=action("cloud"),
        worker=action("worker"),
        pages=action("pages"),
        state=action("state"),
        rollback_pages=action("rollback-pages"),
        rollback_worker=action("rollback-worker"),
        rollback_cloud=action("rollback-cloud"),
        validate_recovery=action("validate-recovery"),
        clear_maintenance=action("clear-maintenance"),
        journal=lambda _value: None,
    )
    transaction = module.new_release_transaction(
        environment="prod",
        target_sha="a" * 40,
        previous_sha="b" * 40,
        previous_kind="immutable",
        previous_pages_deployment_id="old-pages-id",
    )
    transaction.update(
        status="rolled_back",
        phase="recovery_verified",
        attempted_stages=["cloud", "worker", "pages"],
    )

    module.recover_release_transaction(transaction, dependencies)

    assert calls == ["validate-recovery", "clear-maintenance"]
    assert transaction["status"] == "rolled_back"


def test_release_cli_exposes_confirmed_recover_command():
    module = _load_module()

    args = module.build_parser().parse_args(
        [
            "recover",
            "--env",
            "prod",
            "--transaction",
            "a" * 40,
            "--execute",
            "--confirm-prod",
        ]
    )

    assert args.command == "recover"
    assert args.transaction == "a" * 40
    assert args.execute is True


def test_pages_rollback_uses_previous_production_id_and_verifies_canonical(
    monkeypatch,
):
    module = _load_module()
    calls = []

    def fake_api(_args, method, path, **kwargs):
        calls.append((method, path, kwargs))
        canonical = "new-id" if len(calls) == 1 else "old-id"
        return {
            "success": True,
            "result": {"canonical_deployment": {"id": canonical}},
        }

    monkeypatch.setattr(module, "_pages_api_request", fake_api)
    transaction = module.new_release_transaction(
        environment="prod",
        target_sha="a" * 40,
        previous_sha="b" * 40,
        previous_kind="immutable",
        previous_pages_deployment_id="old-id",
    )

    module._rollback_pages(SimpleNamespace(env="prod"), transaction)

    assert calls[1] == (
        "POST",
        "pages/projects/allbot-web-prod/deployments/old-id/rollback",
        {"payload": {}},
    )
    assert calls[2][0:2] == ("GET", "pages/projects/allbot-web-prod")


def test_transaction_journal_rejects_secret_fields_before_remote_write(monkeypatch):
    module = _load_module()
    writes = []
    monkeypatch.setattr(module, "_run", lambda *args, **kwargs: writes.append((args, kwargs)))
    transaction = module.new_release_transaction(
        environment="prod",
        target_sha="a" * 40,
        previous_sha=None,
        previous_kind="legacy",
        previous_pages_deployment_id="old-id",
    )
    transaction["api_token"] = "must-not-be-written"

    with pytest.raises(module.ReleaseError, match="forbidden field"):
        module._write_transaction_journal(
            SimpleNamespace(env="prod", remote_host="prod-control"), transaction
        )

    assert writes == []


def test_transaction_commit_moves_staged_state_before_clearing_dual_maintenance(
    monkeypatch,
):
    module = _load_module()
    calls = []
    monkeypatch.setattr(
        module,
        "_remote_shell",
        lambda host, script, *, execute: calls.append((host, script, execute)),
    )
    args = SimpleNamespace(env="prod", remote_host="prod-control", execute=False)
    transaction = module.new_release_transaction(
        environment="prod",
        target_sha="a" * 40,
        previous_sha=None,
        previous_kind="legacy",
        previous_pages_deployment_id="old-id",
    )
    transaction["phase"] = "state_completed"

    module._clear_transaction_maintenance(args, transaction)

    script = calls[0][1]
    assert script.index("mv -f") < script.index(
        "rm -f /var/lib/allbot/prod/runtime/GENERATION_MAINTENANCE"
    )
    assert "/home/deploy/APP/All_bot/runtime/cloud-prod/GENERATION_MAINTENANCE" in script


def test_preflight_manifest_resolution_never_pulls_or_creates_cache(tmp_path, monkeypatch):
    module = _load_module()
    cache = tmp_path / "missing-cache"
    calls = []
    monkeypatch.setattr(module, "_run", lambda *args, **kwargs: calls.append((args, kwargs)))
    args = SimpleNamespace(
        manifest=None,
        bundle_cache=str(cache),
        sha="a" * 40,
        bundle_repository="ghcr.io/example/release",
    )

    with pytest.raises(module.ReleaseError, match="never pull"):
        module._resolve_manifest_path(args, allow_fetch=False)

    assert not cache.exists()
    assert calls == []
