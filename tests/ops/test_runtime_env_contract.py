import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "runtime_env_contract.py"
CONTRACT_PATH = ROOT / "deploy" / "service-env-contract.yml"


def _load_module():
    spec = importlib.util.spec_from_file_location("runtime_env_contract", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _environment(environment: str) -> dict[str, str]:
    suffix = "test" if environment == "test" else "prod"
    return {
        "ALLBOT_ENV": environment,
        "ALLBOT_STATE_ROOT": f"/var/lib/allbot/{suffix}",
        "DATABASE_URL": f"postgresql+asyncpg://{suffix}-db",
        "REDIS_URL": f"redis://{suffix}-redis/0",
        "WORKER_REDIS_URL": f"redis://{suffix}-worker/0",
        "API_BASE": "http://central-api:8003",
        "API_TOKEN": f"{suffix}-api-token",
        "AUTH_TOKEN": f"{suffix}-auth-token",
        "AGENT_SECRET_TOKEN": f"{suffix}-agent-token",
        "MINIO_ENDPOINT": f"{suffix}-storage",
        "MINIO_ACCESS_KEY": f"{suffix}-access",
        "MINIO_SECRET_KEY": f"{suffix}-secret",
        "MINIO_BUCKET": f"user-data-{suffix}",
        "MINIO_RESULT_BUCKET": f"results-{suffix}",
        "MINIO_SECURE": "true",
        "R2_ENDPOINT": f"https://{suffix}-r2.example.com",
        "R2_ACCESS_KEY": f"{suffix}-r2-access",
        "R2_SECRET_KEY": f"{suffix}-r2-secret",
        "R2_BUCKET": f"user-data-{suffix}",
        "R2_PUBLIC_DOMAIN": f"https://assets-{suffix}.example.com",
        "BOT_TOKEN": f"{suffix}-bot-token",
        "TELEGRAM_API_BASE_URL": f"https://telegram-api-{suffix}.example.com",
        "TELEGRAM_FILE_BASE_URL": f"https://telegram-file-{suffix}.example.com",
        "QQCC_BOT_TOKEN": f"{suffix}-qqcc-token",
        "JWT_SECRET_KEY": f"{suffix}-jwt-secret",
        "DASHBOARD_SECRET_KEY": f"{suffix}-dashboard-secret",
        "DASHBOARD_ADMIN_USERNAME": "admin",
        "DASHBOARD_ADMIN_PASSWORD_HASH": f"{suffix}-dashboard-hash",
        "QQCC_CONFIG_SECRET_KEY": f"{suffix}-qqcc-secret",
        "QQCC_CONFIG_ADMIN_USERNAME": "qqcc_admin",
        "QQCC_CONFIG_ADMIN_PASSWORD_HASH": f"{suffix}-qqcc-hash",
        "QQCC_CONFIG_ADMIN_HOST": f"qqcc-{suffix}.example.com",
        "PRIVATE_QQCC_BOT_OWNER_HOST": f"private-{suffix}.example.com",
        "PRIVATE_QQCC_BOT_ENABLED": "false",
        "PRIVATE_QQCC_BOT_TOKEN_KEYRING": '{"1":"synthetic-key"}',
        "PRIVATE_QQCC_BOT_TOKEN_FINGERPRINT_KEY": f"{suffix}-fingerprint",
        "PAID_GROUP_BOT_TOKEN": f"{suffix}-paid-token",
        "PAID_GROUP_CHAT_ID": "-1000000000000",
        "HUANYUY_NOTIFY_URL": f"https://pay-{suffix}.example.com/notify",
        "HUANYUY_RETURN_URL": f"https://pay-{suffix}.example.com/return",
        "HUANYUY_PID": f"{suffix}-merchant",
        "HUANYUY_KEY": f"{suffix}-payment-key",
        "HUANYUY_GATEWAY": f"https://gateway-{suffix}.example.com",
        "HUANYUY_SITENAME": f"AllBot {suffix}",
        "UNRELATED_OPERATOR_SECRET": "must-not-enter-containers",
    }


def test_builds_scoped_service_projections_without_unrelated_secrets():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)

    snapshot = module.build_snapshot(contract, "prod", _environment("prod"))

    web = snapshot.projections["web-api"]
    bot = snapshot.projections["main-bot"]
    dashboard_frontend = snapshot.projections["dashboard-frontend"]
    assert web["ALLBOT_ENV"] == "prod"
    assert web["ALLBOT_CONFIG_REVISION"] == snapshot.service_revisions["web-api"]
    assert web["BOT_TOKEN"] == "prod-bot-token"
    assert "PAID_GROUP_BOT_TOKEN" not in web
    assert bot["BOT_TOKEN"] == "prod-bot-token"
    assert "UNRELATED_OPERATOR_SECRET" not in bot
    assert set(dashboard_frontend) == {
        "ALLBOT_CONFIG_REVISION",
        "ALLBOT_ENV",
    }


