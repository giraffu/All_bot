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
        "CLOUD_TEST_WORKER_04_NODE_ID": "gpu-226",
        "CLOUD_TEST_WORKER_08_TASK_TYPE_WORKFLOW_OVERRIDES": '{"scail2":"x.json"}',
        "CLOUD_TEST_WORKER_08_FACE_SWAP_V10_ENABLED": "true",
        "SECRET_VALUE": "do-not-log-this",
    }

    values = module.migrate_values(legacy)

    assert values["ALLBOT_ENV"] == "test"
    assert values["ALLBOT_WORKER_SERVICES"] == (
        "worker-01,worker-02,worker-03,worker-04,worker-06,worker-07,worker-08"
    )
    assert values["ALLBOT_WORKER_04_NODE_ID"] == "gpu-226"
    assert values["ALLBOT_WORKER_08_NODE_ID"] == "gpu-002"
    assert values["ALLBOT_WORKER_08_TASK_TYPE_WORKFLOW_OVERRIDES"] == (
        '{"scail2":"x.json"}'
    )
    assert values["ALLBOT_WORKER_08_FACE_SWAP_V10_ENABLED"] == "true"
    assert values["SECRET_VALUE"] == "do-not-log-this"


def test_migration_cli_never_prints_values(tmp_path, capsys):
    module = _load_module()
    source = tmp_path / "legacy.env"
    target = tmp_path / "test.env"
    source.write_text(
        "CLOUD_TEST_CONTROL_HOST=test-control\n"
        "SECRET_VALUE=do-not-log-this\n"
        "invalid-secret-line\n",
        encoding="utf-8",
    )

    assert module.main(["--source", str(source), "--output", str(target)]) == 0
    dry_run_output = capsys.readouterr().out
    assert "do-not-log-this" not in dry_run_output
    assert not target.exists()

    assert module.main(
        ["--source", str(source), "--output", str(target), "--execute"]
    ) == 0
    execute_output = capsys.readouterr().out
    assert "do-not-log-this" not in execute_output
    assert target.stat().st_mode & 0o777 == 0o600
    assert "SECRET_VALUE=do-not-log-this" in target.read_text(encoding="utf-8")
