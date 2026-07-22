import importlib.util
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
RELEASE_PATH = ROOT / "scripts" / "release.py"
FULL_SHA = "a" * 40
DIGEST = "sha256:" + "1" * 64
IMAGE_REF = f"ghcr.io/giraffu/allbot-web-api@{DIGEST}"


def _load_module():
    spec = importlib.util.spec_from_file_location("release_module_config", RELEASE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_deploy_module_parser_accepts_repeated_fixed_modules():
    module = _load_module()

    args = module.build_parser().parse_args(
        [
            "deploy-module",
            "--module",
            "web-api",
            "--module",
            "dashboard",
            "--confirm-prod",
            "--execute",
        ]
    )

    assert args.env == "prod"
    assert args.track == "control-plane"
    assert args.modules == ["web-api", "dashboard"]


def test_deploy_module_requires_exact_promoted_approval():
    module = _load_module()
    manifest = {
        "selected_artifacts": ["web-api"],
        "validation": {"mode": "promoted"},
        "artifacts": {"web-api": {"digest": DIGEST}},
        "promotion_approval": {
            "artifacts": {
                "web-api": {"status": "verified", "digest": DIGEST},
            }
        },
    }

    module.validate_deploy_module_approval(manifest)
    manifest["promotion_approval"]["artifacts"]["web-api"]["digest"] = (
        "sha256:" + "2" * 64
    )

    with pytest.raises(module.ReleaseError, match="exact promoted-main approval"):
        module.validate_deploy_module_approval(manifest)


def test_credential_isolation_completion_requires_fresh_complete_evidence():
    module = _load_module()
    evidence = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "isolation": {
            "checked_keys": [
                "AGENT_SECRET_TOKEN",
                "API_TOKEN",
                "AUTH_TOKEN",
                "DASHBOARD_SECRET_KEY",
                "MINIO_ACCESS_KEY",
                "MINIO_SECRET_KEY",
                "QQCC_CONFIG_SECRET_KEY",
                "R2_ACCESS_KEY",
                "R2_SECRET_KEY",
            ],
            "reused_keys": [],
        },
        "health": {
            "test_worker": True,
            "prod_control_plane": True,
            "prod_workers": True,
        },
        "old_credentials_revoked": True,
    }

    validated = module.validate_credential_isolation_evidence(evidence)
    assert validated["isolation"]["reused_keys"] == []

    evidence["health"]["prod_workers"] = False
    with pytest.raises(module.ReleaseError, match="health evidence is incomplete"):
        module.validate_credential_isolation_evidence(evidence)


def test_credential_isolation_complete_command_is_explicit(
    tmp_path, monkeypatch, capsys
):
    module = _load_module()
    evidence_path = tmp_path / "isolation.json"
    evidence_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "isolation": {
                    "checked_keys": sorted(module.REQUIRED_ISOLATED_SECRET_KEYS),
                    "reused_keys": [],
                },
                "health": {
                    "test_worker": True,
                    "prod_control_plane": True,
                    "prod_workers": True,
                },
                "old_credentials_revoked": True,
            }
        ),
        encoding="utf-8",
    )
    recorded = []
    monkeypatch.setattr(
        module,
        "complete_credential_isolation",
        lambda args, evidence: (
            recorded.append(evidence)
            or {"audit_sha256": "a" * 64, "completed_at": evidence["generated_at"]}
        ),
    )

    result = module.main(
        [
            "credential-isolation-complete",
            "--evidence",
            str(evidence_path),
            "--confirm-prod",
            "--execute",
        ]
    )

    assert result == 0
    assert recorded[0]["isolation"]["reused_keys"] == []
    assert json.loads(capsys.readouterr().out)["status"] == (
        "credential-isolation-complete"
    )