def test_dashboard_backend_projection_requires_agent_control_token():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")

    snapshot = module.build_snapshot(
        contract,
        "prod",
        values,
        services={"dashboard-backend"},
    )

    assert snapshot.projections["dashboard-backend"]["AGENT_SECRET_TOKEN"] == (
        "prod-agent-token"
    )
    assert "UNRELATED_OPERATOR_SECRET" not in snapshot.projections["dashboard-backend"]


def test_dashboard_backend_projection_rejects_missing_agent_control_token():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")
    del values["AGENT_SECRET_TOKEN"]

    with pytest.raises(module.ContractError, match="AGENT_SECRET_TOKEN"):
        module.build_snapshot(
            contract,
            "prod",
            values,
            services={"dashboard-backend"},
        )


def test_missing_required_service_key_fails_closed_without_value_disclosure():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")
    del values["BOT_TOKEN"]

    with pytest.raises(module.ContractError) as exc:
        module.build_snapshot(contract, "prod", values, services={"main-bot"})

    assert "BOT_TOKEN" in str(exc.value)
    assert "prod-bot-token" not in str(exc.value)


def test_disabled_optional_service_does_not_receive_or_require_projection():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")
    values["PRIVATE_QQCC_BOT_ENABLED"] = "false"
    del values["PRIVATE_QQCC_BOT_TOKEN_KEYRING"]
    del values["PRIVATE_QQCC_BOT_TOKEN_FINGERPRINT_KEY"]

    snapshot = module.build_snapshot(contract, "prod", values)

    assert "private-bot-worker" not in snapshot.projections


def test_environment_identity_mismatch_is_rejected():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)

    with pytest.raises(module.ContractError, match="ALLBOT_ENV"):
        module.build_snapshot(contract, "prod", _environment("test"))


def test_changed_key_names_expand_to_affected_services_and_unknown_is_all():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    services = set(contract["services"])

    assert module.affected_services(contract, {"BOT_TOKEN"}) == {
        "main-bot",
        "web-api",
    }
    assert module.affected_services(contract, {"DB_POOL_SIZE"}) == set(
        contract["shared_defaults"]["services"]
    )
    assert module.unknown_changed_keys(contract, {"DB_POOL_SIZE"}) == set()
    assert module.affected_services(contract, {"NEW_UNKNOWN_KEY"}) == services


