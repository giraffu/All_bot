from __future__ import annotations

import importlib.util
from pathlib import Path


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
    assert values["ALLBOT_WORKER_08_NODE_ID"] == "gpu-002"
    assert values["ALLBOT_WORKER_08_TASK_TYPE_WORKFLOW_OVERRIDES"] == (
        '{"scail2":"x.json"}'
    )
    assert values["ALLBOT_WORKER_08_FACE_SWAP_V10_ENABLED"] == "true"
    assert values["CONTROL_SECRET"] == "cloud-authoritative"
    assert values["QQCC_CONFIG_ADMIN_HOST"] == "qqcc-admin-test.aivison.it.com"
    assert values["PRIVATE_QQCC_BOT_OWNER_HOST"] == (
        "private-bot-test.aivison.it.com"
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
