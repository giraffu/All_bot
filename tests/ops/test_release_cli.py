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
QQCC_CONTROL_PLANE_POLICY_PATH = (
    ROOT / "deploy" / "release-policy-qqcc-control-plane.yml"
)
QQCC_TEST_RECONCILE_POLICY_PATH = (
    ROOT / "deploy" / "release-policy-qqcc-control-plane-test-reconcile.yml"
)
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


def test_v2_control_plane_does_not_require_unselected_gpu_profiles(
    monkeypatch, tmp_path
):
    module = _load_module()
    previous_sha = "b" * 40
    artifact = {
        "kind": "image",
        "ref": "ghcr.io/giraffu/allbot-central-api@sha256:" + "1" * 64,
        "digest": "sha256:" + "1" * 64,
        "source_sha": FULL_SHA,
        "oci_revision": FULL_SHA,
        "dependency_closure": [],
    }
    release = SimpleNamespace(
        index={
            "ci_run": "https://github.com/giraffu/All_bot/actions/runs/1",
            "release_channel": "main",
            "source_ref": "refs/heads/main",
        },
        manifests={
            "control-plane": {"artifacts": {"central-api": artifact}},
            "gpu-execution": {
                "completeness": "incomplete",
                "missing_artifacts": ["image_to_video"],
                "artifacts": {},
            },
        },
    )
    manifest = {
        "schema_version": 2,
        "source_sha": FULL_SHA,
        "git_sha": FULL_SHA,
        "ci_run": release.index["ci_run"],
        "release_channel": "main",
        "source_ref": "refs/heads/main",
        "track": "control-plane",
        "artifacts": {"central-api": artifact},
        "selected_artifacts": ["central-api"],
    }
    args = SimpleNamespace(
        sha=FULL_SHA,
        manifest=None,
        bundle_cache=str(tmp_path),
        bundle_repository="ghcr.io/giraffu/allbot-release-v2",
        command="plan",
        modules=[],
        services=[],
        track="control-plane",
        state_file=None,
        from_sha=None,
        env="prod",
        remote_host="prod-control",
        policy=str(POLICY_PATH),
        skip_git_checks=True,
        skip_ci_checks=True,
        dashboard_fast_track=False,
    )

    monkeypatch.setattr(
        module, "_resolve_manifest_path", lambda *_args, **_kwargs: tmp_path / "index"
    )
    monkeypatch.setattr(module, "_read_json", lambda _path: {"schema_version": 2})
    monkeypatch.setattr(
        module, "_resolve_previous_sha", lambda *_args, **_kwargs: previous_sha
    )
    monkeypatch.setattr(
        module,
        "git_changed_paths",
        lambda *_args: ["remote_workers/comfy_agent/workflow_task_patchers.py"],
    )
    monkeypatch.setattr(module, "load_release_index", lambda *_args, **_kwargs: release)
    monkeypatch.setattr(module, "_load_v2_track", lambda *_args, **_kwargs: manifest)

    impact, selected_manifest, resolved_previous = module.build_plan(args)

    assert impact.blockers == set()
    assert selected_manifest["track"] == "control-plane"
    assert resolved_previous == previous_sha


def test_v2_dashboard_fast_track_selects_only_dashboard_artifacts(
    monkeypatch, tmp_path
):
    module = _load_module()
    previous_sha = "b" * 40
    target_parent_sha = "c" * 40
    artifacts = {
        name: {
            "kind": "image",
            "ref": f"ghcr.io/giraffu/{name}@sha256:" + digest * 64,
            "digest": "sha256:" + digest * 64,
            "source_sha": FULL_SHA,
            "oci_revision": FULL_SHA,
            "dependency_closure": [],
        }
        for name, digest in (
            ("central-api", "1"),
            ("dashboard-backend", "2"),
            ("qqcc-config-backend", "3"),
        )
    }
    release = SimpleNamespace(
        index={
            "ci_run": "https://github.com/giraffu/All_bot/actions/runs/1",
            "release_channel": "main",
            "source_ref": "refs/heads/main",
        },
        manifests={
            "control-plane": {"artifacts": artifacts},
            "gpu-execution": {"artifacts": {}},
        },
    )
    captured_modules = []

    def fake_load_v2_track(_path, *, modules, **_kwargs):
        captured_modules.extend(modules)
        return {
            "schema_version": 2,
            "source_sha": FULL_SHA,
            "git_sha": FULL_SHA,
            "ci_run": release.index["ci_run"],
            "release_channel": "main",
            "source_ref": "refs/heads/main",
            "track": "control-plane",
            "artifacts": artifacts,
            "selected_artifacts": list(modules),
        }

    args = SimpleNamespace(
        sha=FULL_SHA,
        manifest=None,
        bundle_cache=str(tmp_path),
        bundle_repository="ghcr.io/giraffu/allbot-release-v2",
        command="plan",
        modules=[],
        services=[],
        track="control-plane",
        state_file=None,
        from_sha=None,
        env="prod",
        remote_host="prod-control",
        policy=str(POLICY_PATH),
        skip_git_checks=True,
        skip_ci_checks=True,
        dashboard_fast_track=True,
    )

    monkeypatch.setattr(
        module, "_resolve_manifest_path", lambda *_args, **_kwargs: tmp_path / "index"
    )
    monkeypatch.setattr(module, "_read_json", lambda _path: {"schema_version": 2})
    monkeypatch.setattr(
        module, "_resolve_previous_sha", lambda *_args, **_kwargs: previous_sha
    )
    monkeypatch.setattr(
        module, "_target_first_parent_sha", lambda _sha: target_parent_sha
    )
    monkeypatch.setattr(
        module,
        "git_changed_paths",
        lambda from_sha, _target_sha: (
            ["dashboard/backend/services/runpod_admin_commands.py"]
            if from_sha == target_parent_sha
            else ["src/services/unrelated.py"]
        ),
    )
    monkeypatch.setattr(module, "load_release_index", lambda *_args, **_kwargs: release)
    monkeypatch.setattr(module, "_load_v2_track", fake_load_v2_track)

    impact, manifest, resolved_previous = module.build_plan(args)

    assert impact.level == "rolling"
    assert impact.services == {"dashboard-backend"}
    assert impact.matched_rules == ["dashboard-fast-track", "track:control-plane"]
    assert captured_modules == ["dashboard-backend"]
    assert manifest["selected_artifacts"] == ["dashboard-backend"]
    assert resolved_previous == previous_sha


