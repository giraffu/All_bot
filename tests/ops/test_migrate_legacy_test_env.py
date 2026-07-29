from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "migrate_legacy_test_env.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("migrate_legacy_test_env", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_maps_active_slots_and_preserves_runtime_overrides():
    module = _load_module()
    legacy = {
        "CLOUD_TEST_CONTROL_HOST": "test-control",
        "CONTROL_SECRET": "cloud-authoritative",
    }
    worker_legacy = {
        "CLOUD_TEST_WORKER_01_TASK_TYPES": (
            "face_swap,i2i_pro,i2i_draw,t2i-pornmaster-turbo"
        ),
        "CLOUD_TEST_WORKER_04_NODE_ID": "gpu-226",
        "CLOUD_TEST_WORKER_08_TASK_TYPE_WORKFLOW_OVERRIDES": '{"scail2":"x.json"}',
        "CLOUD_TEST_WORKER_08_FACE_SWAP_V10_ENABLED": "true",
        "CONTROL_SECRET": "stale-local-value",
    }

    values = module.migrate_values(legacy, worker_legacy=worker_legacy)

    assert values["ALLBOT_ENV"] == "test"
    assert values["ALLBOT_WORKER_SERVICES"] == (
        "worker-01,worker-02,worker-03,worker-04,worker-06,worker-07,worker-08"
    )
    assert values["ALLBOT_WORKER_04_NODE_ID"] == "gpu-226"
    assert values["ALLBOT_WORKER_01_TASK_TYPES"] == (
        "face_swap_v2,i2i_pro,i2i_draw,t2i-pornmaster-turbo"
    )
    assert values["ALLBOT_WORKER_01_NODE_ID"] == "gpu-252"
    assert values["ALLBOT_WORKER_01_GPU_INDEX"] == "1"
    assert values["ALLBOT_WORKER_01_COMFY_API_URL"] == (
        "http://192.168.1.252:8191"
    )
    assert values["ALLBOT_WORKER_01_COMFY_WS_URL"] == (
        "ws://192.168.1.252:8191/ws"
    )
    assert values["ALLBOT_WORKER_03_RUNTIME_PROFILE"] == "ltx_unified"
    assert values["ALLBOT_WORKER_03_TASK_TYPES"] == (
        "ltx_video,ltx_video_flf2v,ltx_video_v2v_audio,ltx_t2v,ltx_t2v_ic"
    )
    assert values["ALLBOT_WORKER_06_NODE_ID"] == "gpu-226"
    assert values["ALLBOT_WORKER_06_RUNTIME_PROFILE"] == "all"
    assert values["ALLBOT_WORKER_06_COMFY_API_URL"] == (
        "http://192.168.1.226:8190"
    )
    assert values["ALLBOT_WORKER_08_NODE_ID"] == "gpu-002"
    assert values["ALLBOT_WORKER_08_TASK_TYPE_WORKFLOW_OVERRIDES"] == (
        '{"scail2":"x.json"}'
    )
    assert "ALLBOT_WORKER_08_FACE_SWAP_V10_ENABLED" not in values
    assert values["CONTROL_SECRET"] == "cloud-authoritative"
    assert values["QQCC_CONFIG_ADMIN_HOST"] == "qqcc-admin-test.aivison.it.com"
    assert values["PRIVATE_QQCC_BOT_OWNER_HOST"] == (
        "private-bot-test.aivison.it.com"
    )


def test_migration_normalizes_known_stale_worker_01_gpu0_assignment():
    module = _load_module()
    legacy = {"CLOUD_TEST_CONTROL_HOST": "test-control"}
    worker_legacy = {
        "CLOUD_TEST_WORKER_01_NODE_ID": "gpu-252",
        "CLOUD_TEST_WORKER_01_GPU_INDEX": "0",
        "CLOUD_TEST_WORKER_01_COMFY_API_URL": "http://192.168.1.252:8192",
        "CLOUD_TEST_WORKER_01_COMFY_WS_URL": "ws://192.168.1.252:8192/ws",
    }

    values = module.migrate_values(legacy, worker_legacy=worker_legacy)

    assert values["ALLBOT_WORKER_01_NODE_ID"] == "gpu-252"
    assert values["ALLBOT_WORKER_01_GPU_INDEX"] == "1"
    assert values["ALLBOT_WORKER_01_COMFY_API_URL"] == (
        "http://192.168.1.252:8191"
    )
    assert values["ALLBOT_WORKER_01_COMFY_WS_URL"] == (
        "ws://192.168.1.252:8191/ws"
    )


def test_migration_preserves_other_explicit_worker_01_assignment():
    module = _load_module()
    legacy = {"CLOUD_TEST_CONTROL_HOST": "test-control"}
    worker_legacy = {
        "CLOUD_TEST_WORKER_01_NODE_ID": "gpu-002",
        "CLOUD_TEST_WORKER_01_GPU_INDEX": "1",
        "CLOUD_TEST_WORKER_01_COMFY_API_URL": "http://192.168.1.2:8191",
        "CLOUD_TEST_WORKER_01_COMFY_WS_URL": "ws://192.168.1.2:8191/ws",
    }

    values = module.migrate_values(legacy, worker_legacy=worker_legacy)

    assert values["ALLBOT_WORKER_01_NODE_ID"] == "gpu-002"
    assert values["ALLBOT_WORKER_01_GPU_INDEX"] == "1"
    assert values["ALLBOT_WORKER_01_COMFY_API_URL"] == (
        "http://192.168.1.2:8191"
    )
    assert values["ALLBOT_WORKER_01_COMFY_WS_URL"] == (
        "ws://192.168.1.2:8191/ws"
    )