def test_gpu_worker_keys_are_outside_control_plane_revision_and_impact():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    original_values = _environment("test")
    original_values.update(
        {
            "ALLBOT_WORKER_I2I_PRO_IMAGE": "registry.example/worker@sha256:old",
            "CLOUD_TEST_WORKER_ENABLED": "false",
            "CLOUD_TEST_SHARED_AIO_PREFETCH_ENABLED": "false",
        }
    )
    changed_values = dict(original_values)
    changed_values.update(
        {
            "ALLBOT_WORKER_I2I_PRO_IMAGE": "registry.example/worker@sha256:new",
            "CLOUD_TEST_WORKER_ENABLED": "true",
            "CLOUD_TEST_SHARED_AIO_PREFETCH_ENABLED": "true",
        }
    )

    original = module.build_snapshot(contract, "test", original_values)
    changed = module.build_snapshot(contract, "test", changed_values)
    active = {
        "key_hashes": original.key_hashes,
        "contract_revision": original.contract_revision,
    }

    assert changed.environment_revision == original.environment_revision
    assert changed.service_revisions == original.service_revisions
    assert "ALLBOT_WORKER_I2I_PRO_IMAGE" not in changed.key_hashes
    assert "CLOUD_TEST_WORKER_ENABLED" not in changed.key_hashes
    assert "CLOUD_TEST_SHARED_AIO_PREFETCH_ENABLED" not in changed.key_hashes
    assert module.changed_keys(changed, active) == set()
    assert (
        module.affected_services(
            contract,
            {
                "ALLBOT_WORKER_I2I_PRO_IMAGE",
                "CLOUD_TEST_WORKER_ENABLED",
                "CLOUD_TEST_SHARED_AIO_PREFETCH_ENABLED",
            },
        )
        == set()
    )
    assert (
        module.unknown_changed_keys(
            contract,
            {
                "ALLBOT_WORKER_I2I_PRO_IMAGE",
                "CLOUD_TEST_WORKER_ENABLED",
                "CLOUD_TEST_SHARED_AIO_PREFETCH_ENABLED",
            },
        )
        == set()
    )
    assert all(
        "ALLBOT_WORKER_I2I_PRO_IMAGE" not in projection
        and "CLOUD_TEST_WORKER_ENABLED" not in projection
        and "CLOUD_TEST_SHARED_AIO_PREFETCH_ENABLED" not in projection
        for projection in changed.projections.values()
    )


def test_external_worker_key_does_not_hide_unknown_control_plane_key():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)

    changed = {"ALLBOT_WORKER_I2I_PRO_IMAGE", "NEW_UNKNOWN_KEY"}

    assert module.affected_services(contract, changed) == set(contract["services"])
    assert module.unknown_changed_keys(contract, changed) == {"NEW_UNKNOWN_KEY"}


def test_contract_change_alters_revision_and_impacts_all_services():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")
    original = module.build_snapshot(contract, "prod", values)
    changed_contract = __import__("copy").deepcopy(contract)
    changed_contract["services"]["web-api"]["patterns"].append("NEW_SETTING")
    changed = module.build_snapshot(changed_contract, "prod", values)
    active = {
        "key_hashes": original.key_hashes,
        "contract_revision": original.contract_revision,
    }

    assert changed.environment_revision != original.environment_revision
    changed_keys = module.changed_keys(changed, active)
    assert changed_keys == {"ALLBOT_SERVICE_CONTRACT_REVISION"}
    assert module.affected_services(changed_contract, changed_keys) == set(
        changed_contract["services"]
    )


def test_snapshot_json_contains_revisions_and_key_names_but_not_values():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    snapshot = module.build_snapshot(contract, "test", _environment("test"))
    document = module.snapshot_summary(snapshot, changed_keys={"API_TOKEN"})
    rendered = module.dumps_summary(document)

    assert "API_TOKEN" in rendered
    assert snapshot.environment_revision in rendered
    assert "test-api-token" not in rendered
    assert "test-agent-token" not in rendered


def test_activation_writes_immutable_scoped_env_files_and_can_roll_back(tmp_path):
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    first = module.build_snapshot(contract, "prod", _environment("prod"))
    module.activate_snapshot(tmp_path, first)

    current = tmp_path / "current"
    web_file = current / "web-api.env"
    assert current.resolve().name == first.environment_revision
    assert oct(web_file.stat().st_mode & 0o777) == "0o600"
    assert "PAID_GROUP_BOT_TOKEN" not in web_file.read_text(encoding="utf-8")

    changed = _environment("prod")
    changed["API_TOKEN"] = "rotated-prod-api-token"
    second = module.build_snapshot(contract, "prod", changed)
    second_state = module.activate_snapshot(tmp_path, second)
    assert second_state["previous_revision"] == first.environment_revision
    assert current.resolve().name == second.environment_revision

    module.rollback_activation(tmp_path, second.environment_revision)
    assert current.resolve().name == first.environment_revision
    assert (
        module.load_active_state(tmp_path)["environment_revision"]
        == first.environment_revision
    )