def test_dashboard_admin_runtime_changes_stay_dashboard_backend_only():
    module = _load_module()
    policy = module.load_structured_file(POLICY_PATH)

    impact = module.plan_changed_paths(
        policy,
        [
            "dashboard/backend/services/system_service.py",
            "dashboard/backend/services/runpod_admin_commands.py",
            "deploy/docker/Dockerfile.dashboard-backend",
            "deploy/release-policy.yml",
            "tests/dashboard/test_system_service.py",
            "tests/ops/test_release_cli.py",
        ],
    )

    assert impact.level == "rolling"
    assert impact.services == {"dashboard-backend"}
    assert impact.blockers == set()
    assert impact.unknown_paths == []


def test_dashboard_shared_schemas_roll_both_dashboard_consumers():
    module = _load_module()
    policy = module.load_structured_file(POLICY_PATH)

    impact = module.plan_changed_paths(policy, ["dashboard/backend/schemas.py"])

    assert impact.level == "rolling"
    assert impact.services == {"dashboard-backend", "qqcc-config-backend"}
    assert impact.blockers == set()
    assert impact.unknown_paths == []


def test_qqcc_control_plane_policy_limits_release_to_qqcc_runtime_closure():
    module = _load_module()
    policy = module.load_structured_file(QQCC_CONTROL_PLANE_POLICY_PATH)

    impact = module.plan_changed_paths(
        policy,
        [
            "backend/app/models.py",
            "dashboard/backend/schemas.py",
            "dashboard/frontend/src/components/QqccBotSettings.vue",
            "qqcc_bot/prompt_handlers.py",
            "shared/locales/zh.json",
            "src/core/task_dispatcher.py",
            "src/services/qqcc_config_service.py",
            "deploy/release-policy.yml",
            "docs/knowledge_base_audit_matrix.md",
            "tests/services/test_quick_video_submission_service.py",
        ],
    )

    assert impact.level == "rolling"
    assert impact.services == {
        "central-api",
        "qqcc-bot",
        "qqcc-config-backend",
        "qqcc-config-frontend",
        "qqcc-private-bot-worker",
    }
    assert impact.blockers == set()
    assert impact.unknown_paths == []


@pytest.mark.parametrize(
    "path",
    [
        "frontend/src/App.vue",
        "workers/comfy_agent/workflows/mappings.json",
        "remote_workers/comfy_agent/workflows/mappings.json",
        "scripts/test_train_release.py",
    ],
)
def test_qqcc_control_plane_policy_fails_closed_for_out_of_scope_paths(path):
    module = _load_module()
    policy = module.load_structured_file(QQCC_CONTROL_PLANE_POLICY_PATH)

    impact = module.plan_changed_paths(policy, [path])

    assert impact.level == "maintenance"
    assert impact.unknown_paths == [path]


def test_release_policy_environment_guard_rejects_test_policy_in_production():
    module = _load_module()

    with pytest.raises(module.ReleaseError, match="only valid for test"):
        module.validate_release_policy_environment(
            {"environment": "test"}, "prod"
        )


def test_qqcc_test_reconcile_policy_ignores_only_audited_test_train_drift():
    module = _load_module()
    policy = module.load_structured_file(QQCC_TEST_RECONCILE_POLICY_PATH)
    module.validate_release_policy_environment(policy, "test")

    impact = module.plan_changed_paths(
        policy,
        [
            "dashboard/frontend/src/components/QqccBotSettings.vue",
            "qqcc_bot/private_bot_fsm.py",
            "src/services/qqcc_config_service.py",
            "AGENTS.md",
            "frontend/src/features/generation/labModeConfig.ts",
            "remote_workers/comfy_agent/workflows/mappings.json",
            "scripts/release.py",
            "scripts/test_train_release.py",
            "src/quota.py",
            "src/services/permission_growth_channel_service.py",
            "workers/comfy_agent/workflows/mappings.json",
        ],
    )

    assert impact.level == "rolling"
    assert impact.services == {
        "central-api",
        "qqcc-bot",
        "qqcc-config-backend",
        "qqcc-config-frontend",
        "qqcc-private-bot-worker",
    }
    assert impact.unknown_paths == []


