from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "sync_test_release_config.py"


def test_test_config_sync_cli_has_no_prod_or_maintenance_controls():
    help_result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "--source-sha" in help_result.stdout
    assert "--execute" in help_result.stdout
    assert "--env" not in help_result.stdout
    assert "prod" not in help_result.stdout.lower()
    assert "maintenance" not in help_result.stdout.lower()


def test_test_config_sync_commands_are_fixed_to_test():
    source = SCRIPT.read_text(encoding="utf-8")

    assert '["python", release, "config-plan", "--env", "test"]' in source
    assert '"config-apply",' in source
    assert '"test",' in source
    assert '"production_changed": False' in source
    assert "--confirm-prod" not in source