def test_config_plan_only_prints_key_names_services_and_revisions(monkeypatch, capsys):
    module = _load_module()
    snapshot = {
        "environment": "prod",
        "environment_revision": "a" * 64,
        "active_revision": "b" * 64,
        "contract_revision": "c" * 64,
        "changed_keys": ["API_TOKEN"],
        "affected_services": ["central-api", "web-api"],
        "unknown_keys": [],
        "service_revisions": {"web-api": "d" * 64},
        "public_values": {"ALLBOT_STATE_ROOT": "/must-not-be-printed"},
        "present_keys": ["API_TOKEN"],
        "drift": True,
    }
    monkeypatch.setattr(
        module,
        "_remote_runtime_env_snapshot",
        lambda _args, **_kwargs: ({}, "a" * 64, snapshot),
    )

    assert module.main(["config-plan", "--env", "prod"]) == 0
    document = json.loads(capsys.readouterr().out)

    assert document["changed_keys"] == ["API_TOKEN"]
    assert document["affected_services"] == ["central-api", "web-api"]
    assert "public_values" not in document
    assert "/must-not-be-printed" not in json.dumps(document)


@pytest.mark.parametrize(
    ("module_name", "expected_services"),
    [
        ("central-api", {"central-api"}),
        ("web-api", {"web-api"}),
        ("payment-api", {"payment-api"}),
        ("dashboard", {"dashboard-backend", "dashboard-frontend"}),
        ("main-bot", {"main-bot"}),
        ("qqcc-bot", {"qqcc-bot"}),
        ("qqcc-config", {"qqcc-config-backend", "qqcc-config-frontend"}),
        ("private-bot-worker", {"private-bot-worker"}),
        ("paid-group-bot", {"paid-group-bot"}),
    ],
)
def test_module_config_plan_limits_remote_projection_to_module_services(
    module_name, expected_services,
    monkeypatch, capsys
):
    module = _load_module()
    commands = []
    monkeypatch.setattr(
        module,
        "_run",
        lambda *args, **kwargs: (
            commands.append(kwargs["input_text"])
            or subprocess.CompletedProcess(
                args[0],
                0,
                stdout=json.dumps(
                    {
                        "environment": "prod",
                        "environment_revision": "a" * 64,
                        "active_revision": None,
                        "contract_revision": "b" * 64,
                        "drift": True,
                        "changed_keys": ["RUNPOD_RELEASE_PROFILE_PINS_JSON"],
                        "affected_services": sorted(expected_services),
                        "unknown_keys": [],
                        "service_revisions": {
                            service: "c" * 64 for service in expected_services
                        },
                        "present_keys": ["ALLBOT_ENV"],
                        "public_values": {},
                    }
                ),
                stderr="",
            )
        ),
    )

    assert module.main(
        ["config-plan", "--env", "prod", "--module", module_name]
    ) == 0
    capsys.readouterr()

    for service in expected_services:
        assert f"--service {service}" in commands[0]
    for service in set(module.CONFIG_SERVICE_TO_COMPOSE) - expected_services:
        assert f"--service {service}" not in commands[0]