def test_dashboard_fast_track_accepts_only_dashboard_runtime_and_release_metadata():
    module = _load_module()

    impact = module.plan_dashboard_fast_track(
        [
            "dashboard/backend/services/runpod_autoscaler_service.py",
            "dashboard/frontend/src/components/QueueStats.vue",
            "deploy/docker/Dockerfile.dashboard-backend",
            "ops/gpu_pool_controller/runpod_profile_catalog.py",
            "scripts/release.py",
            "deploy/release-policy.yml",
            "tests/ops/test_release_cli.py",
            "docs/子模块_Git不可变发布_git_immutable_release.md",
            ".codex/skills/allbot-ops-deployment/SKILL.md",
        ]
    )

    assert impact.level == "rolling"
    assert impact.services == {"dashboard-backend", "dashboard-frontend"}
    assert impact.blockers == set()
    assert impact.unknown_paths == []
    assert impact.matched_rules == ["dashboard-fast-track"]


@pytest.mark.parametrize(
    "path",
    [
        "src/services/task_service_flow.py",
        "migrations/versions/example.py",
        "ops/gpu_pool_controller/runtime.py",
        "deploy/docker-compose-cloud-prod.overlay.yml",
        "unexpected/runtime.bin",
    ],
)
def test_dashboard_fast_track_rejects_non_dashboard_runtime(path):
    module = _load_module()

    with pytest.raises(module.ReleaseError, match="dashboard fast-track"):
        module.plan_dashboard_fast_track(
            ["dashboard/frontend/src/App.vue", path]
        )


def test_dashboard_fast_track_requires_a_dashboard_runtime_change():
    module = _load_module()

    with pytest.raises(module.ReleaseError, match="no Dashboard runtime changes"):
        module.plan_dashboard_fast_track(
            ["scripts/release.py", "tests/ops/test_release_cli.py"]
        )


def test_control_plane_repair_fast_track_accepts_only_image_closure_metadata():
    module = _load_module()

    impact = module.plan_control_plane_repair_fast_track(
        [
            "deploy/docker/Dockerfile.control-plane",
            "deploy/release-artifacts-v2.json",
            "scripts/release.py",
            "tests/ops/test_release_cli.py",
            "tests/ops/test_modular_images.py",
            "docs/knowledge_base_audit_matrix.md",
            ".codex/skills/allbot-ops-deployment/SKILL.md",
            ".codex/skills/allbot-qqcc-lazy-bot/SKILL.md",
        ]
    )

    assert impact.level == "maintenance"
    assert impact.blockers == set()
    assert impact.unknown_paths == []
    assert impact.matched_rules == ["control-plane-repair-fast-track"]


@pytest.mark.parametrize(
    "path",
    [
        "src/services/task_service_flow.py",
        "migrations/versions/example.py",
        "deploy/docker-compose-cloud-prod.overlay.yml",
        "ops/gpu_pool_controller/runtime.py",
        "unexpected/runtime.bin",
    ],
)
def test_control_plane_repair_fast_track_rejects_other_runtime_paths(path):
    module = _load_module()

    with pytest.raises(module.ReleaseError, match="control-plane repair fast-track"):
        module.plan_control_plane_repair_fast_track(
            ["deploy/docker/Dockerfile.control-plane", path]
        )


def test_control_plane_repair_fast_track_requires_private_image_closure_change():
    module = _load_module()

    with pytest.raises(module.ReleaseError, match="image closure changes"):
        module.plan_control_plane_repair_fast_track(
            ["scripts/release.py", "tests/ops/test_release_cli.py"]
        )