def test_active_projection_integrity_rejects_tampering(tmp_path):
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    snapshot = module.build_snapshot(contract, "prod", _environment("prod"))
    active = module.activate_snapshot(tmp_path, snapshot)
    projection = tmp_path / snapshot.environment_revision / "web-api.env"
    projection.write_text(
        projection.read_text(encoding="utf-8") + "TAMPERED=value\n",
        encoding="utf-8",
    )

    with pytest.raises(module.ContractError, match="integrity"):
        module.validate_active_projection_integrity(tmp_path, active)


def test_cli_merges_versioned_defaults_before_host_env_override(tmp_path):
    module = _load_module()
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(
        '{"schema_version":1,"shared_defaults":{"services":["api"],'
        '"keys":["DB_POOL_SIZE"]},"services":{"api":'
        '{"required":["ALLBOT_ENV"],"patterns":[]}}}',
        encoding="utf-8",
    )
    defaults = tmp_path / "defaults.env"
    defaults.write_text("DB_POOL_SIZE=5\n", encoding="utf-8")
    env_file = tmp_path / "prod.env"
    env_file.write_text("ALLBOT_ENV=prod\nDB_POOL_SIZE=9\n", encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"

    assert (
        module.main(
            [
                "activate",
                "--environment",
                "prod",
                "--env-file",
                str(env_file),
                "--defaults",
                str(defaults),
                "--contract",
                str(contract_path),
                "--root",
                str(root),
            ]
        )
        == 0
    )
    projection = (root / "current" / "api.env").read_text(encoding="utf-8")
    assert "DB_POOL_SIZE=9\n" in projection


def test_cli_external_worker_change_is_not_control_plane_drift(tmp_path, capsys):
    module = _load_module()
    env_file = tmp_path / "test.env"
    values = _environment("test")
    values["ALLBOT_WORKER_I2I_PRO_IMAGE"] = "worker@sha256:old"
    values["CLOUD_TEST_WORKER_ENABLED"] = "false"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"
    common = [
        "--environment",
        "test",
        "--env-file",
        str(env_file),
        "--contract",
        str(CONTRACT_PATH),
        "--root",
        str(root),
    ]

    assert module.main(["activate", *common]) == 0
    activated = json.loads(capsys.readouterr().out)
    values["ALLBOT_WORKER_I2I_PRO_IMAGE"] = "worker@sha256:new"
    values["CLOUD_TEST_WORKER_ENABLED"] = "true"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)

    assert module.main(["inspect", *common]) == 0
    inspected = json.loads(capsys.readouterr().out)

    assert inspected["environment_revision"] == activated["environment_revision"]
    assert inspected["active_revision"] == activated["environment_revision"]
    assert inspected["drift"] is False
    assert inspected["changed_keys"] == []
    assert inspected["unknown_keys"] == []
    assert inspected["affected_services"] == []


