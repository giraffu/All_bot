from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "sync_test_release_config.py"
VALIDATE_ENV_SCRIPT = ROOT / "scripts" / "validate_deploy_env.py"


def test_retired_test_config_sync_fails_closed_with_current_entrypoint():
    help_result = subprocess.run(
        [sys.executable, str(SCRIPT), "--source-sha", "0" * 40],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert help_result.returncode == 2
    assert "retired" in help_result.stderr.lower()
    assert "runtime_env_contract.py" in help_result.stderr
    assert "config-plan" not in SCRIPT.read_text(encoding="utf-8")
    assert "config-apply" not in SCRIPT.read_text(encoding="utf-8")


def test_retired_global_env_validator_fails_closed():
    result = subprocess.run(
        [sys.executable, str(VALIDATE_ENV_SCRIPT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "validate-env is retired" in result.stderr
    assert "release.py --help" in result.stderr