def _repair_equivalence_inputs():
    tested_sha = "c" * 40
    target_sha = "d" * 40
    old_central = "sha256:" + "1" * 64
    new_central = "sha256:" + "2" * 64
    old_private = "sha256:" + "3" * 64
    new_private = "sha256:" + "4" * 64
    state = {
        "status": "verified",
        "release_channel": "main",
        "track": "control-plane",
        "git_sha": tested_sha,
        "artifacts": {
            "central-api": {"digest": old_central, "status": "verified"},
            "private-bot-worker": {
                "digest": old_private,
                "status": "verified",
            },
            "public-web": {"digest": "web-same", "status": "verified"},
        },
    }
    manifest = {
        "schema_version": 2,
        "track": "control-plane",
        "git_sha": target_sha,
        "selected_artifacts": [
            "central-api",
            "private-bot-worker",
            "public-web",
        ],
        "artifacts": {
            "central-api": {
                "digest": new_central,
                "ref": "example/central@" + new_central,
            },
            "private-bot-worker": {
                "digest": new_private,
                "ref": "example/private@" + new_private,
            },
            "public-web": {"sha256": "web-same", "ref": "public-web-dist.tgz"},
        },
    }
    tested_catalog = {
        "central-api": {
            "kind": "image",
            "dockerfile": "deploy/docker/Dockerfile.control-plane",
            "target": "central-api",
            "inputs": ["src/**"],
        },
        "private-bot-worker": {
            "kind": "image",
            "dockerfile": "deploy/docker/Dockerfile.control-plane",
            "target": "private-bot-worker",
            "inputs": ["src/**", "qqcc_private_bot/**"],
        },
    }
    target_catalog = json.loads(json.dumps(tested_catalog))
    target_catalog["private-bot-worker"]["inputs"] = [
        "src/**",
        "qqcc_bot/**",
        "qqcc_private_bot/**",
    ]
    old_dockerfile = """FROM runtime AS central-api
COPY src /app/src
FROM runtime AS private-bot-worker
COPY qqcc_private_bot /app/qqcc_private_bot
FROM runtime AS paid-group-bot
"""
    new_dockerfile = """FROM runtime AS central-api
COPY src /app/src
FROM runtime AS private-bot-worker
COPY qqcc_bot /app/qqcc_bot
COPY qqcc_private_bot /app/qqcc_private_bot
FROM runtime AS paid-group-bot
"""
    changed_paths = [
        "deploy/docker/Dockerfile.control-plane",
        "deploy/release-artifacts-v2.json",
        "scripts/release.py",
        "tests/ops/test_release_cli.py",
        "docs/knowledge_base_audit_matrix.md",
    ]
    return (
        state,
        manifest,
        tested_catalog,
        target_catalog,
        old_dockerfile,
        new_dockerfile,
        changed_paths,
    )


def test_control_plane_repair_equivalence_reuses_verified_content_and_smokes_private():
    module = _load_module()
    state, manifest, tested_catalog, target_catalog, old_dockerfile, new_dockerfile, paths = (
        _repair_equivalence_inputs()
    )
    smoked = []

    evidence = module.validate_control_plane_repair_equivalence(
        test_state=state,
        manifest=manifest,
        tested_artifact_catalog=tested_catalog,
        target_artifact_catalog=target_catalog,
        changed_paths=paths,
        tested_dockerfile=old_dockerfile,
        target_dockerfile=new_dockerfile,
        smoke_private_image=smoked.append,
    )

    assert evidence["tested_sha"] == "c" * 40
    assert evidence["equivalent_artifacts"] == ["central-api", "public-web"]
    assert evidence["smoked_artifacts"] == ["private-bot-worker"]
    assert smoked == ["example/private@sha256:" + "4" * 64]


def test_control_plane_repair_equivalence_rejects_other_target_stage_changes():
    module = _load_module()
    state, manifest, tested_catalog, target_catalog, old_dockerfile, new_dockerfile, paths = (
        _repair_equivalence_inputs()
    )
    new_dockerfile = new_dockerfile.replace(
        "COPY src /app/src", "COPY src /app/src\nRUN touch /unexpected"
    )

    with pytest.raises(module.ReleaseError, match="central-api target changed"):
        module.validate_control_plane_repair_equivalence(
            test_state=state,
            manifest=manifest,
            tested_artifact_catalog=tested_catalog,
            target_artifact_catalog=target_catalog,
            changed_paths=paths,
            tested_dockerfile=old_dockerfile,
            target_dockerfile=new_dockerfile,
            smoke_private_image=lambda _ref: None,
        )


def test_control_plane_repair_equivalence_requires_private_runtime_copy():
    module = _load_module()
    state, manifest, tested_catalog, target_catalog, old_dockerfile, new_dockerfile, paths = (
        _repair_equivalence_inputs()
    )
    new_dockerfile = new_dockerfile.replace("COPY qqcc_bot /app/qqcc_bot\n", "")

    with pytest.raises(module.ReleaseError, match="qqcc_bot runtime copy"):
        module.validate_control_plane_repair_equivalence(
            test_state=state,
            manifest=manifest,
            tested_artifact_catalog=tested_catalog,
            target_artifact_catalog=target_catalog,
            changed_paths=paths,
            tested_dockerfile=old_dockerfile,
            target_dockerfile=new_dockerfile,
            smoke_private_image=lambda _ref: None,
        )


def test_control_plane_repair_promotion_uses_verified_base_and_records_evidence(
    monkeypatch,
):
    module = _load_module()
    state, manifest, tested_catalog, target_catalog, old_dockerfile, new_dockerfile, paths = (
        _repair_equivalence_inputs()
    )
    args = SimpleNamespace(
        env="prod",
        command="deploy",
        control_plane_repair_fast_track=True,
        test_state_host="cloud-test",
    )
    smoked = []

    monkeypatch.setattr(module, "_read_test_release_state", lambda *_args: state)
    monkeypatch.setattr(module, "git_changed_paths", lambda *_args: paths)
    monkeypatch.setattr(
        module,
        "_git_file_at_sha",
        lambda sha, _path: old_dockerfile if sha == "c" * 40 else new_dockerfile,
    )
    monkeypatch.setattr(
        module,
        "_artifact_catalog_at_sha",
        lambda sha: tested_catalog if sha == "c" * 40 else target_catalog,
    )
    monkeypatch.setattr(module, "_smoke_private_worker_image", smoked.append)

    module._promotion_check(args, manifest)

    assert args.control_plane_repair_acceptance["tested_sha"] == "c" * 40
    assert args.control_plane_repair_acceptance["target_sha"] == "d" * 40
    assert smoked == ["example/private@sha256:" + "4" * 64]