def test_migration_cli_never_prints_values(tmp_path, capsys):
    module = _load_module()
    source = tmp_path / "legacy.env"
    target = tmp_path / "test.env"
    source.write_text(
        "CLOUD_TEST_CONTROL_HOST=test-control\n"
        "SECRET_VALUE=cloud-do-not-log-this\n"
        "invalid-secret-line\n",
        encoding="utf-8",
    )
    worker_source = tmp_path / "legacy-worker.env"
    worker_source.write_text(
        "CLOUD_TEST_WORKER_04_NODE_ID=gpu-226\n"
        "SECRET_VALUE=worker-do-not-log-this\n",
        encoding="utf-8",
    )

    base_args = [
        "--source",
        str(source),
        "--worker-source",
        str(worker_source),
        "--output",
        str(target),
    ]
    assert module.main(base_args) == 0
    dry_run_output = capsys.readouterr().out
    assert "cloud-do-not-log-this" not in dry_run_output
    assert "worker-do-not-log-this" not in dry_run_output
    assert not target.exists()

    assert module.main([*base_args, "--execute"]) == 0
    execute_output = capsys.readouterr().out
    assert "cloud-do-not-log-this" not in execute_output
    assert "worker-do-not-log-this" not in execute_output
    assert target.stat().st_mode & 0o777 == 0o600
    assert "SECRET_VALUE=cloud-do-not-log-this" in target.read_text(encoding="utf-8")
    assert "ALLBOT_WORKER_04_NODE_ID=gpu-226" in target.read_text(encoding="utf-8")


def test_control_plane_only_migration_canonicalizes_legacy_test_keys_without_worker_changes():
    module = _load_module()
    legacy = {
        "CLOUD_TEST_CONTROL_HOST": "test-control",
        "BOT_TOKEN_TEST": "test-bot-token",
        "QQCC_BOT_TOKEN_TEST": "test-qqcc-token",
        "API_TOKEN_TEST": "legacy-api-token",
        "API_TOKEN": "canonical-api-token",
        "TELEGRAM_API_BASE_URL": "http://bot-api.internal:8081",
        "ALLBOT_WORKER_SERVICES": "worker-99",
        "ALLBOT_WORKER_99_TASK_TYPES": "existing-profile",
    }

    values = module.migrate_values(legacy, normalize_workers=False)

    assert values["BOT_TOKEN"] == "test-bot-token"
    assert values["QQCC_BOT_TOKEN"] == "test-qqcc-token"
    assert values["API_TOKEN"] == "canonical-api-token"
    assert values["TELEGRAM_FILE_BASE_URL"] == "http://bot-api.internal:8082"
    assert values["ALLBOT_WORKER_SERVICES"] == "worker-99"
    assert values["ALLBOT_WORKER_99_TASK_TYPES"] == "existing-profile"
    assert "ALLBOT_WORKER_01_TASK_TYPES" not in values


def test_migration_refuses_to_guess_unknown_telegram_file_endpoint():
    module = _load_module()

    with pytest.raises(module.MigrationError, match="TELEGRAM_FILE_BASE_URL"):
        module.migrate_values(
            {
                "CLOUD_TEST_CONTROL_HOST": "test-control",
                "TELEGRAM_API_BASE_URL": "https://custom-telegram.invalid/api",
            },
            normalize_workers=False,
        )


def test_control_plane_only_cli_writes_restricted_candidate_without_worker_defaults(
    tmp_path,
):
    module = _load_module()
    source = tmp_path / "legacy.env"
    target = tmp_path / "test.env.next"
    source.write_text(
        "CLOUD_TEST_CONTROL_HOST=test-control\n"
        "BOT_TOKEN_TEST=test-bot-token\n"
        "TELEGRAM_API_BASE_URL=http://bot-api.internal:8081\n"
        "ALLBOT_WORKER_SERVICES=worker-99\n",
        encoding="utf-8",
    )

    assert (
        module.main(
            [
                "--source",
                str(source),
                "--output",
                str(target),
                "--control-plane-only",
                "--execute",
            ]
        )
        == 0
    )

    values, ignored = module.parse_legacy(
        target.read_text(encoding="utf-8").splitlines()
    )
    assert ignored == []
    assert values["BOT_TOKEN"] == "test-bot-token"
    assert values["TELEGRAM_FILE_BASE_URL"] == "http://bot-api.internal:8082"
    assert values["ALLBOT_WORKER_SERVICES"] == "worker-99"
    assert "ALLBOT_WORKER_01_TASK_TYPES" not in values
    assert target.stat().st_mode & 0o777 == 0o600