def test_initial_dashboard_config_apply_only_stages_projection(monkeypatch, capsys):
    module = _load_module()
    inspected = {
        "environment": "prod",
        "environment_revision": "a" * 64,
        "active_revision": None,
        "affected_services": ["dashboard-backend", "dashboard-frontend"],
        "unknown_keys": sorted(module.DASHBOARD_INITIAL_PROJECTION_LEGACY_KEYS),
        "drift": True,
    }
    activated = dict(inspected, active_revision="a" * 64, drift=False)
    events = []

    def snapshot(_args, **kwargs):
        command = kwargs.get("command", "inspect")
        events.append(command)
        return ({}, "a" * 64, activated if command == "activate" else inspected)

    monkeypatch.setattr(module, "_remote_runtime_env_snapshot", snapshot)
    monkeypatch.setattr(
        module,
        "_prepare_config_backup",
        lambda *_args, **_kwargs: events.append("backup"),
    )
    monkeypatch.setattr(
        module,
        "_config_apply_cloud",
        lambda *_args, **_kwargs: events.append("compose"),
    )
    monkeypatch.setattr(
        module,
        "_set_config_maintenance",
        lambda *_args, **_kwargs: events.append("maintenance"),
    )

    assert (
        module.main(
            [
                "config-apply",
                "--env",
                "prod",
                "--module",
                "dashboard",
                "--confirm-prod",
                "--execute",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert events == ["inspect", "activate"]
    assert '"status": "config-staged"' in output
    assert '"ignored_legacy_keys"' in output


def test_initial_dashboard_config_apply_rejects_unreviewed_unknown_key(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(
        module,
        "_remote_runtime_env_snapshot",
        lambda _args, **_kwargs: (
            {},
            "a" * 64,
            {
                "environment": "prod",
                "environment_revision": "a" * 64,
                "active_revision": None,
                "affected_services": ["dashboard-backend"],
                "unknown_keys": ["UNREVIEWED_PROD_KEY"],
                "drift": True,
            },
        ),
    )

    with pytest.raises(module.ReleaseError, match="unreviewed unknown keys"):
        module.run_config_command(
            module.build_parser().parse_args(
                [
                    "config-apply",
                    "--env",
                    "prod",
                    "--module",
                    "dashboard",
                    "--confirm-prod",
                    "--execute",
                ]
            )
        )


def test_scoped_config_apply_adds_module_after_initial_activation_without_runtime_mutation(
    monkeypatch, capsys
):
    module = _load_module()
    inspected = {
        "environment": "prod",
        "environment_revision": "a" * 64,
        "active_revision": "a" * 64,
        "affected_services": ["qqcc-config-backend", "qqcc-config-frontend"],
        "unknown_keys": [],
        "drift": True,
    }
    activated = dict(inspected, drift=False)
    events = []

    def snapshot(_args, **kwargs):
        command = kwargs.get("command", "inspect")
        events.append(command)
        return ({}, "a" * 64, activated if command == "activate" else inspected)

    monkeypatch.setattr(module, "_remote_runtime_env_snapshot", snapshot)
    monkeypatch.setattr(
        module, "_prepare_config_backup", lambda *a, **k: events.append("backup")
    )
    monkeypatch.setattr(
        module, "_config_apply_cloud", lambda *a, **k: events.append("compose")
    )
    monkeypatch.setattr(
        module, "_set_config_maintenance", lambda *a, **k: events.append("maintenance")
    )

    assert (
        module.main(
            [
                "config-apply",
                "--env",
                "prod",
                "--module",
                "qqcc-config",
                "--confirm-prod",
                "--execute",
            ]
        )
        == 0
    )

    assert events == ["inspect", "activate"]
    assert '"status": "config-staged"' in capsys.readouterr().out


def test_scoped_config_apply_accepts_active_target_projection_change(
    monkeypatch, capsys
):
    module = _load_module()
    inspected = {
        "environment": "prod",
        "environment_revision": "a" * 64,
        "active_revision": "b" * 64,
        "affected_services": ["dashboard-backend"],
        "unknown_keys": [],
        "drift": True,
    }
    activated = dict(inspected, active_revision="a" * 64, drift=False)
    events = []

    def snapshot(_args, **kwargs):
        command = kwargs.get("command", "inspect")
        events.append(command)
        return ({}, "a" * 64, activated if command == "activate" else inspected)

    monkeypatch.setattr(module, "_remote_runtime_env_snapshot", snapshot)
    monkeypatch.setattr(
        module, "_prepare_config_backup", lambda *a, **k: events.append("backup")
    )
    monkeypatch.setattr(
        module, "_config_apply_cloud", lambda *a, **k: events.append("compose")
    )
    monkeypatch.setattr(
        module, "_set_config_maintenance", lambda *a, **k: events.append("maintenance")
    )

    assert (
        module.main(
            [
                "config-apply",
                "--env",
                "prod",
                "--module",
                "dashboard",
                "--confirm-prod",
                "--execute",
            ]
        )
        == 0
    )

    assert events == ["inspect", "activate"]
    assert '"services": [\n    "dashboard-backend"' in capsys.readouterr().out


def test_scoped_config_apply_rejects_active_projection_change_outside_module(
    monkeypatch,
):
    module = _load_module()
    monkeypatch.setattr(
        module,
        "_remote_runtime_env_snapshot",
        lambda _args, **_kwargs: (
            {},
            "a" * 64,
            {
                "environment": "prod",
                "environment_revision": "a" * 64,
                "active_revision": "b" * 64,
                "affected_services": ["dashboard-backend", "qqcc-bot"],
                "unknown_keys": [],
                "drift": True,
            },
        ),
    )

    with pytest.raises(module.ReleaseError, match="escaped its service closure"):
        module.run_config_command(
            module.build_parser().parse_args(
                [
                    "config-apply",
                    "--env",
                    "prod",
                    "--module",
                    "qqcc-bot",
                    "--confirm-prod",
                    "--execute",
                ]
            )
        )


def test_config_apply_backs_up_current_database_before_full_activation(monkeypatch):
    module = _load_module()
    inspected = {
        "environment": "prod",
        "environment_revision": "a" * 64,
        "active_revision": "b" * 64,
        "affected_services": ["web-api"],
        "unknown_keys": ["NEW_CONTRACT_KEY"],
        "drift": True,
    }
    activated = dict(inspected, drift=False)
    events = []

    def snapshot(_args, **kwargs):
        command = kwargs.get("command", "inspect")
        events.append(command)
        return ({}, "a" * 64, activated if command == "activate" else inspected)

    monkeypatch.setattr(module, "_remote_runtime_env_snapshot", snapshot)
    monkeypatch.setattr(
        module,
        "_prepare_config_backup",
        lambda _args, **_kwargs: events.append("backup"),
    )
    monkeypatch.setattr(
        module,
        "_config_apply_cloud",
        lambda _args, _state, _services: events.append("compose"),
    )
    monkeypatch.setattr(module, "_set_config_maintenance", lambda *a, **k: None)

    assert (
        module.main(["config-apply", "--env", "prod", "--confirm-prod", "--execute"])
        == 0
    )
    assert events == ["inspect", "backup", "activate", "compose"]


def test_config_apply_snapshots_running_and_stopped_non_target_containers(monkeypatch):
    module = _load_module()
    scripts = []
    monkeypatch.setattr(
        module,
        "_run",
        lambda *args, **kwargs: (
            scripts.append(kwargs["input_text"])
            or subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")
        ),
    )

    module._config_apply_cloud(
        SimpleNamespace(env="prod", remote_host="prod-control", remote_env_file=None),
        {
            "environment_revision": "a" * 64,
            "service_revisions": {"dashboard-backend": "b" * 64},
        },
        {"dashboard-backend"},
    )

    assert "docker ps -aq" in scripts[0]
    assert "pg_dump" not in scripts[0]


def test_full_config_backup_uses_current_running_web_api(monkeypatch):
    module = _load_module()
    scripts = []
    monkeypatch.setattr(
        module,
        "_run",
        lambda *args, **kwargs: (
            scripts.append(kwargs["input_text"])
            or subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")
        ),
    )

    module._prepare_config_backup(
        SimpleNamespace(env="prod", remote_host="prod-control", remote_env_file=None),
        initial_cutover=True,
    )

    assert 'docker exec "$container_id"' in scripts[0]
    assert "pg_dump" in scripts[0]
    assert 'case "$DATABASE_URL" in postgresql+asyncpg:*' in scripts[0]
    assert "${DATABASE_URL#postgresql+asyncpg:}" in scripts[0]
    assert "${DATABASE_URL/postgresql+asyncpg:/postgresql:}" not in scripts[0]
    assert "/etc/allbot/prod.env" in scripts[0]


def test_no_change_requires_exact_digest_health_and_service_config_revision(
    monkeypatch,
):
    module = _load_module()
    args = SimpleNamespace(env="prod", remote_host="prod-control")
    impact = module.ReleaseImpact(services={"web-api"}, level="maintenance")
    manifest = {
        "schema_version": 2,
        "git_sha": FULL_SHA,
        "artifacts": {"web-api": {"ref": IMAGE_REF}},
    }
    monkeypatch.setattr(
        module,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout=f"web-api\t{IMAGE_REF}\n",
            stderr="",
        ),
    )

    result = module.verify_deploy_module_no_change(
        args,
        impact,
        manifest,
        {},
        "environment-revision",
        {"web-api": "service-revision"},
    )

    assert result["status"] == "no-change"
    assert result["artifacts"]["web-api"]["digest"] == DIGEST
    assert result["service_config_revisions"] == {
        "web-api": "service-revision",
    }