def test_git_changed_paths_preserves_unicode_and_spaces(monkeypatch):
    module = _load_module()
    expected = [
        "docs/子模块_后台监控与清理_dashboard_monitoring.md",
        "dashboard/frontend/src/a file.vue",
    ]
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="\0".join(expected) + "\0",
            stderr="",
        )

    monkeypatch.setattr(module, "_run", fake_run)

    assert module.git_changed_paths(FULL_SHA, "b" * 40) == expected
    assert "-z" in calls[0]


def test_dashboard_fast_track_skips_test_promotion_but_keeps_ci_preflight(
    tmp_path, monkeypatch
):
    module = _load_module()
    env_file = tmp_path / "prod.env"
    env_file.write_text("ALLBOT_ENV=prod\n", encoding="utf-8")
    # CI runners may use a permissive umask; production preflight requires 0600.
    env_file.chmod(0o600)
    args = SimpleNamespace(
        env="prod",
        dashboard_fast_track=True,
        skip_ci_checks=False,
        local_env_error=False,
        skip_web=True,
        cloudflare_token_file="unused",
    )
    calls = []

    monkeypatch.setattr(module, "local_env_file", lambda _args: env_file)
    monkeypatch.setattr(
        module,
        "verify_release_ci",
        lambda manifest, sha: calls.append((manifest["git_sha"], sha)),
    )
    monkeypatch.setattr(
        module,
        "_promotion_check",
        lambda *_args: pytest.fail("cloud-test promotion must be skipped"),
    )

    blockers = module._operator_preflight(
        args,
        module.ReleaseImpact(
            services={"dashboard-backend", "dashboard-frontend"},
            level="rolling",
        ),
        _manifest(),
        {},
    )

    assert blockers == []
    assert calls == [(FULL_SHA, FULL_SHA)]


def test_dashboard_fast_track_cloud_deploy_is_rolling_and_dashboard_only(monkeypatch):
    module = _load_module()
    args = SimpleNamespace(
        execute=True,
        env="prod",
        remote_host="cloud-prod",
        remote_checkout_root="/release-root",
        remote_env_file="/etc/allbot/prod.env",
        confirm_legacy_cutover=False,
        drain_timeout_seconds=30,
        drain_interval_seconds=1,
    )
    impact = module.ReleaseImpact(
        services={"dashboard-backend", "dashboard-frontend"},
        level="rolling",
        matched_rules=["dashboard-fast-track"],
    )
    remote_scripts = []

    monkeypatch.setattr(
        module,
        "_run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, stdout="", stderr=""
        ),
    )

    def fake_remote(host, script, *, execute):
        remote_scripts.append((host, script, execute))
        return f"ALLBOT_CLOUD_RELEASE_VERIFIED:{FULL_SHA}\n"

    monkeypatch.setattr(module, "_remote_shell", fake_remote)

    module._deploy_cloud(
        args,
        impact,
        _manifest(),
        "ALLBOT_RELEASE_SHA=x\n",
        {},
    )

    assert len(remote_scripts) == 1
    host, script, execute = remote_scripts[0]
    assert host == "cloud-prod"
    assert execute is True
    assert "GENERATION_MAINTENANCE" not in script
    assert "pull dashboard-backend dashboard-frontend" in script
    assert "up -d --no-deps --wait --wait-timeout 180 dashboard-backend dashboard-frontend" in script
    assert "allbot-nontarget" in script
    assert "central-api web-api" not in script


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


def test_test_candidate_ci_must_come_from_exact_test_train_branch(monkeypatch):
    module = _load_module()
    candidate = {
        "ci_run": "https://github.com/giraffu/All_bot/actions/runs/1",
        "release_channel": "test-candidate",
        "source_ref": "refs/heads/codex/test-train",
    }

    def run_for(branch):
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "status": "completed",
                    "conclusion": "success",
                    "headSha": FULL_SHA,
                    "headBranch": branch,
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: run_for("codex/test-train"))
    module.verify_release_ci(candidate, FULL_SHA)

    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: run_for("codex/other"))
    with pytest.raises(module.ReleaseError, match="source branch"):
        module.verify_release_ci(candidate, FULL_SHA)


def test_git_release_uses_channel_specific_remote_ancestry(monkeypatch):
    module = _load_module()
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        stdout = "  origin/codex/test-train\n" if command[1:4] == ["branch", "-r", "--contains"] else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(module, "_run", fake_run)
    module.verify_git_release(
        FULL_SHA,
        release_channel="test-candidate",
        source_ref="refs/heads/codex/test-train",
    )

    assert ["git", "merge-base", "--is-ancestor", FULL_SHA, "origin/codex/test-train"] in commands


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