def test_full_inspect_detects_services_missing_from_scoped_initial_activation(
    tmp_path, capsys
):
    module = _load_module()
    env_file = tmp_path / "prod.env"
    env_file.write_text(module._env_text(_environment("prod")), encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"
    common = [
        "--environment",
        "prod",
        "--env-file",
        str(env_file),
        "--contract",
        str(CONTRACT_PATH),
        "--root",
        str(root),
    ]

    assert (
        module.main(
            [
                "activate",
                *common,
                "--service",
                "dashboard-backend",
                "--service",
                "dashboard-frontend",
            ]
        )
        == 0
    )
    scoped = json.loads(capsys.readouterr().out)
    assert scoped["drift"] is False

    assert module.main(["inspect", *common]) == 0
    full = json.loads(capsys.readouterr().out)

    assert full["active_revision"] == scoped["environment_revision"]
    assert full["drift"] is True
    assert "web-api" in full["affected_services"]


def test_scoped_activation_adds_module_without_rewriting_active_projections(
    tmp_path, capsys
):
    module = _load_module()
    env_file = tmp_path / "prod.env"
    env_file.write_text(module._env_text(_environment("prod")), encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"
    common = [
        "--environment",
        "prod",
        "--env-file",
        str(env_file),
        "--contract",
        str(CONTRACT_PATH),
        "--root",
        str(root),
    ]

    assert (
        module.main(
            [
                "activate",
                *common,
                "--service",
                "dashboard-backend",
                "--service",
                "dashboard-frontend",
            ]
        )
        == 0
    )
    first = json.loads(capsys.readouterr().out)
    dashboard_backend = root / "current" / "dashboard-backend.env"
    dashboard_frontend = root / "current" / "dashboard-frontend.env"
    before = {
        "dashboard-backend": dashboard_backend.read_bytes(),
        "dashboard-frontend": dashboard_frontend.read_bytes(),
    }

    assert (
        module.main(
            [
                "activate",
                *common,
                "--service",
                "qqcc-config-backend",
                "--service",
                "qqcc-config-frontend",
            ]
        )
        == 0
    )
    second = json.loads(capsys.readouterr().out)
    active = module.load_active_state(root)

    assert active is not None
    assert set(active["service_revisions"]) == {
        "dashboard-backend",
        "dashboard-frontend",
        "qqcc-config-backend",
        "qqcc-config-frontend",
    }
    assert dashboard_backend.read_bytes() == before["dashboard-backend"]
    assert dashboard_frontend.read_bytes() == before["dashboard-frontend"]
    assert first["environment_revision"] == second["environment_revision"]
    assert active["previous_revision"] is None
    assert second["drift"] is False
    activation_history = root / "states" / "activations"
    history_files = sorted(activation_history.glob("*.json"))
    assert len(history_files) == 2
    assert activation_history.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in history_files)


def test_scoped_inspect_reports_change_to_an_active_service(tmp_path, capsys):
    module = _load_module()
    env_file = tmp_path / "prod.env"
    values = _environment("prod")
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"
    common = [
        "--environment",
        "prod",
        "--env-file",
        str(env_file),
        "--contract",
        str(CONTRACT_PATH),
        "--root",
        str(root),
    ]

    assert (
        module.main(
            ["activate", *common, "--service", "dashboard-backend"]
        )
        == 0
    )
    capsys.readouterr()
    values["DASHBOARD_SECRET_KEY"] = "rotated-dashboard-secret"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)

    assert (
        module.main(
            ["inspect", *common, "--service", "qqcc-config-backend"]
        )
        == 0
    )
    inspected = json.loads(capsys.readouterr().out)

    assert "dashboard-backend" in inspected["affected_services"]
    assert "qqcc-config-backend" in inspected["affected_services"]

    assert (
        module.main(
            ["activate", *common, "--service", "qqcc-config-backend"]
        )
        == 2
    )
    assert "would change active service projections" in capsys.readouterr().err


def test_full_activation_rollback_restores_incrementally_merged_projection_set(
    tmp_path, capsys
):
    module = _load_module()
    env_file = tmp_path / "prod.env"
    values = _environment("prod")
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"
    common = [
        "--environment",
        "prod",
        "--env-file",
        str(env_file),
        "--contract",
        str(CONTRACT_PATH),
        "--root",
        str(root),
    ]

    assert module.main(["activate", *common, "--service", "dashboard-backend"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert module.main(["activate", *common, "--service", "qqcc-bot"]) == 0
    capsys.readouterr()
    merged = module.load_active_state(root)
    assert merged is not None
    assert set(merged["service_revisions"]) == {"dashboard-backend", "qqcc-bot"}

    values["API_TOKEN"] = "rotated-prod-api-token"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)
    assert module.main(["activate", *common]) == 0
    full = json.loads(capsys.readouterr().out)
    assert full["environment_revision"] != first["environment_revision"]

    assert (
        module.main(
            [
                "rollback",
                *common,
                "--expected-revision",
                full["environment_revision"],
            ]
        )
        == 0
    )
    capsys.readouterr()
    restored = module.load_active_state(root)
    assert restored is not None
    assert set(restored["service_revisions"]) == {
        "dashboard-backend",
        "qqcc-bot",
    }
