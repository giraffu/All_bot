import importlib.util
import json
from pathlib import Path
import subprocess
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
    spec = importlib.util.spec_from_file_location("allbot_config_updater", CONFIG_UPDATER_PATH)
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
            "dashboard_backend": "ghcr.io/giraffu/allbot-dashboard-backend@sha256:" + "3" * 64,
            "dashboard_frontend": "ghcr.io/giraffu/allbot-dashboard-frontend@sha256:" + "4" * 64,
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

    assert module.legacy_worker_containers({"worker-01", "worker-08"}) == [
        "cloud-comfy-agent-test-1",
        "cloud-comfy-agent-test-8",
        "cloud-worker-relay-test",
    ]
    assert module.hold_maintenance_for_worker_cutover("test", impact) is True
    assert module.hold_maintenance_for_worker_cutover("prod", impact) is False


def test_initial_worker_cutover_stops_legacy_before_start_and_clears_maintenance(
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
    remote_calls = []

    def fake_run(command, **kwargs):
        commands.append(command)
        stdout = ""
        if command[:4] == ["git", "-C", str(root / "releases" / FULL_SHA), "rev-parse"]:
            stdout = FULL_SHA + "\n"
        elif command[:4] == ["docker", "image", "inspect", "--format"]:
            stdout = FULL_SHA + "\n"
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
    assert remote_calls == [
        (
            "cloud-test",
            "set -euo pipefail\n"
            "rm -f /var/lib/allbot/test/runtime/GENERATION_MAINTENANCE\n",
            True,
            len(commands),
        )
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


def test_config_impact_recreates_consumers_and_unknown_keys_fail_wide():
    module = _load_module()
    updater = _load_config_updater()
    policy = module.load_structured_file(ROOT / "deploy/config-impact.yml")

    known = updater.affected_services(policy, {"BOT_TOKEN_TEST"})
    unknown = updater.affected_services(policy, {"NEW_UNMAPPED_CONFIG"})

    assert {"bot", "qqcc-bot", "qqcc-private-bot-worker"} <= known
    assert unknown == set(module.load_structured_file(POLICY_PATH)["all_services"])