def _short_observation_evidence(module, manifest, *, completed=None):
    completed = completed or datetime.now(timezone.utc) - timedelta(minutes=1)
    return {
        "git_sha": FULL_SHA,
        "images": manifest["images"],
        "vendor_images": manifest["vendor_images"],
        "observation_started_at": (completed - timedelta(hours=2)).isoformat(),
        "completed_at": completed.isoformat(),
        "approved_by": "ops",
        "checks": {key: True for key in module.REQUIRED_ACCEPTANCE_CHECKS},
    }


def test_short_observation_requires_cli_confirmation_evidence_flag_and_reason():
    module = _load_module()
    manifest = _manifest()
    evidence = _short_observation_evidence(module, manifest)

    with pytest.raises(module.ReleaseError, match="24 hours"):
        module.validate_test_acceptance(evidence, manifest)

    with pytest.raises(module.ReleaseError, match="evidence flag"):
        module.validate_test_acceptance(
            evidence,
            manifest,
            confirm_short_observation=True,
        )

    evidence["short_observation_override"] = True
    evidence["override_reason"] = ""
    with pytest.raises(module.ReleaseError, match="override_reason"):
        module.validate_test_acceptance(
            evidence,
            manifest,
            confirm_short_observation=True,
        )

    evidence["override_reason"] = "User approved promotion after representative smoke"
    with pytest.raises(module.ReleaseError, match="explicit CLI confirmation"):
        module.validate_test_acceptance(evidence, manifest)


def test_short_observation_override_keeps_time_and_smoke_guards():
    module = _load_module()
    manifest = _manifest()
    evidence = _short_observation_evidence(module, manifest)
    evidence.update(
        short_observation_override=True,
        override_reason="User approved promotion after representative smoke",
    )

    evidence["observation_started_at"] = evidence["completed_at"]
    with pytest.raises(module.ReleaseError, match="after observation_started_at"):
        module.validate_test_acceptance(
            evidence,
            manifest,
            confirm_short_observation=True,
        )

    future = datetime.now(timezone.utc) + timedelta(minutes=5)
    evidence["observation_started_at"] = (future - timedelta(hours=1)).isoformat()
    evidence["completed_at"] = future.isoformat()
    with pytest.raises(module.ReleaseError, match="cannot be in the future"):
        module.validate_test_acceptance(
            evidence,
            manifest,
            confirm_short_observation=True,
        )

    evidence = _short_observation_evidence(module, manifest)
    evidence.update(
        short_observation_override=True,
        override_reason="User approved promotion after representative smoke",
    )
    evidence["checks"]["video_task"] = False
    with pytest.raises(module.ReleaseError, match="video_task"):
        module.validate_test_acceptance(
            evidence,
            manifest,
            confirm_short_observation=True,
        )


def test_short_observation_override_returns_auditable_acceptance():
    module = _load_module()
    manifest = _manifest()
    evidence = _short_observation_evidence(module, manifest)
    evidence.update(
        short_observation_override=True,
        override_reason="User approved promotion after representative smoke",
    )

    acceptance = module.validate_test_acceptance(
        evidence,
        manifest,
        confirm_short_observation=True,
    )

    assert acceptance == {
        "approved_by": "ops",
        "completed_at": evidence["completed_at"],
        "observation_started_at": evidence["observation_started_at"],
        "observation_duration_seconds": 7200,
        "short_observation_override": True,
        "override_reason": "User approved promotion after representative smoke",
    }


def test_mark_test_verified_persists_short_observation_audit(monkeypatch, tmp_path):
    module = _load_module()
    manifest = _manifest()
    evidence = _short_observation_evidence(module, manifest)
    evidence.update(
        short_observation_override=True,
        override_reason="User approved promotion after representative smoke",
    )
    manifest_path = tmp_path / "release.json"
    evidence_path = tmp_path / "acceptance.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    state = {
        "git_sha": FULL_SHA,
        "images": manifest["images"],
        "vendor_images": manifest["vendor_images"],
        "web_artifact_sha256": manifest["web_artifact_sha256"],
        "health": {"web": "canonical-runtime-verified"},
    }
    writes = []

    def fake_run(args, **kwargs):
        if args[-1].startswith("cat /var/lib/allbot/deployments/test/current.json"):
            return SimpleNamespace(returncode=0, stdout=json.dumps(state))
        writes.append(kwargs.get("input_text"))
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(module, "_run", fake_run)
    args = SimpleNamespace(
        sha=FULL_SHA,
        manifest=str(manifest_path),
        evidence=str(evidence_path),
        remote_host="test-host",
        execute=True,
        confirm_short_observation=True,
    )

    module._mark_test_verified(args)

    persisted_state = json.loads(writes[1])
    assert persisted_state["status"] == "verified"
    assert persisted_state["acceptance"]["short_observation_override"] is True
    assert persisted_state["acceptance"]["observation_duration_seconds"] == 7200
    assert persisted_state["acceptance"]["override_reason"].startswith("User approved")


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
    assert command[:6] == [
        "npx",
        "--yes",
        "--package=wrangler@4.110.0",
        "wrangler",
        "pages",
        "deploy",
    ]
    assert command[command.index("--project-name") + 1] == expected_project
    assert command[command.index("--branch") + 1] == expected_branch
    assert result["project"] == expected_project
    assert result["deployment_id"] == "deployment-id"
    assert result["canonical_verified"] is True
    assert len(result["runtime_config_revision"]) == 64
    assert not any(command[0] in {"ssh", "scp"} for command, _ in calls)


def test_pages_deployer_rejects_unlocked_wrangler_version(tmp_path, monkeypatch):
    module = _load_module()
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps({"devDependencies": {"wrangler": "^4.110.0"}}),
        encoding="utf-8",
    )
    (frontend / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "": {"devDependencies": {"wrangler": "^4.110.0"}},
                    "node_modules/wrangler": {"version": "4.110.0"},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "ROOT", tmp_path)

    with pytest.raises(module.ReleaseError, match="exact and lockfile-matched"):
        module._pinned_wrangler_version()


def test_config_impact_recreates_consumers_and_unknown_keys_fail_wide():
    module = _load_module()
    updater = _load_config_updater()
    policy = module.load_structured_file(ROOT / "deploy/config-impact.yml")

    known = updater.affected_services(policy, {"BOT_TOKEN_TEST"})
    unknown = updater.affected_services(policy, {"NEW_UNMAPPED_CONFIG"})

    assert {"bot", "qqcc-bot", "qqcc-private-bot-worker"} <= known
    assert unknown == set(module.load_structured_file(POLICY_PATH)["all_services"])


def test_v2_promotion_and_state_are_scoped_per_track(monkeypatch, capsys):
    module = _load_module()
    digest = "sha256:" + "1" * 64
    artifact = {
        "kind": "image",
        "ref": "ghcr.io/giraffu/central@" + digest,
        "digest": digest,
        "source_sha": FULL_SHA,
        "oci_revision": FULL_SHA,
        "dependency_closure": [],
    }
    manifest = {
        "schema_version": 2,
        "track": "control-plane",
        "source_sha": FULL_SHA,
        "git_sha": FULL_SHA,
        "artifacts": {"central-api": artifact},
        "selected_artifacts": ["central-api"],
    }
    state = {
        "schema_version": 2,
        "track": "control-plane",
        "git_sha": FULL_SHA,
        "status": "verified",
        "artifacts": {"central-api": {"digest": digest, "status": "verified"}},
    }
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(state), stderr="")

    monkeypatch.setattr(module, "_run", fake_run)
    args = SimpleNamespace(
        env="prod",
        command="deploy",
        test_state_host="cloud-test",
        execute=False,
    )
    module._promotion_check(args, manifest)
    assert commands[0][-1] == (
        "cat /var/lib/allbot/deployments/test/control-plane/current.json"
    )

    write_args = SimpleNamespace(
        env="test",
        command="deploy",
        remote_host="cloud-test",
        execute=False,
        skip_web=False,
    )
    module._write_state(
        write_args,
        module.ReleaseImpact(services={"central-api"}),
        manifest,
        "f" * 64,
    )
    assert (
        "/var/lib/allbot/deployments/test/control-plane/current.json"
        in capsys.readouterr().out
    )


def test_production_promotion_rejects_candidate_test_state(monkeypatch):
    module = _load_module()
    digest = "sha256:" + "1" * 64
    manifest = {
        "schema_version": 2,
        "track": "control-plane",
        "source_sha": FULL_SHA,
        "git_sha": FULL_SHA,
        "release_channel": "main",
        "source_ref": "refs/heads/main",
        "artifacts": {
            "central-api": {
                "kind": "image",
                "ref": "ghcr.io/giraffu/central@" + digest,
                "digest": digest,
                "source_sha": FULL_SHA,
                "oci_revision": FULL_SHA,
                "dependency_closure": [],
            }
        },
        "selected_artifacts": ["central-api"],
    }
    state = {
        "schema_version": 2,
        "track": "control-plane",
        "git_sha": FULL_SHA,
        "release_channel": "test-candidate",
        "status": "verified",
        "artifacts": {"central-api": {"digest": digest, "status": "verified"}},
    }
    monkeypatch.setattr(
        module,
        "_run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(state), stderr=""
        ),
    )

    with pytest.raises(module.ReleaseError, match="main-channel"):
        module._promotion_check(
            SimpleNamespace(
                env="prod",
                command="deploy",
                test_state_host="cloud-test",
            ),
            manifest,
        )


def test_test_candidate_channel_is_test_only_and_not_verifiable():
    module = _load_module()
    candidate = {
        "schema_version": 2,
        "release_channel": "test-candidate",
        "source_ref": "refs/heads/codex/test-train",
    }

    module.validate_release_channel(candidate, environment="test", purpose="deploy")

    with pytest.raises(module.ReleaseError, match="production"):
        module.validate_release_channel(candidate, environment="prod", purpose="deploy")
    with pytest.raises(module.ReleaseError, match="verify-test"):
        module.validate_release_channel(candidate, environment="test", purpose="verify-test")
    with pytest.raises(module.ReleaseError, match="fast-track"):
        module.validate_release_channel(
            candidate,
            environment="test",
            purpose="deploy",
            dashboard_fast_track=True,
        )


def test_test_rollback_to_main_allows_clean_test_train_operator(monkeypatch):
    module = _load_module()
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        if command[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout=FULL_SHA + "\n", stderr="")
        if command[-1] == "origin/main":
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(module, "_run", fake_run)

    module.verify_operator_worktree_clean(
        source_ref="refs/heads/main",
        environment="test",
        command="rollback",
    )

    assert any(command[-1] == "origin/codex/test-train" for command in commands)


def test_main_deploy_does_not_allow_test_train_operator(monkeypatch):
    module = _load_module()

    def fake_run(command, **_kwargs):
        if command[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout=FULL_SHA + "\n", stderr="")
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="")

    monkeypatch.setattr(module, "_run", fake_run)

    with pytest.raises(module.ReleaseError, match="origin/main"):
        module.verify_operator_worktree_clean(
            source_ref="refs/heads/main",
            environment="test",
            command="deploy",
        )


def test_v2_incremental_track_with_no_changed_modules_selects_nothing(monkeypatch):
    module = _load_module()
    release = SimpleNamespace(
        index={
            "ci_run": "https://github.com/giraffu/All_bot/actions/runs/1",
            "release_channel": "test-candidate",
            "source_ref": "refs/heads/codex/test-train",
        },
        manifests={"control-plane": {"artifacts": {"web-api": {}}}},
    )
    monkeypatch.setattr(module, "load_release_index", lambda *_args, **_kwargs: release)
    monkeypatch.setattr(
        module,
        "select_artifacts",
        lambda *_args, **_kwargs: pytest.fail("empty incremental selection must not expand"),
    )

    manifest = module._load_v2_track(
        Path("release-index.json"),
        sha=FULL_SHA,
        track="control-plane",
        modules=[],
        select_all_when_empty=False,
    )

    assert manifest["selected_artifacts"] == []


def test_main_channel_keeps_production_and_verify_test_compatibility():
    module = _load_module()
    main_release = {
        "schema_version": 2,
        "release_channel": "main",
        "source_ref": "refs/heads/main",
    }

    module.validate_release_channel(main_release, environment="prod", purpose="deploy")
    module.validate_release_channel(main_release, environment="test", purpose="verify-test")


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


def test_prod_rollback_preflight_accepts_cached_v2_release_index(tmp_path):
    module = _load_module()
    previous_sha = "1" * 40
    release_index = tmp_path / previous_sha / "release-v2" / "release-index.json"
    release_index.parent.mkdir(parents=True)
    release_index.write_text("{}\n", encoding="utf-8")
    (release_index.parent / "public-web-dist.tgz").write_bytes(b"web")

    blockers = module._rollback_preflight(
        SimpleNamespace(
            env="prod",
            previous_sha=previous_sha,
            bundle_cache=str(tmp_path),
        ),
        module.ReleaseImpact(
            services={"central-api", "web-static"}, level="rolling"
        ),
        _manifest(),
        {},
    )

    assert blockers == []


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


def test_v2_transaction_commit_moves_staged_state_to_track_paths(monkeypatch):
    module = _load_module()
    calls = []
    monkeypatch.setattr(
        module,
        "_remote_shell",
        lambda host, script, *, execute: calls.append((host, script, execute)),
    )
    args = SimpleNamespace(env="test", remote_host="test-control", execute=False)
    transaction = module.new_release_transaction(
        environment="test",
        target_sha="a" * 40,
        previous_sha="b" * 40,
        previous_kind="immutable",
        previous_pages_deployment_id="old-id",
    )
    transaction["track"] = "control-plane"
    transaction["phase"] = "state_completed"

    module._clear_transaction_maintenance(args, transaction)

    script = calls[0][1]
    assert "/var/lib/allbot/deployments/test/control-plane/current.json" in script
    assert (
        "/var/lib/allbot/deployments/test/control-plane/history/"
        + "a" * 40
        + ".json"
    ) in script


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


def test_release_cli_accepts_nested_oras_v2_bundle_layout(tmp_path):
    module = _load_module()
    cache = tmp_path / "cache"
    nested = cache / FULL_SHA / "release-v2"
    nested.mkdir(parents=True)
    index = nested / "release-index.json"
    index.write_text("{}", encoding="utf-8")
    web = nested / "public-web-dist.tgz"
    web.write_bytes(b"web")
    args = SimpleNamespace(
        manifest=None,
        bundle_cache=str(cache),
        bundle_repository="ghcr.io/giraffu/allbot-release-v2",
        sha=FULL_SHA,
        web_artifact="web-dist.tgz",
    )

    assert module._resolve_manifest_path(args) == index
    assert module._resolved_web_artifact(args, {"git_sha": FULL_SHA}) == web
